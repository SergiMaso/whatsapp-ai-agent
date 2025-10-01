from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from dotenv import load_dotenv
from utils.transcription import transcribe_audio
from utils.appointments import AppointmentManager
from utils.ai_processor import process_message_with_ai
import base64

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# Configuración de Twilio
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Inicializar gestor de citas
appointment_manager = AppointmentManager()

@app.route('/')
def home():
    return """
    <h1>🤖 WhatsApp AI Agent</h1>
    <p>El bot está funcionando correctamente!</p>
    <p>Configura tu webhook de Twilio a: <code>https://tu-dominio.railway.app/whatsapp</code></p>
    """

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """
    Endpoint principal que recibe mensajes de WhatsApp
    """
    
    # Obtener datos del mensaje
    incoming_msg = request.values.get('Body', '').strip()
    media_url = request.values.get('MediaUrl0', '')
    from_number = request.values.get('From', '')
    
    print(f"📱 Mensaje de {from_number}: {incoming_msg}")
    
    # Preparar respuesta
    resp = MessagingResponse()
    
    try:
        # Si hay un audio adjunto, transcribirlo
        if media_url:
            print(f"🎤 Transcribiendo audio...")
            
            # Crear header de autorización para descargar el audio
            auth_str = f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}"
            auth_header = f"Basic {base64.b64encode(auth_str.encode()).decode()}"
            
            transcribed_text = transcribe_audio(media_url, auth_header)
            
            if transcribed_text:
                print(f"✅ Audio transcrito: {transcribed_text}")
                incoming_msg = transcribed_text
            else:
                resp.message("❌ No pude entender el audio. ¿Puedes escribir tu mensaje?")
                return str(resp)
        
        # Si no hay mensaje (ni texto ni audio)
        if not incoming_msg:
            resp.message("👋 Hola! Escribe o envía un mensaje de voz para agendar una cita.")
            return str(resp)
        
        # Procesar mensaje con IA
        ai_response = process_message_with_ai(incoming_msg, from_number, appointment_manager)
        
        # Enviar respuesta
        resp.message(ai_response)
    
    except Exception as e:
        print(f"❌ Error: {e}")
        resp.message("Lo siento, hubo un error. Por favor intenta de nuevo en unos momentos.")
    
    return str(resp)

@app.route('/health')
def health():
    """Endpoint para verificar que el servidor está activo"""
    return {"status": "ok", "message": "Server is running"}

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)