"""
Gestor de trucades telefòniques amb Twilio Voice
Conversa fluida sense IVR
"""

from twilio.twiml.voice_response import VoiceResponse
from utils.ai_processor import process_message_with_ai
from utils.appointments import AppointmentManager, ConversationManager

class VoiceHandler:
    """
    Gestiona les trucades telefòniques amb conversa fluida
    """
    
    # Veus naturals per idioma (Twilio Polly)
    VOICES = {
        'ca': 'Polly.Arlet',      # Dona catalana
        'es': 'Polly.Lucia',      # Dona espanyola  
        'en': 'Polly.Joanna'      # Dona anglesa
    }
    
    # Mapeo d'idiomes a Twilio language codes
    LANGUAGE_CODES = {
        'ca': 'ca-ES',
        'es': 'es-ES',
        'en': 'en-US'
    }
    
    # Keywords de confirmació per idioma
    CONFIRMATION_KEYWORDS = {
        'ca': ['sí', 'si', 'correcte', 'ok', 'val', 'd\'acord', 'dacord', 'perfet', 'perfecte'],
        'es': ['sí', 'si', 'correcto', 'vale', 'de acuerdo', 'perfecto', 'ok'],
        'en': ['yes', 'correct', 'ok', 'sure', 'right', 'perfect', 'yeah', 'yep']
    }
    
    # Keywords de negació per idioma
    NEGATION_KEYWORDS = {
        'ca': ['no', 'pas', 'tampoc', 'gens'],
        'es': ['no', 'tampoco', 'nada'],
        'en': ['no', 'nope', 'not', 'nothing']
    }
    
    # Keywords de finalització per idioma
    END_KEYWORDS = {
        'ca': ['adeu', 'adéu', 'gràcies', 'gracies', 'ja està', 'res més', 'prou', 'fins aviat'],
        'es': ['adiós', 'adios', 'gracias', 'ya está', 'nada más', 'hasta luego'],
        'en': ['goodbye', 'bye', 'thanks', 'thank you', 'that\'s all', 'nothing else']
    }
    
    # Salutacions inicials per idioma
    GREETINGS = {
        'ca': "Hola, benvingut a Amaru. Com et puc ajudar?",
        'es': "Hola, bienvenido a Amaru. ¿Cómo te puedo ayudar?",
        'en': "Hello, welcome to Amaru. How can I help you?"
    }
    
    # Preguntes de continuació per idioma
    CONTINUE_PROMPTS = {
        'ca': "Alguna cosa més?",
        'es': "¿Algo más?",
        'en': "Anything else?"
    }
    
    # Missatges de comiat per idioma
    GOODBYE_MESSAGES = {
        'ca': "Perfecte! Ens veiem aviat. Adeu!",
        'es': "¡Perfecto! Nos vemos pronto. ¡Adiós!",
        'en': "Perfect! See you soon. Goodbye!"
    }
    
    def __init__(self):
        self.appointment_manager = AppointmentManager()
        self.conversation_manager = ConversationManager()
    
    def get_voice_for_language(self, language):
        """Obtenir la veu adequada segons l'idioma"""
        return self.VOICES.get(language, self.VOICES['es'])
    
    def get_language_code(self, language):
        """Obtenir el codi d'idioma per Twilio"""
        return self.LANGUAGE_CODES.get(language, self.LANGUAGE_CODES['es'])
    
    def is_confirmation(self, text, language):
        """Detecta si el text és una confirmació"""
        text_lower = text.lower().strip()
        keywords = self.CONFIRMATION_KEYWORDS.get(language, self.CONFIRMATION_KEYWORDS['es'])
        return any(keyword in text_lower for keyword in keywords)
    
    def is_negation(self, text, language):
        """Detecta si el text és una negació"""
        text_lower = text.lower().strip()
        keywords = self.NEGATION_KEYWORDS.get(language, self.NEGATION_KEYWORDS['es'])
        return any(keyword in text_lower for keyword in keywords)
    
    def wants_to_end(self, text, language):
        """Detecta si l'usuari vol acabar la conversa"""
        text_lower = text.lower().strip()
        keywords = self.END_KEYWORDS.get(language, self.END_KEYWORDS['es'])
        
        # Si diu "no" o similar en resposta a "alguna cosa més?"
        if self.is_negation(text, language) and len(text_lower.split()) <= 3:
            return True
        
        return any(keyword in text_lower for keyword in keywords)
    
    def create_initial_response(self, language='es'):
        """
        Crea la resposta inicial de la trucada
        """
        response = VoiceResponse()
        
        greeting = self.GREETINGS.get(language, self.GREETINGS['es'])
        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)
        
        # Salutació inicial
        response.say(greeting, language=lang_code, voice=voice)
        
        # Començar a escoltar (sense transcribe_callback, Twilio ho gestiona auto)
        response.record(
            action='/voice/process',
            method='POST',
            max_length=30,
            timeout=4,
            transcribe=True,
            play_beep=False,
            trim='trim-silence'
        )
        
        return response
    
    def create_response_and_continue(self, ai_text, language, phone, should_continue=True):
        """
        Crea una resposta de veu i continua escoltant
        """
        response = VoiceResponse()
        
        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)
        
        # Dir la resposta de la IA
        response.say(ai_text, language=lang_code, voice=voice)
        
        if should_continue:
            # Preguntar si vol continuar
            continue_prompt = self.CONTINUE_PROMPTS.get(language, self.CONTINUE_PROMPTS['es'])
            response.say(continue_prompt, language=lang_code, voice=voice)
            
            # Continuar escoltant
            response.record(
                action='/voice/process',
                method='POST',
                max_length=30,
                timeout=4,
                transcribe=True,
                play_beep=False,
                trim='trim-silence'
            )
        else:
            # Finalitzar trucada
            goodbye = self.GOODBYE_MESSAGES.get(language, self.GOODBYE_MESSAGES['es'])
            response.say(goodbye, language=lang_code, voice=voice)
            response.hangup()
        
        return response
    
    def process_transcription(self, transcription, phone, call_sid=None):
        """
        Processa la transcripció i genera resposta
        """
        
        # Si no hi ha transcripció vàlida
        if not transcription or transcription.strip() == '':
            return self.create_error_response()
        
        print(f"📞 [VOICE] Transcripció: '{transcription}' del {phone}")
        
        # Netejar prefix si té
        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '')
        
        # Obtenir idioma del client
        language = self.appointment_manager.get_customer_language(clean_phone)
        if not language:
            language = 'es'  # Default
        
        # Detectar si vol acabar la conversa
        if self.wants_to_end(transcription, language):
            print(f"📞 [VOICE] Client vol acabar la conversa")
            response = VoiceResponse()
            voice = self.get_voice_for_language(language)
            lang_code = self.get_language_code(language)
            
            goodbye = self.GOODBYE_MESSAGES.get(language, self.GOODBYE_MESSAGES['es'])
            response.say(goodbye, language=lang_code, voice=voice)
            response.hangup()
            return response
        
        # Processar amb IA (usa el codi existent!)
        try:
            ai_response = process_message_with_ai(
                transcription,
                clean_phone,
                self.appointment_manager,
                self.conversation_manager
            )
            
            print(f"🤖 [VOICE] Resposta IA: '{ai_response}'")
            
            # Actualitzar idioma si ha canviat
            language = self.appointment_manager.get_customer_language(clean_phone) or language
            
            # Crear resposta i continuar
            return self.create_response_and_continue(
                ai_response,
                language,
                clean_phone,
                should_continue=True
            )
            
        except Exception as e:
            print(f"❌ [VOICE] Error processant amb IA: {e}")
            import traceback
            traceback.print_exc()
            return self.create_error_response(language)
    
    def create_error_response(self, language='es'):
        """
        Crea una resposta d'error genèrica
        """
        response = VoiceResponse()
        
        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)
        
        error_messages = {
            'ca': "Ho sento, no t'he entès bé. Pots repetir-ho?",
            'es': "Lo siento, no te he entendido bien. ¿Puedes repetirlo?",
            'en': "Sorry, I didn't understand that. Can you repeat?"
        }
        
        error_msg = error_messages.get(language, error_messages['es'])
        response.say(error_msg, language=lang_code, voice=voice)
        
        # Continuar escoltant
        response.record(
            action='/voice/process',
            method='POST',
            max_length=30,
            timeout=4,
            transcribe=True,
            play_beep=False,
            trim='trim-silence'
        )
        
        return response
    
    def handle_timeout(self, language='es'):
        """
        Gestiona quan l'usuari no respon (timeout)
        """
        response = VoiceResponse()
        
        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)
        
        timeout_messages = {
            'ca': "Sembla que no t'he sentit. Si vols continuar, torna a trucar. Adeu!",
            'es': "Parece que no te he escuchado. Si quieres continuar, vuelve a llamar. ¡Adiós!",
            'en": "It seems I didn't hear you. If you want to continue, call back. Goodbye!"
        }
        
        timeout_msg = timeout_messages.get(language, timeout_messages['es'])
        response.say(timeout_msg, language=lang_code, voice=voice)
        response.hangup()
        
        return response