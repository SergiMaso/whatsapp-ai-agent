# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
import logging
from urllib.parse import quote

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ElevenLabsAgentManager:
    """
    Gestor per l'agent conversacional d'Eleven Labs
    """
    
    def __init__(self):
        self.api_key = os.getenv('ELEVEN_LABS_API_KEY')
        if not self.api_key:
            logger.error("⚠️  ELEVEN_LABS_API_KEY no configurada!")
            raise ValueError("Necessites configurar ELEVEN_LABS_API_KEY al .env")
        
        self.client = ElevenLabs(api_key=self.api_key)
        self.agent_id = os.getenv('ELEVEN_LABS_AGENT_ID')
        
        logger.info("✅ ElevenLabsAgentManager inicialitzat")
    
    def get_agent_config(self, language='es'):
        """
        Retorna la configuració de l'agent segons idioma
        """
        
        prompts = {
            'ca': """Ets l'assistent de reserves del restaurant Amaru a Barcelona.

PERSONALITAT:
- Càlid, proper i professional
- Eficient i directe
- Parles en català de manera natural

TASQUES:
1. Ajudar a crear reserves (nom, data, hora, número de persones)
2. Consultar reserves existents
3. Modificar reserves
4. Cancel·lar reserves

HORARIS DEL RESTAURANT:
- Dinar: 12:00 a 15:00
- Sopar: 19:00 a 22:30
- Capacitat: 1-8 persones per reserva

IMPORTANT:
- Sigues molt breu i directe (màxim 2 frases)
- NO facis preguntes innecessàries
- Quan tinguis tota la info, crida la funció directament
- Sempre confirma les reserves de manera clara i natural""",

            'es': """Eres el asistente de reservas del restaurante Amaru en Barcelona.

PERSONALIDAD:
- Cálido, cercano y profesional
- Eficiente y directo
- Hablas en español de manera natural

TAREAS:
1. Ayudar a crear reservas (nombre, fecha, hora, número de personas)
2. Consultar reservas existentes
3. Modificar reservas
4. Cancelar reservas

HORARIOS DEL RESTAURANTE:
- Comida: 12:00 a 15:00
- Cena: 19:00 a 22:30
- Capacidad: 1-8 personas por reserva

IMPORTANTE:
- Sé muy breve y directo (máximo 2 frases)
- NO hagas preguntas innecesarias
- Cuando tengas toda la info, llama a la función directamente
- Siempre confirma las reservas de manera clara y natural""",

            'en': """You are the reservation assistant for Amaru restaurant in Barcelona.

PERSONALITY:
- Warm, friendly and professional
- Efficient and direct
- You speak English naturally

TASKS:
1. Help create reservations (name, date, time, number of people)
2. Check existing reservations
3. Modify reservations
4. Cancel reservations

RESTAURANT HOURS:
- Lunch: 12:00 to 15:00
- Dinner: 19:00 to 22:30
- Capacity: 1-8 people per reservation

IMPORTANT:
- Be very brief and direct (max 2 sentences)
- DON'T ask unnecessary questions
- When you have all info, call the function directly
- Always confirm reservations clearly and naturally"""
        }
        
        return prompts.get(language, prompts['es'])
    
    def create_or_update_agent(self, language='es'):
        """
        Crear o actualitzar l'agent d'Eleven Labs
        
        NOTA: Això es fa un cop via dashboard o API.
        Aquest mètode és per referència, normalment ho fas manualment.
        """
        
        try:
            # Configuració de l'agent
            agent_config = {
                "name": f"Amaru Restaurant Agent ({language.upper()})",
                "prompt": self.get_agent_config(language),
                
                # Veu (Rachel - molt natural)
                "voice_id": "21m00Tcm4TlvDq8ikWAM",
                
                # Idioma
                "language": language if language != 'ca' else 'es',  # Eleven Labs no té català natiu
                
                # Configuració de conversa
                "conversation_config": {
                    "turn_timeout": 5,  # Segons d'espera abans de timeout
                },
                
                # Funcions que pot cridar
                "functions": [
                    {
                        "name": "create_appointment",
                        "description": "Crear una reserva al restaurant",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "client_name": {
                                    "type": "string",
                                    "description": "Nom del client"
                                },
                                "date": {
                                    "type": "string",
                                    "description": "Data en format YYYY-MM-DD"
                                },
                                "time": {
                                    "type": "string",
                                    "description": "Hora en format HH:MM"
                                },
                                "num_people": {
                                    "type": "integer",
                                    "description": "Número de persones (1-8)"
                                }
                            },
                            "required": ["client_name", "date", "time", "num_people"]
                        }
                    },
                    {
                        "name": "list_appointments",
                        "description": "Llistar reserves del client",
                        "parameters": {
                            "type": "object",
                            "properties": {}
                        }
                    },
                    {
                        "name": "update_appointment",
                        "description": "Modificar una reserva existent",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "appointment_id": {
                                    "type": "integer",
                                    "description": "ID de la reserva"
                                },
                                "new_date": {
                                    "type": "string",
                                    "description": "Nova data (opcional)"
                                },
                                "new_time": {
                                    "type": "string",
                                    "description": "Nova hora (opcional)"
                                },
                                "new_num_people": {
                                    "type": "integer",
                                    "description": "Nou número de persones (opcional)"
                                }
                            },
                            "required": ["appointment_id"]
                        }
                    },
                    {
                        "name": "cancel_appointment",
                        "description": "Cancel·lar una reserva",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "appointment_id": {
                                    "type": "integer",
                                    "description": "ID de la reserva"
                                }
                            },
                            "required": ["appointment_id"]
                        }
                    }
                ]
            }
            
            logger.info(f"🤖 Agent configurat per idioma: {language}")
            return agent_config
        
        except Exception as e:
            logger.error(f"❌ Error configurant agent: {e}")
            raise
    
    def get_websocket_url(self, phone=None, customer_name=None, language=None):
        """
        Retorna la URL del WebSocket per connectar Twilio amb Eleven Labs
        Inclou variables dinàmiques com a query parameters amb URL encoding correcte
        """
        logger.info(f"🔧 Generant WebSocket URL...")
        logger.info(f"📞 Phone: {phone}")
        logger.info(f"👤 Customer name: {customer_name}")
        logger.info(f"🌐 Language: {language}")
        logger.info(f"🆔 Agent ID: {self.agent_id}")
        
        if not self.agent_id:
            logger.error("⚠️  ELEVEN_LABS_AGENT_ID no configurat!")
            raise ValueError("Necessites crear l'agent primer i guardar el AGENT_ID al .env")
        
        # URL base del WebSocket
        ws_url = f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={self.agent_id}"
        logger.info(f"✅ WebSocket URL base generada: {ws_url}")
        
        # # Afegir informació del client com a query parameters (amb URL encoding)
        # if phone:
        #     # Netejar el + del principi si existeix
        #     clean_phone = phone.replace('+', '')
        #     ws_url += f"&phone={quote(clean_phone)}"
        
        # if customer_name:
        #     ws_url += f"&saved_customer={quote(customer_name)}"
        # else:
        #     ws_url += f"&saved_customer={quote('Cliente Nuevo')}"
        
        # if language:
        #     ws_url += f"&language={quote(language)}"
        # else:
        #     ws_url += "&language=es"
        
        logger.info(f"🎯 WebSocket URL final: {ws_url}")
        return ws_url


# Instància global
elevenlabs_manager = ElevenLabsAgentManager()
