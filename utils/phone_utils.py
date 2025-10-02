"""
Utilitats per normalitzar números de telèfon
Extreu el número real de Telegram i WhatsApp
"""

def normalize_phone_number(phone_id):
    """
    Normalitza l'identificador per obtenir només el número
    
    telegram:8308222570 -> 8308222570
    whatsapp:+34696978421 -> +34696978421
    +34696978421 -> +34696978421
    """
    if phone_id.startswith('telegram:'):
        return phone_id.replace('telegram:', '')
    elif phone_id.startswith('whatsapp:'):
        return phone_id.replace('whatsapp:', '')
    else:
        return phone_id
