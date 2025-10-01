from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from dotenv import load_dotenv
from utils.transcription import transcribe_audio
from utils.appointments import AppointmentManager, ConversationManager
from utils.ai_processor import process_message_with_ai
import base64

load_dotenv()

app = Flask(__name__)

# Configuración de Twilio
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')

if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
    print("ERROR: Variables de Twilio no configuradas")
else:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    print("Cliente Twilio inicializado correctamente")

# Inicializar gestores
appointment_manager = AppointmentManager()
conversation_manager = ConversationManager()

@app.route('/')
def home():
    return """
    <h1>WhatsApp AI Agent - Restaurante</h1>
    <p>Bot de reservas funcionando correctamente</p>
    <p>Webhook: <code>https://tu-dominio.railway.app/whatsapp</code></p>
    """

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """Endpoint principal que recibe mensajes de WhatsApp"""
    
    incoming_msg = request.values.get('Body', '').strip()
    media_url = request.values.get('MediaUrl0', '')
    from_number = request.values.get('From', '')
    
    print(f"📱 Mensaje de {from_number}: {incoming_msg}")
    
    resp = MessagingResponse()
    
    try:
        # Si hay audio, transcribirlo
        if media_url:
            print(f"🎤 Transcribiendo audio...")
            auth_str = f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}"
            auth_header = f"Basic {base64.b64encode(auth_str.encode()).decode()}"
            
            transcribed_text = transcribe_audio(media_url, auth_header)
            
            if transcribed_text:
                print(f"Audio transcrito: {transcribed_text}")
                incoming_msg = transcribed_text
            else:
                resp.message("No pude entender el audio. ¿Puedes escribir tu mensaje?")
                return str(resp)
        
        if not incoming_msg:
            resp.message("Hola! Escribe o envía un mensaje de voz para hacer una reserva.")
            return str(resp)
        
        # Procesar con IA
        ai_response = process_message_with_ai(incoming_msg, from_number, appointment_manager, conversation_manager)
        
        resp.message(ai_response)
    
    except Exception as e:
        print(f"Error: {e}")
        resp.message("Lo siento, hubo un error. Por favor intenta de nuevo.")
    
    return str(resp)

@app.route('/health')
def health():
    """Endpoint de salud"""
    return {"status": "ok", "message": "Server is running"}

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)