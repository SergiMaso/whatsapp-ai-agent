import os
import json
from langdetect import detect, LangDetectException
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime

load_dotenv()

def detect_language(text):
    """Detectar idioma con PRIORIDAD para español y catalán"""
    try:
        text_lower = text.lower().strip()
        
        # PASO 1: Palabras españolas - MÁXIMA PRIORIDAD
        spanish_keywords = [
            'quiero', 'necesito', 'puedo', 'tengo', 'hoy', 'mañana',
            'por favor', 'gracias', 'buenos dias', 'buenas tardes',
            'mesa', 'personas', 'reserva', 'comida', 'cena',
            'estoy', 'está', 'somos', 'son', 'hacer',
            'noche', 'tarde', 'por', 'para', 'con', 'que', 'como',
            'cuando', 'donde', 'quien', 'cual', 'cuantos'
        ]
        
        if any(word in text_lower for word in spanish_keywords):
            return 'es'
        
        # PASO 2: Palabras catalanas
        catalan_keywords = [
            'vull', 'necessito', 'puc', 'tinc', 'avui', 'demà', 'sisplau', 
            'gràcies', 'bon dia', 'bona tarda', 'adéu', 'adeu', 'taula',
            'persones', 'reserva', 'dinar', 'sopar', 'només', 'també', 'però',
            'si us plau', 'moltes', 'estic', 'està', 'som', 'són',
            'quan', 'on', 'qui', 'qual', 'quants'
        ]
        
        if any(word in text_lower for word in catalan_keywords):
            return 'ca'
        
        # PASO 3: Palabras inglesas
        english_keywords = [
            'want', 'need', 'can', 'have', 'today', 'tomorrow',
            'please', 'thank you', 'table', 'people', 'reservation'
        ]
        
        if any(word in text_lower for word in english_keywords):
            return 'en'
        
        # PASO 4: Usar langdetect como último recurso
        detected = detect(text)
        
        # CORRECCIÓN: langdetect confunde idiomas
        if detected in ['tr', 'it', 'pt']:  # Turco, italiano, portugués → probablemente es español o catalán
            # Si tiene acentos españoles, es español
            if any(char in text for char in ['ó', 'í', 'á', 'é', 'ú', 'ñ']):
                return 'es'
            # Si tiene acentos catalanes, es catalán
            if any(char in text for char in ['à', 'è', 'ò', 'ç']):
                return 'ca'
            # Default español
            return 'es'
        
        return detected
        
    except LangDetectException:
        return 'es'  # Default castellano

