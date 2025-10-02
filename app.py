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
    
    print(f"[WEBHOOK] Recibida peticion POST a /whatsapp")
    
    incoming_msg = request.values.get('Body', '').strip()
    media_url = request.values.get('MediaUrl0', '')
    from_number = request.values.get('From', '')
    
    print(f"[MSG] Mensaje de {from_number}: {incoming_msg}")
    
    resp = MessagingResponse()
    
    try:
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
                resp.message("No pude entender el audio. ¿Puedes escribir tu mensaje?")
                return str(resp)
        
        if not incoming_msg:
            resp.message("Hola! Escribe o envía un mensaje de voz para hacer una reserva.")
            return str(resp)
        
        # Procesar con IA
        print(f"[AI] Enviando a procesador de IA: {incoming_msg[:50]}...")
        ai_response = process_message_with_ai(incoming_msg, from_number, appointment_manager, conversation_manager)
        
        print(f"[AI] Respuesta recibida del procesador: {ai_response[:50] if ai_response else 'None'}...")
        print(f"[SEND] Enviando mensaje a WhatsApp (longitud: {len(ai_response)} chars)...")
        
        try:
            resp.message(ai_response)
            print(f"[OK] Mensaje agregado a TwiML response")
        except Exception as msg_error:
            print(f"[ERROR] Error al agregar mensaje: {msg_error}")
            import traceback
            traceback.print_exc()
    
    except Exception as e:
        print(f"[ERROR] Error en webhook: {e}")
        import traceback
        traceback.print_exc()
        resp.message("Lo siento, hubo un error. Por favor intenta de nuevo.")
    
    # Log de la respuesta TwiML completa
    twiml_response = str(resp)
    print(f"[TWIML] Respuesta completa ({len(twiml_response)} chars): {twiml_response}")
    
    # Asegurar que Flask devuelva XML con el content-type correcto
    from flask import Response
    return Response(twiml_response, mimetype='text/xml')

@app.route('/health')
def health():
    """Endpoint de salud"""
    return {"status": "ok", "message": "Server is running"}

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)