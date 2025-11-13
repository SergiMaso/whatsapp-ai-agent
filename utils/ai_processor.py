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
from utils.config import config
load_dotenv()

def detect_language(text, min_keywords=2):
    """
    Detecta l'idioma del text comptant coincidències amb keywords
    Retorna l'idioma amb més paraules úniques detectades, o None si no hi ha prou evidència

    Args:
        text: Text a analitzar
        min_keywords: Mínim de keywords necessàries per considerar la detecció vàlida
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
            'estic', 'som', 'bones', 'voldria', 'mira',
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

        print(f"🔍 [DETECT] Keywords trobades: ca={catalan_matches}, es={spanish_matches}, en={english_matches} (mínim requerit: {min_keywords})")

        # IMPORTANT: Només retornar idioma si hi ha suficients keywords
        max_matches = max(catalan_matches, spanish_matches, english_matches)

        if max_matches < min_keywords:
            print(f"⚠️ [DETECT] Text massa curt o sense keywords clares - no es pot determinar idioma amb seguretat")
            return None

        # Retornar idioma amb més coincidències
        if catalan_matches > spanish_matches and catalan_matches > english_matches:
            print(f"✅ [DETECT] Idioma detectat: ca (amb {catalan_matches} keywords)")
            return 'ca'
        elif spanish_matches > english_matches:
            print(f"✅ [DETECT] Idioma detectat: es (amb {spanish_matches} keywords)")
            return 'es'
        elif english_matches > 0:
            print(f"✅ [DETECT] Idioma detectat: en (amb {english_matches} keywords)")
            return 'en'

        # Si no hi ha coincidències clares, NO usar langdetect (massa poc fiable amb textos curts)
        print(f"⚠️ [DETECT] No s'han trobat keywords suficients - no es pot determinar idioma")
        return None

    except Exception as e:
        print(f"❌ [DETECT] Error detectant idioma: {e}")
        return None

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
    # PRIORITAT: Base de dades > Detecció automàtica
    saved_language = None

    try:
        saved_language = appointment_manager.get_customer_language(phone)
        print(f"🔍 [LANG DEBUG] Idioma des de BD: {saved_language}")
    except Exception as e:
        print(f"⚠️ Error obtenint idioma de BD: {e}")

    # IMPORTANT: Comprovar si hi ha estat actiu abans de detectar idioma
    # Si l'usuari està en WAITING_NOTES o WAITING_MENU, NO detectar/actualitzar idioma
    has_active_state = False
    temp_history = conversation_manager.get_history(phone, limit=5)
    for msg in reversed(temp_history):
        if msg['role'] == 'system' and (msg['content'].startswith('WAITING_NOTES:') or
                                        msg['content'].startswith('WAITING_MENU:') or
                                        msg['content'].startswith('WAITING_CONFIRMATION:')):
            has_active_state = True
            print(f"🔒 [LANG] Estat actiu detectat - NO actualitzarem l'idioma")
            break

    message_count = conversation_manager.get_message_count(phone)
    print(f"🔍 [LANG DEBUG] Nombre de missatges: {message_count}")

    # Lògica d'idioma: SI hi ha idioma guardat, SEMPRE mantenir-lo (no canviar mai automàticament)
    if saved_language:
        # Client conegut: SEMPRE usar idioma de BD, sense excepcions
        language = saved_language
        print(f"🌍 Client conegut - Idioma FIXAT de BD: {language} (no es canviarà)")
    else:
        # Client nou: detectar idioma (només si NO hi ha estat actiu)
        if has_active_state:
            # Si hi ha estat actiu, usar idioma per defecte sense guardar-lo
            language = 'es'  # Per defecte espanyol
            print(f"🔒 [LANG] Estat actiu - usant idioma per defecte temporal: {language}")
        elif message_count == 0:
            # Primer missatge: detectar i guardar NOMÉS si la detecció és segura
            detected_lang = detect_language(message, min_keywords=2)
            if detected_lang:
                # Detecció segura amb suficients keywords
                language = detected_lang
                print(f"👋 Primer missatge → Idioma detectat amb seguretat: {language}")
                try:
                    appointment_manager.save_customer_language(phone, language)
                    print(f"✅ [LANG] Idioma guardat a BD: {language}")
                except Exception as e:
                    print(f"⚠️ Error guardant idioma a BD: {e}")
            else:
                # No hi ha prou evidència - usar per defecte SENSE guardar
                language = 'es'  # Per defecte espanyol
                print(f"⚠️ [LANG] Primer missatge sense keywords suficients - usant espanyol per defecte (NO guardat)")
        else:
            # A partir del segon missatge: usar per defecte (no hauria d'arribar aquí normalment)
            # Si arribem aquí vol dir que BD ha fallat
            language = 'es'  # Per defecte espanyol
            print(f"⚠️ [LANG] No hi ha idioma guardat a BD, usant per defecte: {language}")

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
    # Obtenir configuració dinàmica
    restaurant_name = config.get_str('restaurant_name', 'Amaru')
    max_people = config.get_int('max_people_per_booking', 8)

    system_prompts = {
        'ca': f"""Ets un gestor de reserves virtual del restaurant {restaurant_name}. Només pots respondre preguntes relacionades amb la teva funció de gestió de reserves.

