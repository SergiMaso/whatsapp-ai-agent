import os
from dotenv import load_dotenv

load_dotenv()

# AI Configuration - Choose one
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_SESSION_TOKEN = os.getenv('AWS_SESSION_TOKEN')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
AI_PROVIDER = os.getenv('AI_PROVIDER', 'openai')  # 'openai' or 'bedrock'

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER')

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL')

# Server Configuration
PORT = int(os.getenv('PORT', 8080))
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'