import os
import json
from langdetect import detect, LangDetectException
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime

load_dotenv()

def detect_language(text):
    """Detectar el idioma del texto con PRIORIDAD para catalán"""
    try:
        # PASO 1: Palabras clave catalanas - MÁXIMA PRIORIDAD
        catalan_keywords = [
            'vull', 'necessito', 'puc', 'tinc', 'avui', 'demà', 'sisplau', 
            'gràcies', 'bon dia', 'bona tarda', 'adéu', 'adeu', 'taula',
            'persones', 'reserva', 'dinar', 'sopar', 'canvi', 'modificar',
            'només', 'nomes', 'també', 'tambe', 'però', 'pero', 'si us plau',
            'moltes', 'gracies', 'perdona', 'disculpa', 'ara', 'fet',
            'estic', 'està', 'esta', 'som', 'sou', 'són', 'son',
            'mira', 'ves', 'anem', 'fem', 'farem', 'podries', 'pots'
        ]
        
        text_lower = text.lower()
        
        # Si contiene palabras catalanas, ES CATALÁN
        if any(word in text_lower for word in catalan_keywords):
            return 'ca'
        
        # PASO 2: Palabras españolas
        spanish_keywords = [
            'quiero', 'necesito', 'puedo', 'tengo', 'hoy', 'mañana',
            'por favor', 'gracias', 'buenos dias', 'buenas tardes',
            'mesa', 'personas', 'reserva', 'comida', 'cena',
            'estoy', 'está', 'somos', 'sois', 'son'
        ]
        
        if any(word in text_lower for word in spanish_keywords):
            return 'es'
        
        # PASO 3: Palabras inglesas
        english_keywords = [
            'want', 'need', 'can', 'have', 'today', 'tomorrow',
            'please', 'thank you', 'good morning', 'good afternoon',
            'table', 'people', 'reservation', 'lunch', 'dinner'
        ]
        
        if any(word in text_lower for word in english_keywords):
            return 'en'
        
        # PASO 4: Usar langdetect solo si no hay keywords
        detected = detect(text)
        
        # CORRECCIÓN: langdetect a veces confunde catalán con turco
        if detected == 'tr':
            return 'ca'  # Probablemente es catalán
        
        return detected
        
    except LangDetectException:
        return 'es'  # Default castellano

def detect_language_change_request(text):
    """Detectar si el usuario quiere cambiar de idioma"""
    text_lower = text.lower()
    
    change_keywords = [
        'cambiar idioma', 'change language', 'canviar idioma',
        'hablar en', 'speak in', 'parlar en',
        'cambiar a', 'change to', 'canviar a',
        'responder en', 'respond in', 'respondre en'
    ]
    
    if any(keyword in text_lower for keyword in change_keywords):
        # Detectar idioma objetivo
        if 'español' in text_lower or 'castellano' in text_lower or 'spanish' in text_lower:
            return 'es'
        elif 'català' in text_lower or 'catalan' in text_lower or 'catalán' in text_lower:
            return 'ca'
        elif 'inglés' in text_lower or 'english' in text_lower or 'anglès' in text_lower:
            return 'en'
        elif 'français' in text_lower or 'francés' in text_lower or 'french' in text_lower:
            return 'fr'
    
    return None

