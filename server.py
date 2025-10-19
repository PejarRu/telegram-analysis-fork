from flask import Flask, request, jsonify
import os
from ChannelMessages import get_last_messages

app = Flask(__name__)

# Reading environment variables
api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')
phone = os.getenv('TELEGRAM_PHONE')
username = os.getenv('TELEGRAM_USERNAME')
webhook_endpoint = os.getenv('WEBHOOK_ENDPOINT', 'https://n8n.antonberzins.com/webhook/telegram-messages')

@app.route('/trigger', methods=['POST'])
def trigger():
    data = request.get_json()
    if not data or 'entity' not in data:
        return jsonify({'error': 'entity is required'}), 400

    entity = data['entity']
    webhook_url = data.get('webhook_url', webhook_endpoint)

    try:
        get_last_messages(entity, webhook_url, limit=2)
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)