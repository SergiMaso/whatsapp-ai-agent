from twilio.twiml.voice_response import VoiceResponse
from utils.ai_processor import process_message_with_ai
from utils.appointments import AppointmentManager, ConversationManager

class VoiceHandler:
    """
    Gestiona les trucades telefòniques amb conversa fluida
    """
    
    # Veus naturals per idioma (Twilio Polly)
    VOICES = {
        'ca': 'Polly.Arlet',
        'es': 'Polly.Lucia',
        'en': 'Polly.Joanna'
    }
    
    LANGUAGE_CODES = {
        'ca': 'ca-ES',
        'es': 'es-ES',
        'en': 'en-US'
    }
    
    CONFIRMATION_KEYWORDS = {
        'ca': ['sí', 'si', 'correcte', 'ok', 'val', 'd\'acord', 'dacord', 'perfet', 'perfecte'],
        'es': ['sí', 'si', 'correcto', 'vale', 'de acuerdo', 'perfecto', 'ok'],
        'en': ['yes', 'correct', 'ok', 'sure', 'right', 'perfect', 'yeah', 'yep']
    }
    
    NEGATION_KEYWORDS = {
        'ca': ['no', 'pas', 'tampoc', 'gens'],
        'es': ['no', 'tampoco', 'nada'],
        'en': ['no', 'nope', 'not', 'nothing']
    }
    
    END_KEYWORDS = {
        'ca': ['adeu', 'adéu', 'gràcies', 'gracies', 'ja està', 'res més', 'prou', 'fins aviat'],
        'es': ['adiós', 'adios', 'gracias', 'ya está', 'nada más', 'hasta luego'],
        'en': ['goodbye', 'bye', 'thanks', 'thank you', 'that\'s all', 'nothing else']
    }
    
    GREETINGS = {
        'ca': "Hola, benvingut a Amaru. Com et puc ajudar?",
        'es': "Hola, bienvenido a Amaru. ¿Cómo te puedo ayudar?",
        'en': "Hello, welcome to Amaru. How can I help you?"
    }
    
    CONTINUE_PROMPTS = {
        'ca': "Alguna cosa més?",
        'es': "¿Algo más?",
        'en': "Anything else?"
    }
    
    GOODBYE_MESSAGES = {
        'ca': "Perfecte! Ens veiem aviat. Adeu!",
        'es': "¡Perfecto! Nos vemos pronto. ¡Adiós!",
        'en': "Perfect! See you soon. Goodbye!"
    }
    
    def __init__(self):
        print("🎙️ [VOICE_HANDLER] Inicialitzant VoiceHandler...")
        self.appointment_manager = AppointmentManager()
        self.conversation_manager = ConversationManager()
        print("✅ [VOICE_HANDLER] VoiceHandler inicialitzat correctament")
    
    def get_voice_for_language(self, language):
        voice = self.VOICES.get(language, self.VOICES['es'])
        print(f"🔊 [VOICE_HANDLER] Veu seleccionada: {voice} per idioma {language}")
        return voice
    
    def get_language_code(self, language):
        code = self.LANGUAGE_CODES.get(language, self.LANGUAGE_CODES['es'])
        print(f"🌍 [VOICE_HANDLER] Codi idioma: {code}")
        return code
    
    def is_confirmation(self, text, language):
        text_lower = text.lower().strip()
        keywords = self.CONFIRMATION_KEYWORDS.get(language, self.CONFIRMATION_KEYWORDS['es'])
        result = any(keyword in text_lower for keyword in keywords)
        print(f"✅ [VOICE_HANDLER] És confirmació? {result} - Text: '{text}'")
        return result
    
    def is_negation(self, text, language):
        text_lower = text.lower().strip()
        keywords = self.NEGATION_KEYWORDS.get(language, self.NEGATION_KEYWORDS['es'])
        result = any(keyword in text_lower for keyword in keywords)
        print(f"❌ [VOICE_HANDLER] És negació? {result} - Text: '{text}'")
        return result
    
    def wants_to_end(self, text, language):
        print(f"🔍 [VOICE_HANDLER] Comprovant si vol acabar: '{text}'")
        text_lower = text.lower().strip()
        keywords = self.END_KEYWORDS.get(language, self.END_KEYWORDS['es'])
        
        if self.is_negation(text, language) and len(text_lower.split()) <= 3:
            print("👋 [VOICE_HANDLER] Detectada negació curta - Vol acabar")
            return True
        
        result = any(keyword in text_lower for keyword in keywords)
        print(f"👋 [VOICE_HANDLER] Vol acabar? {result}")
        return result
    
    def create_initial_response(self, language='es'):
        print(f"📞 [VOICE_HANDLER] Creant resposta inicial (idioma: {language})")
        
        if language == 'ca':
            language = 'es'  # Twilio no suporta català
        
        response = VoiceResponse()
        
        greeting = self.GREETINGS.get(language, self.GREETINGS['es'])
        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)
        
        # Usar Gather (més ràpid que Record)
        gather = response.gather(
            input='speech',
            action='/voice/process',
            method='POST',
            language=lang_code,
            timeout=3,
            speech_timeout='auto',
            profanity_filter=False
        )
        
        gather.say(greeting, language=lang_code, voice=voice)
        
        # Si no respon
        response.say("No t'he sentit. Adéu!", language=lang_code, voice=voice)
        response.hangup()
        
        return response
        
    
    def create_response_and_continue(self, ai_text, language, phone, should_continue=True):
        print(f"🤖 [VOICE_HANDLER] Creant resposta amb text IA: '{ai_text[:100]}...'")
        print(f"🔄 [VOICE_HANDLER] Continuar? {should_continue}")
        
        response = VoiceResponse()
        
        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)
        
        # Dir la resposta de la IA
        print(f"💬 [VOICE_HANDLER] Dient resposta IA...")
        response.say(ai_text, language=lang_code, voice=voice)
        
        if should_continue:
            continue_prompt = self.CONTINUE_PROMPTS.get(language, self.CONTINUE_PROMPTS['es'])
            print(f"❓ [VOICE_HANDLER] Preguntant si vol continuar: '{continue_prompt}'")
            response.say(continue_prompt, language=lang_code, voice=voice)
            
            # Continuar escoltant
            print("🎤 [VOICE_HANDLER] Configurant nova gravació...")
            response.record(
                action='/voice/process',
                method='POST',
                max_length=30,
                timeout=5,
                transcribe=True,
                transcribeCallback='/voice/transcription',
                play_beep=False,
                finish_on_key='#'
            )
        else:
            goodbye = self.GOODBYE_MESSAGES.get(language, self.GOODBYE_MESSAGES['es'])
            print(f"👋 [VOICE_HANDLER] Finalitzant amb comiat: '{goodbye}'")
            response.say(goodbye, language=lang_code, voice=voice)
            response.hangup()
            print("📞 [VOICE_HANDLER] Trucada penjada")
        
        twiml = str(response)
        print(f"📋 [VOICE_HANDLER] TwiML resposta:\n{twiml}")
        
        return response
    
    def process_transcription(self, transcription, phone, call_sid=None):
        print("=" * 80)
        print(f"🎯 [VOICE_HANDLER] PROCESSANT TRANSCRIPCIÓ")
        print(f"📝 [VOICE_HANDLER] Text: '{transcription}'")
        print(f"📞 [VOICE_HANDLER] Telèfon: {phone}")
        print(f"🆔 [VOICE_HANDLER] CallSid: {call_sid}")
        print("=" * 80)
        
        if not transcription or transcription.strip() == '':
            print("⚠️  [VOICE_HANDLER] Transcripció buida!")
            return self.create_error_response()
        
        # Netejar prefix
        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '')
        print(f"📱 [VOICE_HANDLER] Telèfon net: {clean_phone}")
        
        # Obtenir idioma del client
        language = self.appointment_manager.get_customer_language(clean_phone)
        if not language:
            print("🌍 [VOICE_HANDLER] Client nou, idioma per defecte: es")
            language = 'es'
        else:
            print(f"🌍 [VOICE_HANDLER] Idioma del client: {language}")
        
        # Detectar si vol acabar
        if self.wants_to_end(transcription, language):
            print("🚪 [VOICE_HANDLER] Client vol acabar la conversa")
            response = VoiceResponse()
            voice = self.get_voice_for_language(language)
            lang_code = self.get_language_code(language)
            
            goodbye = self.GOODBYE_MESSAGES.get(language, self.GOODBYE_MESSAGES['es'])
            response.say(goodbye, language=lang_code, voice=voice)
            response.hangup()
            print("👋 [VOICE_HANDLER] Enviant comiat i penjant")
            return response
        
        # Processar amb IA
        try:
            print("🧠 [VOICE_HANDLER] Cridant a process_message_with_ai...")
            ai_response = process_message_with_ai(
                transcription,
                clean_phone,
                self.appointment_manager,
                self.conversation_manager
            )
            
            print(f"✅ [VOICE_HANDLER] Resposta IA rebuda: '{ai_response[:100]}...'")
            
            # Actualitzar idioma si ha canviat
            new_language = self.appointment_manager.get_customer_language(clean_phone)
            if new_language and new_language != language:
                print(f"🌍 [VOICE_HANDLER] Idioma actualitzat: {language} → {new_language}")
                language = new_language
            
            # Crear resposta i continuar
            print("📤 [VOICE_HANDLER] Creant resposta per continuar conversa...")
            return self.create_response_and_continue(
                ai_response,
                language,
                clean_phone,
                should_continue=True
            )
            
        except Exception as e:
            print(f"❌ [VOICE_HANDLER] ERROR processant amb IA: {e}")
            import traceback
            print("📋 [VOICE_HANDLER] Traceback:")
            traceback.print_exc()
            return self.create_error_response(language)
    
    def create_error_response(self, language='es'):
        print(f"⚠️  [VOICE_HANDLER] Creant resposta d'error (idioma: {language})")
        response = VoiceResponse()
        
        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)
        
        error_messages = {
            'ca': "Ho sento, no t'he entès bé. Pots repetir-ho?",
            'es': "Lo siento, no te he entendido bien. ¿Puedes repetirlo?",
            'en': "Sorry, I didn't understand that. Can you repeat?"
        }
        
        error_msg = error_messages.get(language, error_messages['es'])
        print(f"💬 [VOICE_HANDLER] Missatge error: '{error_msg}'")
        response.say(error_msg, language=lang_code, voice=voice)
        
        # Continuar escoltant
        print("🎤 [VOICE_HANDLER] Configurant nova gravació després d'error...")
        response.record(
            action='/voice/process',
            method='POST',
            max_length=30,
            timeout=5,
            transcribe=True,
            transcribeCallback='/voice/transcription',
            play_beep=False,
            finish_on_key='#'
        )
        
        return response
    
    def handle_timeout(self, language='es'):
        print(f"⏰ [VOICE_HANDLER] Gestionant timeout (idioma: {language})")
        response = VoiceResponse()
        
        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)
        
        timeout_messages = {
            'ca': "Sembla que no t'he sentit. Si vols continuar, torna a trucar. Adeu!",
            'es': "Parece que no te he escuchado. Si quieres continuar, vuelve a llamar. Adiós!",
            'en': "It seems I did not hear you. If you want to continue, call back. Goodbye!"
        }
        
        timeout_msg = timeout_messages.get(language, timeout_messages['es'])
        print(f"💬 [VOICE_HANDLER] Missatge timeout: '{timeout_msg}'")
        response.say(timeout_msg, language=lang_code, voice=voice)
        response.hangup()
        print("📞 [VOICE_HANDLER] Penjant per timeout")
        
        return response