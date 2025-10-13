"""
Main application entry point that runs:
1. Flask (WhatsApp with Twilio) on port 8080
2. Telegram Bot in parallel

Both use the same AI code and database
"""

import os
import threading
from src.platforms.whatsapp.app import app
from src.platforms.telegram.bot import main as telegram_main
from src.config.settings import PORT

def run_flask():
    """Run Flask server (WhatsApp)"""
    print(f"🌐 Flask (WhatsApp) listening on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)

def run_telegram():
    """Run Telegram bot"""
    print("📱 Starting Telegram bot...")
    telegram_main()

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 STARTING BOT SYSTEM")
    print("=" * 60)
    print("✅ WhatsApp (Twilio) - ACTIVE")
    print("✅ Telegram Bot - ACTIVE")
    print("=" * 60)
    
    # Start Flask in a thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Start Telegram in the main thread
    run_telegram()