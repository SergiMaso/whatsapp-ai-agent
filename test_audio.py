"""
Script para probar transcripción de audio localmente
"""

from utils.transcription import transcribe_audio
import base64
import os
from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')

print("🎤 TEST DE TRANSCRIPCIÓN DE AUDIO")
print("-" * 60)

# Ejemplo: URL de un audio de prueba (si tienes uno guardado)
audio_url = input("\nPega la URL del audio de WhatsApp: ")

if audio_url:
    auth_str = f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}"
    auth_header = f"Basic {base64.b64encode(auth_str.encode()).decode()}"
    
    print("\n⏳ Transcribiendo...")
    transcription = transcribe_audio(audio_url, auth_header)
    
    if transcription:
        print(f"\n✅ Transcripción: {transcription}")
    else:
        print("\n❌ Error en transcripción")
else:
    print("\n⚠️ No se proporcionó URL")
