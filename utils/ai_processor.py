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
        text_lower = text.lower().strip()
        
        # Palabras clave INGLESAS - detectar primero
        english_keywords = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening',
                          'i want', 'i need', 'can i', 'i have', 'today', 'tomorrow', 'please',
                          'thank you', 'thanks', 'table', 'people', 'reservation', 'book',
                          'lunch', 'dinner', 'would like', 'could i', 'want to make']
        
        # Palabras clave catalanas para mejorar detección
        catalan_keywords = ['vull', 'necessito', 'puc', 'tinc', 'avui', 'demà', 'sisplau', 
                           'gràcies', 'bon dia', 'bona tarda', 'bona nit', 'hola', 'adéu', 'taula',
                           'persones', 'reserva', 'dinar', 'sopar', 'voldria', 'podria',
                           'estava', 'pensant', 'gust', 'nom', 'estic', 'volia', 'cognom',
                           'pots', 'podem', 'vol', 'fer', 'una', 'quatre']
        
        # Palabras que indican español inequívocamente
        spanish_keywords = ['quiero', 'necesito', 'puedo', 'tengo', 'hoy', 'mañana', 'por favor',
                          'gracias', 'buenos días', 'buenas tardes', 'adiós', 'mesa',
                          'personas', 'comer', 'cenar', 'quería', 'podría', 'apellido']
        
        # Contar palabras clave por idioma
        english_count = sum(1 for word in english_keywords if word in text_lower)
        catalan_count = sum(1 for word in catalan_keywords if word in text_lower)
        spanish_count = sum(1 for word in spanish_keywords if word in text_lower)
        
        # PRIORIDAD: Inglés tiene prioridad si detectamos palabras inglesas
        if english_count >= 1:
            return 'en'
        
        # Si el texto es muy corto (sí, no, ok, etc) y no es inglés, usar default
        if len(text.strip()) <= 3:
            return 'ca'  # Default catalán para respuestas cortas
        
        # Detectar con langdetect
        lang = detect(text)
        
        # Si langdetect dice inglés, confiar
        if lang == 'en':
            return 'en'
        
        # Si tiene palabras españolas claras, es español
        if spanish_count >= 2:
            return 'es'
        
        # Si tiene 2 o más palabras catalanas, es catalán
        if catalan_count >= 2:
            return 'ca'
        
        # Si tiene 1 palabra catalana y detect() no detectó español, es catalán
        if catalan_count >= 1 and lang != 'es':
            return 'ca'
        
        # Si langdetect dice catalán, confiar
        if lang == 'ca':
            return 'ca'
        
        return lang
    except LangDetectException:
        return 'ca'  # Default catalán si falla

