import os
from datetime import datetime
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

# Configure logging
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
            <p>Use the <code>X-API-Key</code> header or <code>Authorization: Bearer</code> to authenticate. All endpoints return JSON.</p>

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

            <p class='meta'>Need the latest received payload? Make an authenticated request to <code>GET /last-response</code>.</p>
        </div>
    </body>
</html>
"""

DOCS_ENDPOINTS = [
        {
                "method": "POST",
                "path": "/trigger",
                "description": "Fetches the latest messages from the channel/group and (optionally) forwards them to a webhook.",
                "details": "JSON body with 'entity', 'limit' (default 2), and optional 'webhook_url'.",
                "sample": """curl -X POST https://<host>/trigger \
    -H 'Content-Type: application/json' \
    -H 'X-API-Key: <api_key>' \
    -d '{\"entity\": \"@canal\", \"limit\": 2}'""",
        },
        {
                "method": "GET",
                "path": "/message",
                "description": "Returns a single message by ID, keeping the same format as /trigger.",
                "details": "Query params: entity, message_id, optional webhook_url.",
                "sample": """curl 'https://<host>/message?entity=@canal&message_id=123' \
    -H 'X-API-Key: <api_key>'""",
        },
        {
                "method": "GET",
                "path": "/media/<token>",
                "description": "Serves downloaded files via signed links (signed_url field in the payload).",
                "details": "Tokens expire after MEDIA_URL_TTL_SECONDS and do not require extra headers.",
                "sample": "curl -L 'https://<host>/media/<token>'",
        },
        {
                "method": "GET",
                "path": "/last-response",
                "description": "Returns the last payload persisted on disk (requires API key).",
                "details": "Useful for debugging what was sent to n8n or another webhook.",
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
    entity_override = request.args.get('entity')
    message_id_override = request.args.get('message_id')
    message_id_value = None
    if message_id_override:
        try:
            message_id_value = int(message_id_override)
        except ValueError:
            message_id_value = None
    try:
        media_path = telegram_service.get_media_path_from_token(
            token,
            entity_override=entity_override,
            message_id_override=message_id_value,
        )
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


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check detallado
    ---
    responses:
      200:
        description: Service is healthy
      503:
        description: Service has issues
    """
    issues = []

    # Verificar archivos esenciales
    session_path = settings.session_path
    if not os.path.exists(session_path):
        issues.append({
            "component": "telegram_session",
            "status": "missing",
            "path": session_path,
            "fix": "Mount volume with session file or set TELEGRAM_SESSION_B64",
        })

    # Verificar directorios
    if not os.path.exists(settings.media_dir):
        issues.append({
            "component": "media_directory",
            "status": "missing",
            "path": settings.media_dir,
            "fix": "Mount persistent volume at /app/data",
        })

    # Verificar conexión Telegram
    try:
        telegram_connected = telegram_service._client and telegram_service._client.is_connected()
    except Exception:  # noqa: BLE001
        telegram_connected = False
        issues.append({
            "component": "telegram_client",
            "status": "disconnected",
            "fix": "Check logs and verify session is authorized",
        })

    if issues:
        return jsonify({
            "status": "unhealthy",
            "issues": issues,
            "timestamp": datetime.utcnow().isoformat(),
        }), 503

    return jsonify({
        "status": "healthy",
        "telegram_connected": telegram_connected,
        "timestamp": datetime.utcnow().isoformat(),
    }), 200


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


@app.errorhandler(500)
def internal_error(error):
    """Error 500 personalizado"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Service Configuration Error</title>
        <style>
            body {{ font-family: monospace; padding: 40px; background: #1a1a1a; color: #ff6b6b; }}
            .error-box {{ background: #2d2d2d; padding: 20px; border-left: 4px solid #ff6b6b; }}
            code {{ background: #000; padding: 2px 6px; }}
        </style>
    </head>
    <body>
        <div class="error-box">
            <h1>⚠ Service Configuration Error</h1>
            <p>The Telegram API service is not properly configured.</p>
            <h3>Common issues:</h3>
            <ul>
                <li>Missing persistent volume mount at <code>/app/data</code></li>
                <li>Session file not found: <code>{settings.session_path}</code></li>
                <li>Incorrect file permissions (needs UID 1000)</li>
            </ul>
            <h3>Quick fix:</h3>
            <pre>docker service update \\
  --mount-add type=volume,source=utils-telegram-data,target=/app/data \\
  utils-utilspythontelegramanalysis-y4g0yx</pre>
            <p><a href="/health">Check detailed health status</a></p>
        </div>
    </body>
    </html>
    """, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)