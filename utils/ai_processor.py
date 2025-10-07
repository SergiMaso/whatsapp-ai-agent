import os
import json
from langdetect import detect, LangDetectException
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime
import re
from unidecode import unidecode

load_dotenv()



def detect_language(text):
    """
    Detecta l'idioma del text amb prioritat per espanyol i català
    
    Ordre de prioritat:
    1. Paraules clau espanyoles
    2. Paraules clau catalanes
    3. Paraules clau angleses
    4. Llibreria langdetect (últim recurs)
    """
    try:
        text_lower = text.lower().strip()
        text_noaccents = unidecode(text_lower)
        
        words = re.findall(r"\b\w+\b", text_noaccents)
        words_set = set(words)

        # PRIORITAT 1: Paraules espanyoles
        spanish_keywords = {
            'quiero', 'necesito', 'puedo', 'tengo', 'hoy', 'manana',
            'por', 'favor', 'gracias', 'buenos', 'dias', 'buenas', 'tardes',
            'mesa', 'personas', 'comida', 'cena','quisiera',
            'estoy', 'esta', 'somos', 'son', 'hacer',
            'noche', 'tarde', 'para', 'con', 'que', 'como',
            'cuando', 'donde', 'quien', 'cual', 'cuantos'
        }
        if words_set & spanish_keywords:
            return 'es'
        
        # PRIORITAT 2: Paraules catalanes
        catalan_keywords = {
            'vull', 'necessito', 'puc', 'tinc', 'avui', 'dema', 'sisplau',
            'gracies', 'bon', 'dia', 'bona', 'tarda', 'adeu',
            'taula', 'persones', 'dinar', 'sopar',
            'nomes', 'tambe', 'pero', 'us', 'plau', 'moltes',
            'estic', 'esta', 'som', 'son','fer','voldria',
            'quan', 'on', 'qui', 'qual', 'quants', 'canviar', 'modificar'
        }
        if words_set & catalan_keywords:
            return 'ca'
        
        # PRIORITAT 3: Paraules angleses
        english_keywords = {
            'want', 'need', 'can', 'have', 'today', 'tomorrow',
            'please', 'thank', 'you', 'table', 'people', 'reservation',
            'hello', 'good', 'morning', 'evening',
            'how', 'when', 'where', 'who', 'what', 'many'
        }
        if words_set & english_keywords:
            return 'en'
        
        # PRIORITAT 4: Usar langdetect com a últim recurs
        detected = detect(text_lower)
        
        return detected
        
    except LangDetectException:
        return 'es'


