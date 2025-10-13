"""
Utilitats per gestionar identificadors d'usuaris
Extreu el número de telèfon real de Telegram i WhatsApp
"""

def extract_phone_number(user_id):
    """
    Extreu el número de telèfon real de l'identificador
    
    Input:
        telegram:8308222570 -> +34XXXXXXXXX (del perfil de Telegram si està disponible)
        whatsapp:+34696978421 -> +34696978421
    
    Output:
        Número de telèfon normalitzat
    """
    if user_id.startswith('whatsapp:'):
        # WhatsApp ja té el número
        return user_id.replace('whatsapp:', '')
    
    elif user_id.startswith('telegram:'):
        # Telegram només té user_id, retornem l'ID per ara
        # En producció podries demanar el telèfon a l'usuari
        return f"tg_{user_id.replace('telegram:', '')}"
    
    return user_id

def get_user_identifier(user_id):
    """
    Genera un identificador únic per l'usuari
    Prioritza número de telèfon real
    """
    return extract_phone_number(user_id)
