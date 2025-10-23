# -*- coding: utf-8 -*-
import os
import logging
from twilio.twiml.voice_response import VoiceResponse
from utils.ai_processor import process_message_with_ai
from utils.appointments import AppointmentManager, ConversationManager
from utils.ai_processor_voice import process_voice_with_ai

# Configuració de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class VoiceHandler:
    """
    Gestiona les trucades telefòniques amb conversa fluida (Twilio + IA)
    """

    # Veus naturals per idioma (Twilio Polly)
    VOICES = {
        'ca': 'Polly.Lucia',   # Twilio no suporta català, s’usa veu espanyola
        'es': 'Polly.Lucia',
        'en': 'Polly.Joanna'
    }

    LANGUAGE_CODES = {
        'ca': 'es-ES',
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

    GREETINGS_WITH_KNOWN_CUSTOMER = {
        'ca': "Hola {saved_customer}, benvingut a Amaru. Com et puc ajudar?",
        'es': "Hola {saved_customer}, bienvenido a Amaru. ¿Cómo te puedo ayudar?",
        'en': "Hello {saved_customer}, welcome to Amaru. How can I help you?"
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
        logger.info("🎙️ Inicialitzant VoiceHandler...")
        self.appointment_manager = AppointmentManager()
        self.conversation_manager = ConversationManager()
        logger.info("✅ VoiceHandler inicialitzat correctament")

    # ======================================================================
    # UTILITATS
    # ======================================================================
    def get_voice_for_language(self, language):
        voice = self.VOICES.get(language, self.VOICES['es'])
        logger.debug(f"Veu seleccionada: {voice} per idioma {language}")
        return voice

    def get_language_code(self, language):
        code = self.LANGUAGE_CODES.get(language, self.LANGUAGE_CODES['es'])
        return code

    def is_confirmation(self, text, language):
        text_lower = text.lower().strip()
        keywords = self.CONFIRMATION_KEYWORDS.get(language, self.CONFIRMATION_KEYWORDS['es'])
        return any(keyword in text_lower for keyword in keywords)

    def is_negation(self, text, language):
        text_lower = text.lower().strip()
        keywords = self.NEGATION_KEYWORDS.get(language, self.NEGATION_KEYWORDS['es'])
        return any(keyword in text_lower for keyword in keywords)

    def wants_to_end(self, text, language):
        text_lower = text.lower().strip()
        keywords = self.END_KEYWORDS.get(language, self.END_KEYWORDS['es'])

        if self.is_negation(text, language) and len(text_lower.split()) <= 3:
            return True

        return any(keyword in text_lower for keyword in keywords)

    # ======================================================================
    # RESPOSTES DE TWILIO
    # ======================================================================
    def create_initial_response(self, language='es', phone=None):
        logger.info(f"📞 Creant resposta inicial (idioma: {language})")

        response = VoiceResponse()
        clean_phone = (phone or '').replace('whatsapp:', '').replace('telegram:', '')

        language = self.appointment_manager.get_customer_language(clean_phone) or 'es'
        saved_customer = self.appointment_manager.get_customer_name(clean_phone)

        # Escollir missatge de benvinguda
        if saved_customer:
            greeting_template = self.GREETINGS_WITH_KNOWN_CUSTOMER.get(language, self.GREETINGS_WITH_KNOWN_CUSTOMER['es'])
            greeting = greeting_template.replace('{saved_customer}', saved_customer)
        else:
            greeting = self.GREETINGS.get(language, self.GREETINGS['es'])

        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)

        gather = response.gather(
            input='speech',
            action='/voice/process',
            method='POST',
            language=lang_code,
            timeout=5,
            speech_timeout='auto'
        )

        gather.say(greeting, language=lang_code, voice=voice)

        # Si no respon
        response.say("No t'he sentit. Adéu!", language=lang_code, voice=voice)
        response.hangup()

        return response

    def create_response_and_continue(self, ai_text, language, phone, should_continue=True):
        logger.info(f"🤖 Creant resposta amb IA: '{ai_text[:80]}...'")
        response = VoiceResponse()

        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)

        response.say(ai_text, language=lang_code, voice=voice)

        if should_continue:
            continue_prompt = self.CONTINUE_PROMPTS.get(language, self.CONTINUE_PROMPTS['es'])
            response.say(continue_prompt, language=lang_code, voice=voice)

            response.gather(
                input='speech',
                action='/voice/process',
                method='POST',
                language=lang_code,
                timeout=5,
                speech_timeout='auto'
            )
        else:
            goodbye = self.GOODBYE_MESSAGES.get(language, self.GOODBYE_MESSAGES['es'])
            response.say(goodbye, language=lang_code, voice=voice)
            response.hangup()

        return response

    # ======================================================================
    # PROCESSAMENT DE TRANSCRIPCIÓ
    # ======================================================================
    def process_transcription(self, transcription, phone, call_sid=None):
        logger.info("=" * 70)
        logger.info(f"🎯 Processant transcripció: {transcription}")
        logger.info(f"📞 Telèfon: {phone}")
        logger.info(f"🆔 CallSid: {call_sid}")
        logger.info("=" * 70)

        if not transcription or transcription.strip() == '':
            return self.create_error_response()

        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '')
        language = self.appointment_manager.get_customer_language(clean_phone) or 'es'

        if self.wants_to_end(transcription, language):
            response = VoiceResponse()
            voice = self.get_voice_for_language(language)
            lang_code = self.get_language_code(language)
            goodbye = self.GOODBYE_MESSAGES.get(language, self.GOODBYE_MESSAGES['es'])
            response.say(goodbye, language=lang_code, voice=voice)
            response.hangup()
            return response

        try:
            ai_response = process_voice_with_ai(
                transcription,
                clean_phone,
                self.appointment_manager,
                self.conversation_manager
            )

            if not ai_response or not ai_response.strip():
                ai_response = "Perdona, pots repetir-ho?"

            new_language = self.appointment_manager.get_customer_language(clean_phone)
            if new_language and new_language != language:
                language = new_language

            return self.create_response_and_continue(ai_response, language, clean_phone, should_continue=True)

        except Exception as e:
            logger.exception(f"❌ Error processant amb IA: {e}")
            return self.create_error_response(language)

    # ======================================================================
    # RESPOSTES D'ERROR I TIMEOUT
    # ======================================================================
    def create_error_response(self, language='es'):
        response = VoiceResponse()
        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)

        error_messages = {
            'ca': "Ho sento, no t'he entès bé. Pots repetir-ho?",
            'es': "Lo siento, no te he entendido bien. ¿Puedes repetirlo?",
            'en': "Sorry, I didn't understand that. Can you repeat?"
        }

        response.say(error_messages.get(language, error_messages['es']),
                     language=lang_code, voice=voice)

        response.gather(
            input='speech',
            action='/voice/process',
            method='POST',
            language=lang_code,
            timeout=5,
            speech_timeout='auto'
        )

        return response

    def handle_timeout(self, language='es'):
        response = VoiceResponse()
        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)

        timeout_messages = {
            'ca': "Sembla que no t'he sentit. Si vols continuar, torna a trucar. Adeu!",
            'es': "Parece que no te he escuchado. Si quieres continuar, vuelve a llamar. ¡Adiós!",
            'en': "It seems I did not hear you. If you want to continue, call back. Goodbye!"
        }

        response.say(timeout_messages.get(language, timeout_messages['es']),
                     language=lang_code, voice=voice)
        response.hangup()
        return response
