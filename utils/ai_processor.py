import os
import json
from langdetect import detect, LangDetectException
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime, timedelta
import re
from unidecode import unidecode
from utils.appointments import AppointmentManager, ConversationManager
from utils.media_manager import MediaManager
load_dotenv()

# Cache d'idiomes en memòria per evitar canvis inesperats quan BD falla
LANGUAGE_CACHE = {}

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
    # PRIORITAT: Cache en memòria > Base de dades > Detecció automàtica
    cached_language = LANGUAGE_CACHE.get(phone)
    saved_language = None

    try:
        saved_language = appointment_manager.get_customer_language(phone)
    except Exception as e:
        print(f"⚠️ Error obtenint idioma de BD (usant cache): {e}")

    message_count = conversation_manager.get_message_count(phone)

    # Si hi ha idioma guardat en BD o cache, SEMPRE usar-lo (no canviar mai)
    if saved_language:
        language = saved_language
        LANGUAGE_CACHE[phone] = language  # Actualitzar cache
        print(f"🌍 Client conegut - Idioma mantingut: {language}")
    elif cached_language:
        language = cached_language
        print(f"💾 Idioma des de cache (BD no disponible): {language}")
    else:
        # Client nou: detectar idioma
        if message_count == 0:
            # Primer missatge: detectar però NO guardar encara
            language = detect_language(message)
            LANGUAGE_CACHE[phone] = language  # Guardar en cache
            print(f"👋 Primer missatge → Idioma detectat (temporal, no guardat): {language}")
        elif message_count == 1:
            # Segon missatge: ara sí que el guardem!
            new_language = detect_language(message)
            try:
                appointment_manager.save_customer_language(phone, new_language)
            except Exception as e:
                print(f"⚠️ Error guardant idioma a BD (mantingut en cache): {e}")
            LANGUAGE_CACHE[phone] = new_language  # Guardar en cache
            language = new_language
            print(f"🔄 Segon missatge → Idioma detectat i guardat: {new_language}")
        else:
            # A partir del tercer missatge: usar el que tinguem (cache o BD)
            language = LANGUAGE_CACHE.get(phone) or saved_language or 'es'
            print(f"📌 Tercer missatge o més → idioma: {language}")

    print(f"✅ Idioma final: {language}")

    # --- STEP 2: Obtenir historial ABANS de processar ---
    history = conversation_manager.get_history(phone, limit=10)
    print(f"📚 DEBUG: Historial obtingut ({len(history)} missatges)")
    for idx, msg in enumerate(history):
        print(f"   [{idx}] {msg['role']}: {msg['content'][:50]}...")
    
    # --- STEP 3: COMPROVAR ESTATS ABANS DE CRIDAR LA IA ---
    print(f"🔍 Comprovant estats actius...")
    
    state_found = False
    for msg in reversed(history):
        # === ESTAT 1: Esperant observacions ===
        if msg['role'] == 'system' and msg['content'].startswith('WAITING_NOTES:'):
            state_found = True
            appointment_id = int(msg['content'].split(':')[1])
            print(f"⏳ Estat actiu: WAITING_NOTES per reserva {appointment_id}")
            
            negative_keywords = ['no', 'cap', 'ninguna', 'res', 'nada', 'nothing', 'none']
            
            # Si respon negativament a observacions
            if any(word in message.lower() for word in negative_keywords) and len(message.split()) <= 3:
                print(f"❌ Resposta negativa detectada: '{message}'")
                # Passar a preguntar pel menú
                conversation_manager.save_message(phone, "system", f"WAITING_MENU:{appointment_id}")
                menu_msgs = {
                    'ca': '✅ Perfecte!\n\n📋 Vols que t\'enviï la carta o el menú del dia?',
                    'es': '✅ ¡Perfecto!\n\n📋 ¿Quieres que te envíe la carta o el menú del día?',
                    'en': '✅ Perfect!\n\n📋 Would you like me to send you the menu or today\'s specials?'
                }
                assistant_reply = menu_msgs.get(language, menu_msgs['es'])
            else:
                print(f"📝 Guardant notes: '{message}'")
                # Guardar notes i passar a preguntar pel menú
                success = appointment_manager.add_notes_to_appointment(phone, appointment_id, message)
                if success:
                    conversation_manager.save_message(phone, "system", f"WAITING_MENU:{appointment_id}")
                    menu_msgs = {
                        'ca': f'✅ Notes afegides: "{message}"\n\n📋 Vols que t\'enviï la carta o el menú del dia?',
                        'es': f'✅ Observación añadida: "{message}"\n\n📋 ¿Quieres que te envíe la carta o el menú del día?',
                        'en': f'✅ Note added: "{message}"\n\n📋 Would you like me to send you the menu or today\'s specials?'
                    }
                    assistant_reply = menu_msgs.get(language, menu_msgs['es'])
                else:
                    assistant_reply = "Error afegint notes."
            
            conversation_manager.save_message(phone, "user", message)
            conversation_manager.save_message(phone, "assistant", assistant_reply)
            print(f"✅ Resposta enviada (WAITING_NOTES): {assistant_reply[:50]}...")
            return assistant_reply
        
        # === ESTAT 2: Esperant resposta sobre menú ===
        elif msg['role'] == 'system' and msg['content'].startswith('WAITING_MENU:'):
            appointment_id = int(msg['content'].split(':')[1])
            print(f"⏳ Estat actiu: WAITING_MENU per reserva {appointment_id}")
            
            negative_keywords = ['no', 'cap', 'ninguna', 'res', 'nada', 'nothing', 'none']
            
            # Si respon negativament
            if any(word in message.lower() for word in negative_keywords) and len(message.split()) <= 3:
                print(f"❌ Resposta negativa detectada: '{message}'")
                thanks_msgs = {
                    'ca': '✅ Perfecte! Ens veiem aviat! 👋',
                    'es': '✅ ¡Perfecto! ¡Nos vemos pronto! 👋',
                    'en': '✅ Perfect! See you soon! 👋'
                }
                assistant_reply = thanks_msgs.get(language, thanks_msgs['es'])
                conversation_manager.save_message(phone, "user", message)
                conversation_manager.save_message(phone, "assistant", assistant_reply)
                print(f"✅ Resposta enviada (WAITING_MENU - NO): {assistant_reply}")
                return assistant_reply
            else:
                print(f"✅ Resposta afirmativa - La IA processarà la petició del menú")
                # Si respon afirmativament, sortir del bucle i deixar que la IA processi
                break
        
        # Continuar buscant estats en tot l'historial
        # (no fer break prematurament)
    
    print(f"✅ Cap estat actiu - Processant amb IA...")

    # --- STEP 4: Obtenir info del client i reserves ---
    customer_name = appointment_manager.get_customer_name(phone)
    latest_appointment = appointment_manager.get_latest_appointment(phone)

    # STEP 5: Preparar informació de data actual
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    day_names = {
        'es': ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
        'ca': ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"],
        'en': ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    }
    day_name = day_names.get(language, day_names['es'])[today.weekday()]

    # STEP 6: Construir context sobre el client
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

    # STEP 7: Construir context sobre reserves actives
    appointment_context = ""
    if latest_appointment:
        apt_contexts = {
            'ca': f"\n\nINFO: Aquest usuari té una reserva recent:\n- ID: {latest_appointment['id']}\n- Data: {latest_appointment['date']}\n- Hora: {latest_appointment['time']}\n- Persones: {latest_appointment['num_people']}\n\nPOT FER MÉS RESERVES! Si vol fer una NOVA reserva, usa create_appointment. Si vol MODIFICAR aquesta reserva, usa update_appointment.",
            'en': f"\n\nINFO: This user has a recent reservation:\n- ID: {latest_appointment['id']}\n- Date: {latest_appointment['date']}\n- Time: {latest_appointment['time']}\n- People: {latest_appointment['num_people']}\n\nCAN MAKE MORE RESERVATIONS! If they want a NEW reservation, use create_appointment. If they want to MODIFY this one, use update_appointment.",
            'es': f"\n\nINFO: Este usuario tiene una reserva reciente:\n- ID: {latest_appointment['id']}\n- Fecha: {latest_appointment['date']}\n- Hora: {latest_appointment['time']}\n- Personas: {latest_appointment['num_people']}\n\n¡PUEDE HACER MÁS RESERVAS! Si quiere hacer una NUEVA reserva, usa create_appointment. Si quiere MODIFICAR esta reserva, usa update_appointment."
        }
        appointment_context = apt_contexts.get(language, apt_contexts['es'])
    
    # STEP 8: Construir system prompts per cada idioma
    system_prompts = {
        'ca': f"""Ets un gestor de reserves virtual del restaurant Amaru. Només pots respondre preguntes relacionades amb la teva funció de gestió de reserves.

DATA ACTUAL: Avui és {day_name} {today_str}.

{customer_context}{appointment_context}

INFORMACIÓ DEL RESTAURANT:
- Capacitat: 12 taules de 4 persones i 5 taules de 2 persones
- MÀXIM 8 persones per reserva (el sistema combina taules automàticament si cal)
- Horaris:
  * Dinar: 12:00 a 15:00
  * Sopar: 19:00 a 22:30

FUNCIONS DISPONIBLES:
1. check_availability – Consultar disponibilitat per una data SENSE crear reserva (usa SEMPRE abans de create_appointment si el client pregunta per disponibilitat)
2. create_appointment – Crear reserva nova
3. update_appointment – Modificar reserva existent
4. list_appointments – Veure reserves de l'usuari
5. cancel_appointment – Cancel·lar reserva existent
6. get_menu – Enviar menú o carta del restaurant
7. save_customer_language – Guardar idioma i nom del client

IMPORTANT - COM INTERPRETAR HORES:
- "a les 8" / "a las 8" = 20:00 (sopar)
- "a les 2" / "a las 2" = 14:00 (dinar)
- "a les 1" / "a la 1" = 13:00 (dinar)
- "a les 9 del matí" = 09:00, "a les 9 del vespre" / "a les 9 de la nit" = 21:00
- Si diuen només un número (1-8) i s'està parlant de reserves, SEMPRE és l'hora, NO el nombre de persones
- El nombre de persones normalment es diu explícitament: "2 persones", "per a 4", "som 6"

WORKFLOW CRÍTIC:
- Si el client pregunta "quines hores tens?" o similars → Usa check_availability PRIMER
- Si el client diu "vull reserva per [data] a les [hora]" amb totes les dades → Usa create_appointment IMMEDIATAMENT sense preguntar res més
- NOMÉS pregunta les dades que falten. Si ja tens nom, data, hora i persones → Crea la reserva!

Sigues càlid, professional i proper.

IMPORTANT: No contestis mai temes no relacionats amb les reserves del restaurant.""",
        
        'es': f"""Eres un gestor de reservas virtual del restaurante Amaru. Solo puedes responder preguntas relacionadas con tu función de gestión de reservas.

FECHA ACTUAL: Hoy es {day_name} {today_str}.

{customer_context}{appointment_context}

INFORMACIÓN DEL RESTAURANTE:
- Capacidad: 12 mesas de 4 personas y 5 mesas de 2 personas
- MÁXIMO 8 personas por reserva (el sistema combina mesas automáticamente si es necesario)
- Horarios:
  * Comida: 12:00 a 15:00
  * Cena: 19:00 a 22:30

FUNCIONES DISPONIBLES:
1. check_availability – Consultar disponibilidad para una fecha SIN crear reserva (usa SIEMPRE antes de create_appointment si el cliente pregunta por disponibilidad)
2. create_appointment – Crear nueva reserva
3. update_appointment – Modificar reserva existente
4. list_appointments – Ver reservas del usuario
5. cancel_appointment – Cancelar reserva existente
6. get_menu – Enviar menú o carta del restaurante
7. save_customer_language – Guardar idioma y nombre del cliente

IMPORTANTE - CÓMO INTERPRETAR HORAS:
- "a las 8" / "a les 8" = 20:00 (cena)
- "a las 2" / "a les 2" = 14:00 (comida)
- "a la 1" / "a les 1" = 13:00 (comida)
- "a las 9 de la mañana" = 09:00, "a las 9 de la noche" = 21:00
- Si dicen solo un número (1-8) y se está hablando de reservas, SIEMPRE es la hora, NO el número de personas
- El número de personas normalmente se dice explícitamente: "2 personas", "para 4", "somos 6"

WORKFLOW CRÍTICO:
- Si el cliente pregunta "qué horas tienes?" o similares → Usa check_availability PRIMERO
- Si el cliente dice "quiero reserva para [fecha] a las [hora]" con todos los datos → Usa create_appointment INMEDIATAMENTE sin preguntar nada más
- SOLO pregunta los datos que faltan. Si ya tienes nombre, fecha, hora y personas → ¡Crea la reserva!

Sé cálido, profesional y cercano.

IMPORTANTE: No contestes nunca temas no relacionados con las reservas del restaurante.""",
        
        'en': f"""You are a virtual reservation manager for Amaru restaurant. You can only answer questions related to your reservation management function.

CURRENT DATE: Today is {day_name} {today_str}.

{customer_context}{appointment_context}

RESTAURANT INFORMATION:
- Capacity: 12 tables for 4 people and 5 tables for 2 people
- MAXIMUM 8 people per reservation (system automatically combines tables if needed)
- Hours:
  * Lunch: 12:00 to 15:00
  * Dinner: 19:00 to 22:30

AVAILABLE FUNCTIONS:
1. check_availability – Check availability for a date WITHOUT creating a reservation (ALWAYS use before create_appointment if client asks about availability)
2. create_appointment – Create a new reservation
3. update_appointment – Modify an existing reservation
4. list_appointments – View user reservations
5. cancel_appointment – Cancel an existing reservation
6. get_menu – Send restaurant menu or card
7. save_customer_language – Save customer's language and name

IMPORTANT - HOW TO INTERPRET TIMES:
- "at 8" = 20:00 (dinner)
- "at 2" = 14:00 (lunch)
- "at 1" = 13:00 (lunch)
- "at 9 AM" = 09:00, "at 9 PM" = 21:00
- If they say just a number (1-8) while talking about reservations, it's ALWAYS the time, NOT the number of people
- Number of people is usually explicit: "2 people", "for 4", "we are 6"

CRITICAL WORKFLOW:
- If client asks "what times do you have?" or similar → Use check_availability FIRST
- If client says "I want reservation for [date] at [time]" with all data → Use create_appointment IMMEDIATELY without asking anything else
- ONLY ask for missing data. If you already have name, date, time and people → Create the reservation!

Be warm, professional, and friendly.

IMPORTANT: Never answer topics unrelated to restaurant reservations."""
}
    
    system_prompt = system_prompts.get(language, system_prompts['es'])
    
    try:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "create_appointment",
                        "description": "Crear una reserva nova quan tinguis TOTES les dades necessàries. Si l'usuari diu 'a les 8' interpreta com 20:00, 'a les 2' com 14:00, etc.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "client_name": {"type": "string", "description": "Nom del client"},
                                "date": {"type": "string", "description": "Data en format YYYY-MM-DD"},
                                "time": {"type": "string", "description": "Hora en format HH:MM (24 hores). Exemples: 'a les 8'→20:00, 'a la 1'→13:00, 'a les 2'→14:00, 'a les 9'→21:00"},
                                "num_people": {"type": "integer", "description": "Número de persones (1-8). Normalment s'expressa com '2 persones', 'som 4', etc."}
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
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_menu",
                        "description": "Obtenir menú segons el que demana el client. IMPORTANT: Si demanen 'menú' o 'menu' (sense especificar), és el menú del dia ('menu_dia'). Si demanen específicament 'carta', és la carta permanent ('carta'). Usa 'menu_dia' amb el nom del dia (dilluns/monday/lunes, dimarts/tuesday/martes, dimecres/wednesday/miércoles, dijous/thursday/jueves, divendres/friday/viernes, dissabte/saturday/sábado, diumenge/sunday/domingo) per menús específics del dia.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "menu_type": {
                                    "type": "string",
                                    "enum": ["carta", "menu_dia"],
                                    "description": "Tipus de menú: 'carta' NOMÉS si demanen explícitament 'carta', 'menu_dia' per menú del dia o quan diuen 'menú/menu'"
                                },
                                "day_name": {
                                    "type": "string",
                                    "description": "Nom del dia en qualsevol idioma (dilluns, lunes, monday, dimarts, martes, tuesday, etc.). Només per menu_dia. Si demanen 'avui' o 'demà', calcula el dia de la setmana corresponent."
                                }
                            },
                            "required": ["menu_type"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "check_availability",
                        "description": "Consultar disponibilitat de taules per una data i nombre de persones SENSE crear reserva. Usa aquesta funció quan el client pregunta per disponibilitat ('quines hores tens?', 'disponibilitat per dijous', etc.) abans de confirmar la reserva.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date": {"type": "string", "description": "Data en format YYYY-MM-DD"},
                                "num_people": {"type": "integer", "description": "Número de persones (1-8)"}
                            },
                            "required": ["date", "num_people"]
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
                
                if num_people < 1 or num_people > 8:
                    error_msgs = {
                        'es': "Lo siento, solo aceptamos reservas de 1 a 8 personas.",
                        'ca': "Ho sento, només acceptem reserves d'1 a 8 persones.",
                        'en': "Sorry, we only accept reservations for 1 to 8 people."
                    }
                    return error_msgs.get(language, error_msgs['es'])
                
                # IMPORTANT: Guardar nom del client
                appointment_manager.save_customer_info(phone, function_args.get('client_name'))
                
                # NOVA CRIDA AMB VALIDACIONS I ALTERNATIVES
                result = appointment_manager.create_appointment_with_alternatives(
                    phone=phone,
                    client_name=function_args.get('client_name'),
                    date=function_args.get('date'),
                    time=function_args.get('time'),
                    num_people=num_people,
                    duration_hours=1
                )
                
                if result['success']:
                    # Reserva creada correctament
                    appointment_data = result['appointment']
                    table_info = appointment_data['table']
                    
                    # Missatges segons idioma
                    if language == 'ca':
                        confirmation = f"✅ Reserva confirmada!\n\n👤 Nom: {function_args['client_name']}\n👥 Persones: {num_people}\n📅 Data: {function_args['date']}\n🕐 Hora: {function_args['time']}\n🪑 Taula: {table_info['number']} (capacitat {table_info['capacity']})\n\nT'esperem!\n\n📝 Tens alguna observació especial? (trona, al·lèrgies, preferències...)"
                    elif language == 'en':
                        confirmation = f"✅ Reservation confirmed!\n\n👤 Name: {function_args['client_name']}\n👥 People: {num_people}\n📅 Date: {function_args['date']}\n🕐 Time: {function_args['time']}\n🪑 Table: {table_info['number']} (capacity {table_info['capacity']})\n\nSee you soon!\n\n📝 Any special requests? (high chair, allergies, preferences...)"
                    else:
                        confirmation = f"✅ ¡Reserva confirmada!\n\n👤 Nombre: {function_args['client_name']}\n👥 Personas: {num_people}\n📅 Fecha: {function_args['date']}\n🕐 Hora: {function_args['time']}\n🪑 Mesa: {table_info['number']} (capacidad {table_info['capacity']})\n\n¡Te esperamos!\n\n📝 ¿Alguna observación especial? (trona, alergias, preferencias...)"
                    
                    assistant_reply = confirmation
                    
                    # Guardar estat esperant observacions
                    conversation_manager.save_message(phone, "system", f"WAITING_NOTES:{appointment_data['id']}")
                    print(f"📌 Estat guardat: WAITING_NOTES:{appointment_data['id']}")
                
                elif 'alternative' in result:
                    # Hi ha una alternativa disponible
                    alt = result['alternative']
                    requested_time = function_args['time']
                    requested_date = function_args['date']

                    # Determinar si l'hora sol·licitada és dinar o sopar
                    hour = int(requested_time.split(':')[0])
                    is_lunch = 12 <= hour < 17
                    is_dinner = hour >= 19

                    # Buscar més alternatives el mateix dia i proper dia
                    same_day_availability = appointment_manager.check_availability(requested_date, num_people)

                    # Filtrar alternatives pel mateix torn (dinar o sopar)
                    same_period_slots = []
                    if same_day_availability and same_day_availability.get('available'):
                        for slot in same_day_availability.get('available_slots', []):
                            if is_lunch and slot.get('period') == 'lunch':
                                same_period_slots.append(slot['time'])
                            elif is_dinner and slot.get('period') == 'dinner':
                                same_period_slots.append(slot['time'])

                    # Buscar proper dia disponible (provem els propers 7 dies)
                    next_day_info = None
                    date_obj = datetime.strptime(requested_date, '%Y-%m-%d').date()
                    for i in range(1, 8):
                        next_date = (date_obj + timedelta(days=i)).strftime('%Y-%m-%d')
                        next_availability = appointment_manager.check_availability(next_date, num_people)
                        if next_availability and next_availability.get('available'):
                            slots = next_availability.get('available_slots', [])
                            if slots:
                                times = [s['time'] for s in slots[:3]]  # Primeres 3 hores
                                next_day_info = {'date': next_date, 'times': times}
                                break

                    # Construir missatge
                    if language == 'ca':
                        period_name = "dinar" if is_lunch else "sopar"
                        msg = f"⚠️ Ho sento però no tenim disponibilitat per {num_people} persones a les {requested_time}.\n\n"

                        if same_period_slots:
                            msg += f"✅ En aquest mateix dia tenim hora de {period_name} a les:\n"
                            msg += "🕐 " + ", ".join(same_period_slots) + "\n\n"

                        if next_day_info:
                            msg += f"📅 El dia més pròxim amb disponibilitat és el {next_day_info['date']} a les:\n"
                            msg += "🕐 " + ", ".join(next_day_info['times']) + "\n\n"

                        msg += "Quina hora t'interessa?"
                        assistant_reply = msg
                    elif language == 'en':
                        period_name = "lunch" if is_lunch else "dinner"
                        msg = f"⚠️ Sorry, we don't have availability for {num_people} people at {requested_time}.\n\n"

                        if same_period_slots:
                            msg += f"✅ On the same day we have {period_name} at:\n"
                            msg += "🕐 " + ", ".join(same_period_slots) + "\n\n"

                        if next_day_info:
                            msg += f"📅 The next available day is {next_day_info['date']} at:\n"
                            msg += "🕐 " + ", ".join(next_day_info['times']) + "\n\n"

                        msg += "Which time works for you?"
                        assistant_reply = msg
                    else:
                        period_name = "comida" if is_lunch else "cena"
                        msg = f"⚠️ Lo siento pero no tenemos disponibilidad para {num_people} personas a las {requested_time}.\n\n"

                        if same_period_slots:
                            msg += f"✅ En este mismo día tenemos hora de {period_name} a las:\n"
                            msg += "🕐 " + ", ".join(same_period_slots) + "\n\n"

                        if next_day_info:
                            msg += f"📅 El día más próximo con disponibilidad es el {next_day_info['date']} a las:\n"
                            msg += "🕐 " + ", ".join(next_day_info['times']) + "\n\n"

                        msg += "¿Qué hora te interesa?"
                        assistant_reply = msg
                
                else:
                    # No hi ha disponibilitat
                    if language == 'ca':
                        assistant_reply = f"😔 Ho sento molt, no tinc disponibilitat per {num_people} persones en els propers dies.\n\n📞 Et recomano que ens truquis directament per buscar alternatives: [número de telèfon]"
                    elif language == 'en':
                        assistant_reply = f"😔 I'm very sorry, I don't have availability for {num_people} people in the coming days.\n\n📞 I recommend calling us directly to find alternatives: [phone number]"
                    else:
                        assistant_reply = f"😔 Lo siento mucho, no tengo disponibilidad para {num_people} personas en los próximos días.\n\n📞 Te recomiendo que nos llames directamente para buscar alternativas: [número de teléfono]"
            
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
            
            elif function_name == "get_menu":
                # Obtenir menú del restaurant (carta o menú del dia)
                media_manager = MediaManager()
                menu_type = function_args.get('menu_type', 'carta')
                day_name_arg = function_args.get('day_name')
                
                # Si demanen menú del dia sense especificar dia, usar el dia de la reserva
                if menu_type == 'menu_dia' and not day_name_arg:
                    # Buscar si hi ha una reserva en estat WAITING_MENU
                    reservation_date = None
                    for msg in reversed(history):
                        if msg['role'] == 'system' and msg['content'].startswith('WAITING_MENU:'):
                            appointment_id = int(msg['content'].split(':')[1])
                            # Obtenir la data de la reserva
                            apt = appointment_manager.get_appointment_by_id(phone, appointment_id)
                            if apt:
                                reservation_date = apt['date']
                            break
                    
                    day_names_map = {
                        0: ['dilluns', 'lunes', 'monday'],
                        1: ['dimarts', 'martes', 'tuesday'],
                        2: ['dimecres', 'miércoles', 'wednesday'],
                        3: ['dijous', 'jueves', 'thursday'],
                        4: ['divendres', 'viernes', 'friday'],
                        5: ['dissabte', 'sábado', 'saturday'],
                        6: ['diumenge', 'domingo', 'sunday']
                    }
                    
                    # Si tenim data de reserva, usar el dia de la setmana de la reserva
                    if reservation_date:
                        if isinstance(reservation_date, str):
                            date_obj = datetime.strptime(reservation_date, '%Y-%m-%d')
                        else:
                            date_obj = reservation_date
                        reservation_day_num = date_obj.weekday()
                        # Usar el nom del dia segons l'idioma del client
                        if language == 'ca':
                            day_name_arg = day_names_map[reservation_day_num][0]
                        elif language == 'es':
                            day_name_arg = day_names_map[reservation_day_num][1]
                        else:
                            day_name_arg = day_names_map[reservation_day_num][2]
                        print(f"📅 Usant dia de la reserva: {reservation_date} -> {day_name_arg}")
                    else:
                        # Si no hi ha reserva, usar el dia d'avui
                        today_num = datetime.now().weekday()
                        if language == 'ca':
                            day_name_arg = day_names_map[today_num][0]
                        elif language == 'es':
                            day_name_arg = day_names_map[today_num][1]
                        else:
                            day_name_arg = day_names_map[today_num][2]
                        print(f"📅 Usant dia d'avui: {day_name_arg}")
                
                menu = media_manager.get_menu(menu_type, day_name_arg)
                
                if menu:
                    if menu_type == 'carta':
                        menu_msgs = {
                            'ca': f"📝 Aquí tens la nostra carta:\n\n🔗 {menu['url']}\n\nQue gaudeixis!",
                            'es': f"📝 Aquí tienes nuestra carta:\n\n🔗 {menu['url']}\n\n¡Que disfrutes!",
                            'en': f"📝 Here's our menu:\n\n🔗 {menu['url']}\n\nEnjoy!"
                        }
                    else:
                        menu_msgs = {
                            'ca': f"📝 Aquí tens el menú del dia ({day_name_arg}):\n\n🔗 {menu['url']}\n\nQue gaudeixis!",
                            'es': f"📝 Aquí tienes el menú del día ({day_name_arg}):\n\n🔗 {menu['url']}\n\n¡Que disfrutes!",
                            'en': f"📝 Here's today's menu ({day_name_arg}):\n\n🔗 {menu['url']}\n\nEnjoy!"
                        }
                    assistant_reply = menu_msgs.get(language, menu_msgs['es'])
                else:
                    no_menu_msgs = {
                        'ca': "Ho sento, ara mateix no tinc aquest menú disponible. Pots consultar-lo al restaurant.",
                        'es': "Lo siento, ahora mismo no tengo ese menú disponible. Puedes consultarlo en el restaurante.",
                        'en': "Sorry, I don't have that menu available right now. You can check it at the restaurant."
                    }
                    assistant_reply = no_menu_msgs.get(language, no_menu_msgs['es'])

            elif function_name == "check_availability":
                # Consultar disponibilitat sense crear reserva
                date = function_args.get('date')
                num_people = function_args.get('num_people', 2)

                result = appointment_manager.check_availability(date, num_people)

                if result['available']:
                    # Hi ha disponibilitat - mostrar slots disponibles
                    available_slots = result.get('available_slots', [])

                    # Agrupar per periode (dinar/sopar)
                    lunch_slots = [s['time'] for s in available_slots if s.get('period') == 'lunch']
                    dinner_slots = [s['time'] for s in available_slots if s.get('period') == 'dinner']

                    if language == 'ca':
                        header = f"✅ Disponibilitat per {num_people} persones el {date}:\n\n"
                        if lunch_slots:
                            header += f"🍽️ Dinar: {', '.join(lunch_slots)}\n"
                        if dinner_slots:
                            header += f"🌙 Sopar: {', '.join(dinner_slots)}\n"
                        header += "\nQuina hora et va millor?"
                    elif language == 'en':
                        header = f"✅ Availability for {num_people} people on {date}:\n\n"
                        if lunch_slots:
                            header += f"🍽️ Lunch: {', '.join(lunch_slots)}\n"
                        if dinner_slots:
                            header += f"🌙 Dinner: {', '.join(dinner_slots)}\n"
                        header += "\nWhich time works best for you?"
                    else:
                        header = f"✅ Disponibilidad para {num_people} personas el {date}:\n\n"
                        if lunch_slots:
                            header += f"🍽️ Comida: {', '.join(lunch_slots)}\n"
                        if dinner_slots:
                            header += f"🌙 Cena: {', '.join(dinner_slots)}\n"
                        header += "\n¿Qué hora te va mejor?"

                    assistant_reply = header
                else:
                    # No hi ha disponibilitat
                    if language == 'ca':
                        assistant_reply = f"😔 Ho sento, no tinc disponibilitat per {num_people} persones el {date}.\n\nVols que busqui en un altre dia?"
                    elif language == 'en':
                        assistant_reply = f"😔 Sorry, I don't have availability for {num_people} people on {date}.\n\nWould you like me to check another day?"
                    else:
                        assistant_reply = f"😔 Lo siento, no tengo disponibilidad para {num_people} personas el {date}.\n\n¿Quieres que busque en otro día?"
        else:
            assistant_reply = message_response.content
        
        conversation_manager.save_message(phone, "user", message)
        conversation_manager.save_message(phone, "assistant", assistant_reply)
        print(f"✅ Historial guardat correctament")
        
        return assistant_reply
    
    except Exception as e:
        print(f"❌ ERROR procesando con IA: {e}")
        import traceback
        traceback.print_exc()
        return "Lo siento, hubo un error. ¿Puedes intentar de nuevo?"