DATA ACTUAL: Avui és {day_name} {today_str}.

{customer_context}{appointment_context}

INFORMACIÓ DEL RESTAURANT:
- Capacitat: 12 taules de 4 persones i 5 taules de 2 persones
- MÀXIM {max_people} persones per reserva (el sistema combina taules automàticament si cal)
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
- "a les 9" / "a las 9" = 21:00 (sopar)
- "a les 2" / "a las 2" = 14:00 (dinar)
- "a les 1" / "a la 1" = 13:00 (dinar)
- "a les 9 del matí" = 09:00, "a les 9 del vespre" / "a les 9 de la nit" = 21:00
- Si diuen només un número (1-9) i s'està parlant de reserves, SEMPRE és l'hora, NO el nombre de persones
- El nombre de persones normalment es diu explícitament: "2 persones", "per a 4", "som 6"

WORKFLOW CRÍTIC:
- Si el client pregunta "quines hores tens?" o similars → Usa check_availability PRIMER
- Si el client diu "vull reserva per [data] a les [hora]" amb totes les dades → Usa create_appointment IMMEDIATAMENT sense preguntar res més
- NOMÉS pregunta les dades que falten. Si ja tens nom, data, hora i persones → Crea la reserva!

Sigues càlid, professional i proper.

IMPORTANT: No contestis mai temes no relacionats amb les reserves del restaurant.""",
        
        'es': f"""Eres un gestor de reservas virtual del restaurante {restaurant_name}. Solo puedes responder preguntas relacionadas con tu función de gestión de reservas.

FECHA ACTUAL: Hoy es {day_name} {today_str}.

{customer_context}{appointment_context}

INFORMACIÓN DEL RESTAURANTE:
- Capacidad: 12 mesas de 4 personas y 5 mesas de 2 personas
- MÁXIMO {max_people} personas por reserva (el sistema combina mesas automáticamente si es necesario)
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
- "a las 9" / "a les 9" = 21:00 (cena)
- "a las 2" / "a les 2" = 14:00 (comida)
- "a la 1" / "a les 1" = 13:00 (comida)
- "a las 9 de la mañana" = 09:00, "a las 9 de la noche" = 21:00
- Si dicen solo un número (1-9) y se está hablando de reservas, SIEMPRE es la hora, NO el número de personas
- El número de personas normalmente se dice explícitamente: "2 personas", "para 4", "somos 6"

WORKFLOW CRÍTICO:
- Si el cliente pregunta "qué horas tienes?" o similares → Usa check_availability PRIMERO
- Si el cliente dice "quiero reserva para [fecha] a las [hora]" con todos los datos → Usa create_appointment INMEDIATAMENTE sin preguntar nada más
- SOLO pregunta los datos que faltan. Si ya tienes nombre, fecha, hora y personas → ¡Crea la reserva!

Sé cálido, profesional y cercano.

IMPORTANTE: No contestes nunca temas no relacionados con las reservas del restaurante.""",
        
        'en': f"""You are a virtual reservation manager for {restaurant_name} restaurant. You can only answer questions related to your reservation management function.

CURRENT DATE: Today is {day_name} {today_str}.

{customer_context}{appointment_context}

