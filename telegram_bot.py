"""
Bot de Telegram - Funciona en paralelo con WhatsApp
Con soporte para botones inline (teclados)
"""

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
from utils.appointments import AppointmentManager, ConversationManager
from utils.ai_processor import process_message_with_ai, detect_language
from utils.conversation_state import should_show_time_buttons, set_conversation_state, get_conversation_state
from utils.telegram_keyboards import (
    get_time_slots_keyboard,
    get_lunch_times_keyboard,
    get_dinner_times_keyboard
)

load_dotenv()

# Configuración - Railway usa variables de entorno directamente
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')

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
    user_id = update.effective_user.id
    lang = detect_language("hola")  # Default
    
    if lang == 'ca':
        text = (
            "Hola! Sóc el bot de reserves del restaurant.\n\n"
            "Pots escriure o enviar missatges de veu per a:\n"
            "• Fer una reserva\n"
            "• Veure les teves reserves\n"
            "• Cancel·lar una reserva\n\n"
            "En què puc ajudar-te?"
        )
    else:
        text = (
            "¡Hola! Soy el bot de reservas del restaurante.\n\n"
            "Puedes escribir o enviar mensajes de voz para:\n"
            "• Hacer una reserva\n"
            "• Ver tus reservas\n"
            "• Cancelar una reserva\n\n"
            "¿En qué puedo ayudarte?"
        )
    
    await update.message.reply_text(text)

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
        
        # Detectar si debemos mostrar botones de hora
        language = detect_language(user_message)
        if should_show_time_buttons(user_id, user_message, response):
            logger.info("[BUTTONS] Mostrando botones de horario")
            keyboard = get_time_slots_keyboard(language)
            await update.message.reply_text(response, reply_markup=keyboard)
        else:
            await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"[ERROR] Error procesando mensaje: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(
            "Lo siento, hubo un error procesando tu mensaje. Por favor intenta de nuevo."
        )

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar clicks en botones inline"""
    query = update.callback_query
    user_id = f"telegram:{update.effective_user.id}"
    
    await query.answer()  # Acknowledge the callback
    
    callback_data = query.data
    logger.info(f"[BUTTON] Usuario {user_id} presionó: {callback_data}")
    
    language = detect_language(get_conversation_state(user_id).get('last_message', 'hola'))
    
    # Manejar diferentes tipos de callbacks
    if callback_data == 'time_category_lunch':
        # Mostrar horarios de comida
        keyboard = get_lunch_times_keyboard(language)
        text = "🍽️ Selecciona la hora de comida:" if language != 'ca' else "🍽️ Selecciona l'hora de dinar:"
        await query.edit_message_text(text=text, reply_markup=keyboard)
        
    elif callback_data == 'time_category_dinner':
        # Mostrar horarios de cena
        keyboard = get_dinner_times_keyboard(language)
        text = "🌙 Selecciona la hora de cena:" if language != 'ca' else "🌙 Selecciona l'hora de sopar:"
        await query.edit_message_text(text=text, reply_markup=keyboard)
        
    elif callback_data == 'back_to_categories':
        # Volver al menú principal de horarios
        keyboard = get_time_slots_keyboard(language)
        text = "¿Comida o cena?" if language != 'ca' else "Dinar o sopar?"
        await query.edit_message_text(text=text, reply_markup=keyboard)
        
    elif callback_data.startswith('time_'):
        # Usuario seleccionó una hora específica
        time_selected = callback_data.replace('time_', '')
        logger.info(f"[TIME] Usuario seleccionó hora: {time_selected}")
        
        # Remover el teclado
        await query.edit_message_text(text=f"✅ Hora seleccionada: {time_selected}")
        
        # Procesar la hora seleccionada como si el usuario la hubiera escrito
        await update.effective_chat.send_action(action="typing")
        
        response = process_message_with_ai(
            time_selected, 
            user_id, 
            appointment_manager, 
            conversation_manager
        )
        
        await query.message.reply_text(response)

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
        
        # Detectar si debemos mostrar botones
        language = detect_language(transcribed_text)
        if should_show_time_buttons(user_id, transcribed_text, response):
            keyboard = get_time_slots_keyboard(language)
            await update.message.reply_text(f"📝 Escuché: \"{transcribed_text}\"\n\n{response}", reply_markup=keyboard)
        else:
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
    application.add_handler(CallbackQueryHandler(handle_button_click))  # Para los botones
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
