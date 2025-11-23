import os
from flask import Flask, request, jsonify, send_file, render_template_string
import logging
import json
from dotenv import load_dotenv
from itsdangerous import BadSignature, SignatureExpired

load_dotenv()

from .config import settings  # noqa: E402
from .services.webhook import WebhookService  # noqa: E402
from .services.telegram import TelegramService  # noqa: E402
from .version import APP_VERSION  # noqa: E402

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logger.info("Starting Flask app...")

app = Flask(__name__)

webhook_service = WebhookService(settings.webhook_headers_raw, settings.data_dir)
telegram_service = TelegramService(settings, webhook_service)

DOCS_TEMPLATE = """
<!doctype html>
<html lang='en'>
    <head>
        <meta charset='utf-8' />
        <meta name='viewport' content='width=device-width, initial-scale=1' />
        <title>Telegram Analysis API · v{{ version }}</title>
        <style>
            body { font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color:#0f172a; background:#f9fafb; margin:0; padding:2rem; }
            h1 { margin-top:0; }
            .card { background:#fff; border-radius:16px; padding:2.5rem; box-shadow:0 25px 65px rgba(15,23,42,.12); max-width:960px; margin:auto; }
            code, pre { font-family:'JetBrains Mono','SFMono-Regular',Consolas,monospace; font-size:.95rem; }
            pre { background:#0f172a; color:#f8fafc; padding:1rem; border-radius:10px; overflow:auto; }
            .endpoint { margin-bottom:1.75rem; }
            .badge { display:inline-block; padding:0.2rem 0.65rem; border-radius:999px; font-size:.75rem; font-weight:600; color:#fff; margin-right:.5rem; }
            .badge.GET { background:#0ea5e9; }
            .badge.POST { background:#22c55e; }
            .meta { color:#64748b; font-size:.95rem; }
            a { color:#2563eb; }
        </style>
    </head>
    <body>
        <div class='card'>
            <h1>Telegram Analysis API</h1>
            <p class='meta'>Version {{ version }} · Single Telethon client + Flask proxy</p>
            <p>Usa la cabecera <code>X-API-Key</code> o <code>Authorization: Bearer</code> para autenticarte. Todos los endpoints devuelven JSON.</p>

            {% for ep in endpoints %}
            <div class='endpoint'>
                <div>
                    <span class='badge {{ ep.method }}'>{{ ep.method }}</span>
                    <strong>{{ ep.path }}</strong>
                </div>
                <p>{{ ep.description }}</p>
                {% if ep.details %}<p class='meta'>{{ ep.details }}</p>{% endif %}
                {% if ep.sample %}<pre>{{ ep.sample }}</pre>{% endif %}
            </div>
            {% endfor %}

            <p class='meta'>¿Necesitas el último payload recibido? Haz una petición autenticada a <code>GET /last-response</code>.</p>
        </div>
    </body>
</html>
"""

DOCS_ENDPOINTS = [
        {
                "method": "POST",
                "path": "/trigger",
                "description": "Recupera los últimos mensajes del canal/grupo y (opcional) los reenvía a un webhook.",
                "details": "Body JSON con 'entity', 'limit' (2 por defecto) y 'webhook_url' opcional.",
                "sample": """curl -X POST https://<host>/trigger \
    -H 'Content-Type: application/json' \
    -H 'X-API-Key: <api_key>' \
    -d '{\"entity\": \"@canal\", \"limit\": 2}'""",
        },
        {
                "method": "GET",
                "path": "/message",
                "description": "Devuelve un único mensaje por ID manteniendo el formato de /trigger.",
                "details": "Query params: entity, message_id, webhook_url opcional.",
                "sample": """curl 'https://<host>/message?entity=@canal&message_id=123' \
    -H 'X-API-Key: <api_key>'""",
        },
        {
                "method": "GET",
                "path": "/media/<token>",
                "description": "Sirve archivos descargados mediante enlaces firmados (campo signed_url del payload).",
                "details": "Los tokens expiran tras MEDIA_URL_TTL_SECONDS y no requieren cabeceras extra.",
                "sample": "curl -L 'https://<host>/media/<token>'",
        },
        {
                "method": "GET",
                "path": "/last-response",
                "description": "Entrega el último payload persistido en disco (requiere API key).",
                "details": "Útil para depurar qué se envió a n8n u otro webhook.",
                "sample": "curl https://<host>/last-response -H 'X-API-Key: <api_key>'",
        },
]