def process_message_with_ai(message, phone, appointment_manager, conversation_manager):
    """
    Procesar mensaje con GPT-4 usando sistema de idioma inteligente
    """
    
    print(f"📝 Missatge rebut: '{message}'")
    
    # PASO 1: Verificar si quiere cambiar idioma
    language_change = detect_language_change_request(message)
    if language_change:
        appointment_manager.save_customer_language(phone, language_change)
        print(f"🔄 Canvi d'idioma: {language_change}")
        
        change_msgs = {
            'es': "✅ Perfecto, ahora te responderé en español.",
            'ca': "✅ Perfecte, ara et respondré en català.",
            'en': "✅ Perfect, I'll now respond in English.",
            'fr': "✅ Parfait, je vais maintenant répondre en français."
        }
        return change_msgs.get(language_change, change_msgs['es'])
    
    # PASO 2: Obtener idioma guardado del cliente
    saved_language = appointment_manager.get_customer_language(phone)
    
    # PASO 3: Contar mensajes del usuario
    message_count = conversation_manager.get_message_count(phone)
    
    # PASO 4: Decidir idioma según lógica
    if saved_language and saved_language != 'tr':  # Ignorar si es 'tr' (error)
        # Cliente existente: usar idioma guardado
        language = saved_language
        print(f"🌍 Client conegut - Idioma: {language}")
    elif message_count == 0:
        # PRIMER MENSAJE: si es solo "hola" → castellano default
        if message.lower().strip() in ['hola', 'hello', 'hi', 'hey', 'bon dia', 'bona tarda']:
            language = 'es'
            print(f"👋 Primer missatge genèric → Default: {language}")
        else:
            # Primer mensaje con contenido → detectar y guardar
            language = detect_language(message)
            appointment_manager.save_customer_language(phone, language)
            print(f"🆕 Primer missatge → Detectat i guardat: {language}")
    else:
        # SEGUNDO MENSAJE o posteriores: detectar y guardar
        language = detect_language(message)
        appointment_manager.save_customer_language(phone, language)
        print(f"📝 Missatge {message_count + 1} → Detectat i guardat: {language}")
    
    print(f"✅ Idioma final: {language}")
    
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
    
    # Obtener última reserva activa
    latest_appointment = appointment_manager.get_latest_appointment(phone)
    
    # Fecha actual para contexto
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    day_name_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][today.weekday()]
    day_name_ca = ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"][today.weekday()]
    day_name_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][today.weekday()]
    
    if language == 'ca':
        day_name = day_name_ca
    elif language == 'en':
        day_name = day_name_en
    else:
        day_name = day_name_es
    
    # Saludo personalizado si conocemos al cliente
    customer_context = ""
    if customer_name:
        if language == 'ca':
            customer_context = f"IMPORTANT: Aquest client ja és conegut. El seu nom és {customer_name}. Saluda'l pel nom sempre!"
        elif language == 'en':
            customer_context = f"IMPORTANT: This customer is already known. Their name is {customer_name}. Always greet them by name!"
        else:
            customer_context = f"IMPORTANTE: Este cliente ya es conocido. Su nombre es {customer_name}. ¡Salúdalo por su nombre siempre!"
    
    # Contexto de reserva activa
    appointment_context = ""
    if latest_appointment:
        if language == 'ca':
            appointment_context = f"\n\nRECORDA: Aquest usuari té una reserva activa:\n- ID: {latest_appointment['id']}\n- Data: {latest_appointment['date']}\n- Hora: {latest_appointment['time']}\n- Persones: {latest_appointment['num_people']}\n\nSi demana canviar/modificar la reserva, usa update_appointment amb aquest ID."
        elif language == 'en':
            appointment_context = f"\n\nREMEMBER: This user has an active reservation:\n- ID: {latest_appointment['id']}\n- Date: {latest_appointment['date']}\n- Time: {latest_appointment['time']}\n- People: {latest_appointment['num_people']}\n\nIf they ask to change/modify the reservation, use update_appointment with this ID."
        else:
            appointment_context = f"\n\nRECUERDA: Este usuario tiene una reserva activa:\n- ID: {latest_appointment['id']}\n- Fecha: {latest_appointment['date']}\n- Hora: {latest_appointment['time']}\n- Personas: {latest_appointment['num_people']}\n\nSi pide cambiar/modificar la reserva, usa update_appointment con este ID."
    
    # System prompt adaptado al idioma
    if language == 'ca':
        system_prompt = f"""Ets un assistent virtual per a reserves d'un restaurant. Respon SEMPRE en català.

DATA ACTUAL: Avui és {day_name} {today_str} (3 d'octubre de 2025).

{customer_context}{appointment_context}

INFORMACIÓ DEL RESTAURANT:
- Capacitat: 20 taules de 4 persones i 8 taules de 2 persones
- **MÀXIM 4 persones per reserva**
- Horaris: Dinar 12:00-14:30, Sopar 19:00-22:00

CAPACITATS:
1. Agendar reserves (nom, data, hora, persones 1-4)
2. Modificar reserves (update_appointment)
3. Consultar reserves
4. Cancel·lar reserves

PROCÉS DE RESERVA:
1. Saluda (si coneixes el client, pel nom)
2. Pregunta persones (1-4 MÀXIM, UNA SOLA VEGADA)
3. Pregunta dia
4. Pregunta hora
5. Pregunta nom (NOMÉS si no el tens)
6. Confirma i crea

MODIFICACIÓ:
- Si diu "canviar", "modificar" → usa update_appointment
- NO cancel·lis, només actualitza

INSTRUCCIONS:
- Mantén context
- Sigues càlid i proper
- NO repeteixis preguntes
- Usa les funcions quan tinguis totes les dades"""
    
    elif language == 'en':
        system_prompt = f"""You are a virtual assistant for restaurant reservations. Always respond in English.

CURRENT DATE: Today is {day_name} {today_str} (October 3rd, 2025).

{customer_context}{appointment_context}

RESTAURANT INFO:
- Capacity: 20 tables of 4 people and 8 tables of 2 people
- **MAXIMUM 4 people per reservation**
- Hours: Lunch 12:00-14:30, Dinner 19:00-22:00

CAPABILITIES:
1. Create reservations (name, date, time, people 1-4)
2. Modify reservations (update_appointment)
3. Check reservations
4. Cancel reservations

RESERVATION PROCESS:
1. Greet (if you know the customer, by name)
2. Ask for people (1-4 MAX, ONLY ONCE)
3. Ask for date
4. Ask for time
5. Ask for name (ONLY if you don't have it)
6. Confirm and create

MODIFICATION:
- If they say "change", "modify" → use update_appointment
- DON'T cancel, just update

INSTRUCTIONS:
- Keep context
- Be warm and friendly
- DON'T repeat questions
- Use functions when you have all data"""
    
    else:  # español
        system_prompt = f"""Eres un asistente virtual para reservas de un restaurante. Responde SIEMPRE en español.

FECHA ACTUAL: Hoy es {day_name} {today_str} (3 de octubre de 2025).

{customer_context}{appointment_context}

INFORMACIÓN DEL RESTAURANTE:
- Capacidad: 20 mesas de 4 personas y 8 mesas de 2 personas
- **MÁXIMO 4 personas por reserva**
- Horarios: Comida 12:00-14:30, Cena 19:00-22:00

CAPACIDADES:
1. Agendar reservas (nombre, fecha, hora, personas 1-4)
2. Modificar reservas (update_appointment)
3. Consultar reservas
4. Cancelar reservas

PROCESO DE RESERVA:
1. Saluda (si conoces al cliente, por su nombre)
2. Pregunta personas (1-4 MÁXIMO, UNA SOLA VEZ)
3. Pregunta día
4. Pregunta hora
5. Pregunta nombre (SOLO si no lo tienes)
6. Confirma y crea

MODIFICACIÓN:
- Si dice "cambiar", "modificar" → usa update_appointment
- NO canceles, solo actualiza

INSTRUCCIONES:
- Mantén contexto
- Sé cálido y cercano
- NO repitas preguntas
- Usa las funciones cuando tengas todos los datos"""

    try:
        # Obtener historial
        history = conversation_manager.get_history(phone, limit=10)
        
        # Construir mensajes
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        
        # Llamada a OpenAI
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=messages,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "create_appointment",
                        "description": "Crear una reserva NUEVA",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "client_name": {"type": "string"},
                                "date": {"type": "string"},
                                "time": {"type": "string"},
                                "num_people": {"type": "integer"}
                            },
                            "required": ["client_name", "date", "time", "num_people"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "update_appointment",
                        "description": "MODIFICAR reserva existente",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "appointment_id": {"type": "integer"},
                                "new_date": {"type": "string"},
                                "new_time": {"type": "string"},
                                "new_num_people": {"type": "integer"}
                            },
                            "required": ["appointment_id"]
                        }
                    }
                },
                {"type": "function", "function": {"name": "list_appointments"}},
                {
                    "type": "function",
                    "function": {
                        "name": "cancel_appointment",
                        "parameters": {
                            "type": "object",
                            "properties": {"appointment_id": {"type": "integer"}},
                            "required": ["appointment_id"]
                        }
                    }
                }
            ],
            temperature=0.7
        )
        
        message_response = response.choices[0].message
        assistant_reply = ""
        
        # Procesar funciones (código existente igual...)
        if message_response.tool_calls:
            tool_call = message_response.tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            if function_name == "create_appointment":
                num_people = function_args.get('num_people', 2)
                
                if num_people < 1 or num_people > 4:
                    error_msgs = {
                        'es': "Lo siento, solo aceptamos reservas de 1 a 4 personas.",
                        'ca': "Ho sento, només acceptem reserves d'1 a 4 persones.",
                        'en': "Sorry, we only accept reservations for 1 to 4 people."
                    }
                    return error_msgs.get(language, error_msgs['es'])
                
                try:
                    time_str = function_args.get('time')
                    if ':' in time_str:
                        hour, minute = time_str.split(':')
                        hour = int(hour)
                        minute = int(minute)
                        time_str = f"{hour:02d}:{minute:02d}"
                    
                    is_lunch = 12 <= hour < 15 or (hour == 14 and minute <= 30)
                    is_dinner = 19 <= hour < 23 or (hour == 22 and minute == 0)
                    
                    if not (is_lunch or is_dinner):
                        error_msgs = {
                            'es': "Lo siento, solo aceptamos reservas de 12:00-14:30 o 19:00-22:00.",
                            'ca': "Ho sento, només acceptem reserves de 12:00-14:30 o 19:00-22:00.",
                            'en': "Sorry, we only accept reservations from 12:00-14:30 or 19:00-22:00."
                        }
                        return error_msgs.get(language, error_msgs['es'])
                    
                    function_args['time'] = time_str
                except:
                    pass
                
                appointment_manager.save_customer_info(phone, function_args.get('client_name'), language)
                
                result = appointment_manager.create_appointment(
                    phone=phone,
                    client_name=function_args.get('client_name'),
                    date=function_args.get('date'),
                    time=function_args.get('time'),
                    num_people=num_people
                )
                
                if result:
                    table_info = result['table']
                    confirmations = {
                        'es': f"✅ ¡Reserva confirmada!\n\n👤 {function_args['client_name']}\n👥 {num_people} personas\n📅 {function_args['date']}\n🕐 {function_args['time']}\n🪑 Mesa {table_info['number']}\n\n¡Te esperamos!",
                        'ca': f"✅ Reserva confirmada!\n\n👤 {function_args['client_name']}\n👥 {num_people} persones\n📅 {function_args['date']}\n🕐 {function_args['time']}\n🪑 Taula {table_info['number']}\n\nT'esperem!",
                        'en': f"✅ Reservation confirmed!\n\n👤 {function_args['client_name']}\n👥 {num_people} people\n📅 {function_args['date']}\n🕐 {function_args['time']}\n🪑 Table {table_info['number']}\n\nSee you soon!"
                    }
                    
                    assistant_reply = confirmations.get(language, confirmations['es'])
                    conversation_manager.clear_history(phone)
                else:
                    no_tables_msgs = {
                        'es': f"Lo siento, no hay mesas disponibles.",
                        'ca': f"Ho sento, no hi ha taules disponibles.",
                        'en': f"Sorry, no tables available."
                    }
                    assistant_reply = no_tables_msgs.get(language, no_tables_msgs['es'])
            
            # Resto de funciones (update, list, cancel) igual...
            elif function_name == "update_appointment":
                # ... código existente ...
                pass
            elif function_name == "list_appointments":
                # ... código existente ...
                pass
            elif function_name == "cancel_appointment":
                # ... código existente ...
                pass
        
        else:
            assistant_reply = message_response.content
        
        # Guardar en historial
        conversation_manager.save_message(phone, "user", message)
        conversation_manager.save_message(phone, "assistant", assistant_reply)
        
        # Detectar reinicio
        restart_keywords = ["empezar de nuevo", "olvidar", "reiniciar", "start over", "començar de nou"]
        if any(word in message.lower() for word in restart_keywords):
            conversation_manager.clear_history(phone)
        
        return assistant_reply
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        error_msgs = {
            'es': "Lo siento, hubo un error.",
            'ca': "Ho sento, hi ha hagut un error.",
            'en': "Sorry, there was an error."
        }
        return error_msgs.get(language if 'language' in locals() else 'es', error_msgs['es'])