RESTAURANT INFORMATION:
- Capacity: 12 tables for 4 people and 5 tables for 2 people
- MAXIMUM {max_people} people per reservation (system automatically combines tables if needed)
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
- "at 9" = 21:00 (dinner)
- "at 2" = 14:00 (lunch)
- "at 1" = 13:00 (lunch)
- "at 9 AM" = 09:00, "at 9 PM" = 21:00
- If they say just a number (1-9) while talking about reservations, it's ALWAYS the time, NOT the number of people
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
                        "description": "Modificar/actualitzar una reserva existent. IMPORTANT: Pots identificar la reserva amb appointment_id O amb date+time. Si no tens l'ID, primer usa list_appointments per obtenir la data i hora de la reserva.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "appointment_id": {"type": "integer", "description": "ID de la reserva a modificar (opcional si proporciones date+time)"},
                                "date": {"type": "string", "description": "Data actual de la reserva (YYYY-MM-DD) - necessari si no tens appointment_id"},
                                "time": {"type": "string", "description": "Hora actual de la reserva (HH:MM) - necessari si no tens appointment_id"},
                                "new_date": {"type": "string", "description": "Nova data (YYYY-MM-DD) o null si no canvia"},
                                "new_time": {"type": "string", "description": "Nova hora (HH:MM) o null si no canvia"},
                                "new_num_people": {"type": "integer", "description": "Nou número de persones o null si no canvia"}
                            },
                            "required": []
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
                        "description": "Cancel·lar una reserva existent. IMPORTANT: Primer usa list_appointments per veure les reserves del client amb les seves dates i hores, després usa aquesta funció amb la data i hora de la reserva que vol cancel·lar.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "date": {"type": "string", "description": "Data de la reserva a cancel·lar (YYYY-MM-DD)"},
                                "time": {"type": "string", "description": "Hora de la reserva a cancel·lar (HH:MM en format 24h)"}
                            },
                            "required": ["date", "time"]
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
                max_people = config.get_int('max_people_per_booking', 8)
                default_duration = config.get_float('default_booking_duration_hours', 1.0)

                if num_people < 1 or num_people > max_people:
                    error_msgs = {
                        'es': f"Lo siento, solo aceptamos reservas de 1 a {max_people} personas.",
                        'ca': f"Ho sento, només acceptem reserves d'1 a {max_people} persones.",
                        'en': f"Sorry, we only accept reservations for 1 to {max_people} people."
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
                    duration_hours=default_duration
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

                    # NOMÉS buscar proper dia disponible si NO hi ha disponibilitat el mateix dia
                    next_day_info = None
                    if not same_period_slots:
                        # No hi ha alternatives el mateix dia - busquem en els propers dies
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
                            # Hi ha disponibilitat el mateix dia
                            msg += f"✅ En aquest mateix dia tenim hora de {period_name} a les:\n"
                            msg += "🕐 " + ", ".join(same_period_slots) + "\n\n"
                            msg += "Quina hora t'interessa? Si no et van bé aquestes hores, puc buscar-te un altre dia."
                        elif next_day_info:
                            # No hi ha disponibilitat el mateix dia, però sí en els propers dies
                            msg += f"📅 El dia més pròxim amb disponibilitat és el {next_day_info['date']} a les:\n"
                            msg += "🕐 " + ", ".join(next_day_info['times']) + "\n\n"
                            msg += "Quina hora t'interessa?"
                        else:
                            # No hi ha disponibilitat en cap dia
                            msg += "😔 No tinc disponibilitat en els propers dies. Vols que busqui per un altra data més endavant?"

                        assistant_reply = msg
                    elif language == 'en':
                        period_name = "lunch" if is_lunch else "dinner"
                        msg = f"⚠️ Sorry, we don't have availability for {num_people} people at {requested_time}.\n\n"

                        if same_period_slots:
                            # There's availability on the same day
                            msg += f"✅ On the same day we have {period_name} at:\n"
                            msg += "🕐 " + ", ".join(same_period_slots) + "\n\n"
                            msg += "Which time works for you? If these times don't work, I can look for another day."
                        elif next_day_info:
                            # No availability on the same day, but available on upcoming days
                            msg += f"📅 The next available day is {next_day_info['date']} at:\n"
                            msg += "🕐 " + ", ".join(next_day_info['times']) + "\n\n"
                            msg += "Which time works for you?"
                        else:
                            # No availability on any day
                            msg += "😔 I don't have availability in the coming days. Would you like me to search for a later date?"

                        assistant_reply = msg
                    else:
                        period_name = "comida" if is_lunch else "cena"
                        msg = f"⚠️ Lo siento pero no tenemos disponibilidad para {num_people} personas a las {requested_time}.\n\n"

                        if same_period_slots:
                            # Hay disponibilidad el mismo día
                            msg += f"✅ En este mismo día tenemos hora de {period_name} a las:\n"
                            msg += "🕐 " + ", ".join(same_period_slots) + "\n\n"
                            msg += "¿Qué hora te interesa? Si no te van bien estas horas, puedo buscarte otro día."
                        elif next_day_info:
                            # No hay disponibilidad el mismo día, pero sí en los próximos días
                            msg += f"📅 El día más próximo con disponibilidad es el {next_day_info['date']} a las:\n"
                            msg += "🕐 " + ", ".join(next_day_info['times']) + "\n\n"
                            msg += "¿Qué hora te interesa?"
                        else:
                            # No hay disponibilidad en ningún día
                            msg += "😔 No tengo disponibilidad en los próximos días. ¿Quieres que busque para otra fecha más adelante?"

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
                date = function_args.get('date')
                time = function_args.get('time')
                new_date = function_args.get('new_date')
                new_time = function_args.get('new_time')
                new_num_people = function_args.get('new_num_people')
                current_num_people = None

                # Si no tenim apt_id però tenim date+time, buscar la reserva
                if not apt_id and date and time:
                    appointments = appointment_manager.get_appointments(phone)
                    for apt in appointments:
                        apt_id_temp, name, apt_date, start_time, end_time, num_people, table_num, capacity, status = apt
                        if str(apt_date) == date and start_time.strftime("%H:%M") == time:
                            apt_id = apt_id_temp
                            current_num_people = num_people
                            break

                if not apt_id:
                    error_msgs = {
                        'es': "❌ No encuentro la reserva que quieres modificar. Usa list_appointments para ver tus reservas.",
                        'ca': "❌ No trobo la reserva que vols modificar. Usa list_appointments per veure les teves reserves.",
                        'en': "❌ I can't find the reservation you want to modify. Use list_appointments to see your reservations."
                    }
                    assistant_reply = error_msgs.get(language, error_msgs['es'])
                else:
                    # Si tenim apt_id però no tenim current_num_people, obtenir-lo de les reserves
                    if not current_num_people:
                        appointments = appointment_manager.get_appointments(phone)
                        for apt in appointments:
                            apt_id_temp, name, apt_date, start_time, end_time, num_people, table_num, capacity, status = apt
                            if apt_id_temp == apt_id:
                                current_num_people = num_people
                                if not date:
                                    date = str(apt_date)
                                break

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
                        # Si ha fallat l'actualització i s'ha intentat canviar l'hora, oferir slots disponibles
                        if new_time:
                            target_date = new_date if new_date else date
                            target_num_people = new_num_people if new_num_people else current_num_people
                            available_slots = appointment_manager.get_available_time_slots(target_date, target_num_people)

                            # Filtrar slots que ja han passat si la reserva és per avui
                            from datetime import datetime
                            import pytz
                            barcelona_tz = pytz.timezone('Europe/Madrid')
                            now = datetime.now(barcelona_tz)
                            today_str = now.strftime("%Y-%m-%d")

                            if target_date == today_str and available_slots:
                                current_time = now.strftime("%H:%M")
                                available_slots = [slot for slot in available_slots if slot > current_time]

                            if available_slots:
                                # Formatar les hores segons idioma
                                if language == 'ca':
                                    time_format = lambda t: f"{t} ({int(t.split(':')[0])}h)"
                                elif language == 'en':
                                    hour = int(new_time.split(':')[0])
                                    time_format = lambda t: f"{t} ({'noon' if t == '12:00' else 'midnight' if t == '00:00' else t})"
                                else:  # es
                                    time_format = lambda t: f"{t} ({int(t.split(':')[0])}h)"

                                slots_formatted = [time_format(slot) for slot in available_slots]

                                if len(slots_formatted) == 1:
                                    slots_text = slots_formatted[0]
                                elif len(slots_formatted) == 2:
                                    conj = {'ca': ' o ', 'en': ' or ', 'es': ' o '}[language]
                                    slots_text = f"{slots_formatted[0]}{conj}{slots_formatted[1]}"
                                else:
                                    conj = {'ca': ' o ', 'en': ', or ', 'es': ' o '}[language]
                                    slots_text = ", ".join(slots_formatted[:-1]) + conj + slots_formatted[-1]

                                error_msgs = {
                                    'ca': f"❌ Ho sento, l'hora {new_time} no està disponible.\n\nℹ️ Només pots reservar a: {slots_text}\n\nQuina hora prefereixes?",
                                    'en': f"❌ Sorry, {new_time} is not available.\n\nℹ️ You can only book at: {slots_text}\n\nWhich time do you prefer?",
                                    'es': f"❌ Lo siento, la hora {new_time} no está disponible.\n\nℹ️ Solo puedes reservar a: {slots_text}\n\n¿Qué hora prefieres?"
                                }
                                assistant_reply = error_msgs.get(language, error_msgs['es'])
                            else:
                                # No hi ha slots disponibles (restaurant tancat o sense configuració)
                                error_msgs = {
                                    'ca': "❌ Ho sento, no s'ha pogut actualitzar la reserva. No hi ha horaris disponibles per aquesta data.",
                                    'en': "❌ Sorry, couldn't update the reservation. There are no available times for this date.",
                                    'es': "❌ Lo siento, no se pudo actualizar la reserva. No hay horarios disponibles para esta fecha."
                                }
                                assistant_reply = error_msgs.get(language, error_msgs['es'])
                        else:
                            # Missatge genèric si no s'ha intentat canviar l'hora
                            error_msgs = {
                                'ca': "Ho sento, no s'ha pogut actualitzar la reserva. Pot ser que no hi hagi taules disponibles en aquest horari.",
                                'en': "Sorry, couldn't update the reservation. There might not be tables available at that time.",
                                'es': "Lo siento, no se pudo actualizar la reserva. Puede que no haya mesas disponibles en ese horario."
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
                date = function_args.get('date')
                time = function_args.get('time')

                # Buscar la reserva per data i hora
                appointments = appointment_manager.get_appointments(phone)

                if not appointments:
                    no_apt_msgs = {
                        'es': "❌ No tienes ninguna reserva programada.",
                        'ca': "❌ No tens cap reserva programada.",
                        'en': "❌ You don't have any scheduled reservations."
                    }
                    assistant_reply = no_apt_msgs.get(language, no_apt_msgs['es'])
                else:
                    # Buscar la reserva que coincideixi
                    apt_id = None
                    for apt in appointments:
                        apt_id_temp, name, apt_date, start_time, end_time, num_people, table_num, capacity, status = apt

                        if str(apt_date) == date and start_time.strftime("%H:%M") == time:
                            apt_id = apt_id_temp
                            break

                    if not apt_id:
                        not_found_msgs = {
                            'es': f"❌ No encuentro ninguna reserva para el {date} a las {time}.",
                            'ca': f"❌ No trobo cap reserva pel {date} a les {time}.",
                            'en': f"❌ I can't find any reservation for {date} at {time}."
                        }
                        assistant_reply = not_found_msgs.get(language, not_found_msgs['es'])
                    else:
                        success = appointment_manager.cancel_appointment(phone, apt_id)

                        if success:
                            cancel_msgs = {
                                'es': f"✅ Reserva del {date} a las {time} cancelada correctamente.",
                                'ca': f"✅ Reserva del {date} a les {time} cancel·lada correctament.",
                                'en': f"✅ Reservation for {date} at {time} cancelled successfully."
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

                    # Filtrar slots que ja han passat si la reserva és per avui
                    from datetime import datetime
                    import pytz
                    barcelona_tz = pytz.timezone('Europe/Madrid')
                    now = datetime.now(barcelona_tz)
                    today_str = now.strftime("%Y-%m-%d")

                    if date == today_str and available_slots:
                        current_time = now.strftime("%H:%M")
                        available_slots = [s for s in available_slots if s['time'] > current_time]

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