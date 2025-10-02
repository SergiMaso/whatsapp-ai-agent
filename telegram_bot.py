"""
Bot de Telegram - Funciona en paralelo con WhatsApp
No interfiere con el código de Twilio
"""

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from utils.appointments import AppointmentManager, ConversationManager
from utils.ai_processor import process_message_with_ai
from utils.transcription import transcribe_audio
import asyncio

load_dotenv()

# Configuración
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Logging
logging.basicConfig(
    format='[%(levelname)s] %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Inicializar gestores
appointment_manager = AppointmentManager()
conversation_manager = ConversationManager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    await update.message.reply_text(
        "¡Hola! Soy el bot de reservas del restaurante.\n\n"
        "Puedes escribir o enviar mensajes de voz para:\n"
        "• Hacer una reserva\n"
        "• Ver tus reservas\n"
        "• Cancelar una reserva\n\n"
        "¿En qué puedo ayudarte?"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar mensajes de texto"""
    user_message = update.message.text
    user_id = f"telegram:{update.effective_user.id}"
    
    logger.info(f"[MSG] Mensaje de {user_id}: {user_message}")
    
    # Mostrar "escribiendo..."
    await update.message.chat.send_action(action="typing")
    
    # Procesar con IA
    try:
        response = process_message_with_ai(
            user_message, 
            user_id, 
            appointment_manager, 
            conversation_manager
        )
        
        logger.info(f"[SEND] Enviando respuesta: {response[:50]}...")
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"[ERROR] Error procesando mensaje: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(
            "Lo siento, hubo un error procesando tu mensaje. Por favor intenta de nuevo."
        )

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar mensajes de voz"""
    user_id = f"telegram:{update.effective_user.id}"
    
    logger.info(f"[AUDIO] Audio recibido de {user_id}")
    
    await update.message.reply_text("🎤 Escuchando tu mensaje...")
    
    try:
        # Descargar el archivo de audio
        voice_file = await update.message.voice.get_file()
        voice_url = voice_file.file_path
        
        logger.info(f"[AUDIO] Descargando desde: {voice_url}")
        
        # Descargar el audio
        import requests
        audio_response = requests.get(voice_url)
        
        if audio_response.status_code != 200:
            await update.message.reply_text("No pude descargar el audio. Intenta de nuevo.")
            return
        
        # Guardar temporalmente
        audio_path = 'temp_telegram_audio.ogg'
        with open(audio_path, 'wb') as f:
            f.write(audio_response.content)
        
        logger.info("[WHISPER] Transcribiendo...")
        
        # Transcribir con Whisper
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        with open(audio_path, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es"
            )
        
        transcribed_text = transcript.text
        logger.info(f"[OK] Transcripción: {transcribed_text}")
        
        # Limpiar archivo temporal
        if os.path.exists(audio_path):
            os.remove(audio_path)
        
        # Procesar el texto transcrito
        await update.message.chat.send_action(action="typing")
        
        response = process_message_with_ai(
            transcribed_text, 
            user_id, 
            appointment_manager, 
            conversation_manager
        )
        
        await update.message.reply_text(f"📝 Escuché: \"{transcribed_text}\"\n\n{response}")
        
    except Exception as e:
        logger.error(f"[ERROR] Error procesando audio: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(
            "No pude procesar el audio. ¿Puedes escribir tu mensaje?"
        )

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar archivos de audio"""
    # Telegram diferencia entre voice y audio
    await handle_voice(update, context)

def main():
    """Iniciar el bot de Telegram"""
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("ERROR: TELEGRAM_BOT_TOKEN no configurado en .env")
        return
    
    logger.info("🤖 Iniciando bot de Telegram...")
    
    # Crear aplicación
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Agregar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    
    # Iniciar bot
    logger.info("✅ Bot de Telegram iniciado correctamente")
    logger.info("📱 Busca tu bot en Telegram y envía /start")
    
    # Polling (se queda escuchando)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
