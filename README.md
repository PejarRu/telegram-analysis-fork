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
2. In Dockploy:
   - Select source: Connect your GitHub/GitLab/Bitbucket repo.
   - Build Type: Dockerfile
   - Environment: Upload or paste your `.env` file.
   - Domain: Set your subdomain (e.g., telegram.yourdomain.com) if needed.
3. Deploy!

### API Usage
Send a POST request to `/trigger` with JSON:
```json
{
  "entity": "@channel_name",
  "webhook_url": "https://your-webhook.com"
}
```
It will fetch the last 2 messages and send them to the webhook.
