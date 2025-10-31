from flask import Flask, request, jsonify
import logging
import json
from dotenv import load_dotenv

load_dotenv()

from .config import settings  # noqa: E402
from .services.webhook import WebhookService  # noqa: E402
from .services.telegram import TelegramService  # noqa: E402

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logger.info("Starting Flask app...")

app = Flask(__name__)

webhook_service = WebhookService(settings.webhook_headers_raw, settings.data_dir)
telegram_service = TelegramService(settings, webhook_service)

@app.before_request
def check_api_key():
    protected = {
        ('/trigger', 'POST'),
        ('/message', 'GET'),
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

@app.route('/', methods=['GET'])
def get_last_response():
    # Check X-API-Key header or Authorization Bearer token
    auth_header = request.headers.get('X-API-Key')
    bearer_token = None
    auth_bearer = request.headers.get('Authorization')
    if auth_bearer and auth_bearer.startswith('Bearer '):
        bearer_token = auth_bearer[7:]  # Remove 'Bearer ' prefix
    
    if not ((auth_header and auth_header == settings.api_key) or (bearer_token and bearer_token == settings.api_key)):
        return jsonify({'status': 'ok'}), 200

    try:
        with open(f"{settings.data_dir}/last_response.json", 'r') as f:
            data = json.load(f)
        return jsonify(data), 200
    except FileNotFoundError:
        return jsonify({'message': 'No response yet'}), 200
    except Exception as e:
        logger.error(f"Error reading last response: {str(e)}")
        return jsonify({'error': 'Internal error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)