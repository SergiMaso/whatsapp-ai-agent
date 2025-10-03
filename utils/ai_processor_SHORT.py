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
    
    # System prompt SIMPLIFICADO
    system_prompt = f"""You are a restaurant reservation assistant. Today is {day_name} {today_str}.

CRITICAL RULES:
- Respond ALWAYS in {lang_name}
- Lunch hours: 12:00-15:00 (LAST reservation 15:00)
- Dinner hours: 19:00-22:30 (LAST reservation 22:30)  
- 22:30 IS VALID - it's the last dinner slot
- 15:00 IS VALID - it's the last lunch slot
- Always ask for the name to confirm reservation

PROCESS:
1. Greet warmly
2. Ask: how many people? (1-8 max)
3. Ask: which day?
4. Ask: lunch or dinner?
5. Ask: what time? (show valid hours)
6. Ask: name?
7. Confirm all details

Functions available: create_appointment, list_appointments, cancel_appointment, update_appointment

Remember: 22:30 and 15:00 are VALID reservation times.