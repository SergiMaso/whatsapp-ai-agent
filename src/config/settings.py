import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

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