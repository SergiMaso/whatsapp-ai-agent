import os
import json
from langdetect import detect, LangDetectException
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime

load_dotenv()

def detect_language(text):
    """Detectar el idioma del texto con mejor soporte para catalán"""
    try:
        lang = detect(text)
        
        # Palabras clave catalanas para mejorar detección
        catalan_keywords = ['vull', 'necessito', 'puc', 'tinc', 'avui', 'demà', 'sisplau', 
                           'gràcies', 'bon dia', 'bona tarda', 'hola', 'adéu', 'taula',
                           'persones', 'reserva', 'dinar', 'sopar']
        
        text_lower = text.lower()
        if any(word in text_lower for word in catalan_keywords):
            return 'ca'
        
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
        'ca': 'català',
        'fr': 'francés',
        'de': 'alemán',
        'it': 'italiano',
        'pt': 'portugués'
    }
    
    lang_name = language_names.get(language, 'español')
    
    # Verificar si el cliente ya existe
    customer_name = appointment_manager.get_customer_name(phone)
    
    # Fecha actual para contexto
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    day_name_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][today.weekday()]
    day_name_ca = ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"][today.weekday()]
    
    day_name = day_name_ca if language == 'ca' else day_name_es
    
    # Saludo personalizado
    if customer_name and language == 'ca':
        customer_greeting = f"Ja et conec, {customer_name}! "
    elif customer_name and language == 'es':
        customer_greeting = f"Ya te conozco, {customer_name}! "
    elif customer_name:
        customer_greeting = f"I remember you, {customer_name}! "
    else:
        customer_greeting = ""
    
    # System prompt para restaurante
    system_prompt = f"""Eres un asistente virtual para reservas de un restaurante.

FECHA ACTUAL: Hoy es {day_name} {today_str} (1 de octubre de 2025).

IDIOMA: El usuario está escribiendo en {lang_name}. Responde SIEMPRE en {lang_name}.
{customer_greeting}

INFORMACIÓN DEL RESTAURANTE:
- Capacidad: 20 mesas de 4 personas y 8 mesas de 2 personas
- Horarios de servicio:
  * Comida: 12:00 a 14:30 (última reserva)
  * Cena: 19:00 a 22:00 (última reserva)
- Solo aceptamos reservas en estos horarios

CAPACIDADES:
1. Agendar nuevas reservas (necesitas: nombre, fecha, hora, número de personas)
2. Consultar reservas existentes
3. Cancelar reservas (necesitas el ID de la reserva)
4. Responder preguntas generales

PROCESO DE RESERVA:
1. Saluda cordialmente
2. Pregunta para cuántas personas (1-8 personas máximo)
3. Pregunta qué día (acepta "hoy", "mañana", "el viernes", fechas específicas)
4. Pregunta horario preferido y hora específica
5. Pregunta el nombre (si no lo tienes guardado)
6. Confirma todos los detalles antes de crear la reserva

PROCESO DE CANCELACIÓN:
1. Primero muestra las reservas del usuario con list_appointments
2. Pide que indiquen qué reserva quieren cancelar
3. Usa cancel_appointment con el ID correcto

INSTRUCCIONES:
- Mantén contexto de la conversación anterior
- Sé cálido, profesional y cercano
- Si ya conoces al cliente, salúdalo por su nombre
- Usa lenguaje natural del idioma del usuario
- Si dice "empezar de nuevo", olvida la conversación
- Cuando tengas TODOS los datos, usa las funciones apropiadas"""

    try:
        # Obtener historial de conversación
        history = conversation_manager.get_history(phone, limit=10)
        
        # Construir mensajes incluyendo historial
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        
        # Inicializar cliente OpenAI
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Llamada a GPT-4 con function calling
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=messages,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "create_appointment",
                        "description": "Crear una reserva cuando tengas TODOS los datos necesarios",
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
                                "num_people": {
                                    "type": "integer",
                                    "description": "Número de personas (1-8)"
                                }
                            },
                            "required": ["client_name", "date", "time", "num_people"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "list_appointments",
                        "description": "Listar las reservas del usuario"
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "cancel_appointment",
                        "description": "Cancelar una reserva existente del usuario",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "appointment_id": {
                                    "type": "integer",
                                    "description": "ID de la reserva a cancelar"
                                }
                            },
                            "required": ["appointment_id"]
                        }
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
                num_people = function_args.get('num_people', 2)
                
                # Validar número de personas
                if num_people < 1 or num_people > 8:
                    error_msgs = {
                        'es': "Lo siento, solo aceptamos reservas de 1 a 8 personas.",
                        'ca': "Ho sento, només acceptem reserves d'1 a 8 persones.",
                        'en': "Sorry, we only accept reservations for 1 to 8 people."
                    }
                    return error_msgs.get(language, error_msgs['es'])
                
                # Validar horarios
                try:
                    hour = int(function_args.get('time').split(':')[0])
                    minute = int(function_args.get('time').split(':')[1])
                    
                    is_lunch = 12 <= hour < 15 or (hour == 14 and minute <= 30)
                    is_dinner = 19 <= hour < 23 or (hour == 22 and minute == 0)
                    
                    if not (is_lunch or is_dinner):
                        error_msgs = {
                            'es': "Lo siento, solo aceptamos reservas de 12:00-14:30 o 19:00-22:00. ¿Prefieres otro horario?",
                            'ca': "Ho sento, només acceptem reserves de 12:00-14:30 o 19:00-22:00. Prefereixes un altre horari?",
                            'en': "Sorry, we only accept reservations from 12:00-14:30 or 19:00-22:00. Would you prefer another time?"
                        }
                        return error_msgs.get(language, error_msgs['es'])
                except:
                    pass
                
                # Guardar nombre del cliente
                appointment_manager.save_customer_info(phone, function_args.get('client_name'))
                
                # Crear la reserva
                result = appointment_manager.create_appointment(
                    phone=phone,
                    client_name=function_args.get('client_name'),
                    date=function_args.get('date'),
                    time=function_args.get('time'),
                    num_people=num_people,
                    language=language
                )
                
                if result:
                    table_info = result['table']
                    confirmations = {
                        'es': f"¡Reserva confirmada!\n\n👤 Nombre: {function_args['client_name']}\n👥 Personas: {num_people}\n📅 Fecha: {function_args['date']}\n🕐 Hora: {function_args['time']}\n🪑 Mesa: {table_info['number']} (capacidad {table_info['capacity']})\n\n¡Te esperamos! Si necesitas modificar la reserva, avísanos.",
                        'ca': f"Reserva confirmada!\n\n👤 Nom: {function_args['client_name']}\n👥 Persones: {num_people}\n📅 Data: {function_args['date']}\n🕐 Hora: {function_args['time']}\n🪑 Taula: {table_info['number']} (capacitat {table_info['capacity']})\n\nT'esperem! Si necessites modificar la reserva, avisa'ns.",
                        'en': f"Reservation confirmed!\n\n👤 Name: {function_args['client_name']}\n👥 People: {num_people}\n📅 Date: {function_args['date']}\n🕐 Time: {function_args['time']}\n🪑 Table: {table_info['number']} (capacity {table_info['capacity']})\n\nWe look forward to seeing you!"
                    }
                    
                    assistant_reply = confirmations.get(language, confirmations['es'])
                    conversation_manager.clear_history(phone)
                else:
                    no_tables_msgs = {
                        'es': f"Lo siento, no tenemos mesas disponibles para {num_people} personas el {function_args['date']} a las {function_args['time']}. ¿Te gustaría probar con otro horario?",
                        'ca': f"Ho sento, no tenim taules disponibles per a {num_people} persones el {function_args['date']} a les {function_args['time']}. Vols provar amb un altre horari?",
                        'en': f"Sorry, we don't have tables available for {num_people} people on {function_args['date']} at {function_args['time']}. Would you like to try another time?"
                    }
                    assistant_reply = no_tables_msgs.get(language, no_tables_msgs['es'])
            
            elif function_name == "list_appointments":
                appointments = appointment_manager.get_appointments(phone)
                
                if not appointments:
                    no_apts = {
                        'es': "No tienes reservas programadas.",
                        'en': "You don't have any scheduled reservations.",
                        'ca': "No tens reserves programades."
                    }
                    assistant_reply = no_apts.get(language, no_apts['es'])
                else:
                    apts_list = {
                        'es': "Tus reservas:\n\n",
                        'en': "Your reservations:\n\n",
                        'ca': "Les teves reserves:\n\n"
                    }
                    
                    assistant_reply = apts_list.get(language, apts_list['es'])
                    
                    for apt in appointments:
                        apt_id, name, date, time, num_people, table_num, table_cap, status = apt
                        assistant_reply += f"ID: {apt_id}\n• {date} a las {time}\n  {num_people} personas - Mesa {table_num}\n  {name} - {status}\n\n"
            
            elif function_name == "cancel_appointment":
                apt_id = function_args.get('appointment_id')
                success = appointment_manager.cancel_appointment(phone, apt_id)
                
                if success:
                    cancel_msgs = {
                        'es': "✅ Reserva cancelada correctamente.",
                        'ca': "✅ Reserva cancel·lada correctament.",
                        'en': "✅ Reservation cancelled successfully."
                    }
                    assistant_reply = cancel_msgs.get(language, cancel_msgs['es'])
                else:
                    error_msgs = {
                        'es': "❌ No se pudo cancelar la reserva. Verifica el ID de la reserva.",
                        'ca': "❌ No s'ha pogut cancel·lar la reserva. Verifica l'ID de la reserva.",
                        'en': "❌ Could not cancel the reservation. Please verify the reservation ID."
                    }
                    assistant_reply = error_msgs.get(language, error_msgs['es'])
        
        else:
            assistant_reply = message_response.content
        
        # Guardar en historial
        conversation_manager.save_message(phone, "user", message)
        conversation_manager.save_message(phone, "assistant", assistant_reply)
        
        # Detectar si el usuario quiere empezar de nuevo
        restart_keywords = ["empezar de nuevo", "olvidar", "reiniciar", "start over", "començar de nou"]
        if any(word in message.lower() for word in restart_keywords):
            conversation_manager.clear_history(phone)
        
        return assistant_reply
    
    except Exception as e:
        print(f"Error procesando con IA: {e}")
        return "Lo siento, hubo un error procesando tu mensaje. ¿Puedes intentar de nuevo?"