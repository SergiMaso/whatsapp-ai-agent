"""
Test mode for the restaurant reservation bot
Allows direct interaction without WhatsApp or Telegram
"""

import os
from src.core.ai_processor import process_message_with_ai
from src.core.appointments import AppointmentManager, ConversationManager
from src.config.settings import AI_PROVIDER

def main():
    print("=" * 60)
    print("🧪 BOT TEST MODE")
    print("=" * 60)
    print(f"🤖 AI Provider: {AI_PROVIDER.upper()}")
    print("📱 Simulating WhatsApp/Telegram messages")
    print("💡 Type 'quit' or 'exit' to stop")
    print("=" * 60)
    
    # Initialize managers
    appointment_manager = AppointmentManager()
    conversation_manager = ConversationManager()
    
    # Test phone number
    test_phone = "test:+1234567890"
    
    print("\n🤖 Bot: Hello! I'm the restaurant reservation bot. How can I help you?")
    
    while True:
        try:
            # Get user input
            user_input = input("\n👤 You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            if not user_input:
                continue
            
            # Process with AI
            print("🤖 Bot: ", end="", flush=True)
            response = process_message_with_ai(
                user_input,
                test_phone,
                appointment_manager,
                conversation_manager
            )
            
            print(response)
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("Please try again.")

if __name__ == '__main__':
    main()