@app.before_request
def check_api_key():
    protected = {
        ('/trigger', 'POST'),
        ('/message', 'GET'),
        ('/last-response', 'GET'),
    }
    request_signature = (request.path.rstrip('/') or '/', request.method)
    if request_signature not in protected:
        return

    auth_header = request.headers.get('X-API-Key')
    bearer_token = None
    auth_bearer = request.headers.get('Authorization')
    if auth_bearer and auth_bearer.startswith('Bearer '):
        bearer_token = auth_bearer[7:]

    if not ((auth_header and auth_header == settings.api_key) or (bearer_token and bearer_token == settings.api_key)):
        logger.warning("Unauthorized access attempt at %s %s", request.method, request.path)
        return jsonify({'error': 'Unauthorized'}), 401

@app.route('/trigger', methods=['POST'])
def trigger():
    data = request.get_json()
    if not data or 'entity' not in data:
        return jsonify({'error': 'entity is required'}), 400

    entity = data['entity']
    webhook_url = data.get('webhook_url', settings.default_webhook)
    limit = data.get('limit', 2)

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return jsonify({'error': 'limit must be an integer'}), 400

    if limit < 1:
        return jsonify({'error': 'limit must be greater than zero'}), 400

    try:
        logger.info(f"Processing request for entity: {entity}, limit: {limit}")
        messages = telegram_service.get_last_messages(entity, limit, webhook_url)
        logger.info(f"Retrieved {len(messages)} messages")
        return jsonify(messages), 200
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/message', methods=['GET'])
def get_message():
    entity = request.args.get('entity')
    message_id = request.args.get('message_id')
    webhook_url = request.args.get('webhook_url', settings.default_webhook)

    if not entity:
        return jsonify({'error': 'entity is required'}), 400

    if not message_id:
        return jsonify({'error': 'message_id is required'}), 400

    try:
        int_message_id = int(message_id)
    except ValueError:
        return jsonify({'error': 'message_id must be an integer'}), 400

    try:
        logger.info("Fetching message %s for entity %s", int_message_id, entity)
        message = telegram_service.get_message_by_id(entity, int_message_id, webhook_url)
        if not message:
            return jsonify({'error': 'Message not found'}), 404
        return jsonify([message]), 200
    except Exception as e:  # noqa: BLE001
        logger.error("Error fetching message %s for %s: %s", int_message_id, entity, e)
        return jsonify({'error': str(e)}), 500


@app.route('/media/<token>', methods=['GET'])
def serve_media(token: str):
    try:
        media_path = telegram_service.get_media_path_from_token(token)
    except SignatureExpired:
        return jsonify({'error': 'Link expired'}), 410
    except BadSignature:
        return jsonify({'error': 'Invalid media link'}), 404

    if not os.path.exists(media_path):
        return jsonify({'error': 'File not found'}), 404

    return send_file(media_path, as_attachment=True)

@app.route('/', methods=['GET'])
def docs_home():
    return render_template_string(
        DOCS_TEMPLATE,
        version=APP_VERSION,
        endpoints=DOCS_ENDPOINTS,
    )


@app.route('/last-response', methods=['GET'])
def get_last_response():
    try:
        with open(os.path.join(settings.data_dir, 'last_response.json'), 'r') as f:
            data = json.load(f)
        return jsonify(data), 200
    except FileNotFoundError:
        return jsonify({'message': 'No response yet'}), 200
    except Exception as e:
        logger.error("Error reading last response: %s", e)
        return jsonify({'error': 'Internal error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)