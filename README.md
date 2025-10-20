# telegram-analysis
Tools to analyze Telegram groups and channels

Please note that groups are as same as channels in Telegram. so you can use this code to get users and messages from any public group or channel. Also if you are a member of a private group or channel you can still get users list and messages from that group.

A short video tutorial on how to use this script:
https://www.youtube.com/watch?v=aU1p-F7gDo4&ab_channel=AmirYousefi

A complete tutorial about using this script is available on Medium

https://medium.com/@AmirYousefi/how-to-get-data-from-telegram-82af55268a4b

## Deployment with Dockploy

This project is configured for easy deployment using Dockploy.

### Setup
1. Copy `.env.example` to `.env` and fill in your Telegram API credentials.
2. Create the Telegram session locally:
   - Run the app locally: `python -m app.main`
   - Enter your phone and code to authenticate.
   - This creates `data/session.session`. Copy this file to the deployment.
3. In Dockploy:
   - Select source: Connect your GitHub/GitLab/Bitbucket repo.
   - Build Type: Dockerfile, Path: `.` (root)
   - Environment: Upload or paste your `.env` file.
   - Mount volume: `/app/data` for session persistence.
   - Domain: Set your subdomain (e.g., api-telegram.antonberzins.com) if needed.
4. Deploy!

### API Usage
Send a POST request to `/trigger` with JSON and Authorization header:
```bash
curl -X POST https://api-telegram.antonberzins.com/trigger \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"entity": "@channel_name", "webhook_url": "https://your-webhook.com", "limit": 5}'
```
Parameters:
- `entity` (required): Telegram channel/group username or ID.
- `webhook_url` (optional): URL to send messages. Defaults to env var.
- `limit` (optional): Number of last messages to fetch/send (default: 2).

It will fetch the messages and send them to the webhook.

### View Last Response
GET `https://api-telegram.antonberzins.com/` to view the last message sent (for debugging).
