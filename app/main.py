from flask import Flask, request, jsonify
import os
import logging
import json
from dotenv import load_dotenv
from .ChannelMessages import (
    get_last_messages,
    start_listener,
    get_message_by_id,
)

# Load environment variables
load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logger.info("Starting Flask app...")

app = Flask(__name__)

# Reading environment variables
api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')
phone = os.getenv('TELEGRAM_PHONE')
username = os.getenv('TELEGRAM_USERNAME')
webhook_endpoint = os.getenv('N8N_WEBHOOK_URL')
api_key = os.getenv('API_KEY')  # Nueva variable para autenticación
listener_entity = os.getenv('TELEGRAM_LISTENER_ENTITY')
listener_webhook = os.getenv('LISTENER_WEBHOOK_URL') or webhook_endpoint

if listener_entity:
    try:
        start_listener(listener_entity, listener_webhook)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to start Telegram listener: %s", exc)
else:
    logger.info("Telegram listener inactive. Set TELEGRAM_LISTENER_ENTITY in the environment to enable it.")

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

    if not ((auth_header and auth_header == api_key) or (bearer_token and bearer_token == api_key)):
        logger.warning("Unauthorized access attempt at %s %s", request.method, request.path)
        return jsonify({'error': 'Unauthorized'}), 401

@app.route('/trigger', methods=['POST'])
def trigger():
    data = request.get_json()
    if not data or 'entity' not in data:
        return jsonify({'error': 'entity is required'}), 400

    entity = data['entity']
    webhook_url = data.get('webhook_url', webhook_endpoint)
    limit = data.get('limit', 2)  # Default 2, configurable

    try:
        logger.info(f"Processing request for entity: {entity}, limit: {limit}")
        messages = get_last_messages(entity, webhook_url, limit=limit)
        logger.info(f"Retrieved {len(messages)} messages")
        return jsonify(messages), 200
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/message', methods=['GET'])
def get_message():
    entity = request.args.get('entity')
    message_id = request.args.get('message_id')
    webhook_url = request.args.get('webhook_url', webhook_endpoint)

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
        message = get_message_by_id(entity, int_message_id, webhook_url)
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
    
    if not ((auth_header and auth_header == api_key) or (bearer_token and bearer_token == api_key)):
        return jsonify({'status': 'ok'}), 200

    try:
        with open('/app/data/last_response.json', 'r') as f:
            data = json.load(f)
        return jsonify(data), 200
    except FileNotFoundError:
        return jsonify({'message': 'No response yet'}), 200
    except Exception as e:
        logger.error(f"Error reading last response: {str(e)}")
        return jsonify({'error': 'Internal error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)