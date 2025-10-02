from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from dotenv import load_dotenv
from utils.transcription import transcribe_audio
from utils.appointments import AppointmentManager, ConversationManager
from utils.ai_processor import process_message_with_ai
import base64
import threading

load_dotenv()

app = Flask(__name__)

# Configuración de Twilio
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')

if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
    print("ERROR: Variables de Twilio no configuradas")
else:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    print("Cliente Twilio inicializado correctamente")

# Inicializar gestores
appointment_manager = AppointmentManager()
conversation_manager = ConversationManager()

def process_and_send(incoming_msg, from_number, media_url):
    """Procesar mensaje en segundo plano y enviar respuesta"""
    try:
        print(f"[ASYNC] Iniciando procesamiento para {from_number}")
        
        # Si hay audio, transcribirlo
        if media_url:
            print(f"[AUDIO] Audio detectado: {media_url}")
            auth_str = f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}"
            auth_header = f"Basic {base64.b64encode(auth_str.encode()).decode()}"
            
            transcribed_text = transcribe_audio(media_url, auth_header)
            
            if transcribed_text:
                print(f"[OK] Audio transcrito: {transcribed_text}")
                incoming_msg = transcribed_text
            else:
                print("[ERROR] Error transcribiendo audio")
                twilio_client.messages.create(
                    from_=TWILIO_WHATSAPP_NUMBER,
                    body="No pude entender el audio. ¿Puedes escribir tu mensaje?",
                    to=from_number
                )
                return
        
        if not incoming_msg:
            print("[WARN] Mensaje vacio, no hay nada que procesar")
            return
        
        # Procesar con IA
        print(f"[AI] Procesando mensaje: {incoming_msg[:50]}...")
        ai_response = process_message_with_ai(incoming_msg, from_number, appointment_manager, conversation_manager)
        
        print(f"[AI] Respuesta generada: {ai_response[:50]}...")
        
        # Enviar mensaje usando API de Twilio
        print(f"[SEND] Enviando mensaje via Twilio API...")
        message = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=ai_response,
            to=from_number
        )
        
        print(f"[OK] Mensaje enviado exitosamente! SID: {message.sid}")
        
    except Exception as e:
        print(f"[ERROR] Error en procesamiento asincrono: {e}")
        import traceback
        traceback.print_exc()
        
        # Intentar enviar mensaje de error
        try:
            twilio_client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                body="Lo siento, hubo un error procesando tu mensaje. Por favor intenta de nuevo.",
                to=from_number
            )
        except:
            print("[ERROR] No se pudo enviar mensaje de error")

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
    
    print(f"[WEBHOOK] Recibida peticion POST a /whatsapp")
    
    incoming_msg = request.values.get('Body', '').strip()
    media_url = request.values.get('MediaUrl0', '')
    from_number = request.values.get('From', '')
    
    print(f"[MSG] Mensaje de {from_number}: {incoming_msg if incoming_msg else '(audio)'}") 
    
    # Procesar en segundo plano
    thread = threading.Thread(
        target=process_and_send, 
        args=(incoming_msg, from_number, media_url)
    )
    thread.daemon = True
    thread.start()
    
    print(f"[ASYNC] Thread iniciado, respondiendo inmediatamente a Twilio")
    
    # Responder inmediatamente con TwiML vacío (200 OK)
    resp = MessagingResponse()
    return Response(str(resp), mimetype='text/xml')

@app.route('/health')
def health():
    """Endpoint de salud"""
    return {"status": "ok", "message": "Server is running"}

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
