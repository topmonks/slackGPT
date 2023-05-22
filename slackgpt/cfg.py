import logging
import os

# Secrets
SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
SLACK_BOT_SIGN_SECRET = os.getenv('SLACK_BOT_SIGN_SECRET')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# App Settings
LOG_FILE = os.getenv('LOG_FILE')
LOG_LEVEL = os.getenv('LOG_LEVEL') or logging.INFO
CHAT_GPT_ERROR_RETRIES = os.getenv('CHAT_GPT_ERROR_RETRIES') or 3
SLACK_ERROR_RETRIES = os.getenv('SLACK_ERROR_RETRIES') or 3
PORT = os.getenv('PORT') or 3000

PORT = int(PORT)
CHAT_GPT_ERROR_RETRIES = int(CHAT_GPT_ERROR_RETRIES)
SLACK_ERROR_RETRIES = int(SLACK_ERROR_RETRIES)

SLACK_CHANNEL_TYPE_IM = 'im'
MAX_TOKEN_COUNT = {
    'gpt-3.5-turbo': 4096,
    'gpt-4': 8192,
    'gpt-4-ext': 32768
}

