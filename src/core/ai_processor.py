import os
import json
from langdetect import detect, LangDetectException
from dotenv import load_dotenv
from openai import OpenAI
import boto3
from datetime import datetime
import re
from unidecode import unidecode
from src.config.settings import (
    OPENAI_API_KEY, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, 
    AWS_SESSION_TOKEN, AWS_REGION, AI_PROVIDER
)
load_dotenv()

def detect_language(text):
    """
    Detecta l'idioma del text comptant coincidències amb keywords
    Retorna l'idioma amb més paraules úniques detectades
    """
    try:
        text_lower = text.lower().strip()
        text_noaccents = unidecode(text_lower)
        
        words = re.findall(r"\b\w+\b", text_noaccents)
        words_set = set(words)

        # Keywords espanyoles (sense paraules comunes amb català)
        spanish_keywords = {
            'quiero', 'necesito', 'puedo', 'tengo', 'hoy', 'manana',
            'por', 'favor', 'gracias', 'buenos', 'dias', 'buenas', 'tardes',
            'mesa', 'personas', 'comida', 'cena',
            'estoy', 'somos', 'son', 'hacer',
            'noche', 'tarde', 'para', 'con', 'que', 'como',
            'cuando', 'donde', 'quien', 'cual', 'cuantos'
        }
        
        # Keywords catalanes
        catalan_keywords = {
            'vull', 'necessito', 'puc', 'tinc', 'avui', 'dema', 'sisplau',
            'gracies', 'bon', 'dia', 'bona', 'tarda', 'adeu',
            'taula', 'persones', 'dinar', 'sopar',
            'nomes', 'tambe', 'pero', 'si', 'us', 'plau', 'moltes',
            'estic', 'som',
            'quan', 'on', 'qui', 'qual', 'quants', 'canviar', 'modificar',
            'dic', 'em', 'fer'
        }
        
        # Keywords angleses
        english_keywords = {
            'want', 'need', 'can', 'have', 'today', 'tomorrow',
            'please', 'thank', 'you', 'table', 'people', 'reservation',
            'hello', 'good', 'morning', 'evening',
            'how', 'when', 'where', 'who', 'what', 'many'
        }
        
        # Comptar coincidències
        spanish_matches = len(words_set & spanish_keywords)
        catalan_matches = len(words_set & catalan_keywords)
        english_matches = len(words_set & english_keywords)
        
        # Retornar idioma amb més coincidències
        if catalan_matches > spanish_matches and catalan_matches > english_matches:
            return 'ca'
        elif spanish_matches > english_matches:
            return 'es'
        elif english_matches > 0:
            return 'en'
        
        # Si no hi ha coincidències clares, usar langdetect
        detected = detect(text_lower)
        
        # Corregir falsos positius comuns
        if detected in ['cy', 'tr', 'it', 'pt']:
            return 'es'
        
        return detected
        
    except LangDetectException:
        return 'es'

def call_bedrock_claude(messages, tools):
    """
    Call AWS Bedrock Claude model with function calling
    """
    try:
        # Build client parameters
        client_params = {
            'service_name': 'bedrock-runtime',
            'region_name': AWS_REGION
        }
        
        # Add credentials if provided
        if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
            client_params['aws_access_key_id'] = AWS_ACCESS_KEY_ID
            client_params['aws_secret_access_key'] = AWS_SECRET_ACCESS_KEY
            
            # Add session token if provided (for temporary credentials)
            if AWS_SESSION_TOKEN:
                client_params['aws_session_token'] = AWS_SESSION_TOKEN
        
        bedrock = boto3.client(**client_params)
        
        # Convert OpenAI format to Claude format
        claude_messages = []
        system_message = ""
        
        for msg in messages:
            if msg['role'] == 'system':
                system_message = msg['content']
            else:
                claude_messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })
        
        # Convert tools to Claude format
        claude_tools = []
        for tool in tools:
            claude_tool = {
                "name": tool['function']['name'],
                "description": tool['function']['description']
            }
            # Only add input_schema if parameters exist
            if 'parameters' in tool['function']:
                claude_tool["input_schema"] = tool['function']['parameters']
            else:
                claude_tool["input_schema"] = {"type": "object", "properties": {}}
            
            claude_tools.append(claude_tool)
        
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "system": system_message,
            "messages": claude_messages,
            "tools": claude_tools
        }
        
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body=json.dumps(body)
        )
        
        result = json.loads(response['body'].read())
        
        # Convert Claude response to OpenAI format
        content = result['content'][0]
        
        if content['type'] == 'tool_use':
            return {
                'choices': [{
                    'message': {
                        'tool_calls': [{
                            'function': {
                                'name': content['name'],
                                'arguments': json.dumps(content['input'])
                            }
                        }]
                    }
                }]
            }
        else:
            return {
                'choices': [{
                    'message': {
                        'content': content['text'],
                        'tool_calls': None
                    }
                }]
            }
    
    except Exception as e:
        print(f"❌ Error calling Bedrock: {e}")
        print(f"📍 Region: {AWS_REGION}")
        print(f"📍 Model ID: anthropic.claude-3-sonnet-20240229-v1:0")
        print("Check AWS Bedrock Console for available models in your region")
        raise e