def process_message_with_ai(message, phone, appointment_manager, conversation_manager):
    """Procesar mensaje con GPT-4 usando sistema de idioma inteligente"""
    
    print(f"📝 Missatge rebut: '{message}'")
    
    # PASO 1: Obtener idioma guardado del cliente
    saved_language = appointment_manager.get_customer_language(phone)
    
    # PASO 2: Contar mensajes del usuario
    message_count = conversation_manager.get_message_count(phone)
    
    # PASO 3: Decidir idioma según lógica
    if saved_language and saved_language not in ['tr', 'it', 'pt']:  # Ignorar falsos positivos
        # Cliente existente: usar idioma guardado
        language = saved_language
        print(f"🌍 Client conegut - Idioma: {language}")
    elif message_count == 0:
        # PRIMER MENSAJE: siempre español por defecto
        language = 'es'
        print(f"👋 Primer missatge → Default: {language}")
    else:
        # SEGUNDO MENSAJE o posteriores: detectar y GUARDAR definitivamente
        language = detect_language(message)
        # Validar que no sea un falso positivo
        if language in ['tr', 'it', 'pt']:
            language = 'es'  # Forzar español si hay confusión
        appointment_manager.save_customer_language(phone, language)
        print(f"🌍 Idioma guardado: {phone} → {language}")
        print(f"📝 Missatge {message_count + 1} → Detectat i guardat: {language}")
    
    print(f"✅ Idioma final: {language}")
    
    # Mapeo de idiomas
    language_names = {
        'es': 'español',
        'en': 'inglés',
        'ca': 'català',
        'fr': 'francés'
    }
    
    lang_name = language_names.get(language, 'español')
    
    # Verificar si el cliente ya existe
    customer_name = appointment_manager.get_customer_name(phone)
    
    # Obtener última reserva activa
    latest_appointment = appointment_manager.get_latest_appointment(phone)
    
    # Fecha actual
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    day_names = {
        'es': ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
        'ca': ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"],
        'en': ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    }
    day_name = day_names.get(language, day_names['es'])[today.weekday()]
    
    # Saludo personalizado SOLO si conocemos al cliente
    customer_context = ""
    if customer_name:
        greetings = {
            'ca': f"IMPORTANT: Aquest client ja és conegut. El seu nom és {customer_name}. Saluda'l sempre pel nom!",
            'en': f"IMPORTANT: This customer is known. Their name is {customer_name}. Always greet them by name!",
            'es': f"IMPORTANTE: Este cliente ya es conocido. Su nombre es {customer_name}. ¡Salúdalo siempre por su nombre!"
        }
        customer_context = greetings.get(language, greetings['es'])
    else:
        # NO CONOCEMOS AL CLIENTE - No usar nombre por defecto
        no_name_instructions = {
            'ca': "IMPORTANT: Aquest és un client NOU. NO tens el seu nom encara. NO l'hagis de dir cap nom genèric. Només saluda amb 'Hola!' sense cap nom fins que ell et digui el seu nom.",
            'en': "IMPORTANT: This is a NEW customer. You DON'T have their name yet. DO NOT use any generic name. Just say 'Hello!' without any name until they tell you their name.",
            'es': "IMPORTANTE: Este es un cliente NUEVO. NO tienes su nombre todavía. NO uses ningún nombre genérico. Solo saluda con '¡Hola!' sin ningún nombre hasta que te diga su nombre."
        }
        customer_context = no_name_instructions.get(language, no_name_instructions['es'])
    
    # Contexto de reserva activa
    appointment_context = ""
    if latest_appointment:
        apt_contexts = {
            'ca': f"\n\nRECORDA: Aquest usuari té una reserva activa:\n- ID: {latest_appointment['id']}\n- Data: {latest_appointment['date']}\n- Hora: {latest_appointment['time']}\n- Persones: {latest_appointment['num_people']}",
            'en': f"\n\nREMEMBER: This user has an active reservation:\n- ID: {latest_appointment['id']}\n- Date: {latest_appointment['date']}\n- Time: {latest_appointment['time']}\n- People: {latest_appointment['num_people']}",
            'es': f"\n\nRECUERDA: Este usuario tiene una reserva activa:\n- ID: {latest_appointment['id']}\n- Fecha: {latest_appointment['date']}\n- Hora: {latest_appointment['time']}\n- Personas: {latest_appointment['num_people']}"
        }
        appointment_context = apt_contexts.get(language, apt_contexts['es'])
    
    # System prompts por idioma
    system_prompts = {
        'ca': f"""Ets un assistent virtual per a reserves d'un restaurant. Respon SEMPRE en català.

DATA ACTUAL: Avui és {day_name} {today_str} (3 d'octubre de 2025).

{customer_context}{appointment_context}

INFORMACIÓ DEL RESTAURANT:
- Capacitat: 20 taules de 4 persones i 8 taules de 2 persones
- MÀXIM 4 persones per reserva
- Horaris:
  * Dinar: 12:00 a 14:30
  * Sopar: 19:00 a 22:00

PROCÉS DE RESERVA:
1. Saluda (si és client nou, NO diguis cap nom fins que ell et digui el seu)
2. Pregunta per quantes persones (màxim 4)
3. Pregunta quin dia
4. Pregunta quin horari i hora específica
5. Pregunta el nom (només si no el tens)
6. Confirma tots els detalls abans de crear

SÉ càlid, professional i proper.""",
        
        'es': f"""Eres un asistente virtual para reservas de un restaurante. Responde SIEMPRE en español.

FECHA ACTUAL: Hoy es {day_name} {today_str} (3 de octubre de 2025).

{customer_context}{appointment_context}

INFORMACIÓN DEL RESTAURANTE:
- Capacidad: 20 mesas de 4 personas y 8 mesas de 2 personas
- MÁXIMO 4 personas por reserva
- Horarios:
  * Comida: 12:00 a 14:30
  * Cena: 19:00 a 22:00

PROCESO DE RESERVA:
1. Saluda (si es cliente nuevo, NO digas ningún nombre hasta que él te diga el suyo)
2. Pregunta para cuántas personas (máximo 4)
3. Pregunta qué día
4. Pregunta qué horario y hora específica
5. Pregunta el nombre (solo si no lo tienes)
6. Confirma todos los detalles antes de crear

SÉ cálido, profesional y cercano.""",
        
        'en': f"""You are a virtual assistant for a restaurant reservations. Always respond in English.

CURRENT DATE: Today is {day_name} {today_str} (October 3, 2025).

{customer_context}{appointment_context}

RESTAURANT INFO:
- Capacity: 20 tables of 4 people and 8 tables of 2 people
- MAXIMUM 4 people per reservation
- Hours:
  * Lunch: 12:00 to 14:30
  * Dinner: 19:00 to 22:00

RESERVATION PROCESS:
1. Greet (if new customer, DON'T say any name until they tell you theirs)
2. Ask for how many people (maximum 4)
3. Ask which day
4. Ask which time slot and specific time
5. Ask for name (only if you don't have it)
6. Confirm all details before creating

BE warm, professional and friendly."""
    }
    
    system_prompt = system_prompts.get(language, system_prompts['es'])
    
    try:
        # Obtener historial
        history = conversation_manager.get_history(phone, limit=10)
        
        # Construir mensajes
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
                                "client_name": {"type": "string", "description": "Nombre del cliente"},
                                "date": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
                                "time": {"type": "string", "description": "Hora en formato HH:MM (24 horas)"},
                                "num_people": {"type": "integer", "description": "Número de personas (1-4)"}
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
                        "description": "Cancelar una reserva existente",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "appointment_id": {"type": "integer", "description": "ID de la reserva"}
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
                if num_people < 1 or num_people > 4:
                    error_msgs = {
                        'es': "Lo siento, solo aceptamos reservas de 1 a 4 personas.",
                        'ca': "Ho sento, només acceptem reserves d'1 a 4 persones.",
                        'en': "Sorry, we only accept reservations for 1 to 4 people."
                    }
                    return error_msgs.get(language, error_msgs['es'])
                
                # Guardar nombre del cliente
                appointment_manager.save_customer_info(phone, function_args.get('client_name'))
                
                # Crear la reserva
                result = appointment_manager.create_appointment(
                    phone=phone,
                    client_name=function_args.get('client_name'),
                    date=function_args.get('date'),
                    time=function_args.get('time'),
                    num_people=num_people,
                    duration_hours=1
                )
                
                if result:
                    table_info = result['table']
                    confirmations = {
                        'es': f"✅ ¡Reserva confirmada!\n\n👤 Nombre: {function_args['client_name']}\n👥 Personas: {num_people}\n📅 Fecha: {function_args['date']}\n🕐 Hora: {function_args['time']}\n🪑 Mesa: {table_info['number']} (capacidad {table_info['capacity']})\n\n¡Te esperamos!",
                        'ca': f"✅ Reserva confirmada!\n\n👤 Nom: {function_args['client_name']}\n👥 Persones: {num_people}\n📅 Data: {function_args['date']}\n🕐 Hora: {function_args['time']}\n🪑 Taula: {table_info['number']} (capacitat {table_info['capacity']})\n\nT'esperem!",
                        'en': f"✅ Reservation confirmed!\n\n👤 Name: {function_args['client_name']}\n👥 People: {num_people}\n📅 Date: {function_args['date']}\n🕐 Time: {function_args['time']}\n🪑 Table: {table_info['number']} (capacity {table_info['capacity']})\n\nSee you soon!"
                    }
                    assistant_reply = confirmations.get(language, confirmations['es'])
                    conversation_manager.clear_history(phone)
                else:
                    no_tables_msgs = {
                        'es': f"Lo siento, no hay mesas disponibles para {num_people} personas el {function_args['date']} a las {function_args['time']}. ¿Prefieres otro horario?",
                        'ca': f"Ho sento, no hi ha taules disponibles per a {num_people} persones el {function_args['date']} a les {function_args['time']}. Prefereixes un altre horari?",
                        'en': f"Sorry, no tables available for {num_people} people on {function_args['date']} at {function_args['time']}. Would you like another time?"
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
                    headers = {
                        'es': "Tus reservas:\n\n",
                        'en': "Your reservations:\n\n",
                        'ca': "Les teves reserves:\n\n"
                    }
                    assistant_reply = headers.get(language, headers['es'])
                    
                    for apt in appointments:
                        apt_id, name, date, start_time, end_time, num_people, table_num, capacity, status = apt
                        time_str = start_time.strftime("%H:%M")
                        assistant_reply += f"ID: {apt_id}\n• {date} - {time_str}\n  {num_people} persones - Mesa {table_num}\n  {name} - {status}\n\n"
            
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
                        'es': "❌ No se pudo cancelar la reserva.",
                        'ca': "❌ No s'ha pogut cancel·lar la reserva.",
                        'en': "❌ Could not cancel the reservation."
                    }
                    assistant_reply = error_msgs.get(language, error_msgs['es'])
        else:
            assistant_reply = message_response.content
        
        # Guardar en historial
        print(f"📝 DEBUG: Guardando en historial...")
        conversation_manager.save_message(phone, "user", message)
        conversation_manager.save_message(phone, "assistant", assistant_reply)
        print(f"📝 DEBUG: Historial guardado correctamente")
        
        return assistant_reply
    
    except Exception as e:
        print(f"❌ ERROR procesando con IA: {e}")
        import traceback
        traceback.print_exc()
        return "Lo siento, hubo un error. ¿Puedes intentar de nuevo?"
