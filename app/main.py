from flask import Flask, request, jsonify
import os
import logging
import json
from .ChannelMessages import get_last_messages

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
webhook_endpoint = os.getenv('N8N_WEBHOOK_URL', 'https://n8n.antonberzins.com/webhook/telegram-messages')
api_key = os.getenv('API_KEY')  # Nueva variable para autenticación

@app.before_request
def check_api_key():
    if request.method == 'POST' and request.path == '/trigger':
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning("Unauthorized access attempt")
            return jsonify({'error': 'Unauthorized'}), 401
        token = auth_header.split(' ')[1]
        if token != api_key:
            logger.warning("Invalid API key")
            return jsonify({'error': 'Invalid API key'}), 403

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
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def get_last_response():
    try:
        with open('/app/data/last_response.json', 'r') as f:
            data = json.load(f)
        return jsonify(data), 200
    except FileNotFoundError:
        return jsonify({'message': 'No response yet'}), 404
    except Exception as e:
        logger.error(f"Error reading last response: {str(e)}")
        return jsonify({'error': 'Internal error'}), 500