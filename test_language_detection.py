"""
Test de detecció d'idioma millorat
"""

from utils.ai_processor import detect_language

# Tests de detecció d'idioma
test_cases = [
    ("Hello", "en"),
    ("Hi", "en"),
    ("I want to make a reservation", "en"),
    ("Lunch", "en"),
    ("Dinner", "en"),
    ("Hola", "ca"),  # Ambiguo, default catalán
    ("Bon dia", "ca"),
    ("Vull fer una reserva", "ca"),
    ("Dinar", "ca"),
    ("Quiero hacer una reserva", "es"),
    ("Buenos días", "es"),
    ("Comida", "es"),
]

print("🧪 Test de detecció d'idioma\n")
print("=" * 50)

for text, expected_lang in test_cases:
    detected = detect_language(text)
    status = "✅" if detected == expected_lang else "❌"
    print(f"{status} '{text}' -> Detectat: {detected}, Esperat: {expected_lang}")

print("=" * 50)
