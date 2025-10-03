"""
Teclados inline (botones) para Telegram
Muestra opciones de horario cuando el usuario no especifica una hora
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_time_slots_keyboard(language='es'):
    """
    Generar teclado con opciones de horario
    """
    
    if language == 'ca':
        lunch_label = "🍽️ Dinar"
        dinner_label = "🌙 Sopar"
    elif language == 'es':
        lunch_label = "🍽️ Comida"
        dinner_label = "🌙 Cena"
    else:
        lunch_label = "🍽️ Lunch"
        dinner_label = "🌙 Dinner"
    
    keyboard = [
        [InlineKeyboardButton(lunch_label, callback_data='time_category_lunch')],
        [InlineKeyboardButton(dinner_label, callback_data='time_category_dinner')]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_lunch_times_keyboard(language='es'):
    """
    Horarios de comida: 12:00, 12:30, 13:00, 13:30, 14:00, 14:30, 15:00
    """
    
    keyboard = [
        [
            InlineKeyboardButton("12:00", callback_data='time_12:00'),
            InlineKeyboardButton("12:30", callback_data='time_12:30'),
            InlineKeyboardButton("13:00", callback_data='time_13:00')
        ],
        [
            InlineKeyboardButton("13:30", callback_data='time_13:30'),
            InlineKeyboardButton("14:00", callback_data='time_14:00'),
            InlineKeyboardButton("14:30", callback_data='time_14:30')
        ],
        [
            InlineKeyboardButton("15:00", callback_data='time_15:00'),
            InlineKeyboardButton("⬅️ Tornar" if language == 'ca' else "⬅️ Volver", callback_data='back_to_categories')
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_dinner_times_keyboard(language='es'):
    """
    Horarios de cena: 19:00, 19:30, 20:00, 20:30, 21:00, 21:30, 22:00, 22:30
    """
    
    keyboard = [
        [
            InlineKeyboardButton("19:00", callback_data='time_19:00'),
            InlineKeyboardButton("19:30", callback_data='time_19:30'),
            InlineKeyboardButton("20:00", callback_data='time_20:00')
        ],
        [
            InlineKeyboardButton("20:30", callback_data='time_20:30'),
            InlineKeyboardButton("21:00", callback_data='time_21:00'),
            InlineKeyboardButton("21:30", callback_data='time_21:30')
        ],
        [
            InlineKeyboardButton("22:00", callback_data='time_22:00'),
            InlineKeyboardButton("22:30", callback_data='time_22:30'),
            InlineKeyboardButton("⬅️ Tornar" if language == 'ca' else "⬅️ Volver", callback_data='back_to_categories')
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)

def get_confirmation_keyboard(language='es'):
    """
    Botones de confirmación Sí/No
    """
    
    if language == 'ca':
        yes_text = "✅ Sí, confirmar"
        no_text = "❌ No, cancel·lar"
    elif language == 'es':
        yes_text = "✅ Sí, confirmar"
        no_text = "❌ No, cancelar"
    else:
        yes_text = "✅ Yes, confirm"
        no_text = "❌ No, cancel"
    
    keyboard = [
        [InlineKeyboardButton(yes_text, callback_data='confirm_yes')],
        [InlineKeyboardButton(no_text, callback_data='confirm_no')]
    ]
    
    return InlineKeyboardMarkup(keyboard)
