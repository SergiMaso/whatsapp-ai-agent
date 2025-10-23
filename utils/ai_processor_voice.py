import os
import json
import time
import logging
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime

load_dotenv()

# Configurar logger específic per voice
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def process_voice_with_ai(message, phone, appointment_manager, conversation_manager):
    """
    Processador SIMPLIFICAT per veu - optimitzat per latència mínima
    
    DIFERÈNCIES amb WhatsApp:
    - Historial mínim (3 missatges vs 10)
    - Sense gestió d'estats complexos (WAITING_NOTES, WAITING_MENU)
    - Respostes curtes i directes
    - Idioma només a l'inici (no re-detectat)
    """
    # ⏱️ INICI - Timing total
    start_time_total = time.time()
    logger.info("=" * 80)
    logger.info(f"🎤 [VOICE] INICI processament | Phone: {phone}")
    logger.info(f"📝 [VOICE] Missatge: '{message[:100]}...'")
    
    # Netejar prefixos del telèfon
    if phone.startswith('whatsapp:'):
        phone = phone.replace('whatsapp:', '')
    elif phone.startswith('telegram:'):
        phone = phone.replace('telegram:', '')

    # --- STEP 1: Obtenir idioma del client (NO re-detectar) ---
    start_time_language = time.time()
    
    language = appointment_manager.get_customer_language(phone) or 'es'
    
    elapsed_language = time.time() - start_time_language
    logger.info(f"⏱️  [VOICE] Idioma obtingut en {elapsed_language:.3f}s: {language}")

    # --- STEP 2: Historial MÍNIM (només 3 últims missatges) ---
    start_time_history = time.time()
    
    history = conversation_manager.get_history(phone, limit=6)
    
    elapsed_history = time.time() - start_time_history
    logger.info(f"⏱️  [VOICE] Historial obtingut en {elapsed_history:.3f}s ({len(history)} missatges)")

    # --- STEP 3: Info del client (ràpid) ---
    start_time_customer = time.time()
    
    customer_name = appointment_manager.get_customer_name(phone)
    
    elapsed_customer = time.time() - start_time_customer
    logger.info(f"⏱️  [VOICE] Info client en {elapsed_customer:.3f}s")

    # --- STEP 4: Preparar context SIMPLIFICAT ---
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    day_names = {
        'es': ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
        'ca': ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"],
        'en': ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    }
    day_name = day_names.get(language, day_names['es'])[today.weekday()]

    # Context MOLT simple
    customer_context = f"Client: {customer_name}" if customer_name else "Client NOU"

    # System prompt SIMPLIFICAT i CURT
    system_prompts = {
        'ca': f"""Ets l'assistent de reserves d'Amaru. {customer_context}. Avui és {day_name} {today_str}.

Respon de forma MOLT BREU i DIRECTA. 1-2 frases màxim.

Funcions: create_appointment, update_appointment, list_appointments, cancel_appointment.

IMPORTANT: NO facis preguntes de seguiment. Confirma la reserva i prou.""",
        
        'es': f"""Eres el asistente de reservas de Amaru. {customer_context}. Hoy es {day_name} {today_str}.

Responde de forma MUY BREVE y DIRECTA. 1-2 frases máximo.

Funciones: create_appointment, update_appointment, list_appointments, cancel_appointment.

IMPORTANTE: NO hagas preguntas de seguimiento. Confirma la reserva y ya está.""",
        
        'en': f"""You're Amaru's reservation assistant. {customer_context}. Today is {day_name} {today_str}.

Respond VERY BRIEFLY and DIRECTLY. 1-2 sentences max.

Functions: create_appointment, update_appointment, list_appointments, cancel_appointment.

IMPORTANT: NO follow-up questions. Just confirm the reservation."""
    }
    
    system_prompt = system_prompts.get(language, system_prompts['es'])
    
    try:
        # --- STEP 5: Cridar OpenAI (amb model ràpid) ---
        start_time_openai = time.time()
        logger.info("🤖 [VOICE] Cridant OpenAI API...")
        
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Usar gpt-4o-mini per rapidesa
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=150,  # Limitar tokens per respostes curtes
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "create_appointment",
                        "description": "Crear reserva",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "client_name": {"type": "string"},
                                "date": {"type": "string", "description": "Format YYYY-MM-DD"},
                                "time": {"type": "string", "description": "Format HH:MM"},
                                "num_people": {"type": "integer", "description": "1-8 persones"}
                            },
                            "required": ["client_name", "date", "time", "num_people"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "update_appointment",
                        "description": "Modificar reserva",
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
                {
                    "type": "function",
                    "function": {
                        "name": "list_appointments",
                        "description": "Llistar reserves"
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "cancel_appointment",
                        "description": "Cancel·lar reserva",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "appointment_id": {"type": "integer"}
                            },
                            "required": ["appointment_id"]
                        }
                    }
                }
            ]
        )
        
        elapsed_openai = time.time() - start_time_openai
        logger.info(f"⏱️  [VOICE] OpenAI resposta en {elapsed_openai:.3f}s")
        
        # --- STEP 6: Processar resposta ---
        start_time_processing = time.time()
        
        message_response = response.choices[0].message
        assistant_reply = ""
        
        if message_response.tool_calls:
            tool_call = message_response.tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            logger.info(f"🔧 [VOICE] Funció cridada: {function_name}")
            
            if function_name == "create_appointment":
                num_people = function_args.get('num_people', 2)
                
                if num_people < 1 or num_people > 8:
                    error_msgs = {
                        'es': "Lo siento, solo aceptamos de 1 a 8 personas.",
                        'ca': "Ho sento, només acceptem d'1 a 8 persones.",
                        'en': "Sorry, we accept 1 to 8 people only."
                    }
                    assistant_reply = error_msgs.get(language, error_msgs['es'])
                else:
                    # Guardar nom del client
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
                        # Confirmació CURTA i DIRECTA (sense preguntes de seguiment)
                        confirmations = {
                            'ca': f"Reserva confirmada per {num_people} persones el {function_args['date']} a les {function_args['time']}. Ens veiem!",
                            'es': f"Reserva confirmada para {num_people} personas el {function_args['date']} a las {function_args['time']}. ¡Nos vemos!",
                            'en': f"Reservation confirmed for {num_people} people on {function_args['date']} at {function_args['time']}. See you!"
                        }
                        assistant_reply = confirmations.get(language, confirmations['es'])
                    else:
                        no_tables_msgs = {
                            'es': f"Lo siento, no hay mesas disponibles para {num_people} personas ese día a esa hora.",
                            'ca': f"Ho sento, no hi ha taules disponibles per {num_people} persones aquell dia a aquesta hora.",
                            'en': f"Sorry, no tables available for {num_people} people at that time."
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
                    update_msgs = {
                        'es': "Reserva actualizada correctamente.",
                        'ca': "Reserva actualitzada correctament.",
                        'en': "Reservation updated successfully."
                    }
                    assistant_reply = update_msgs.get(language, update_msgs['es'])
                else:
                    error_msgs = {
                        'es': "No se pudo actualizar la reserva.",
                        'ca': "No s'ha pogut actualitzar la reserva.",
                        'en': "Could not update the reservation."
                    }
                    assistant_reply = error_msgs.get(language, error_msgs['es'])
            
            elif function_name == "list_appointments":
                appointments = appointment_manager.get_appointments(phone)
                
                if not appointments:
                    no_apts = {
                        'es': "No tienes reservas.",
                        'en': "No reservations.",
                        'ca': "No tens reserves."
                    }
                    assistant_reply = no_apts.get(language, no_apts['es'])
                else:
                    # Només la primera reserva (simplificat)
                    apt = appointments[0]
                    apt_id, name, date, start_time, end_time, num_people, table_num, capacity, status = apt
                    time_str = start_time.strftime("%H:%M")
                    
                    list_msgs = {
                        'es': f"Tienes reserva el {date} a las {time_str} para {num_people} personas.",
                        'ca': f"Tens reserva el {date} a les {time_str} per {num_people} persones.",
                        'en': f"You have a reservation on {date} at {time_str} for {num_people} people."
                    }
                    assistant_reply = list_msgs.get(language, list_msgs['es'])
            
            elif function_name == "cancel_appointment":
                apt_id = function_args.get('appointment_id')
                success = appointment_manager.cancel_appointment(phone, apt_id)
                
                if success:
                    cancel_msgs = {
                        'es': "Reserva cancelada.",
                        'ca': "Reserva cancel·lada.",
                        'en': "Reservation cancelled."
                    }
                    assistant_reply = cancel_msgs.get(language, cancel_msgs['es'])
                else:
                    error_msgs = {
                        'es': "No se pudo cancelar.",
                        'ca': "No s'ha pogut cancel·lar.",
                        'en': "Could not cancel."
                    }
                    assistant_reply = error_msgs.get(language, error_msgs['es'])
        else:
            assistant_reply = message_response.content
        
        elapsed_processing = time.time() - start_time_processing
        logger.info(f"⏱️  [VOICE] Processament en {elapsed_processing:.3f}s")
        
        # Guardar a historial
        conversation_manager.save_message(phone, "user", message)
        conversation_manager.save_message(phone, "assistant", assistant_reply)
        
        elapsed_total = time.time() - start_time_total
        logger.info(f"✅ [VOICE] Resposta: {assistant_reply[:80]}...")
        logger.info(f"⏱️  [VOICE] ⭐ TEMPS TOTAL: {elapsed_total:.3f}s ⭐")
        logger.info("=" * 80)
        
        return assistant_reply
    
    except Exception as e:
        elapsed_total = time.time() - start_time_total
        logger.error(f"❌ [VOICE] ERROR després de {elapsed_total:.3f}s: {e}")
        import traceback
        traceback.print_exc()
        
        error_msgs = {
            'es': "Lo siento, hubo un error. ¿Puedes repetir?",
            'ca': "Ho sento, hi ha hagut un error. Pots repetir?",
            'en': "Sorry, there was an error. Can you repeat?"
        }
        return error_msgs.get(language, error_msgs['es'])
