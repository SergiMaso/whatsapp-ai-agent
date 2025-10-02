"""
Contexto de conversación para detectar cuándo mostrar botones
"""

# Estado temporal de conversaciones (en memoria)
# En producción esto debería estar en la BD
conversation_states = {}

def should_show_time_buttons(phone, message, ai_response):
    """
    Detectar si debemos mostrar botones de hora
    Retorna True si:
    - El bot pregunta por la hora
    - El usuario aún no ha dado una hora específica
    """
    
    # Frases que indican que el bot está pidiendo la hora
    time_request_phrases = {
        'es': ['qué hora', 'hora prefieres', 'horario', 'a qué hora', 'cuando quieres'],
        'ca': ['quina hora', 'hora prefereixes', 'horari', 'a quina hora', 'quan vols'],
        'en': ['what time', 'preferred time', 'when would you', 'what hour']
    }
    
    ai_lower = ai_response.lower()
    
    for lang_phrases in time_request_phrases.values():
        if any(phrase in ai_lower for phrase in lang_phrases):
            # El bot está preguntando por la hora
            # Verificar que el usuario no la haya dado ya
            message_lower = message.lower()
            
            # Si el mensaje del usuario tiene formato de hora, no mostrar botones
            import re
            time_patterns = [
                r'\d{1,2}:\d{2}',  # 14:30
                r'\d{1,2}\s*(h|am|pm)',  # 2pm, 14h
                r'(las|a les|at)\s*\d{1,2}',  # las 2, a les 2
            ]
            
            has_time = any(re.search(pattern, message_lower) for pattern in time_patterns)
            
            if not has_time:
                return True
    
    return False

def get_conversation_state(phone):
    """Obtener estado de la conversación"""
    return conversation_states.get(phone, {})

def set_conversation_state(phone, key, value):
    """Guardar estado de la conversación"""
    if phone not in conversation_states:
        conversation_states[phone] = {}
    conversation_states[phone][key] = value

def get_conversation_language(phone):
    """Obtener idioma de la conversación actual"""
    state = get_conversation_state(phone)
    return state.get('language', 'ca')  # Default catalán

def set_conversation_language(phone, language):
    """Guardar idioma de la conversación"""
    set_conversation_state(phone, 'language', language)

def clear_conversation_state(phone):
    """Limpiar estado de la conversación"""
    if phone in conversation_states:
        del conversation_states[phone]
