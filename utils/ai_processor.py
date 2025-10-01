import os
import json
from langdetect import detect, LangDetectException
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

def detect_language(text):
    """Detectar el idioma del texto"""
    try:
        lang = detect(text)
        return lang
    except LangDetectException:
        return 'es'

def process_message_with_ai(message, phone, appointment_manager, conversation_manager):
    """
    Procesar mensaje con GPT-4 usando historial de conversación
    """
    
    # Detectar idioma
    language = detect_language(message)
    
    # Mapeo de idiomas
    language_names = {
        'es': 'español',
        'en': 'inglés',
        'ca': 'catalán',
        'fr': 'francés',
        'de': 'alemán',
        'it': 'italiano',
        'pt': 'portugués'
    }
    
    lang_name = language_names.get(language, 'español')
    
    # System prompt
    system_prompt = f"""Eres un asistente virtual para gestión de citas médicas/de servicios.

IDIOMA: El usuario está escribiendo en {lang_name}. Responde SIEMPRE en {lang_name}.

CAPACIDADES:
1. Agendar nuevas citas (necesitas: fecha, hora, nombre del cliente, servicio)
2. Consultar citas existentes
3. Cancelar citas
4. Responder preguntas generales

FORMATO DE FECHAS: Acepta formatos naturales como "mañana", "el lunes", "15 de octubre"
FORMATO DE HORAS: Acepta "10 de la mañana", "15:30", "3 de la tarde"

INSTRUCCIONES IMPORTANTES:
- Mantén el contexto de la conversación anterior
- Si el usuario ya te dio algún dato (nombre, fecha, hora, servicio), recuérdalo
- Pide información faltante una cosa a la vez
- Confirma los detalles antes de crear la cita
- Si el usuario quiere agendar, usa la función create_appointment cuando tengas TODOS los datos
- Si el usuario quiere ver sus citas, usa list_appointments

SERVICIOS DISPONIBLES: Corte de pelo, Manicure, Pedicure, Masaje, Consulta médica, Revisión

Si el usuario dice "empezar de nuevo" o "cancelar", olvida la conversación anterior."""

    try:
        print(f"🔍 Intentando procesar mensaje: {message}")
        print(f"🔍 API Key configurada: {os.getenv('OPENAI_API_KEY')[:20]}...")
        
        # Obtener historial de conversación
        history = conversation_manager.get_history(phone, limit=10)
        
        # Construir mensajes incluyendo historial
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        
        # Inicializar cliente OpenAI
        print("🔍 Inicializando cliente OpenAI...")
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        print("✅ Cliente OpenAI inicializado")
        
        # Llamada a GPT-4 con function calling
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=messages,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "create_appointment",
                        "description": "Crear una nueva cita cuando tengas TODOS los datos necesarios",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "client_name": {
                                    "type": "string",
                                    "description": "Nombre del cliente"
                                },
                                "date": {
                                    "type": "string",
                                    "description": "Fecha en formato YYYY-MM-DD"
                                },
                                "time": {
                                    "type": "string",
                                    "description": "Hora en formato HH:MM (24 horas)"
                                },
                                "service": {
                                    "type": "string",
                                    "description": "Servicio solicitado"
                                }
                            },
                            "required": ["client_name", "date", "time", "service"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "list_appointments",
                        "description": "Listar las citas del usuario"
                    }
                }
            ],
            temperature=0.7
        )
        
        message_response = response.choices[0].message
        assistant_reply = ""
        
        # Si la IA quiere ejecutar una función
        if message_response.tool_calls:
            tool_call = message_response.tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            if function_name == "create_appointment":
                # Crear la cita
                apt_id = appointment_manager.create_appointment(
                    phone=phone,
                    client_name=function_args.get('client_name'),
                    date=function_args.get('date'),
                    time=function_args.get('time'),
                    service=function_args.get('service'),
                    language=language
                )
                
                if apt_id:
                    # Mensajes de confirmación según idioma
                    confirmations = {
                        'es': f"✅ ¡Cita confirmada!\n\n👤 Nombre: {function_args['client_name']}\n📅 Fecha: {function_args['date']}\n🕐 Hora: {function_args['time']}\n💼 Servicio: {function_args['service']}\n\nTe enviaremos un recordatorio el día anterior.",
                        'en': f"✅ Appointment confirmed!\n\n👤 Name: {function_args['client_name']}\n📅 Date: {function_args['date']}\n🕐 Time: {function_args['time']}\n💼 Service: {function_args['service']}\n\nWe'll send you a reminder the day before.",
                        'ca': f"✅ Cita confirmada!\n\n👤 Nom: {function_args['client_name']}\n📅 Data: {function_args['date']}\n🕐 Hora: {function_args['time']}\n💼 Servei: {function_args['service']}\n\nT'enviarem un recordatori el dia anterior."
                    }
                    
                    assistant_reply = confirmations.get(language, confirmations['es'])
                    
                    # Limpiar historial después de completar la cita
                    conversation_manager.clear_history(phone)
                else:
                    assistant_reply = "❌ Hubo un error al crear la cita. Por favor intenta de nuevo."
            
            elif function_name == "list_appointments":
                appointments = appointment_manager.get_appointments(phone)
                
                if not appointments:
                    no_apts = {
                        'es': "📅 No tienes citas programadas.",
                        'en': "📅 You don't have any scheduled appointments.",
                        'ca': "📅 No tens cites programades."
                    }
                    assistant_reply = no_apts.get(language, no_apts['es'])
                else:
                    # Formatear lista de citas
                    apts_list = {
                        'es': "📅 Tus citas:\n\n",
                        'en': "📅 Your appointments:\n\n",
                        'ca': "📅 Les teves cites:\n\n"
                    }
                    
                    assistant_reply = apts_list.get(language, apts_list['es'])
                    
                    for apt in appointments:
                        apt_id, name, date, time, service, status = apt
                        assistant_reply += f"• {date} a las {time}\n  {service} - {name}\n  Estado: {status}\n\n"
        else:
            # Respuesta directa sin función
            assistant_reply = message_response.content
        
        # Guardar en historial
        conversation_manager.save_message(phone, "user", message)
        conversation_manager.save_message(phone, "assistant", assistant_reply)
        
        # Detectar si el usuario quiere empezar de nuevo
        if any(word in message.lower() for word in ["empezar de nuevo", "cancelar", "olvidar", "reiniciar", "start over"]):
            conversation_manager.clear_history(phone)
        
        return assistant_reply
    
    except Exception as e:
        print(f"Error procesando con IA: {e}")
        return "Lo siento, hubo un error procesando tu mensaje. ¿Puedes intentar de nuevo?"