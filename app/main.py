from flask import Flask, request, jsonify
import os
import logging
import json
from dotenv import load_dotenv
from .ChannelMessages import get_last_messages

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

@app.before_request
def check_api_key():
    if request.method == 'POST' and request.path == '/trigger':
        # Check X-API-Key header or Authorization Bearer token
        auth_header = request.headers.get('X-API-Key')
        bearer_token = None
        auth_bearer = request.headers.get('Authorization')
        if auth_bearer and auth_bearer.startswith('Bearer '):
            bearer_token = auth_bearer[7:]  # Remove 'Bearer ' prefix
        
        if not ((auth_header and auth_header == api_key) or (bearer_token and bearer_token == api_key)):
            logger.warning("Unauthorized access attempt")
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