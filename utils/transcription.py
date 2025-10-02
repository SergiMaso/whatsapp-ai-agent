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
        print(f"\ud83c\udfa7 Descargando audio desde: {audio_url}")
        
        # Descargar el audio desde WhatsApp (requiere auth de Twilio)
        response = requests.get(audio_url, headers={'Authorization': auth_header}, timeout=30)
        
        print(f"\ud83d\udcc4 Status code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"\u274c Error descargando audio: Status {response.status_code}")
            return None
        
        print(f"\u2705 Audio descargado: {len(response.content)} bytes")
        
        # Guardar temporalmente
        audio_path = 'temp_audio.ogg'
        with open(audio_path, 'wb') as f:
            f.write(response.content)
        
        print("\ud83e\udde0 Iniciando transcripci\u00f3n con Whisper...")
        
        # Inicializar cliente OpenAI
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Transcribir con Whisper
        with open(audio_path, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es"
            )
        
        print(f"\u2705 Transcripci\u00f3n exitosa: {transcript.text}")
        
        # Limpiar archivo temporal
        if os.path.exists(audio_path):
            os.remove(audio_path)
        
        return transcript.text
    
    except Exception as e:
        print(f"\u274c Error transcribiendo audio: {e}")
        import traceback
        traceback.print_exc()
        return None