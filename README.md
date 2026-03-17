# VoyagersIPA Bot

Telegram bot that patches IPA files and posts to @VoyagersIPA channel.

## Deploy to Render

1. Push this repo to GitHub
2. Go to render.com → New → Background Worker
3. Connect your GitHub repo
4. Set environment variables:
   - `BOT_TOKEN` = your bot token
   - `ADMIN_ID` = your Telegram user ID
   - `CHANNEL_ID` = @VoyagersIPA

## Usage

Send any `.ipa` file to the bot → it patches → auto-posts to channel.
Or send a direct `.ipa` URL link.
