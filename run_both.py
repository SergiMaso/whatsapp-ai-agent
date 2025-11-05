"""
Servidor principal que corre:
1. Flask (WhatsApp con Twilio) en puerto 8080
2. Telegram Bot en paralelo
3. Scheduler per tasques automàtiques (manteniment setmanal)

Ambos usan el mismo código de IA y base de datos
"""

import os
import threading
import signal
import sys
from app import app
from telegram_bot import main as telegram_main
from utils.weekly_defaults import WeeklyDefaultsManager
from utils.appointments import ConversationManager
from utils.scheduler import start_scheduler, stop_scheduler

# Variable global pel scheduler
scheduler = None

def run_flask():
    """Correr servidor Flask (WhatsApp)"""
    port = int(os.getenv('PORT', 8080))
    print(f"🌐 Flask (WhatsApp) escoltant al port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

def run_telegram():
    """Correr bot de Telegram"""
    print("📱 Iniciant bot de Telegram...")
    telegram_main()

def signal_handler(sig, frame):
    """Gestionar señales per shutdown graceful"""
    global scheduler
    print("\n🛑 Rebuda señal de shutdown...")
    if scheduler:
        stop_scheduler(scheduler)
    print("👋 Adéu!")
    sys.exit(0)

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 INICIANDO SISTEMA DE BOTS")
    print("=" * 60)
    print("✅ WhatsApp (Twilio) - ACTIU")
    print("✅ Telegram Bot - ACTIU")
    print("✅ Scheduler Automàtic - ACTIU")
    print("=" * 60)
    
    # Registrar signal handlers per shutdown graceful
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Inicialitzar i iniciar scheduler
    try:
        weekly_defaults_manager = WeeklyDefaultsManager()
        conversation_manager = ConversationManager()
        scheduler = start_scheduler(weekly_defaults_manager, conversation_manager)
    except Exception as e:
        print(f"⚠️  No s'ha pogut iniciar el scheduler: {e}")
        print("   El sistema seguirà funcionant sense tasques automàtiques")
    
    # Iniciar Flask en un thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Iniciar Telegram en el thread principal
    try:
        run_telegram()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