def process_message_with_ai(message, phone, appointment_manager, conversation_manager):
    """
    Procesar mensaje con GPT-4 usando historial de conversación
    """
    
    from utils.phone_utils import normalize_phone_number
    
    # Normalizar teléfono (quitar telegram:/whatsapp:)
    normalized_phone = normalize_phone_number(phone)
    
    print(f"[DEBUG] Procesando mensaje de {normalized_phone}: {message}")
    
    # 1. Obtener idioma guardado en BD
    saved_language = appointment_manager.get_customer_language(normalized_phone)
    
    # 2. Detectar si el usuario pide cambiar idioma
    language_change_keywords = {
        'en': ['english', 'in english', 'speak english', 'english please'],
        'es': ['español', 'castellano', 'en español', 'en castellano', 'habla español', 'spanish', 'castellan'],
        'ca': ['català', 'catala', 'en català', 'en catala', 'parla català', 'parla en catala', 'parla en català', 'catalan'],
        'fr': ['français', 'en français', 'parle français', 'french'],
        'de': ['deutsch', 'auf deutsch', 'german'],
        'it': ['italiano', 'in italiano', 'italian']
    }
    
    message_lower = message.lower()
    language_requested = None
    
    for lang, keywords in language_change_keywords.items():
        if any(keyword in message_lower for keyword in keywords):
            language_requested = lang
            print(f"[LANG] Usuario pide cambiar a: {lang}")
            appointment_manager.update_customer_language(normalized_phone, lang)
            saved_language = lang
            break
    
    # 3. Si no hay idioma guardado, detectar del mensaje
    if not saved_language:
        # Detectar idioma del mensaje (incluso saludos cortos)
        detected_lang = detect_language(message)
        
        # Solo saludos en catalán/español sin palabra clave inglesa son ambiguos
        if len(message.strip()) <= 10 and message.lower() in ['hola', 'bon dia', 'bona tarda']:
            language = 'ca'  # Default catalán para saludos ambiguos cat/es, esperamos
            print(f"[LANG] Saludo corto - usando default: ca (sin guardar)")
        else:
            # Guardar idioma detectado (incluso si es 'hello' -> 'en')
            print(f"[LANG] Primer mensaje - detectado: {detected_lang}")
            appointment_manager.save_customer_info(normalized_phone, None, detected_lang)
            language = detected_lang
    else:
        # IMPORTANTE: Si el usuario está hablando en otro idioma diferente al guardado,
        # actualizar automáticamente (excepto si solo es una hora como "22:30")
        if len(message.strip()) > 5:  # No actualizar para mensajes muy cortos como horas
            detected_lang = detect_language(message)
            # Si el idioma detectado es diferente y tiene alta confianza, actualizar
            if detected_lang != saved_language and detected_lang in ['en', 'es', 'ca']:
                print(f"[LANG] Cambio automático de {saved_language} a {detected_lang}")
                appointment_manager.update_customer_language(normalized_phone, detected_lang)
                language = detected_lang
            else:
                language = saved_language
        else:
            language = saved_language
    
    print(f"[DEBUG] Idioma usado: {language}")
    
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
    
    # Verificar si el cliente ya existe
    customer_name = appointment_manager.get_customer_name(normalized_phone)
    
    # Fecha actual para contexto
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    current_hour = today.hour
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
    
    # Determinar si solo cena está disponible hoy
    only_dinner_today = current_hour >= 15
    
    # System prompt para restaurante
    system_prompt = f"""Eres un asistente virtual para reservas de un restaurante.

FECHA Y HORA ACTUAL: Hoy es {day_name} {today_str} (2 de octubre de 2025), hora actual: {current_hour}:00

IDIOMA: El usuario está escribiendo en {lang_name}. Responde SIEMPRE en {lang_name}.
{customer_greeting}

INFORMACIÓ DEL RESTAURANTE:
- Capacidad: 20 mesas de 4 personas y 8 mesas de 2 personas
- Horarios de servicio:
  * Comida: 12:00 a 15:00 (última reserva)
  * Cena: 19:00 a 22:30 (última reserva)
- Solo aceptamos reservas en estos horarios

CAPACIDADES:
1. Agendar nuevas reservas (necesitas: nombre, fecha, hora, número de personas)
2. Consultar reservas existentes
3. Cancelar reservas (necesitas el ID de la reserva)
4. MODIFICAR reservas existentes (cambiar personas, fecha u hora)
5. Responder preguntas generales

PROCESO DE RESERVA:
1. Saluda cordialmente
2. Pregunta para cuántas personas (1-8 personas máximo)
3. Pregunta qué día (acepta "hoy", "mañana", "el viernes", fechas específicas)
4. Pregunta horario preferido y hora específica
   - Si pide HOY después de las 15:00, SOLO ofrece CENA (19:00-22:30)
   - Si pide otro día, pregunta: ¿comida (12:00-15:00) o cena (19:00-22:30)?
5. Pregunta SIEMPRE el nombre, incluso si ya está guardado (para confirmar)
6. Confirma todos los detalles antes de crear la reserva
7. IMPORTANTE: Convierte horas en formato natural a formato 24h:
   - "2 del mediodía" / "2 de la tarde" / "2 del migdia" = 14:00
   - "9 de la noche" / "9 del vespre" = 21:00
   - "8 de la noche" / "8 pm" = 20:00
   - "1 del mediodía" = 13:00
   - "medio día" / "12 del mediodía" / "migdia" = 12:00
   - "las 2" (en contexto de comida) = 14:00
   - "las 8" / "les 8" (en contexto de cena) = 20:00
   - "las 9" / "les 9" (en contexto de cena) = 21:00
8. CRÍTICO: 22:30 ES VÁLIDA - es la Última hora de cena permitida

PROCESO DE MODIFICACIÓN:
1. Si el usuario quiere MODIFICAR una reserva (cambiar personas, fecha u hora):
   - Primero lista sus reservas con list_appointments
   - Pide que confirme qué reserva modificar (ID)
   - Pregunta qué quiere cambiar específicamente
   - Usa update_appointment con el ID y los nuevos datos
   - Verifica disponibilidad antes de confirmar
2. NO elimines y crees nueva reserva, usa update_appointment

PROCESO DE CANCELACIÓN:
1. Primero muestra las reservas del usuario con list_appointments
2. Pide que indiquen qué reserva quieren cancelar
3. Usa cancel_appointment con el ID correcto

INSTRUCCIONES:
- Mantén contexto de la conversación anterior
- Sé cálido, profesional y cercano
- Usa lenguaje natural del idioma del usuario
- Si dice "empezar de nuevo", olvida la conversación
- Cuando tengas TODOS los datos, usa las funciones apropiadas
- Al listar reservas, SOLO muestra las confirmadas (status='confirmed')
- ACEPTA 15:00 y 22:30 como horas válidas (son las últimas horas permitidas)"""

    try:
        # Obtener historial de conversación
        history = conversation_manager.get_history(phone, limit=10)
        
        # Construir mensajes incluyendo historial
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        
        # Inicializar cliente OpenAI
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        print(f"[GPT] Llamando a GPT-4 con {len(messages)} mensajes...")
        
        # Llamada a GPT-4 con function calling
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=messages,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "create_appointment",
                        "description": "Crear una reserva SOLO cuando tengas TODOS los datos necesarios Y la hora esté en el rango permitido (12:00-14:30 o 19:00-22:00)",
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
                                    "description": "Hora en formato HH:MM (24 horas). Convierte formatos naturales: '2 del mediodía' = 14:00, '8 de la noche' = 20:00"
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
                        "name": "update_appointment",
                        "description": "Modificar una reserva existente (cambiar personas, fecha u hora). Verifica disponibilidad antes de modificar.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "appointment_id": {
                                    "type": "integer",
                                    "description": "ID de la reserva a modificar"
                                },
                                "num_people": {
                                    "type": "integer",
                                    "description": "Nuevo número de personas (opcional)"
                                },
                                "date": {
                                    "type": "string",
                                    "description": "Nueva fecha en formato YYYY-MM-DD (opcional)"
                                },
                                "time": {
                                    "type": "string",
                                    "description": "Nueva hora en formato HH:MM (opcional)"
                                }
                            },
                            "required": ["appointment_id"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "list_appointments",
                        "description": "Listar las reservas confirmadas del usuario (solo status='confirmed')"
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
        
        print(f"[GPT] Respuesta recibida de GPT-4")
        
        message_response = response.choices[0].message
        assistant_reply = ""
        
        print(f"[GPT] Tool calls: {message_response.tool_calls is not None}")
        print(f"[GPT] Content: {message_response.content[:50] if message_response.content else 'None'}...")
        
        # Si la IA quiere ejecutar una función
        if message_response.tool_calls:
            tool_call = message_response.tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            print(f"[FUNC] Funcion llamada: {function_name}")
            print(f"[ARGS] Argumentos: {function_args}")
            
            if function_name == "create_appointment":
                num_people = function_args.get('num_people', 2)
                time_str = function_args.get('time', '')
                
                print(f"[CREATE] Creando reserva - Personas: {num_people}, Hora: {time_str}")
                
                # Validar número de personas
                if num_people < 1 or num_people > 8:
                    error_msgs = {
                        'es': "Lo siento, solo aceptamos reservas de 1 a 8 personas.",
                        'ca': "Ho sento, només acceptem reserves d'1 a 8 persones.",
                        'en': "Sorry, we only accept reservations for 1 to 8 people."
                    }
                    assistant_reply = error_msgs.get(language, error_msgs['es'])
                    conversation_manager.save_message(phone, "user", message)
                    conversation_manager.save_message(phone, "assistant", assistant_reply)
                    return assistant_reply
                
                # Validar horarios
                try:
                    hour = int(time_str.split(':')[0])
                    minute = int(time_str.split(':')[1])
                    
                    print(f"[TIME] Hora parseada: {hour}:{minute}")
                    
                    is_lunch = 12 <= hour < 16 or (hour == 15 and minute == 0)
                    is_dinner = 19 <= hour < 23 or (hour == 22 and minute <= 30)
                    
                    if not (is_lunch or is_dinner):
                        print(f"[ERROR] Hora fuera de rango - Lunch: {is_lunch}, Dinner: {is_dinner}")
                        error_msgs = {
                            'es': "Lo siento, solo aceptamos reservas de 12:00-15:00 o 19:00-22:30. ¿Prefieres otro horario?",
                            'ca': "Ho sento, només acceptem reserves de 12:00-15:00 o 19:00-22:30. Prefereixes un altre horari?",
                            'en': "Sorry, we only accept reservations from 12:00-15:00 or 19:00-22:30. Would you prefer another time?"
                        }
                        assistant_reply = error_msgs.get(language, error_msgs['es'])
                        conversation_manager.save_message(phone, "user", message)
                        conversation_manager.save_message(phone, "assistant", assistant_reply)
                        return assistant_reply
                    
                    print(f"[OK] Hora valida - Procediendo a crear reserva")
                    
                except Exception as time_error:
                    print(f"[ERROR] Error parseando hora {time_str}: {time_error}")
                    error_msgs = {
                        'es': "No entendí bien la hora. ¿Puedes decirme la hora en formato HH:MM? Por ejemplo: 14:00 o 20:30",
                        'ca': "No he entès bé l'hora. Pots dir-me l'hora en format HH:MM? Per exemple: 14:00 o 20:30",
                        'en': "I didn't understand the time. Can you tell me the time in HH:MM format? For example: 14:00 or 20:30"
                    }
                    assistant_reply = error_msgs.get(language, error_msgs['es'])
                    conversation_manager.save_message(phone, "user", message)
                    conversation_manager.save_message(phone, "assistant", assistant_reply)
                    return assistant_reply
                
                # Usar nombre guardado si existe, sino el del argumento
                client_name_to_use = customer_name if customer_name else function_args.get('client_name')
                
                # Guardar nombre del cliente si es nuevo
                if not customer_name:
                    appointment_manager.save_customer_info(normalized_phone, client_name_to_use, language)
                
                # Crear la reserva
                result = appointment_manager.create_appointment(
                    phone=normalized_phone,
                    client_name=client_name_to_use,
                    date=function_args.get('date'),
                    time=function_args.get('time'),
                    num_people=num_people,
                    language=language
                )
                
                if result:
                    # Incrementar contador de reservas
                    appointment_manager.increment_reservation_count(normalized_phone)
                    table_info = result['table']
                    print(f"[OK] Reserva creada exitosamente - Mesa {table_info['number']}")
                    
                    # Mensajes de confirmación SIMPLES sin emojis problemáticos
                    if language == 'ca':
                        assistant_reply = f"Reserva confirmada!\n\nNom: {client_name_to_use}\nPersones: {num_people}\nData: {function_args['date']}\nHora: {function_args['time']}\nTaula: {table_info['number']}\n\nT'esperem!"
                    elif language == 'es':
                        assistant_reply = f"Reserva confirmada!\n\nNombre: {client_name_to_use}\nPersonas: {num_people}\nFecha: {function_args['date']}\nHora: {function_args['time']}\nMesa: {table_info['number']}\n\nTe esperamos!"
                    else:
                        assistant_reply = f"Reservation confirmed!\n\nName: {client_name_to_use}\nPeople: {num_people}\nDate: {function_args['date']}\nTime: {function_args['time']}\nTable: {table_info['number']}\n\nSee you!"
                    
                    conversation_manager.clear_history(phone)
                else:
                    print(f"[ERROR] No hay mesas disponibles")
                    no_tables_msgs = {
                        'es': f"Lo siento, no tenemos mesas disponibles para {num_people} personas el {function_args['date']} a las {function_args['time']}. ¿Te gustaría probar con otro horario?",
                        'ca': f"Ho sento, no tenim taules disponibles per a {num_people} persones el {function_args['date']} a les {function_args['time']}. Vols provar amb un altre horari?",
                        'en': f"Sorry, we don't have tables available for {num_people} people on {function_args['date']} at {function_args['time']}. Would you like to try another time?"
                    }
                    assistant_reply = no_tables_msgs.get(language, no_tables_msgs['es'])
            
            elif function_name == "update_appointment":
                apt_id = function_args.get('appointment_id')
                new_num_people = function_args.get('num_people')
                new_date = function_args.get('date')
                new_time = function_args.get('time')
                
                print(f"[UPDATE] Modificando reserva {apt_id} - Personas: {new_num_people}, Fecha: {new_date}, Hora: {new_time}")
                
                # Actualizar la reserva
                success = appointment_manager.update_appointment(
                    phone=normalized_phone,
                    appointment_id=apt_id,
                    num_people=new_num_people,
                    date=new_date,
                    time=new_time
                )
                
                if success:
                    # Obtener los detalles actualizados de la reserva
                    appointments = appointment_manager.get_appointments(normalized_phone)
                    updated_apt = next((apt for apt in appointments if apt[0] == apt_id), None)
                    
                    if updated_apt:
                        apt_id_db, name, apt_date, apt_time, people, table_num, table_cap, status = updated_apt
                        
                        if language == 'ca':
                            assistant_reply = f"Reserva modificada correctament!\n\nNom: {name}\nPersones: {people}\nData: {apt_date}\nHora: {apt_time}\nTaula: {table_num}\n\nT'esperem!"
                        elif language == 'es':
                            assistant_reply = f"Reserva modificada correctamente!\n\nNombre: {name}\nPersonas: {people}\nFecha: {apt_date}\nHora: {apt_time}\nMesa: {table_num}\n\nTe esperamos!"
                        else:
                            assistant_reply = f"Reservation updated successfully!\n\nName: {name}\nPeople: {people}\nDate: {apt_date}\nTime: {apt_time}\nTable: {table_num}\n\nSee you!"
                    else:
                        # Fallback si no se encuentra la reserva actualizada
                        update_msgs = {
                            'es': "Reserva modificada correctamente!",
                            'ca': "Reserva modificada correctament!",
                            'en': "Reservation updated successfully!"
                        }
                        assistant_reply = update_msgs.get(language, update_msgs['es'])
                else:
                    error_msgs = {
                        'es': "No se pudo modificar la reserva. Puede que no haya disponibilidad para los nuevos datos.",
                        'ca': "No s'ha pogut modificar la reserva. Pot ser que no hi hagi disponibilitat per les noves dades.",
                        'en': "Could not update the reservation. There might not be availability for the new details."
                    }
                    assistant_reply = error_msgs.get(language, error_msgs['es'])
            
            elif function_name == "list_appointments":
                appointments = appointment_manager.get_appointments(normalized_phone)
                
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
                        if status == 'confirmed':  # Solo mostrar confirmadas
                            assistant_reply += f"ID: {apt_id}\n- {date} a las {time}\n  {num_people} personas - Mesa {table_num}\n  {name}\n\n"
            
            elif function_name == "cancel_appointment":
                apt_id = function_args.get('appointment_id')
                success = appointment_manager.cancel_appointment(normalized_phone, apt_id)
                
                if success:
                    # Decrementar contador de reservas
                    appointment_manager.decrement_reservation_count(normalized_phone)
                    
                    cancel_msgs = {
                        'es': "Reserva cancelada correctamente.",
                        'ca': "Reserva cancel·lada correctament.",
                        'en': "Reservation cancelled successfully."
                    }
                    assistant_reply = cancel_msgs.get(language, cancel_msgs['es'])
                else:
                    error_msgs = {
                        'es': "No se pudo cancelar la reserva. Verifica el ID de la reserva.",
                        'ca': "No s'ha pogut cancel·lar la reserva. Verifica l'ID de la reserva.",
                        'en': "Could not cancel the reservation. Please verify the reservation ID."
                    }
                    assistant_reply = error_msgs.get(language, error_msgs['es'])
        
        else:
            assistant_reply = message_response.content
        
        # Asegurarse de que siempre hay una respuesta
        if not assistant_reply or assistant_reply.strip() == "":
            assistant_reply = "Lo siento, no pude procesar tu solicitud. ¿Puedes intentar de nuevo?"
            print("[WARN] No se genero respuesta, usando mensaje por defecto")
        
        # Guardar en historial
        print(f"[SAVE] Guardando en historial...")
        print(f"[SAVE] Respuesta a enviar ({len(assistant_reply)} chars): {assistant_reply[:100]}...")
        conversation_manager.save_message(phone, "user", message)
        conversation_manager.save_message(phone, "assistant", assistant_reply)
        print(f"[OK] Historial guardado correctamente")
        
        # Detectar si el usuario quiere empezar de nuevo
        restart_keywords = ["empezar de nuevo", "olvidar", "reiniciar", "start over", "començar de nou"]
        if any(word in message.lower() for word in restart_keywords):
            conversation_manager.clear_history(phone)
        
        print(f"[RETURN] Devolviendo respuesta al webhook...")
        return assistant_reply
    
    except Exception as e:
        print(f"[ERROR] ERROR COMPLETO procesando con IA: {e}")
        import traceback
        traceback.print_exc()
        return "Lo siento, hubo un error procesando tu mensaje. ¿Puedes intentar de nuevo?"
