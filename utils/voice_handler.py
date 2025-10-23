# -*- coding: utf-8 -*-
import os
import time
import logging
from twilio.twiml.voice_response import VoiceResponse
from utils.ai_processor_voice import process_voice_with_ai
from utils.appointments import AppointmentManager, ConversationManager

# Configuració de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class VoiceHandler:
    """
    Gestiona les trucades telefòniques amb conversa fluida (Twilio + IA)
    OPTIMITZAT per latència mínima
    """

    # Veus naturals per idioma (Twilio Polly)
    VOICES = {
        'ca': 'Google.es-ES-Neural2-A',  # Veu femenina espanyola
        'es': 'Google.es-ES-Neural2-C',  # Veu masculina espanyola
        'en': 'Google.en-US-Neural2-F'   # Veu femenina anglesa
    }

    LANGUAGE_CODES = {
        'ca': 'es-ES',
        'es': 'es-ES',
        'en': 'en-US'
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
        return voice

    def get_language_code(self, language):
        code = self.LANGUAGE_CODES.get(language, self.LANGUAGE_CODES['es'])
        return code

    def wants_to_end(self, text, language):
        text_lower = text.lower().strip()
        keywords = self.END_KEYWORDS.get(language, self.END_KEYWORDS['es'])
        
        # També detectar "no" curt
        if text_lower in ['no', 'res', 'nada', 'nothing']:
            return True
            
        return any(keyword in text_lower for keyword in keywords)

    # ======================================================================
    # RESPOSTES DE TWILIO
    # ======================================================================
    def create_initial_response(self, language='es', phone=None):
        start_time = time.time()
        logger.info(f"📞 [HANDLER] Creant resposta inicial (idioma: {language})")

        response = VoiceResponse()
        clean_phone = (phone or '').replace('whatsapp:', '').replace('telegram:', '')

        language = self.appointment_manager.get_customer_language(clean_phone) or 'es'
        saved_customer = self.appointment_manager.get_customer_name(clean_phone)

        # Escollir missatge de benvinguda
        if saved_customer:
            greeting_template = self.GREETINGS_WITH_KNOWN_CUSTOMER.get(language, self.GREETINGS_WITH_KNOWN_CUSTOMER['es'])
            greeting = greeting_template.replace('{saved_customer}', saved_customer)
            logger.info(f"👤 [HANDLER] Client conegut: {saved_customer}")
        else:
            greeting = self.GREETINGS.get(language, self.GREETINGS['es'])
            logger.info(f"🆕 [HANDLER] Client nou")

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
        
        elapsed = time.time() - start_time
        logger.info(f"⏱️  [HANDLER] Resposta inicial creada en {elapsed:.3f}s")

        return response

    def create_response_and_continue(self, ai_text, language, phone, should_continue=True):
        start_time = time.time()
        logger.info(f"🤖 [HANDLER] Creant resposta TwiML...")
        
        response = VoiceResponse()

        voice = self.get_voice_for_language(language)
        lang_code = self.get_language_code(language)

        # Resposta de la IA
        response.say(ai_text, language=lang_code, voice=voice)

        if should_continue:
            # SENSE preguntar "Alguna cosa més?" per reduir latència
            # Directament esperar input
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
        
        elapsed = time.time() - start_time
        logger.info(f"⏱️  [HANDLER] TwiML creat en {elapsed:.3f}s")

        return response

    # ======================================================================
    # PROCESSAMENT DE TRANSCRIPCIÓ
    # ======================================================================
    def process_transcription(self, transcription, phone, call_sid=None):
        start_time_total = time.time()
        
        logger.info("=" * 70)
        logger.info(f"🎯 [HANDLER] Processant transcripció: {transcription}")
        logger.info(f"📞 [HANDLER] Telèfon: {phone}")
        logger.info(f"🆔 [HANDLER] CallSid: {call_sid}")
        logger.info("=" * 70)

        if not transcription or transcription.strip() == '':
            logger.warning("⚠️  [HANDLER] Transcripció buida")
            return self.create_error_response()

        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '')
        
        # Obtenir idioma
        start_time_lang = time.time()
        language = self.appointment_manager.get_customer_language(clean_phone) or 'es'
        elapsed_lang = time.time() - start_time_lang
        logger.info(f"⏱️  [HANDLER] Idioma obtingut en {elapsed_lang:.3f}s: {language}")

        # Detectar si vol acabar
        if self.wants_to_end(transcription, language):
            logger.info("👋 [HANDLER] Usuari vol acabar la trucada")
            response = VoiceResponse()
            voice = self.get_voice_for_language(language)
            lang_code = self.get_language_code(language)
            goodbye = self.GOODBYE_MESSAGES.get(language, self.GOODBYE_MESSAGES['es'])
            response.say(goodbye, language=lang_code, voice=voice)
            response.hangup()
            
            elapsed_total = time.time() - start_time_total
            logger.info(f"⏱️  [HANDLER] ⭐ TEMPS TOTAL HANDLER: {elapsed_total:.3f}s ⭐")
            
            return response

        try:
            # Cridar AI processor (aquí és on es fa la major part del treball)
            start_time_ai = time.time()
            logger.info("🤖 [HANDLER] Cridant AI processor...")
            
            ai_response = process_voice_with_ai(
                transcription,
                clean_phone,
                self.appointment_manager,
                self.conversation_manager
            )
            
            elapsed_ai = time.time() - start_time_ai
            logger.info(f"⏱️  [HANDLER] AI processor ha trigat {elapsed_ai:.3f}s")

            if not ai_response or not ai_response.strip():
                logger.warning("⚠️  [HANDLER] Resposta IA buida")
                ai_response = "Perdona, pots repetir-ho?"

            # Comprovar si l'idioma ha canviat
            new_language = self.appointment_manager.get_customer_language(clean_phone)
            if new_language and new_language != language:
                logger.info(f"🔄 [HANDLER] Idioma canviat: {language} → {new_language}")
                language = new_language

            # Crear resposta TwiML
            start_time_twiml = time.time()
            response = self.create_response_and_continue(ai_response, language, clean_phone, should_continue=True)
            elapsed_twiml = time.time() - start_time_twiml
            logger.info(f"⏱️  [HANDLER] TwiML generat en {elapsed_twiml:.3f}s")
            
            elapsed_total = time.time() - start_time_total
            logger.info(f"⏱️  [HANDLER] ⭐ TEMPS TOTAL HANDLER: {elapsed_total:.3f}s ⭐")
            logger.info("=" * 70)
            
            return response

        except Exception as e:
            elapsed_total = time.time() - start_time_total
            logger.exception(f"❌ [HANDLER] ERROR després de {elapsed_total:.3f}s: {e}")
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
