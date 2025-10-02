"""
Script para probar el bot localmente SIN Twilio
Simula conversaciones directamente
"""

from utils.appointments import AppointmentManager, ConversationManager
from utils.ai_processor import process_message_with_ai

# Inicializar gestores
appointment_manager = AppointmentManager()
conversation_manager = ConversationManager()

# Simular un número de teléfono
test_phone = "whatsapp:+34696978421"

print("=" * 60)
print("🤖 BOT DE RESERVAS - MODO PRUEBA LOCAL")
print("=" * 60)
print("\nEscribe 'salir' para terminar")
print("Escribe 'reset' para limpiar el historial\n")

while True:
    # Obtener mensaje del usuario
    user_message = input("\n💬 Tú: ")
    
    if user_message.lower() == 'salir':
        print("\n👋 ¡Hasta luego!")
        break
    
    if user_message.lower() == 'reset':
        conversation_manager.clear_history(test_phone)
        print("\n🔄 Historial limpiado")
        continue
    
    if not user_message.strip():
        continue
    
    # Procesar con IA
    print("\n⏳ Procesando...")
    response = process_message_with_ai(
        user_message, 
        test_phone, 
        appointment_manager, 
        conversation_manager
    )
    
    # Mostrar respuesta
    print(f"\n🤖 Bot: {response}")
    print("-" * 60)

print("\n✅ Prueba completada")
