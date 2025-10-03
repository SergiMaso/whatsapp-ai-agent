"""
Servidor principal que corre:
1. Flask (WhatsApp con Twilio) en puerto 8080 - TEMPORALMENT DESCONNECTAT
2. Telegram Bot en paralelo

Ambos usan el mismo código de IA y base de datos
"""

import os
import threading
from app import app
from telegram_bot import main as telegram_main

def run_flask():
    """Correr servidor Flask (WhatsApp) - TEMPORALMENT DESCONNECTAT"""
    port = int(os.getenv('PORT', 8080))
    print(f"⚠️  WhatsApp DESCONNECTAT temporalment per proves")
    print(f"🌐 Flask escoltant al port {port} però no processant missatges")
    app.run(host='0.0.0.0', port=port, debug=False)

def run_telegram():
    """Correr bot de Telegram"""
    print("📱 Iniciant bot de Telegram...")
    telegram_main()

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 INICIANDO SISTEMA DE BOTS")
    print("=" * 60)
    print("⚠️  WhatsApp (Twilio) - DESCONNECTAT (proves)")
    print("✅ Telegram Bot - ACTIU")
    print("=" * 60)
    
    # Iniciar Flask en un thread (por si acaso Railway lo necesita)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Iniciar Telegram en el thread principal
    try:
        run_telegram()
    except KeyboardInterrupt:
        print("\n\n👋 Cerrando bots...")