def process_message_with_ai(message, phone, appointment_manager, conversation_manager):
    """
    Processa el missatge de l'usuari amb GPT per gestionar reserves.
    """


    # IMPORTANT: Netejar prefixos del telèfon
    if phone.startswith('whatsapp:'):
        phone = phone.replace('whatsapp:', '')
    elif phone.startswith('telegram:'):
        phone = phone.replace('telegram:', '')
    
    print(f"📝 Missatge rebut: '{message}'")

    # --- STEP 1: Gestió de l'idioma ---
    saved_language = appointment_manager.get_customer_language(phone)
    message_count = conversation_manager.get_message_count(phone)

    if saved_language:
        language = saved_language
        print(f"🌍 Client conegut - Idioma mantingut: {language}")
    else:
        if message_count == 0:
            language = detect_language(message)
            appointment_manager.save_customer_language(phone, language)
            print(f"👋 Primer missatge → Idioma detectat i guardat: {language}")
        elif message_count == 1:
            new_language = detect_language(message)
            old_language = appointment_manager.get_customer_language(phone)
            if new_language != old_language:
                appointment_manager.save_customer_language(phone, new_language)
                language = new_language
                print(f"🔄 Segon missatge → idioma actualitzat: {old_language} → {new_language}")
            else:
                language = old_language
                print(f"✅ Segon missatge → idioma mantingut: {language}")
        else:
            language = appointment_manager.get_customer_language(phone)
            print(f"📌 Tercer missatge o més → idioma fix: {language}")

    print(f"✅ Idioma final: {language}")

    # --- STEP 2: Obtenir info del client i reserves ---
    customer_name = appointment_manager.get_customer_name(phone)
    latest_appointment = appointment_manager.get_latest_appointment(phone)

    # STEP 3: Preparar informació de data actual
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    day_names = {
        'es': ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
        'ca': ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"],
        'en': ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    }
    day_name = day_names.get(language, day_names['es'])[today.weekday()]

    # STEP 4: Construir context sobre el client
    customer_context = ""
    if customer_name:
        if language == 'ca':
            customer_context = f"IMPORTANT: Aquest client ja és conegut. El seu nom és {customer_name}. Saluda'l sempre pel nom!"
        elif language == 'en':
            customer_context = f"IMPORTANT: This customer is known. Their name is {customer_name}. Always greet them by name!"
        else:
            customer_context = f"IMPORTANTE: Este cliente ya es conocido. Su nombre es {customer_name}. ¡Salúdalo siempre por su nombre!"
    else:
        if language == 'ca':
            customer_context = "IMPORTANT: Aquest és un client NOU. NO tens el seu nom. Saluda amb 'Hola!' i pregunta educadament pel seu nom quan calgui fer la reserva."
        elif language == 'en':
            customer_context = "IMPORTANT: This is a NEW customer. You DON'T have their name. Say 'Hello!' and politely ask for their name when needed for the reservation."
        else:
            customer_context = "IMPORTANTE: Este es un cliente NUEVO. NO tienes su nombre. Saluda con '¡Hola!' y pide educadamente su nombre cuando sea necesario para la reserva."

    # STEP 5: Construir context sobre reserves actives
    appointment_context = ""
    if latest_appointment:
        apt_contexts = {
            'ca': f"\n\nINFO: Aquest usuari té una reserva recent:\n- ID: {latest_appointment['id']}\n- Data: {latest_appointment['date']}\n- Hora: {latest_appointment['time']}\n- Persones: {latest_appointment['num_people']}\n\nPOT FER MÉS RESERVES! Si vol fer una NOVA reserva, usa create_appointment. Si vol MODIFICAR aquesta reserva, usa update_appointment.",
            'en': f"\n\nINFO: This user has a recent reservation:\n- ID: {latest_appointment['id']}\n- Date: {latest_appointment['date']}\n- Time: {latest_appointment['time']}\n- People: {latest_appointment['num_people']}\n\nCAN MAKE MORE RESERVATIONS! If they want a NEW reservation, use create_appointment. If they want to MODIFY this one, use update_appointment.",
            'es': f"\n\nINFO: Este usuario tiene una reserva reciente:\n- ID: {latest_appointment['id']}\n- Fecha: {latest_appointment['date']}\n- Hora: {latest_appointment['time']}\n- Personas: {latest_appointment['num_people']}\n\n¡PUEDE HACER MÁS RESERVAS! Si quiere hacer una NUEVA reserva, usa create_appointment. Si quiere MODIFICAR esta reserva, usa update_appointment."
        }
        appointment_context = apt_contexts.get(language, apt_contexts['es'])
    
    # STEP 6: Construir system prompts per cada idioma
    system_prompts = {
        'ca': f"""Ets un gestor de reserves virtual del restaurant Amaru. Només pots respondre preguntes relacionades amb la teva funció de gestió de reserves.

DATA ACTUAL: Avui és {day_name} {today_str}.

{customer_context}{appointment_context}

INFORMACIÓ DEL RESTAURANT:
- Capacitat: 20 taules de 4 persones i 8 taules de 2 persones
- MÀXIM 4 persones per reserva
- Horaris:
  * Dinar: 12:00 a 15:00
  * Sopar: 19:00 a 22:30


FUNCIONS DISPONIBLES:

1. create_appointment – Crear reserva nova
2. update_appointment – Modificar reserva existent
3. list_appointments – Veure reserves de l’usuari
4. cancel_appointment – Cancel·lar reserva existent
5. save_customer_language – Guardar idioma i nom del client

PROCÉS DE RESERVA:

1. Saluda el client inicialment sense preguntar què vol. Respon només si proporciona informació addicional.
2. Detecta la intenció del client: reserva, modificació, cancel·lació o consulta.
3. Si vol fer una reserva:

   * Pregunta per la data, hora i número de persones.
   * Si ja saps el nom, confirma les dades i crida create_appointment.
   * Si no saps el nom, pregunta per ell. Guarda només noms vàlids i després confirma les dades amb create_appointment.
4. Si vol modificar una reserva: pregunta la nova data, hora i número de persones, confirma els detalls i crida update_appointment.
5. Si vol cancel·lar una reserva: mostra les reserves amb list_appointments, pregunta quina vol cancel·lar i crida cancel_appointment.
6. Si vol consultar informació sobre la seva reserva (hora, data, persones), mostra la informació de les reserves actives amb list_appointments.
7. Si demana canviar l’idioma, actualitza’l amb save_customer_language.






Sigues càlid, professional i proper.

IMPORTANT: No contestis mai temes no relacionats amb les reserves del restaurant.""",
        
        'es': f"""Eres un gestor de reservas virtual del restaurante Amaru. Solo puedes responder preguntas relacionadas con tu función de gestión de reservas.

FECHA ACTUAL: Hoy es {day_name} {today_str}.

{customer_context}{appointment_context}

INFORMACIÓN DEL RESTAURANTE:

* Capacidad: 20 mesas de 4 personas y 8 mesas de 2 personas
* MÁXIMO 4 personas por reserva
* Horarios:

  * Comida: 12:00 a 15:00
  * Cena: 19:00 a 22:30

FUNCIONES DISPONIBLES:

1. create_appointment – Crear nueva reserva
2. update_appointment – Modificar reserva existente
3. list_appointments – Ver reservas del usuario
4. cancel_appointment – Cancelar reserva existente
5. save_customer_language – Guardar idioma y nombre del cliente

PROCESO DE RESERVA:

1. Saluda al cliente inicialmente sin preguntar qué quiere. Responde solo si proporciona información adicional.
2. Detecta la intención del cliente: reserva, modificación, cancelación o consulta.
3. Si quiere hacer una reserva:

   * Pregunta por la fecha, hora y número de personas.
   * Si ya sabes su nombre, confirma los datos y llama a create_appointment.
   * Si no sabes su nombre, pregúntalo. Guarda solo nombres válidos y después confirma los datos con create_appointment.
4. Si quiere modificar una reserva: pregunta la nueva fecha, hora y número de personas, confirma los detalles y llama a update_appointment.
5. Si quiere cancelar una reserva: muestra las reservas con list_appointments, pregunta cuál desea cancelar y llama a cancel_appointment.
6. Si quiere consultar información sobre sus reservas (hora, fecha, personas), muestra la información de las reservas activas con list_appointments.
7. Si pide cambiar el idioma, actualízalo con save_customer_language.

Sé cálido, profesional y cercano.

IMPORTANTE: No contestes nunca temas no relacionados con las reservas del restaurante.""",
        
        'en': f"""You are a virtual reservation manager for Amaru restaurant. You can only answer questions related to your reservation management function.

CURRENT DATE: Today is {day_name} {today_str}.

{customer_context}{appointment_context}

RESTAURANT INFORMATION:

* Capacity: 20 tables for 4 people and 8 tables for 2 people
* MAXIMUM 4 people per reservation
* Hours:

  * Lunch: 12:00 to 15:00
  * Dinner: 19:00 to 22:30

AVAILABLE FUNCTIONS:

1. create_appointment – Create a new reservation
2. update_appointment – Modify an existing reservation
3. list_appointments – View user reservations
4. cancel_appointment – Cancel an existing reservation
5. save_customer_language – Save the customer’s language and name

RESERVATION PROCESS:

1. Greet the customer initially without asking what they want. Only respond if they provide additional information.
2. Detect the customer’s intention: reservation, modification, cancellation, or inquiry.
3. If the customer wants to make a reservation:

   * Ask for the date, time, and number of people.
   * If you already know the customer’s name, confirm the details and call create_appointment.
   * If you don’t know the name, ask for it. Save only valid names and then confirm the details with create_appointment.
4. If the customer wants to modify a reservation: ask for the new date, time, and number of people, confirm the details, and call update_appointment.
5. If the customer wants to cancel a reservation: show the reservations with list_appointments, ask which one they want to cancel, and call cancel_appointment.
6. If the customer asks for details about their reservation (time, date, people), show their active reservations with list_appointments.
7. If the customer asks to change the language, update it using save_customer_language.

Be warm, professional, and friendly.

IMPORTANT: Never answer topics unrelated to restaurant reservations."""
}
    
    system_prompt = system_prompts.get(language, system_prompts['es'])
    
    try:
        history = conversation_manager.get_history(phone, limit=10)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "create_appointment",
                    "description": "Crear una reserva nova quan tinguis TOTES les dades necessaris",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "client_name": {"type": "string", "description": "Nom del client"},
                            "date": {"type": "string", "description": "Data en format YYYY-MM-DD"},
                            "time": {"type": "string", "description": "Hora en format HH:MM (24 hores)"},
                            "num_people": {"type": "integer", "description": "Número de persones (1-4)"}
                        },
                        "required": ["client_name", "date", "time", "num_people"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_appointment",
                    "description": "Modificar/actualitzar una reserva existent sense cancel·lar-la",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "appointment_id": {"type": "integer", "description": "ID de la reserva a modificar"},
                            "new_date": {"type": "string", "description": "Nova data (YYYY-MM-DD) o null si no canvia"},
                            "new_time": {"type": "string", "description": "Nova hora (HH:MM) o null si no canvia"},
                            "new_num_people": {"type": "integer", "description": "Nou número de persones o null si no canvia"}
                        },
                        "required": ["appointment_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_appointments",
                    "description": "Llistar les reserves de l'usuari"
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "cancel_appointment",
                    "description": "Cancel·lar una reserva existent",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "appointment_id": {"type": "integer", "description": "ID de la reserva"}
                        },
                        "required": ["appointment_id"]
                    }
                }
            }
        ]
        
        # Choose AI provider
        if AI_PROVIDER == 'bedrock':
            response = call_bedrock_claude(messages, tools)
            message_response = response['choices'][0]['message']
        else:
            client = OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=tools
            )
            message_response = response.choices[0].message
        assistant_reply = ""
        
        # Handle tool calls for both providers
        tool_calls = None
        if AI_PROVIDER == 'bedrock':
            tool_calls = message_response.get('tool_calls')
        else:
            tool_calls = message_response.tool_calls
            
        if tool_calls:
            if AI_PROVIDER == 'bedrock':
                tool_call = tool_calls[0]
                function_name = tool_call['function']['name']
                function_args = json.loads(tool_call['function']['arguments'])
            else:
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
                
                # IMPORTANT: Guardar nom del client
                appointment_manager.save_customer_info(phone, function_args.get('client_name'))
                
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
                    
                    # Missatges segons idioma amb pregunta per notes
                    if language == 'ca':
                        confirmation = f"✅ Reserva confirmada!\n\n👤 Nom: {function_args['client_name']}\n👥 Persones: {num_people}\n📅 Data: {function_args['date']}\n🕐 Hora: {function_args['time']}\n🪑 Taula: {table_info['number']} (capacitat {table_info['capacity']})\n\nT'esperem!\n\n📝 Tens alguna observació especial? (trona, al·lèrgies, preferències...)"
                    elif language == 'en':
                        confirmation = f"✅ Reservation confirmed!\n\n👤 Name: {function_args['client_name']}\n👥 People: {num_people}\n📅 Date: {function_args['date']}\n🕐 Time: {function_args['time']}\n🪑 Table: {table_info['number']} (capacity {table_info['capacity']})\n\nSee you soon!\n\n📝 Any special requests? (high chair, allergies, preferences...)"
                    else:
                        confirmation = f"✅ ¡Reserva confirmada!\n\n👤 Nombre: {function_args['client_name']}\n👥 Personas: {num_people}\n📅 Fecha: {function_args['date']}\n🕐 Hora: {function_args['time']}\n🪑 Mesa: {table_info['number']} (capacidad {table_info['capacity']})\n\n¡Te esperamos!\n\n📝 ¿Alguna observación especial? (trona, alergias, preferencias...)"
                    
                    assistant_reply = confirmation
                    
                    # Guardar ID de la reserva creada per afegir notes després
                    conversation_manager.save_message(phone, "system", f"LAST_APPOINTMENT_ID:{result['id']}")
                    # No netejar historial perè poden afegir notes
                else:
                    no_tables_msgs = {
                        'es': f"Lo siento, no hay mesas disponibles para {num_people} personas el {function_args['date']} a las {function_args['time']}. ¿Prefieres otro horario?",
                        'ca': f"Ho sento, no hi ha taules disponibles per a {num_people} persones el {function_args['date']} a les {function_args['time']}. Prefereixes un altre horari?",
                        'en': f"Sorry, no tables available for {num_people} people on {function_args['date']} at {function_args['time']}. Would you like another time?"
                    }
                    assistant_reply = no_tables_msgs.get(language, no_tables_msgs['es'])
            
            elif function_name == "update_appointment":
                apt_id = function_args.get('appointment_id')
                new_date = function_args.get('new_date')
                new_time = function_args.get('new_time')
                new_num_people = function_args.get('new_num_people')
                
                result = appointment_manager.update_appointment(
                    phone=phone,
                    appointment_id=apt_id,
                    new_date=new_date,
                    new_time=new_time,
                    new_num_people=new_num_people
                )
                
                if result:
                    table_info = result['table']
                    update_msgs = {
                        'es': f"✅ ¡Reserva actualizada!\n\n📅 Nueva fecha: {result['start'].strftime('%Y-%m-%d')}\n🕐 Nueva hora: {result['start'].strftime('%H:%M')}\n👥 Personas: {new_num_people if new_num_people else 'sin cambios'}\n🪑 Mesa: {table_info['number']}\n\n¡Te esperamos!",
                        'ca': f"✅ Reserva actualitzada!\n\n📅 Nova data: {result['start'].strftime('%Y-%m-%d')}\n🕐 Nova hora: {result['start'].strftime('%H:%M')}\n👥 Persones: {new_num_people if new_num_people else 'sense canvis'}\n🪑 Taula: {table_info['number']}\n\nT'esperem!",
                        'en': f"✅ Reservation updated!\n\n📅 New date: {result['start'].strftime('%Y-%m-%d')}\n🕐 New time: {result['start'].strftime('%H:%M')}\n👥 People: {new_num_people if new_num_people else 'no change'}\n🪑 Table: {table_info['number']}\n\nSee you soon!"
                    }
                    assistant_reply = update_msgs.get(language, update_msgs['es'])
                else:
                    error_msgs = {
                        'es': "Lo siento, no se pudo actualizar la reserva. Puede que no haya mesas disponibles en ese horario.",
                        'ca': "Ho sento, no s'ha pogut actualitzar la reserva. Pot ser que no hi hagi taules disponibles en aquest horari.",
                        'en': "Sorry, couldn't update the reservation. There might not be tables available at that time."
                    }
                    assistant_reply = error_msgs.get(language, error_msgs['es'])
            
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
            if AI_PROVIDER == 'bedrock':
                assistant_reply = message_response.get('content', '')
            else:
                assistant_reply = message_response.content
        
        print(f"📝 DEBUG: Guardando en historial...")
        
        # STEP 7: Detectar si l'usuari està responent amb notes després de confirmar reserva
        if history:
            for msg in reversed(history):
                if msg['role'] == 'system' and msg['content'].startswith('LAST_APPOINTMENT_ID:'):
                    # L'usuari ha confirmat una reserva recentment i ara respon
                    appointment_id = int(msg['content'].split(':')[1])
                    
                    # Si el missatge sembla una resposta negativa
                    negative_keywords = ['no', 'cap', 'ninguna', 'res', 'nada', 'nothing', 'none']
                    if any(word in message.lower() for word in negative_keywords) and len(message.split()) <= 3:
                        # conversation_manager.clear_history(phone)  # SILENCIAT
                        thanks_msgs = {
                            'ca': '✅ Perfecte! Ens veiem aviat!',
                            'es': '✅ ¡Perfecto! ¡Nos vemos pronto!',
                            'en': '✅ Perfect! See you soon!'
                        }
                        assistant_reply = thanks_msgs.get(language, thanks_msgs['es'])
                        # Guardar missatges abans de retornar
                        conversation_manager.save_message(phone, "user", message)
                        conversation_manager.save_message(phone, "assistant", assistant_reply)
                        return assistant_reply
                    
                    # Afegir les notes a la reserva
                    success = appointment_manager.add_notes_to_appointment(phone, appointment_id, message)
                    
                    if success:
                        # conversation_manager.clear_history(phone)  # SILENCIAT
                        success_msgs = {
                            'ca': f'✅ Notes afegides: "{message}"\n\nGràcies! Ens veiem aviat!',
                            'es': f'✅ Observación añadida: "{message}"\n\n¡Gracias! ¡Nos vemos pronto!',
                            'en': f'✅ Note added: "{message}"\n\nThank you! See you soon!'
                        }
                        assistant_reply = success_msgs.get(language, success_msgs['es'])
                        # Guardar missatges abans de retornar
                        conversation_manager.save_message(phone, "user", message)
                        conversation_manager.save_message(phone, "assistant", assistant_reply)
                        return assistant_reply
                    
                    break
        
        conversation_manager.save_message(phone, "user", message)
        conversation_manager.save_message(phone, "assistant", assistant_reply)
        print(f"📝 DEBUG: Historial guardado correctamente")
        
        return assistant_reply
    
    except Exception as e:
        print(f"❌ ERROR procesando con IA: {e}")
        import traceback
        traceback.print_exc()
        return "Lo siento, hubo un error. ¿Puedes intentar de nuevo?"
