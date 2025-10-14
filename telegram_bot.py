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
from utils.conversation_state import (
    should_show_time_buttons, 
    should_show_only_dinner,
    should_show_lunch_directly,
    should_show_dinner_directly,
    set_conversation_state, 
    get_conversation_state
)
from utils.telegram_keyboards import (
    get_time_slots_keyboard,
    get_lunch_times_keyboard,
    get_dinner_times_keyboard
)

load_dotenv()

# Configuración - Railway usa variables de entorno directamente
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')

# LOGS REDUÏTS - Només errors i converses
logging.basicConfig(
    format='%(message)s',
    level=logging.WARNING  # Només WARNING i ERROR
)
logger = logging.getLogger(__name__)

# Desactivar logs d'altres llibreries
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# Inicializar gestores
appointment_manager = AppointmentManager()
conversation_manager = ConversationManager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    user_id = update.effective_user.id
    
    text = (
        "Hola! Sóc el bot de reserves del restaurant.\n\n"
        "Pots escriure o enviar missatges de veu per a:\n"
        "• Fer una reserva\n"
        "• Veure les teves reserves\n"
        "• Cancel·lar una reserva\n\n"
        "En què puc ajudar-te?"
    )
    
    print(f"\n💬 [USUARI {user_id}] /start")
    print(f"🤖 [BOT] {text[:50]}...")
    
    await update.message.reply_text(text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar mensajes de texto"""
    user_message = update.message.text
    user_id = f"telegram:{update.effective_user.id}"
    
    print(f"\n💬 [USUARI] {user_message}")
    
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
        
        print(f"🤖 [BOT] {response}")
        
        # Detectar si debemos mostrar botones de hora
        language = detect_language(user_message)
        
        # PRIORIDAD 1: Si el usuario mencionó específicamente LUNCH/DINAR
        if should_show_time_buttons(user_id, user_message, response) and should_show_lunch_directly(user_message):
            keyboard = get_lunch_times_keyboard(language)
            print(f"⌨️  [BOTONS] Mostrant horaris de dinar")
            await update.message.reply_text(response, reply_markup=keyboard)
        # PRIORIDAD 2: Si el usuario mencionó específicamente DINNER/SOPAR
        elif should_show_time_buttons(user_id, user_message, response) and should_show_dinner_directly(user_message):
            keyboard = get_dinner_times_keyboard(language)
            print(f"⌨️  [BOTONS] Mostrant horaris de sopar")
            await update.message.reply_text(response, reply_markup=keyboard)
        # PRIORIDAD 3: Si es tarde y pide para HOY, solo cena
        elif should_show_time_buttons(user_id, user_message, response) and should_show_only_dinner(user_message):
            keyboard = get_dinner_times_keyboard(language)
            print(f"⌨️  [BOTONS] Només sopar disponible")
            await update.message.reply_text(response, reply_markup=keyboard)
        # PRIORIDAD 4: Mostrar menú general (comida/cena)
        elif should_show_time_buttons(user_id, user_message, response):
            keyboard = get_time_slots_keyboard(language)
            print(f"⌨️  [BOTONS] Mostrant dinar/sopar")
            await update.message.reply_text(response, reply_markup=keyboard)
        else:
            await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"❌ Error procesando mensaje: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(
            "Ho sento, hi ha hagut un error. Si us plau intenta-ho de nou."
        )

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar clicks en botones inline"""
    query = update.callback_query
    user_id = f"telegram:{update.effective_user.id}"
    
    await query.answer()  # Acknowledge the callback
    
    callback_data = query.data
    
    print(f"\n🔘 [USUARI] Botó premut: {callback_data}")
    
    language = detect_language(get_conversation_state(user_id).get('last_message', 'hola'))
    
    # Manejar diferentes tipos de callbacks
    if callback_data == 'time_category_lunch':
        # Mostrar horarios de comida
        keyboard = get_lunch_times_keyboard(language)
        text = "🍽️ Selecciona l'hora de dinar:"
        print(f"🤖 [BOT] {text}")
        await query.edit_message_text(text=text, reply_markup=keyboard)
        
    elif callback_data == 'time_category_dinner':
        # Mostrar horarios de cena
        keyboard = get_dinner_times_keyboard(language)
        text = "🌙 Selecciona l'hora de sopar:"
        print(f"🤖 [BOT] {text}")
        await query.edit_message_text(text=text, reply_markup=keyboard)
        
    elif callback_data == 'back_to_categories':
        # Volver al menú principal de horarios
        keyboard = get_time_slots_keyboard(language)
        text = "Dinar o sopar?"
        print(f"🤖 [BOT] {text}")
        await query.edit_message_text(text=text, reply_markup=keyboard)
        
    elif callback_data.startswith('time_'):
        # Usuario seleccionó una hora específica
        time_selected = callback_data.replace('time_', '')
        
        print(f"⏰ [USUARI] Hora seleccionada: {time_selected}")
        
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
        
        print(f"🤖 [BOT] {response}")
        await query.message.reply_text(response)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar mensajes de voz"""
    user_id = f"telegram:{update.effective_user.id}"
    
    print(f"\n🎤 [USUARI] Missatge de veu rebut")
    
    await update.message.reply_text("🎤 Escoltant...")
    
    try:
        # Descargar el archivo de audio
        voice_file = await update.message.voice.get_file()
        voice_url = voice_file.file_path
        
        # Descargar el audio
        import requests
        audio_response = requests.get(voice_url)
        
        if audio_response.status_code != 200:
            await update.message.reply_text("No he pogut descarregar l'àudio. Intenta-ho de nou.")
            return
        
        # Guardar temporalmente
        audio_path = 'temp_telegram_audio.ogg'
        with open(audio_path, 'wb') as f:
            f.write(audio_response.content)
        
        # Transcribir con Whisper
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        with open(audio_path, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ca"  # Català per defecte
            )
        
        transcribed_text = transcript.text
        
        print(f"📝 [TRANSCRIPCIÓ] \"{transcribed_text}\"")
        
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
        
        print(f"🤖 [BOT] {response}")
        
        # Detectar si debemos mostrar botones
        language = detect_language(transcribed_text)
        
        # Mostrar solo el texto transcrito entre comillas, sin "Escuché:"
        transcription_display = f'"{transcribed_text}"\n\n{response}'
        
        # PRIORIDAD 1: Si el usuario mencionó LUNCH/DINAR
        if should_show_time_buttons(user_id, transcribed_text, response) and should_show_lunch_directly(transcribed_text):
            keyboard = get_lunch_times_keyboard(language)
            print(f"⌨️  [BOTONS] Mostrant horaris de dinar")
            await update.message.reply_text(transcription_display, reply_markup=keyboard)
        # PRIORIDAD 2: Si el usuario mencionó DINNER/SOPAR
        elif should_show_time_buttons(user_id, transcribed_text, response) and should_show_dinner_directly(transcribed_text):
            keyboard = get_dinner_times_keyboard(language)
            print(f"⌨️  [BOTONS] Mostrant horaris de sopar")
            await update.message.reply_text(transcription_display, reply_markup=keyboard)
        # PRIORIDAD 3: Si es tarde y pide para HOY
        elif should_show_time_buttons(user_id, transcribed_text, response) and should_show_only_dinner(transcribed_text):
            keyboard = get_dinner_times_keyboard(language)
            print(f"⌨️  [BOTONS] Només sopar disponible")
            await update.message.reply_text(transcription_display, reply_markup=keyboard)
        # PRIORIDAD 4: Menú general
        elif should_show_time_buttons(user_id, transcribed_text, response):
            keyboard = get_time_slots_keyboard(language)
            print(f"⌨️  [BOTONS] Mostrant dinar/sopar")
            await update.message.reply_text(transcription_display, reply_markup=keyboard)
        else:
            await update.message.reply_text(transcription_display)
        
    except Exception as e:
        logger.error(f"❌ Error procesando audio: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(
            "No he pogut processar l'àudio. Pots escriure el teu missatge?"
        )

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejar archivos de audio"""
    await handle_voice(update, context)

def main():
    """Iniciar el bot de Telegram"""
    
    if not TELEGRAM_BOT_TOKEN:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN no configurado")
        return
    
    print("✅ Bot de Telegram inicializado")
    print("="*60)
    print("📱 LOGS DE CONVERSA ACTIVATS")
    print("="*60)
    
    # Crear aplicación
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Agregar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_button_click))  # Para los botones
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    
    # Iniciar bot
    try:
        application.run_polling()
    except telegram.error.Conflict:
        print("⚠️ Un altre procés del bot està actiu. Esperant...")

if __name__ == '__main__':
    main()