def process_message_with_ai(message, phone, appointment_manager, conversation_manager):
    """
    Processa el missatge de l'usuari amb GPT per gestionar reserves.

    Gestió de l'idioma:
    - Si el client ja existeix → mantenir sempre el seu idioma.
    - Si és un client nou:
        1r missatge → detectar idioma i guardar-lo.
        2n missatge → tornar a detectar; si ha canviat, actualitzar.
        3r missatge i següents → no cal detectar més, es manté el guardat.
    """

    print(f"📝 Missatge rebut: '{message}'")

    # --- STEP 1: Gestió de l'idioma ---
    saved_language = appointment_manager.get_customer_language(phone)
    message_count = conversation_manager.get_message_count(phone)

    if saved_language:
        # Client conegut → sempre manté el mateix idioma
        language = saved_language
        print(f"🌍 Client conegut - Idioma mantingut: {language}")
    else:
        # Client nou → depèn del nombre de missatges
        if message_count == 0:
            # Primer missatge → detectar i guardar
            language = detect_language(message)
            appointment_manager.save_customer_language(phone, language)
            print(f"👋 Primer missatge → Idioma detectat i guardat: {language}")
        elif message_count == 1:
            # Segon missatge → detectar novament i actualitzar si canvia
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
            # Tercer missatge o més → no es torna a detectar
            language = appointment_manager.get_customer_language(phone)
            print(f"📌 Tercer missatge o més → idioma fix: {language}")

    language_names = { 'es': 'español', 'en': 'inglés', 'ca': 'català', 'fr': 'francés' } 
    lang_name = language_names.get(language, 'español')
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
        elif language == 'fr':
            customer_context = f"IMPORTANT: Ce client est déjà connu. Son nom est {customer_name}. Saluez-le toujours par son nom!"
        else:
            customer_context = f"IMPORTANTE: Este cliente ya es conocido. Su nombre es {customer_name}. ¡Salúdalo siempre por su nombre!"
    else:
        if language == 'ca':
            customer_context = "IMPORTANT: Aquest és un client NOU. Només saluda amb 'Hola!' fins que et digui el seu nom."
        elif language == 'en':
            customer_context = "IMPORTANT: This is a NEW customer. Just say 'Hello!' until they tell you their name."
        elif language == 'fr':
            customer_context = "IMPORTANT: C'est un NOUVEAU client. Dites simplement 'Bonjour!' jusqu'à ce qu'il vous le donne."
        else:
            customer_context = "IMPORTANTE: Este es un cliente NUEVO. Solo saluda con '¡Hola!' hasta que te diga su nombre."

    # STEP 5: Construir context sobre reserves actives
    appointment_context = ""
    if latest_appointment:
        apt_contexts = {
            'ca': f"\n\nRECORDA: Aquest usuari té una reserva activa:\n- ID: {latest_appointment['id']}\n- Data: {latest_appointment['date']}\n- Hora: {latest_appointment['time']}\n- Persones: {latest_appointment['num_people']}\n\nSi demana canviar/modificar la reserva, usa update_appointment amb aquest ID.",
            'en': f"\n\nREMEMBER: This user has an active reservation:\n- ID: {latest_appointment['id']}\n- Date: {latest_appointment['date']}\n- Time: {latest_appointment['time']}\n- People: {latest_appointment['num_people']}\n\nIf they ask to change/modify, use update_appointment with this ID.",
            'es': f"\n\nRECUERDA: Este usuario tiene una reserva activa:\n- ID: {latest_appointment['id']}\n- Fecha: {latest_appointment['date']}\n- Hora: {latest_appointment['time']}\n- Personas: {latest_appointment['num_people']}\n\nSi pide cambiar/modificar, usa update_appointment con este ID."
        }
        appointment_context = apt_contexts.get(language, apt_contexts['es'])
    
    # STEP 6: Construir system prompts per cada idioma

    system_prompts = {
        'ca': f"""Ets un ASSISTENT VIRTUAL per a la gestió de RESERVES d’un restaurant.

    INSTRUCCIONS GENERALS:
    - Has d’actuar com un assistent humà, amable, educat i eficient.
    - Comunica’t SEMPRE en el mateix idioma que el client.
    - Si el client és nou, NO diguis cap nom fins que ell te’l proporcioni.
    - Si el client ja és conegut, saluda’l pel seu nom.
    - Mantén un to càlid, professional i proper.
    - No facis accions fins que tinguis totes les dades necessàries (persones, data, hora, nom).

    DATA ACTUAL: Avui és {day_name} {today_str}.

    {customer_context}{appointment_context}

    INFORMACIÓ DEL RESTAURANT:
    - Capacitat total: 20 taules de 4 persones i 8 taules de 2 persones.
    - Màxim: 4 persones per reserva.
    - Horaris disponibles:
    * Dinar: de 12:00 a 15:00
    * Sopar: de 19:00 a 22:30

    FUNCIONS DISPONIBLES (pots cridar aquestes funcions quan sigui necessari):
    1. create_appointment – Crear una nova reserva.
    2. update_appointment – Modificar una reserva existent (NO cancel·lar).
    3. list_appointments – Mostrar reserves actuals.
    4. cancel_appointment – Cancel·lar una reserva.

    PROCÉS RECOMANAT DE RESERVA:
    1. Saluda el client.
    2. Pregunta per a quantes persones és la reserva (màxim 4).
    3. Pregunta quin dia vol venir.
    4. Pregunta per l’horari (dinar o sopar) i l’hora exacta.
    5. Si no tens el seu nom, demana’l.
    6. Confirma TOTS els detalls abans de crear la reserva.
    7. Si el client vol modificar una reserva existent, utilitza update_appointment amb l’ID corresponent (no cal cancel·lar-la primer).

    IMPORTANT:
    - NO inventis informació.
    - NO assumeixis dades que el client no hagi confirmat.
    - Si no entens alguna cosa, demana aclariments.

    SÉ natural, atent i útil en tot moment.""",

        'es': f"""Eres un ASISTENTE VIRTUAL para la gestión de RESERVAS de un restaurante.

    INSTRUCCIONES GENERALES:
    - Actúa como un asistente humano, amable, educado y eficiente.
    - Comunícate SIEMPRE en el mismo idioma que el cliente.
    - Si el cliente es nuevo, NO digas ningún nombre hasta que te lo diga.
    - Si el cliente ya es conocido, salúdalo por su nombre.
    - Mantén un tono cálido, profesional y cercano.
    - No ejecutes acciones hasta tener todos los datos necesarios (personas, fecha, hora, nombre).

    FECHA ACTUAL: Hoy es {day_name} {today_str}.

    {customer_context}{appointment_context}

    INFORMACIÓN DEL RESTAURANTE:
    - Capacidad total: 20 mesas de 4 personas y 8 mesas de 2 personas.
    - Máximo: 4 personas por reserva.
    - Horarios:
    * Comida: 12:00 a 15:00
    * Cena: 19:00 a 22:30

    FUNCIONES DISPONIBLES:
    1. create_appointment – Crear nueva reserva.
    2. update_appointment – Modificar reserva existente (NO cancelar).
    3. list_appointments – Ver reservas.
    4. cancel_appointment – Cancelar reserva.

    PROCESO RECOMENDADO:
    1. Saluda al cliente.
    2. Pregunta para cuántas personas (máximo 4).
    3. Pregunta qué día.
    4. Pregunta qué horario (comida o cena) y hora específica.
    5. Si no tienes su nombre, pídeselo.
    6. Confirma todos los detalles antes de crear la reserva.
    7. Si el cliente quiere modificar una reserva, usa update_appointment (no hace falta cancelar primero).

    IMPORTANTE:
    - NO inventes información.
    - NO asumas datos no confirmados.
    - Si no entiendes algo, pide aclaración.

    SÉ cálido, profesional y cercano.""",

        'en': f"""You are a VIRTUAL ASSISTANT for managing RESTAURANT RESERVATIONS.

    GENERAL INSTRUCTIONS:
    - Act as a polite, friendly, and efficient human assistant.
    - ALWAYS reply in the same language as the customer.
    - If the customer is new, DO NOT say any name until they give you theirs.
    - If the customer is known, greet them by name.
    - Maintain a warm, professional, and natural tone.
    - Do not execute actions until all details are confirmed (people, date, time, name).

    CURRENT DATE: Today is {day_name} {today_str}.

    {customer_context}{appointment_context}

    RESTAURANT INFORMATION:
    - Total capacity: 20 tables of 4 people and 8 tables of 2 people.
    - Maximum 4 people per reservation.
    - Opening hours:
    * Lunch: 12:00 to 15:00
    * Dinner: 19:00 to 22:30

    AVAILABLE FUNCTIONS:
    1. create_appointment – Create a new reservation.
    2. update_appointment – Modify an existing reservation (DO NOT cancel).
    3. list_appointments – View existing reservations.
    4. cancel_appointment – Cancel a reservation.

    RECOMMENDED RESERVATION FLOW:
    1. Greet the customer.
    2. Ask for the number of people (maximum 4).
    3. Ask for the day.
    4. Ask for the time slot (lunch or dinner) and exact time.
    5. Ask for the name (if not already known).
    6. Confirm ALL details before creating the reservation.
    7. If the customer wants to modify a booking, use update_appointment with the reservation ID (no need to cancel first).

    IMPORTANT:
    - DO NOT invent or assume any information.
    - Ask for clarification if needed.

    BE warm, professional, and friendly at all times."""
    }

    
    system_prompt = system_prompts.get(language, system_prompts['es'])
    
    try:
        history = conversation_manager.get_history(phone, limit=10)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # FIX: Canviar model i eliminar temperature
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "create_appointment",
                        "description": "Crear una reserva nova quan tinguis TOTS els datos necessaris",
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
        )
        
        message_response = response.choices[0].message
        assistant_reply = ""
        
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
            assistant_reply = message_response.content
        
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
