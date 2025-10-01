import requests
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

def transcribe_audio(audio_url, auth_header):
    """
    Descarga y transcribe un audio de WhatsApp usando Whisper
    """
    try:
        # Descargar el audio desde WhatsApp (requiere auth de Twilio)
        response = requests.get(audio_url, headers={'Authorization': auth_header})
        
        if response.status_code != 200:
            return None
        
        # Guardar temporalmente
        audio_path = 'temp_audio.ogg'
        with open(audio_path, 'wb') as f:
            f.write(response.content)
        
        # Inicializar cliente OpenAI
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Transcribir con Whisper
        with open(audio_path, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es"
            )
        
        # Limpiar archivo temporal
        if os.path.exists(audio_path):
            os.remove(audio_path)
        
        return transcript.text
    
    except Exception as e:
        print(f"Error transcribiendo audio: {e}")
        return None