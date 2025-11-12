from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from dotenv import load_dotenv
from utils.transcription import transcribe_audio
from utils.appointments import AppointmentManager, ConversationManager
from utils.ai_processor import process_message_with_ai
from utils.weekly_defaults import WeeklyDefaultsManager
import base64
from datetime import datetime
from werkzeug.utils import secure_filename
from utils.media_manager import MediaManager
from utils.voice_handler import VoiceHandler
from utils.elevenlabs_agent import elevenlabs_manager
import logging
from twilio.twiml.voice_response import VoiceResponse
import time

# Imports per autenticació
from flask_login import login_required, current_user
from utils.auth import login_manager, auth_bp, owner_required, admin_required, read_access

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)

# Configuració de Flask
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
# Configuració de cookies per autenticació cross-domain
IS_PRODUCTION = os.getenv('ENVIRONMENT', 'development') == 'production'

app.config['SESSION_COOKIE_HTTPONLY'] = True  # Protecció XSS
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hores

if IS_PRODUCTION:
    # Producció: HTTPS obligatori amb SameSite=None per cross-domain
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
else:
    # Development: Permetre HTTP amb SameSite=Lax
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Habilitar CORS per al frontend amb suport de credentials
# Suporta múltiples origens: localhost, Vercel, AWS, etc.
FRONTEND_ORIGIN = os.getenv('FRONTEND_URL', 'http://localhost:8080')

# Llista d'origens permesos (base)
allowed_origins = [
    FRONTEND_ORIGIN,
    'http://localhost:8080',
    'http://localhost:5173',
    'http://localhost:3000',
    'https://frontend-restaurant-rho.vercel.app',  # Vercel production
]

# Afegir dominis de Vercel adicionals si existeixen
vercel_url = os.getenv('VERCEL_URL')
if vercel_url and vercel_url not in allowed_origins:
    allowed_origins.append(f'https://{vercel_url}')

print(f"✅ CORS origens permesos (base): {allowed_origins}")

# # Funció per validar origens de Vercel dinàmicament
# def is_vercel_origin(origin):
#     """Comprova si l'origen és un deployment de Vercel"""
#     if not origin:
#         return False
#     # Acceptar qualsevol subdomain de vercel.app
#     return origin.startswith('https://') and '.vercel.app' in origin

# # Handler dinàmic per CORS que accepta tots els deployments de Vercel
# def cors_origin_handler(origin, *args, **kwargs):
#     """Handler dinàmic per CORS que accepta tots els deployments de Vercel"""
#     if origin in allowed_origins:
#         return True
#     if is_vercel_origin(origin):
#         print(f"✅ CORS: Acceptant origen de Vercel: {origin}")
#         return True
#     print(f"❌ CORS: Origen rebutjat: {origin}")
#     return False

CORS(app, 
     supports_credentials=True,
     origins=allowed_origins,  # Usar funció dinàmica
     allow_headers=['Content-Type', 'Authorization'],
     expose_headers=['Set-Cookie'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])

# Inicialitzar Flask-Login
login_manager.init_app(app)
login_manager.login_view = None  # No redirigir automàticament (API)

# Registrar Blueprint d'autenticació
app.register_blueprint(auth_bp)

# Configuración de Twilio
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')

if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
    print("❌ ERROR: Variables de Twilio no configuradas")
else:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    print("✅ Cliente Twilio inicializado correctamente")

# Inicializar gestores
appointment_manager = AppointmentManager()
conversation_manager = ConversationManager()
weekly_defaults_manager = WeeklyDefaultsManager()
media_manager = MediaManager()
voice_handler = VoiceHandler()

# Configuració per pujada d'arxius
UPLOAD_FOLDER = '/tmp/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    return """
    <h1>WhatsApp AI Agent - Restaurante</h1>
    <p>✅ Bot de WhatsApp ACTIVO</p>
    <p>✅ Bot de Telegram ACTIVO</p>
    <p>Webhook WhatsApp: <code>https://tu-dominio.railway.app/whatsapp</code></p>
    """

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """Endpoint principal que recibe mensajes de WhatsApp"""
    
    incoming_msg = request.values.get('Body', '').strip()
    media_url = request.values.get('MediaUrl0', '')
    from_number = request.values.get('From', '')
    
    print(f"📱 Mensaje WhatsApp de {from_number}: {incoming_msg}")
    
    resp = MessagingResponse()
    
    try:
        # Si hay audio, transcribirlo
        if media_url:
            print(f"🎤 Transcribiendo audio...")
            auth_str = f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}"
            auth_header = f"Basic {base64.b64encode(auth_str.encode()).decode()}"
            
            transcribed_text = transcribe_audio(media_url, auth_header)
            
            if transcribed_text:
                print(f"📝 Audio transcrito: {transcribed_text}")
                incoming_msg = transcribed_text
            else:
                resp.message("No pude entender el audio. ¿Puedes escribir tu mensaje?")
                return str(resp)
        
        if not incoming_msg:
            resp.message("Hola! Escribe o envía un mensaje de voz para hacer una reserva.")
            return str(resp)
        
        # Procesar con IA
        ai_response = process_message_with_ai(
            incoming_msg, 
            from_number, 
            appointment_manager, 
            conversation_manager
        )
        
        resp.message(ai_response)
    
    except Exception as e:
        print(f"❌ Error en webhook: {e}")
        import traceback
        traceback.print_exc()
        resp.message("Lo siento, hubo un error. Por favor intenta de nuevo.")
    
    return str(resp)

@app.route('/health')
def health():
    """Endpoint de salud"""
    return {"status": "ok", "message": "WhatsApp bot active and running"}

@app.route('/elevenlabs/test')
def elevenlabs_test():
    """Endpoint de test per verificar que Eleven Labs pot arribar"""
    logger.info("🧪 [TEST] Endpoint /elevenlabs/test cridat")
    return jsonify({
        "status": "ok",
        "message": "ElevenLabs webhooks are reachable",
        "endpoints": {
            "init": "/elevenlabs/init",
            "create_appointment": "/elevenlabs/create_appointment",
            "list_appointments": "/elevenlabs/list_appointments",
            "update_appointment": "/elevenlabs/update_appointment",
            "cancel_appointment": "/elevenlabs/cancel_appointment"
        },
        "timestamp": datetime.now().isoformat()
    }), 200

# ========================================
# API REST ENDPOINTS
# ========================================

@app.route('/api/appointments', methods=['GET'])
@read_access
def get_appointments():
    """Obtenir totes les reserves (requere login)"""
    try:
        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Configurar timezone per la sessió
                cursor.execute("SET timezone TO 'Europe/Madrid'")

                # Obtenir reserves amb informació de taules i notes
                cursor.execute("""
                    SELECT a.id, a.phone, a.client_name, a.date, a.start_time, a.end_time,
                           a.num_people, a.status, a.table_ids, a.created_at, a.notes,
                           a.seated_at, a.left_at, a.duration_minutes, a.no_show, a.delay_minutes, a.booking_group_id
                    FROM appointments a
                    ORDER BY a.start_time DESC
                """)

                appointments = []
                for row in cursor.fetchall():
                    table_ids = row[8]

                    # Obtenir informació de les taules
                    if table_ids:
                        cursor.execute("""
                            SELECT table_number, capacity
                            FROM tables
                            WHERE id = ANY(%s)
                            ORDER BY table_number
                        """, (table_ids,))
                        tables_info = cursor.fetchall()

                        table_numbers = '+'.join(str(t[0]) for t in tables_info) if tables_info else 'N/A'
                        total_capacity = sum(t[1] for t in tables_info) if tables_info else 0
                    else:
                        table_numbers = 'N/A'
                        total_capacity = 0

                    appointments.append({
                        'id': row[0],
                        'phone': row[1],
                        'client_name': row[2],
                        'date': row[3].isoformat() if row[3] else None,
                        'start_time': row[4].isoformat() if row[4] else None,
                        'end_time': row[5].isoformat() if row[5] else None,
                        'num_people': row[6],
                        'status': row[7],
                        'table_numbers': table_numbers,
                        'table_capacity': total_capacity,
                        'created_at': row[9].isoformat() if row[9] else None,
                        'notes': row[10],
                        'table_ids': table_ids,
                        'seated_at': row[11].isoformat() if row[11] else None,
                        'left_at': row[12].isoformat() if row[12] else None,
                        'duration_minutes': row[13],
                        'no_show': row[14],
                        'delay_minutes': row[15],
                        'booking_group_id': str(row[16]) if row[16] else None
                    })

        return jsonify(appointments), 200

    except Exception as e:
        print(f"❌ Error obtenint reserves: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/appointments/<int:appointment_id>', methods=['GET'])
@read_access
def get_appointment(appointment_id):
    """Obtenir una reserva específica (requere login)"""
    try:
        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT a.id, a.phone, a.client_name, a.date, a.start_time, a.end_time,
                           a.num_people, a.status, a.table_ids
                    FROM appointments a
                    WHERE a.id = %s
                """, (appointment_id,))

                row = cursor.fetchone()

                if not row:
                    return jsonify({'error': 'Reserva no trobada'}), 404

                table_ids = row[8]

                # Obtenir informació de les taules
                if table_ids:
                    cursor.execute("""
                        SELECT table_number, capacity
                        FROM tables
                        WHERE id = ANY(%s)
                        ORDER BY table_number
                    """, (table_ids,))
                    tables_info = cursor.fetchall()

                    table_numbers = '+'.join(str(t[0]) for t in tables_info) if tables_info else 'N/A'
                    total_capacity = sum(t[1] for t in tables_info) if tables_info else 0
                else:
                    table_numbers = 'N/A'
                    total_capacity = 0

                appointment = {
                    'id': row[0],
                    'phone': row[1],
                    'client_name': row[2],
                    'date': row[3].isoformat() if row[3] else None,
                    'start_time': row[4].isoformat() if row[4] else None,
                    'end_time': row[5].isoformat() if row[5] else None,
                    'num_people': row[6],
                    'status': row[7],
                    'table_numbers': table_numbers,
                    'table_capacity': total_capacity,
                    'table_ids': table_ids
                }

        return jsonify(appointment), 200
    
    except Exception as e:
        print(f"❌ Error obtenint reserva: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/appointments', methods=['POST'])
@admin_required
def create_appointment_api():
    """Crear nova reserva des del frontend (requere Owner/Admin)"""
    try:
        data = request.json
        
        # Validació
        required = ['phone', 'client_name', 'date', 'time', 'num_people']
        for field in required:
            if field not in data:
                return jsonify({'error': f'Camp obligatori: {field}'}), 400

        # Validar time slots si el mode és 'fixed'
        time_slots_mode = config.get_str('time_slots_mode', 'interval')
        if time_slots_mode == 'fixed':
            # Obtenir horaris d'obertura per determinar si és lunch o dinner
            opening_hours_data = appointment_manager.get_opening_hours(data['date'])
            if not opening_hours_data or opening_hours_data.get('status') == 'closed':
                return jsonify({'error': 'El restaurant està tancat aquest dia'}), 400

            # Convertir el format de opening_hours a llista de slots
            time_slots = []
            if opening_hours_data.get('lunch_start') and opening_hours_data.get('lunch_end'):
                time_slots.append({
                    'start': opening_hours_data['lunch_start'],
                    'end': opening_hours_data['lunch_end'],
                    'name': 'lunch'
                })
            if opening_hours_data.get('dinner_start') and opening_hours_data.get('dinner_end'):
                time_slots.append({
                    'start': opening_hours_data['dinner_start'],
                    'end': opening_hours_data['dinner_end'],
                    'name': 'dinner'
                })

            if not time_slots:
                return jsonify({'error': 'No hi ha horaris disponibles per aquest dia'}), 400

            # Determinar el període (lunch/dinner) segons l'hora
            requested_time = data['time']
            time_parts = requested_time.split(':')
            requested_minutes = int(time_parts[0]) * 60 + int(time_parts[1])

            period = None
            for slot in time_slots:
                slot_start_parts = slot['start'].split(':')
                slot_start_minutes = int(slot_start_parts[0]) * 60 + int(slot_start_parts[1])
                slot_end_parts = slot['end'].split(':')
                slot_end_minutes = int(slot_end_parts[0]) * 60 + int(slot_end_parts[1])

                if slot_start_minutes <= requested_minutes <= slot_end_minutes:
                    period = slot['name']
                    break

            if not period:
                return jsonify({'error': f'L\'hora {requested_time} està fora dels horaris d\'obertura'}), 400

            # Obtenir els time slots permesos per aquest període
            if period == 'lunch':
                allowed_slots = config.get_list('fixed_time_slots_lunch', ['13:00', '15:00'])
            else:  # dinner
                allowed_slots = config.get_list('fixed_time_slots_dinner', ['20:00', '21:30'])

            # Validar que l'hora sol·licitada estigui en els slots permesos
            if requested_time not in allowed_slots:
                slots_str = ', '.join(allowed_slots)
                return jsonify({
                    'error': f'L\'hora {requested_time} no està disponible. Horaris permesos per {period}: {slots_str}'
                }), 400

        # Crear reserva (usar configuració per defecte si no s'especifica duració)
        default_duration = config.get_float('default_booking_duration_hours', 1.0)
        result = appointment_manager.create_appointment(
            phone=data['phone'],
            client_name=data['client_name'],
            date=data['date'],
            time=data['time'],
            num_people=data['num_people'],
            duration_hours=data.get('duration_hours', default_duration),
            language=data.get('language', 'es')
        )
        
        if not result:
            return jsonify({'error': 'No hi ha taules disponibles'}), 409
        
        return jsonify({
            'message': 'Reserva creada correctament',
            'appointment_id': result['id'],
            'table': result['table']
        }), 201
    
    except Exception as e:
        print(f"❌ Error creant reserva: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/appointments/<int:appointment_id>', methods=['PUT'])
@admin_required
def update_appointment_api(appointment_id):
    """Actualitzar una reserva (requere Owner/Admin)"""
    try:
        data = request.json

        # Obtenir phone de la reserva existent
        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT phone FROM appointments WHERE id = %s", (appointment_id,))
                row = cursor.fetchone()

        if not row:
            return jsonify({'error': 'Reserva no trobada'}), 404

        phone = row[0]

        # Actualitzar (ara incloent table_ids)
        result = appointment_manager.update_appointment(
            phone=phone,
            appointment_id=appointment_id,
            new_date=data.get('date'),
            new_time=data.get('time'),
            new_num_people=data.get('num_people'),
            new_table_ids=data.get('table_ids')  # Array d'IDs de taules
        )

        if not result:
            return jsonify({'error': 'No s\'ha pogut actualitzar la reserva'}), 409

        return jsonify({
            'message': 'Reserva actualitzada correctament',
            'appointment_id': result['id'],
            'tables': result.get('tables', []),
            'table_ids': result.get('table_ids', [])
        }), 200

    except Exception as e:
        print(f"❌ Error actualitzant reserva: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/appointments/<int:appointment_id>', methods=['DELETE'])
@admin_required
def delete_appointment_api(appointment_id):
    """Cancel·lar una reserva (requere Owner/Admin)"""
    try:
        # Obtenir phone de la reserva
        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT phone FROM appointments WHERE id = %s", (appointment_id,))
                row = cursor.fetchone()

        if not row:
            return jsonify({'error': 'Reserva no trobada'}), 404

        phone = row[0]
        
        # Cancel·lar
        success = appointment_manager.cancel_appointment(phone, appointment_id)
        
        if success:
            return jsonify({'message': 'Reserva cancel·lada correctament'}), 200
        else:
            return jsonify({'error': 'Error cancel·lant la reserva'}), 500
    
    except Exception as e:
        print(f"❌ Error cancel·lant reserva: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/appointments/<int:appointment_id>/notes', methods=['PUT'])
def add_notes_to_appointment_api(appointment_id):
    """Afegir notes a una reserva"""
    try:
        data = request.json
        notes = data.get('notes', '')

        # Obtenir phone de la reserva
        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT phone FROM appointments WHERE id = %s", (appointment_id,))
                row = cursor.fetchone()

                if not row:
                    return jsonify({'error': 'Reserva no trobada'}), 404

                phone = row[0]

        # Afegir notes
        success = appointment_manager.add_notes_to_appointment(phone, appointment_id, notes)

        if success:
            return jsonify({'message': 'Notes afegides correctament'}), 200
        else:
            return jsonify({'error': 'Error afegint notes'}), 500

    except Exception as e:
        print(f"❌ Error afegint notes: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tables', methods=['GET'])
def get_tables():
    """Obtenir totes les taules"""
    try:
        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, table_number, capacity, status, pairing
                    FROM tables
                    ORDER BY table_number
                """)

                tables = []
                for row in cursor.fetchall():
                    tables.append({
                        'id': row[0],
                        'table_number': row[1],
                        'capacity': row[2],
                        'status': row[3],
                        'pairing': row[4] if row[4] else []
                    })

        return jsonify(tables), 200

    except Exception as e:
        print(f"❌ Error obtenint taules: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tables', methods=['POST'])
def create_table():
    """Crear nova taula amb pairing bidireccional"""
    try:
        data = request.json

        required = ['table_number', 'capacity']
        for field in required:
            if field not in data:
                return jsonify({'error': f'Camp obligatori: {field}'}), 400

        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM tables WHERE table_number = %s", (data['table_number'],))
                if cursor.fetchone():
                    return jsonify({'error': 'Ja existeix una taula amb aquest número'}), 409

                pairing = data.get('pairing', None)
                status = data.get('status', 'available')

                cursor.execute("""
                    INSERT INTO tables (table_number, capacity, status, pairing)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (data['table_number'], data['capacity'], status, pairing))

                new_id = cursor.fetchone()[0]

                # GESTIÓ BIDIRECCIONAL: afegir aquesta taula al pairing de les altres
                if pairing:
                    for table_num in pairing:
                        cursor.execute("SELECT id, pairing FROM tables WHERE table_number = %s", (table_num,))
                        target = cursor.fetchone()
                        if target:
                            target_id = target[0]
                            target_pairing = list(target[1]) if target[1] else []

                            if data['table_number'] not in target_pairing:
                                target_pairing.append(data['table_number'])
                                cursor.execute(
                                    "UPDATE tables SET pairing = %s WHERE id = %s",
                                    (target_pairing, target_id)
                                )

                conn.commit()

        return jsonify({'message': 'Taula creada correctament', 'id': new_id}), 201

    except Exception as e:
        print(f"❌ Error creant taula: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/tables/<int:table_id>', methods=['PUT'])
def update_table(table_id):
    """Actualitzar paràmetres d'una taula amb pairing bidireccional"""
    try:
        data = request.json

        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Obtenir pairing actual abans de l'actualització
                cursor.execute("SELECT pairing, table_number FROM tables WHERE id = %s", (table_id,))
                result = cursor.fetchone()
                if not result:
                    return jsonify({'error': 'Taula no trobada'}), 404

                old_pairing = result[0] if result[0] else []
                current_table_number = result[1]

                # Construir query dinàmica
                updates = []
                values = []

                if 'table_number' in data:
                    cursor.execute("SELECT id FROM tables WHERE table_number = %s AND id != %s",
                                  (data['table_number'], table_id))
                    if cursor.fetchone():
                        return jsonify({'error': 'Ja existeix una taula amb aquest número'}), 409
                    updates.append("table_number = %s")
                    values.append(data['table_number'])
                    # Si canviem el número, actualitzar referències
                    current_table_number = data['table_number']

                if 'capacity' in data:
                    updates.append("capacity = %s")
                    values.append(data['capacity'])

                if 'status' in data:
                    if data['status'] not in ['available', 'unavailable']:
                        return jsonify({'error': 'Status invàlid'}), 400
                    updates.append("status = %s")
                    values.append(data['status'])

                new_pairing = None
                if 'pairing' in data:
                    new_pairing = data['pairing']
                    updates.append("pairing = %s")
                    values.append(new_pairing)

                if not updates:
                    return jsonify({'error': 'No hi ha camps per actualitzar'}), 400

                values.append(table_id)
                query = f"UPDATE tables SET {', '.join(updates)} WHERE id = %s"

                cursor.execute(query, values)

                # GESTIÓ BIDIRECCIONAL DEL PAIRING
                if 'pairing' in data:
                    new_pairing_set = set(new_pairing) if new_pairing else set()
                    old_pairing_set = set(old_pairing)

                    # Taules afegides al pairing
                    added = new_pairing_set - old_pairing_set
                    # Taules eliminades del pairing
                    removed = old_pairing_set - new_pairing_set

                    # AFEGIR aquesta taula al pairing de les taules noves
                    for table_num in added:
                        cursor.execute("SELECT id, pairing FROM tables WHERE table_number = %s", (table_num,))
                        target = cursor.fetchone()
                        if target:
                            target_id = target[0]
                            target_pairing = list(target[1]) if target[1] else []

                            if current_table_number not in target_pairing:
                                target_pairing.append(current_table_number)
                                cursor.execute(
                                    "UPDATE tables SET pairing = %s WHERE id = %s",
                                    (target_pairing, target_id)
                                )

                    # ELIMINAR aquesta taula del pairing de les taules que ja no estan
                    for table_num in removed:
                        cursor.execute("SELECT id, pairing FROM tables WHERE table_number = %s", (table_num,))
                        target = cursor.fetchone()
                        if target:
                            target_id = target[0]
                            target_pairing = list(target[1]) if target[1] else []

                            if current_table_number in target_pairing:
                                target_pairing.remove(current_table_number)
                                cursor.execute(
                                    "UPDATE tables SET pairing = %s WHERE id = %s",
                                    (target_pairing if target_pairing else None, target_id)
                                )

                conn.commit()

        return jsonify({'message': 'Taula actualitzada correctament'}), 200

    except Exception as e:
        print(f"❌ Error actualitzant taula: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/tables/<int:table_id>', methods=['DELETE'])
def delete_table(table_id):
    """Eliminar una taula i netejar pairing bidireccional"""
    try:
        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Obtenir info de la taula
                cursor.execute("SELECT table_number, pairing FROM tables WHERE id = %s", (table_id,))
                result = cursor.fetchone()
                if not result:
                    return jsonify({'error': 'Taula no trobada'}), 404

                table_number = result[0]
                pairing = result[1] if result[1] else []

                # Verificar reserves futures (ara amb table_ids array)
                cursor.execute("""
                    SELECT COUNT(*) FROM appointments
                    WHERE %s = ANY(table_ids) AND status = 'confirmed' AND date >= CURRENT_DATE
                """, (table_id,))

                count = cursor.fetchone()[0]

                if count > 0:
                    return jsonify({'error': f'No es pot eliminar. La taula té {count} reserves futures'}), 409

                # ELIMINAR referències d'aquesta taula en el pairing d'altres taules
                for paired_table_num in pairing:
                    cursor.execute("SELECT id, pairing FROM tables WHERE table_number = %s", (paired_table_num,))
                    target = cursor.fetchone()
                    if target:
                        target_id = target[0]
                        target_pairing = list(target[1]) if target[1] else []

                        if table_number in target_pairing:
                            target_pairing.remove(table_number)
                            cursor.execute(
                                "UPDATE tables SET pairing = %s WHERE id = %s",
                                (target_pairing if target_pairing else None, target_id)
                            )

                # Ara també eliminar aquesta taula de qualsevol altre pairing que la referencii
                cursor.execute("SELECT id, table_number, pairing FROM tables WHERE pairing @> ARRAY[%s]::integer[]", (table_number,))
                for row in cursor.fetchall():
                    other_id = row[0]
                    other_pairing = list(row[2]) if row[2] else []
                    if table_number in other_pairing:
                        other_pairing.remove(table_number)
                        cursor.execute(
                            "UPDATE tables SET pairing = %s WHERE id = %s",
                            (other_pairing if other_pairing else None, other_id)
                        )

                # Eliminar la taula
                cursor.execute("DELETE FROM tables WHERE id = %s", (table_id,))

                conn.commit()

        return jsonify({'message': 'Taula eliminada correctament'}), 200

    except Exception as e:
        print(f"❌ Error eliminant taula: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    

@app.route('/api/customers', methods=['GET'])
def get_customers():
    """Obtenir tots els clients"""
    try:
        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        c.phone,
                        c.name,
                        c.language,
                        c.visit_count,
                        c.last_visit,
                        CASE
                            WHEN EXISTS (
                                SELECT 1 FROM appointments a
                                WHERE a.phone = c.phone
                                AND a.date = CURRENT_DATE
                                AND a.status IN ('confirmed', 'completed')
                            ) THEN 1
                            ELSE 0
                        END as has_reservation_today
                    FROM customers c
                    WHERE c.name != 'TEMP'
                    ORDER BY
                        has_reservation_today DESC,  -- Primer: amb reserva avui (confirmed o completed)
                        c.visit_count DESC,          -- Segon: més visites
                        c.last_visit DESC            -- Tercer: més recents
                """)

                customers = []
                for row in cursor.fetchall():
                    customers.append({
                        'phone': row[0],
                        'name': row[1],
                        'language': row[2],
                        'visit_count': row[3],
                        'last_visit': row[4].isoformat() if row[4] else None,
                        'has_reservation_today': bool(row[5])
                    })

        return jsonify(customers), 200

    except Exception as e:
        print(f"❌ Error obtenint clients: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/conversations/<phone>', methods=['GET'])
def get_conversations(phone):
    """Obtenir historial de conversa d'un client (sense missatges system)"""
    try:
        # Netejar prefix whatsapp: o telegram: si existeix
        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '')

        with conversation_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, role, content, created_at
                    FROM conversations
                    WHERE phone = %s AND role != 'system'
                    ORDER BY created_at ASC
                """, (clean_phone,))

                conversations = []
                for row in cursor.fetchall():
                    conversations.append({
                        'id': row[0],
                        'role': row[1],
                        'content': row[2],
                        'created_at': row[3].isoformat() if row[3] else None
                    })

        return jsonify(conversations), 200

    except Exception as e:
        print(f"❌ Error obtenint converses: {e}")
        return jsonify({'error': str(e)}), 500

# ========================================
# OPENING HOURS ENDPOINTS
# ========================================

@app.route('/api/opening-hours', methods=['GET'])
def get_opening_hours_api():
    """
    Obtenir horaris d'obertura
    Query params: date (single), from+to (range)
    """
    try:
        single_date = request.args.get('date')
        from_date = request.args.get('from')
        to_date = request.args.get('to')
        
        if single_date:
            # Obtenir horaris d'un dia específic
            hours = appointment_manager.get_opening_hours(single_date)
            hours['date'] = single_date
            return jsonify(hours), 200
        elif from_date and to_date:
            # Obtenir rang de dates
            hours_list = appointment_manager.get_opening_hours_range(from_date, to_date)
            return jsonify(hours_list), 200
        else:
            return jsonify({'error': 'Cal especificar date o from+to'}), 400
    
    except Exception as e:
        print(f"❌ Error obtenint horaris: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/opening-hours', methods=['POST'])
def set_opening_hours_api():
    """
    Crear/actualitzar horaris d'obertura per una data
    """
    try:
        data = request.json
        
        required = ['date', 'status']
        for field in required:
            if field not in data:
                return jsonify({'error': f'Camp obligatori: {field}'}), 400
        
        # Validar status
        valid_statuses = ['closed', 'lunch_only', 'dinner_only', 'full_day']
        if data['status'] not in valid_statuses:
            return jsonify({'error': f'Status invàlid. Usa: {", ".join(valid_statuses)}'}), 400
        
        success = appointment_manager.set_opening_hours(
            date=data['date'],
            status=data['status'],
            lunch_start=data.get('lunch_start'),
            lunch_end=data.get('lunch_end'),
            dinner_start=data.get('dinner_start'),
            dinner_end=data.get('dinner_end'),
            notes=data.get('notes')
        )
        
        if success:
            return jsonify({'message': 'Horaris guardats correctament'}), 200
        else:
            return jsonify({'error': 'Error guardant horaris'}), 500
    
    except Exception as e:
        print(f"❌ Error guardant horaris: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/opening-hours/<date>', methods=['PUT'])
def update_opening_hours_api(date):
    """
    Actualitzar horaris d'una data específica
    """
    try:
        data = request.json
        
        if 'status' in data:
            valid_statuses = ['closed', 'lunch_only', 'dinner_only', 'full_day']
            if data['status'] not in valid_statuses:
                return jsonify({'error': f'Status invàlid. Usa: {", ".join(valid_statuses)}'}), 400
        
        success = appointment_manager.set_opening_hours(
            date=date,
            status=data.get('status', 'full_day'),
            lunch_start=data.get('lunch_start'),
            lunch_end=data.get('lunch_end'),
            dinner_start=data.get('dinner_start'),
            dinner_end=data.get('dinner_end'),
            notes=data.get('notes')
        )
        
        if success:
            return jsonify({'message': 'Horaris actualitzats correctament'}), 200
        else:
            return jsonify({'error': 'Error actualitzant horaris'}), 500
    
    except Exception as e:
        print(f"❌ Error actualitzant horaris: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/opening-hours/recurring', methods=['POST'])
def set_recurring_hours_api():
    """
    Configurar horaris recurrents per dia de la setmana
    """
    try:
        data = request.json
        
        required = ['day_of_week', 'status', 'start_date', 'end_date']
        for field in required:
            if field not in data:
                return jsonify({'error': f'Camp obligatori: {field}'}), 400
        
        # Validar status
        valid_statuses = ['closed', 'lunch_only', 'dinner_only', 'full_day']
        if data['status'] not in valid_statuses:
            return jsonify({'error': f'Status invàlid. Usa: {", ".join(valid_statuses)}'}), 400
        
        # Validar day_of_week (0=dilluns, 6=diumenge)
        day_of_week = int(data['day_of_week'])
        if day_of_week < 0 or day_of_week > 6:
            return jsonify({'error': 'day_of_week ha de ser entre 0 (dilluns) i 6 (diumenge)'}), 400
        
        # Aplicar horaris recurrents
        from datetime import datetime, timedelta
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        
        current_date = start_date
        count = 0
        
        while current_date <= end_date:
            # weekday() retorna 0=dilluns, 6=diumenge
            if current_date.weekday() == day_of_week:
                appointment_manager.set_opening_hours(
                    date=current_date.strftime('%Y-%m-%d'),
                    status=data['status'],
                    lunch_start=data.get('lunch_start'),
                    lunch_end=data.get('lunch_end'),
                    dinner_start=data.get('dinner_start'),
                    dinner_end=data.get('dinner_end'),
                    notes=data.get('notes')
                )
                count += 1
            
            current_date += timedelta(days=1)
        
        return jsonify({
            'message': f'Horaris recurrents aplicats correctament a {count} dies',
            'days_updated': count
        }), 200
    
    except Exception as e:
        print(f"❌ Error configurant horaris recurrents: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/weekly-defaults', methods=['GET'])
def get_weekly_defaults_api():
    """
    Obtenir configuració per defecte per cada dia de la setmana
    """
    try:
        defaults = weekly_defaults_manager.get_all_defaults()
        return jsonify(defaults), 200
    except Exception as e:
        print(f"❌ Error obtenint configuració setmanal: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/weekly-defaults/<int:day_of_week>', methods=['PUT'])
def update_weekly_default_api(day_of_week):
    """
    Actualitzar configuració per defecte d'un dia de la setmana
    I aplicar a tots els dies futurs d'aquest tipus que NO estiguin customitzats
    """
    try:
        data = request.json
        
        if day_of_week < 0 or day_of_week > 6:
            return jsonify({'error': 'day_of_week ha de ser entre 0 (dilluns) i 6 (diumenge)'}), 400
        
        # Validar status
        valid_statuses = ['closed', 'lunch_only', 'dinner_only', 'full_day']
        if data.get('status') and data['status'] not in valid_statuses:
            return jsonify({'error': f'Status invàlid. Usa: {", ".join(valid_statuses)}'}), 400
        
        # Actualitzar defaults i aplicar
        result = weekly_defaults_manager.update_default(
            day_of_week=day_of_week,
            status=data.get('status', 'full_day'),
            lunch_start=data.get('lunch_start'),
            lunch_end=data.get('lunch_end'),
            dinner_start=data.get('dinner_start'),
            dinner_end=data.get('dinner_end')
        )
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
    
    except Exception as e:
        print(f"❌ Error actualitzant configuració setmanal: {e}")
        return jsonify({'error': str(e)}), 500
    


# ========================================
# MEDIA ENDPOINTS (PDFs, Imatges)
# ========================================


@app.route('/api/media', methods=['GET'])
def get_media_api():
    """Obtenir llista de media"""
    print("🔍 [MEDIA] GET /api/media - Rebuda petició")
    try:
        media_type = request.args.get('type')
        date = request.args.get('date')
        
        print(f"📋 [MEDIA] Filtres: type={media_type}, date={date}")
        
        media_list = media_manager.get_active_media(media_type, date)
        
        print(f"✅ [MEDIA] Retornant {len(media_list)} arxius")
        return jsonify(media_list), 200
    
    except Exception as e:
        print(f"❌ [MEDIA] Error obtenint media: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/carta', methods=['GET'])
def get_carta_api():
    """Obtenir la carta del restaurant"""
    print("🔍 [MEDIA] GET /api/media/carta - Rebuda petició")
    try:
        carta = media_manager.get_menu(menu_type='carta')
        
        if carta:
            print(f"✅ [MEDIA] Carta trobada: {carta['title']}")
            return jsonify(carta), 200
        else:
            print("⚠️  [MEDIA] No hi ha carta disponible")
            return jsonify({'message': 'No hi ha carta disponible'}), 404
    
    except Exception as e:
        print(f"❌ [MEDIA] Error obtenint carta: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/upload', methods=['POST'])
def upload_media_api():
    """Pujar un nou arxiu (PDF o imatge)"""
    print("🔍 [MEDIA] POST /api/media/upload - Rebuda petició")
    print(f"📦 [MEDIA] Content-Type: {request.content_type}")
    print(f"📦 [MEDIA] Files: {list(request.files.keys())}")
    print(f"📦 [MEDIA] Form data: {list(request.form.keys())}")
    
    try:
        # Validar que hi ha arxiu
        if 'file' not in request.files:
            print("❌ [MEDIA] No s'ha proporcionat cap arxiu")
            return jsonify({'error': 'No s\'ha proporcionat cap arxiu'}), 400
        
        file = request.files['file']
        print(f"📄 [MEDIA] Arxiu rebut: {file.filename}")
        
        if file.filename == '':
            print("❌ [MEDIA] Nom d'arxiu buit")
            return jsonify({'error': 'Nom d\'arxiu buit'}), 400
        
        if not allowed_file(file.filename):
            print(f"❌ [MEDIA] Tipus d'arxiu no permès: {file.filename}")
            return jsonify({'error': f'Tipus d\'arxiu no permès. Usa: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
        
        print("✅ [MEDIA] Arxiu vàlid")
        
        # Validar camps obligatoris
        media_type = request.form.get('type')
        title = request.form.get('title')
        
        print(f"📋 [MEDIA] Tipus: {media_type}, Títol: {title}")
        
        if not media_type or not title:
            print("❌ [MEDIA] Falten camps obligatoris")
            return jsonify({'error': 'Els camps type i title són obligatoris'}), 400
        
        valid_types = ['menu_dia', 'carta', 'promocio', 'event']
        if media_type not in valid_types:
            print(f"❌ [MEDIA] Tipus invàlid: {media_type}")
            return jsonify({'error': f'Tipus invàlid. Usa: {", ".join(valid_types)}'}), 400
        
        # Guardar arxiu temporalment
        filename = secure_filename(file.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        print(f"💾 [MEDIA] Guardant temporalment a: {temp_path}")
        file.save(temp_path)
        print(f"✅ [MEDIA] Arxiu guardat temporalment")
        
        # Obtenir camps opcionals
        description = request.form.get('description')
        date = request.form.get('date')
        
        print(f"📝 [MEDIA] Descripció: {description}")
        print(f"📅 [MEDIA] Data: {date}")
        
        # Comprovar variables Cloudinary
        cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
        api_key = os.getenv('CLOUDINARY_API_KEY')
        api_secret = os.getenv('CLOUDINARY_API_SECRET')
        
        if not cloud_name or not api_key or not api_secret:
            print("❌ [MEDIA] Variables Cloudinary no configurades!")
            print(f"   CLOUDINARY_CLOUD_NAME: {'✅' if cloud_name else '❌'}")
            print(f"   CLOUDINARY_API_KEY: {'✅' if api_key else '❌'}")
            print(f"   CLOUDINARY_API_SECRET: {'✅' if api_secret else '❌'}")
            return jsonify({'error': 'Cloudinary no configurat. Contacta amb l\'administrador'}), 500
        
        print("✅ [MEDIA] Variables Cloudinary configurades")
        
        # Pujar a Cloudinary i guardar a BD
        print("☁️  [MEDIA] Pujant a Cloudinary...")
        result = media_manager.upload_media(
            file_path=temp_path,
            media_type=media_type,
            title=title,
            description=description,
            date=date
        )
        
        # Eliminar arxiu temporal
        if os.path.exists(temp_path):
            os.remove(temp_path)
            print("🗑️  [MEDIA] Arxiu temporal eliminat")
        
        if result:
            print(f"✅ [MEDIA] Arxiu pujat correctament! ID: {result.get('id')}")
            print(f"🔗 [MEDIA] URL: {result.get('url')}")
            return jsonify({
                'message': 'Arxiu pujat correctament',
                'media': result
            }), 201
        else:
            print("❌ [MEDIA] Error pujant l'arxiu (result=None)")
            return jsonify({'error': 'Error pujant l\'arxiu'}), 500
    
    except Exception as e:
        print(f"❌ [MEDIA] Error pujant media: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<int:media_id>', methods=['DELETE'])
def delete_media_api(media_id):
    """Eliminar un media (BD + Cloudinary)"""
    print(f"🔍 [MEDIA] DELETE /api/media/{media_id} - Rebuda petició")
    try:
        success = media_manager.delete_media(media_id)
        
        if success:
            print(f"✅ [MEDIA] Media {media_id} eliminat correctament")
            return jsonify({'message': 'Media eliminat correctament'}), 200
        else:
            print(f"❌ [MEDIA] Error eliminant media {media_id}")
            return jsonify({'error': 'Error eliminant el media'}), 500
    
    except Exception as e:
        print(f"❌ [MEDIA] Error eliminant media: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/media/<int:media_id>/deactivate', methods=['PUT'])
def deactivate_media_api(media_id):
    """Desactivar un media (no l'elimina)"""
    print(f"🔍 [MEDIA] PUT /api/media/{media_id}/deactivate - Rebuda petició")
    try:
        success = media_manager.deactivate_media(media_id)
        
        if success:
            print(f"✅ [MEDIA] Media {media_id} desactivat correctament")
            return jsonify({'message': 'Media desactivat correctament'}), 200
        else:
            print(f"❌ [MEDIA] Error desactivant media {media_id}")
            return jsonify({'error': 'Error desactivant el media'}), 500
    
    except Exception as e:
        print(f"❌ [MEDIA] Error desactivant media: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ==========================================
# ENDPOINTS PER TRACKING DE CLIENTS
# ==========================================

@app.route('/api/appointments/<int:appointment_id>/seated', methods=['POST'])
def mark_appointment_seated(appointment_id):
    """⚡ Marcar que el client s'ha assentat"""
    try:
        success, delay = appointment_manager.mark_seated(appointment_id)
        
        if success:
            return jsonify({
                'message': 'Client marcat com assentat', 
                'appointment_id': appointment_id,
                'delay_minutes': delay
            }), 200
        else:
            return jsonify({'error': 'No s\'ha pogut marcar com assentat'}), 400
    
    except Exception as e:
        print(f"❌ Error marcant seated: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/appointments/<int:appointment_id>/left', methods=['POST'])
def mark_appointment_left(appointment_id):
    """👋 Marcar que el client ha marxat"""
    try:
        success, duration = appointment_manager.mark_left(appointment_id)
        
        if success:
            return jsonify({
                'message': 'Client marcat com marxat',
                'appointment_id': appointment_id,
                'duration_minutes': duration
            }), 200
        else:
            return jsonify({'error': 'No s\'ha pogut marcar com marxat'}), 400
    
    except Exception as e:
        print(f"❌ Error marcant left: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/appointments/<int:appointment_id>/no-show', methods=['POST'])
def mark_appointment_no_show(appointment_id):
    """❌ Marcar no-show"""
    try:
        data = request.get_json() or {}
        phone = data.get('phone')
        
        if not phone:
            return jsonify({'error': 'Telèfon obligatori'}), 400
        
        success = appointment_manager.mark_no_show(appointment_id, phone)
        
        if success:
            return jsonify({
                'message': 'No-show registrat',
                'appointment_id': appointment_id
            }), 200
        else:
            return jsonify({'error': 'No s\'ha pogut registrar el no-show'}), 400
    
    except Exception as e:
        print(f"❌ Error marcant no-show: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/customers/<phone>/stats', methods=['GET'])
def get_customer_stats_api(phone):
    """📊 Obtenir estadístiques d'un client"""
    try:
        stats = appointment_manager.get_customer_stats(phone)
        
        if stats:
            return jsonify(stats), 200
        else:
            return jsonify({'error': 'Client no trobat'}), 404
    
    except Exception as e:
        print(f"❌ Error obtenint stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats/global', methods=['GET'])
def get_global_stats_api():
    """🌎 Obtenir estadístiques globals"""
    try:
        stats = appointment_manager.get_global_stats()
        
        if stats:
            return jsonify(stats), 200
        else:
            return jsonify({'error': 'No s\'han pogut obtenir les estadístiques'}), 500
    
    except Exception as e:
        print(f"❌ Error obtenint stats globals: {e}")
        return jsonify({'error': str(e)}), 500


# ==========================================
# BROADCAST MESSAGES (Missatges Difusos)
# ==========================================

@app.route('/api/broadcast', methods=['POST'])
def send_broadcast():
    """📢 Enviar missatge difús a tots els clients o filtrats"""
    try:
        data = request.json

        message = data.get('message')
        filter_type = data.get('filter_type', 'all')
        filter_value = data.get('filter_value')

        if not message:
            return jsonify({'error': 'El missatge és obligatori'}), 400

        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                if filter_type == 'all':
                    cursor.execute("""
                        SELECT DISTINCT phone, name, language
                        FROM customers
                        WHERE name != 'TEMP'
                    """)
                elif filter_type == 'language':
                    if not filter_value:
                        return jsonify({'error': "Cal especificar l'idioma"}), 400
                    cursor.execute("""
                        SELECT DISTINCT phone, name, language
                        FROM customers
                        WHERE language = %s AND name != 'TEMP'
                    """, (filter_value,))
                elif filter_type == 'recent_customers':
                    cursor.execute("""
                        SELECT DISTINCT phone, name, language
                        FROM customers
                        WHERE last_visit >= CURRENT_DATE - INTERVAL '30 days'
                        AND name != 'TEMP'
                    """)
                else:
                    return jsonify({'error': 'Tipus de filtre invàlid'}), 400

                recipients = cursor.fetchall()

        if not recipients:
            return jsonify({'error': "No s'han trobat destinataris"}), 404
        
        sent_count = 0
        failed_count = 0
        results = []
        
        for phone, name, language in recipients:
            try:
                if phone.startswith('telegram:'):
                    user_id = phone.replace('telegram:', '')
                    import requests
                    url = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage"
                    payload = {
                        'chat_id': user_id,
                        'text': message
                    }
                    response = requests.post(url, json=payload)
                    
                    if response.status_code == 200:
                        sent_count += 1
                        results.append({'phone': phone, 'name': name, 'status': 'sent', 'channel': 'telegram'})
                        print(f"✅ Telegram enviat a {name} ({phone})")
                    else:
                        failed_count += 1
                        results.append({'phone': phone, 'name': name, 'status': 'failed', 'channel': 'telegram', 'error': response.text})
                        print(f"❌ Error Telegram a {name}: {response.text}")
                else:
                    clean_phone = phone.replace('whatsapp:', '')
                    
                    twilio_message = twilio_client.messages.create(
                        from_=os.getenv('TWILIO_WHATSAPP_NUMBER'),
                        body=message,
                        to=f'whatsapp:{clean_phone}'
                    )
                    
                    sent_count += 1
                    results.append({'phone': phone, 'name': name, 'status': 'sent', 'channel': 'whatsapp'})
                    print(f"✅ WhatsApp enviat a {name} ({phone})")
                    
            except Exception as e:
                failed_count += 1
                results.append({'phone': phone, 'name': name, 'status': 'failed', 'error': str(e)})
                print(f"❌ Error enviant a {name} ({phone}): {e}")
        
        return jsonify({
            'message': 'Missatge difús processat',
            'total_recipients': len(recipients),
            'sent': sent_count,
            'failed': failed_count,
            'results': results
        }), 200
    
    except Exception as e:
        print(f"❌ Error enviant broadcast: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/send-message', methods=['POST'])
@admin_required
def send_individual_message():
    """
    📤 Enviar missatge individual a un client específic
    
    Body:
    {
        "phone": "+34600000000",
        "message": "Hola, tenim una oferta especial avui!"
    }
    """
    try:
        data = request.json
        
        phone = data.get('phone')
        message = data.get('message')
        
        if not phone or not message:
            return jsonify({'error': 'El telèfon i el missatge són obligatoris'}), 400
        
        # Obtenir el client de la base de dades
        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT name, language FROM customers WHERE phone = %s
                """, (phone,))
                result = cursor.fetchone()
                
                if not result:
                    return jsonify({'error': 'Client no trobat'}), 404
                
                name = result[0]
                language = result[1] or 'es'
        
        # Intentar enviar via WhatsApp/Telegram segons el prefix
        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '').strip()
        
        try:
            # Si és un telèfon (sense prefix telegram:), enviar via WhatsApp
            if not phone.startswith('telegram:'):
                twilio_message = twilio_client.messages.create(
                    from_=os.getenv('TWILIO_WHATSAPP_NUMBER'),
                    body=message,
                    to=f'whatsapp:{clean_phone}'
                )
                
                # Guardar el missatge a conversations
                with appointment_manager.get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO conversations (phone, role, content)
                            VALUES (%s, %s, %s)
                        """, (phone, 'assistant', message))
                        conn.commit()
                
                print(f"✅ WhatsApp enviat a {name} ({phone})")
                return jsonify({
                    'success': True,
                    'message': 'Missatge enviat correctament',
                    'channel': 'whatsapp',
                    'phone': phone,
                    'name': name
                }), 200
            
            # Si té prefix telegram:, enviar via Telegram
            else:
                telegram_chat_id = clean_phone
                telegram_bot.send_message(
                    chat_id=telegram_chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
                
                # Guardar el missatge a conversations
                with appointment_manager.get_db_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO conversations (phone, role, content)
                            VALUES (%s, %s, %s)
                        """, (phone, 'assistant', message))
                        conn.commit()
                
                print(f"✅ Telegram enviat a {name} ({phone})")
                return jsonify({
                    'success': True,
                    'message': 'Missatge enviat correctament',
                    'channel': 'telegram',
                    'phone': phone,
                    'name': name
                }), 200
                
        except Exception as e:
            print(f"❌ Error enviant missatge a {phone}: {e}")
            return jsonify({
                'error': f'Error enviant el missatge: {str(e)}'
            }), 500
            
    except Exception as e:
        print(f"❌ Error en send_individual_message: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/broadcast/preview', methods=['POST'])
def preview_broadcast():
    """👁️ Previsualitzar destinataris del missatge difús"""
    try:
        data = request.json

        filter_type = data.get('filter_type', 'all')
        filter_value = data.get('filter_value')

        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                if filter_type == 'all':
                    cursor.execute("""
                        SELECT phone, name, language
                        FROM customers
                        WHERE name != 'TEMP'
                        ORDER BY last_visit DESC
                    """)
                elif filter_type == 'language':
                    if not filter_value:
                        return jsonify({'error': "Cal especificar l'idioma"}), 400
                    cursor.execute("""
                        SELECT phone, name, language
                        FROM customers
                        WHERE language = %s AND name != 'TEMP'
                        ORDER BY last_visit DESC
                    """, (filter_value,))
                elif filter_type == 'recent_customers':
                    cursor.execute("""
                        SELECT phone, name, language
                        FROM customers
                        WHERE last_visit >= CURRENT_DATE - INTERVAL '30 days'
                        AND name != 'TEMP'
                        ORDER BY last_visit DESC
                    """)
                else:
                    return jsonify({'error': 'Tipus de filtre invàlid'}), 400

                recipients = cursor.fetchall()
        
        by_channel = {'whatsapp': 0, 'telegram': 0}
        by_language = {'ca': 0, 'es': 0, 'en': 0}
        recipient_list = []
        
        for phone, name, language in recipients:
            channel = 'telegram' if phone.startswith('telegram:') else 'whatsapp'
            by_channel[channel] += 1
            by_language[language] = by_language.get(language, 0) + 1
            
            recipient_list.append({
                'phone': phone,
                'name': name,
                'language': language,
                'channel': channel
            })
        
        return jsonify({
            'total': len(recipients),
            'by_channel': by_channel,
            'by_language': by_language,
            'recipients': recipient_list
        }), 200
    
    except Exception as e:
        print(f"❌ Error previsualitzant broadcast: {e}")
        return jsonify({'error': str(e)}), 500
    
    
# ==========================================
# CUSTOMER UPDATE & DELETE ENDPOINTS
# ==========================================

@app.route('/api/customers/<phone>', methods=['PUT'])
def update_customer_api(phone):
    """✏️ Actualitzar informació d'un client"""
    try:
        data = request.json

        # Netejar prefix whatsapp: o telegram: si existeix
        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '')

        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Validar que existeix el client
                cursor.execute("SELECT name FROM customers WHERE phone = %s", (clean_phone,))
                existing = cursor.fetchone()

                if not existing:
                    return jsonify({'error': 'Client no trobat'}), 404

                # Camps actualitzables
                updates = []
                values = []

                if 'name' in data:
                    if not data['name'] or data['name'].strip() == '':
                        return jsonify({'error': 'El nom no pot estar buit'}), 400
                    updates.append("name = %s")
                    values.append(data['name'].strip())

                if 'language' in data:
                    # Acceptar qualsevol idioma (no limitem)
                    updates.append("language = %s")
                    values.append(data['language'])

                # Si s'ha canviat el telèfon
                new_phone = None
                if 'phone' in data and data['phone'] != clean_phone:
                    new_phone = data['phone'].strip()

                    # Validar que el nou telèfon no existeix ja
                    cursor.execute("SELECT name FROM customers WHERE phone = %s", (new_phone,))
                    if cursor.fetchone():
                        return jsonify({'error': 'Ja existeix un client amb aquest telèfon'}), 409

                    # Actualitzar telèfon a customers
                    updates.append("phone = %s")
                    values.append(new_phone)

                if not updates:
                    return jsonify({'error': 'No hi ha camps per actualitzar'}), 400

                # Actualitzar client
                values.append(clean_phone)
                query = f"UPDATE customers SET {', '.join(updates)} WHERE phone = %s"

                cursor.execute(query, values)

                # Si s'ha canviat el telèfon, actualitzar també a appointments i conversations
                if new_phone:
                    cursor.execute("UPDATE appointments SET phone = %s WHERE phone = %s", (new_phone, clean_phone))
                    cursor.execute("UPDATE conversations SET phone = %s WHERE phone = %s", (new_phone, clean_phone))
                    print(f"✅ Telèfon actualitzat de {clean_phone} a {new_phone}")

                conn.commit()

                # Obtenir dades actualitzades
                final_phone = new_phone if new_phone else clean_phone
                cursor.execute("""
                    SELECT phone, name, language, visit_count, last_visit
                    FROM customers
                    WHERE phone = %s
                """, (final_phone,))

                row = cursor.fetchone()

        if row:
            updated_customer = {
                'phone': row[0],
                'name': row[1],
                'language': row[2],
                'visit_count': row[3],
                'last_visit': row[4].isoformat() if row[4] else None
            }

            return jsonify({
                'message': 'Client actualitzat correctament',
                'customer': updated_customer
            }), 200
        else:
            return jsonify({'error': 'Error obtenint dades actualitzades'}), 500

    except Exception as e:
        print(f"❌ Error actualitzant client: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/customers/<phone>', methods=['DELETE'])
def delete_customer_api(phone):
    """🗑️ Eliminar un client i totes les seves dades"""
    try:
        # Netejar prefix whatsapp: o telegram: si existeix
        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '')

        with appointment_manager.get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Verificar que existeix el client
                cursor.execute("SELECT name FROM customers WHERE phone = %s", (clean_phone,))
                existing = cursor.fetchone()

                if not existing:
                    return jsonify({'error': 'Client no trobat'}), 404

                # Comprovar si té reserves futures
                cursor.execute("""
                    SELECT COUNT(*) FROM appointments
                    WHERE phone = %s AND status = 'confirmed' AND date >= CURRENT_DATE
                """, (clean_phone,))

                future_appointments = cursor.fetchone()[0]

                if future_appointments > 0:
                    return jsonify({
                        'error': f'No es pot eliminar. El client té {future_appointments} reserves futures. Cancel·la-les primer.'
                    }), 409

                # Eliminar en cascada:
                # 1. Conversations
                cursor.execute("DELETE FROM conversations WHERE phone = %s", (clean_phone,))
                deleted_conversations = cursor.rowcount

                # 2. Appointments (passades)
                cursor.execute("DELETE FROM appointments WHERE phone = %s", (clean_phone,))
                deleted_appointments = cursor.rowcount

                # 3. Customer
                cursor.execute("DELETE FROM customers WHERE phone = %s", (clean_phone,))

                conn.commit()

        print(f"✅ Client {clean_phone} eliminat:")
        print(f"   - {deleted_conversations} converses")
        print(f"   - {deleted_appointments} reserves")

        return jsonify({
            'message': 'Client eliminat correctament',
            'deleted': {
                'conversations': deleted_conversations,
                'appointments': deleted_appointments
            }
        }), 200

    except Exception as e:
        print(f"❌ Error eliminant client: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    

# --------------------------------------------------------------------------
# ENDPOINT PRINCIPAL - ENTRADA DE TRUCADA
# --------------------------------------------------------------------------
@app.route('/voice', methods=['POST'])
def voice_webhook():
    """
    📞 Endpoint inicial quan es rep una trucada telefònica
    Redirigeix a Eleven Labs Conversational AI
    """
    logger.info("📞 Trucada rebuda! Redirigint a Eleven Labs...")

    try:
        phone = request.values.get('From', '')
        call_sid = request.values.get('CallSid', '')
        
        # LOGS DETALLATS - Request complet
        logger.info(f"📞 De: {phone}, CallSid: {call_sid}")
        logger.info(f"📋 Request.values complet: {dict(request.values)}")
        logger.info(f"🔑 Headers rebuts: {dict(request.headers)}")

        # Netejar prefix si cal
        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '')
        customer_name = appointment_manager.get_customer_name(clean_phone)
        language = appointment_manager.get_customer_language(clean_phone) or 'es'

        # Crear resposta TwiML per connectar a Eleven Labs
        response = VoiceResponse()
        connect = response.connect()
        
        # WebSocket stream a Eleven Labs AMB totes les dades
        ws_url = elevenlabs_manager.get_websocket_url(
            phone=clean_phone,
            customer_name=customer_name,
            language=language
        )
        
        # LOGS DETALLATS - WebSocket URL
        logger.info(f"🌐 WebSocket URL generada: {ws_url}")
        logger.info(f"🔍 Tipus URL: {type(ws_url)}, Longitud: {len(ws_url) if ws_url else 0}")
        
        # Verificar que la URL sigui vàlida
        if not ws_url or not ws_url.startswith('wss://'):
            logger.error(f"❌ URL WebSocket INVÀLIDA: '{ws_url}'")
            raise ValueError(f"WebSocket URL invàlida: {ws_url}")
        
        # Configurar Stream amb paràmetres per Eleven Labs
        # IMPORTANT: Afegim statusCallback per veure què passa amb el WebSocket
        stream = connect.stream(
            url=ws_url,
            statusCallback='https://web-production-261e.up.railway.app/voice/stream/events',
            statusCallbackMethod='POST'
        )

        logger.info(f"🔔 Status callback configurat: /voice/stream/events")

        # Paràmetres opcionals (si Eleven Labs els necessita)
        # stream.parameter(name='phone', value=clean_phone)

        # LOGS DETALLATS - TwiML generat
        twiml_str = str(response)
        logger.info("=" * 80)
        logger.info(f"📤 TwiML Response generat:")
        logger.info(twiml_str)
        logger.info("=" * 80)
        logger.info(f"📏 Longitud TwiML: {len(twiml_str)} bytes")
        logger.info(f"🔗 WebSocket URL enviat a Twilio:")
        logger.info(f"   {ws_url}")
        logger.info("=" * 80)
        logger.info("✅ Resposta TwiML enviada a Twilio")
        logger.info("🔄 Ara Twilio hauria de connectar al WebSocket d'ElevenLabs")
        logger.info("🔄 Si ElevenLabs accepta la connexió, cridarà /elevenlabs/init")
        logger.info("🔄 MIRA ELS LOGS - Si NO veus '🎉 ELEVENLABS /INIT CRIDAT!' en els propers segons,")
        logger.info("🔄 significa que ElevenLabs NO té configurat el webhook o rebutja la connexió")
        logger.info("=" * 80)

        return twiml_str

    except Exception as e:
        logger.exception("❌ Error en voice_webhook")
        response = VoiceResponse()
        response.say(
            "Lo siento, ha ocurrido un error. Por favor, intenta llamar de nuevo más tarde.",
            language='es-ES',
            voice='Google.es-ES-Neural2-C'
        )
        response.hangup()
        return str(response)

# # --------------------------------------------------------------------------
# # ENDPOINT DE PROCESSAMENT DE LA CONVERSA
# # --------------------------------------------------------------------------
# @app.route('/voice/process', methods=['POST'])
# def voice_process():
#     """
#     🎤 Endpoint que processa el text transcrit de la veu de l'usuari
#     """
#     start_time = time.time()
#     logger.info("🎤 Processant entrada de veu...")

#     try:
#         phone = request.values.get('From', '')
#         call_sid = request.values.get('CallSid', '')
#         speech_result = request.values.get('SpeechResult', '').strip()

#         logger.info(f"🎤 De: {phone}")
#         logger.info(f"🗣️ Text: '{speech_result}'")

#         if not speech_result:
#             return str(voice_handler.create_error_response())

#         # Processar transcripció (inclou IA + TTS)
#         response = voice_handler.process_transcription(speech_result, phone, call_sid)
        
#         total_time = time.time() - start_time
#         logger.info(f"⏱️ ENDPOINT TOTAL: {total_time:.2f}s")
        
#         return str(response)

#     except Exception as e:
#         logger.exception("❌ Error en voice_process")
#         return str(voice_handler.create_error_response())

# # --------------------------------------------------------------------------
# # CALLBACK DE TRANSCRIPCIÓ ASÍNCRONA
# # --------------------------------------------------------------------------
# @app.route('/voice/transcription', methods=['POST'])
# def voice_transcription():
#     """
#     📝 Callback que rep la transcripció de Twilio de manera asíncrona
#     """
#     logger.info("📝 Callback de transcripció rebut!")

#     try:
#         transcription = request.values.get('TranscriptionText', '')
#         phone = request.values.get('From', '')
#         call_sid = request.values.get('CallSid', '')
#         transcription_sid = request.values.get('TranscriptionSid', '')

#         logger.info(f"📝 Transcripció: '{transcription}'")
#         logger.info(f"📝 De: {phone}, CallSid: {call_sid}")

#         if not transcription or transcription.strip() == '':
#             logger.warning("⚠️ Transcripció buida!")
#             return jsonify({'status': 'empty'}), 200

#         # Processar amb la IA
#         voice_handler.process_transcription(transcription, phone, call_sid)
#         return jsonify({'status': 'processed'}), 200

#     except Exception as e:
#         logger.exception("❌ Error en voice_transcription")
#         return jsonify({'error': str(e)}), 500

# --------------------------------------------------------------------------
# CALLBACK D'ESTAT DE LA TRUCADA
# --------------------------------------------------------------------------
@app.route('/voice/status', methods=['POST'])
def voice_status():
    """
    📊 Callback d'estat de la trucada (completada, fallida, ocupada, etc.)
    """
    call_status = request.values.get('CallStatus', '')
    phone = request.values.get('From', '')
    call_sid = request.values.get('CallSid', '')

    # LOGS DETALLATS - Tota la informació del status
    call_duration = request.values.get('CallDuration', '0')
    recording_duration = request.values.get('RecordingDuration', '0')

    # NOUS LOGS - Capturar TOTS els possibles errors i informació de Twilio
    error_code = request.values.get('ErrorCode', '')
    error_message = request.values.get('ErrorMessage', '')
    stream_sid = request.values.get('StreamSid', '')

    # Capturar més camps d'error possibles
    recording_url = request.values.get('RecordingUrl', '')
    recording_sid = request.values.get('RecordingSid', '')
    parent_call_sid = request.values.get('ParentCallSid', '')
    answered_by = request.values.get('AnsweredBy', '')

    logger.info(f"📊 Estat de trucada: {call_status} | Telèfon: {phone} | CallSid: {call_sid}")
    logger.info(f"⏱️ Duració trucada: {call_duration} segons")

    # Informació addicional útil
    if stream_sid:
        logger.info(f"📡 Stream SID: {stream_sid}")
    if answered_by:
        logger.info(f"📞 Answered by: {answered_by}")
    if parent_call_sid:
        logger.info(f"🔗 Parent Call SID: {parent_call_sid}")

    # LOG ERROR SI EXISTEIX
    if error_code:
        logger.error("=" * 80)
        logger.error(f"🚨 ERROR TWILIO DETECTAT!")
        logger.error(f"🚨 Error Code: {error_code}")
        logger.error(f"🚨 Error Message: {error_message}")
        logger.error(f"🔍 Stream SID: {stream_sid}")
        logger.error(f"🔍 Call SID: {call_sid}")
        logger.error("=" * 80)

        # Error 31921 és específic de WebSocket close
        if error_code == '31921':
            logger.error("💥 ERROR 31921: WebSocket tancat per ElevenLabs")
            logger.error("🔍 DIAGNÒSTIC:")
            logger.error("   ❌ ElevenLabs ha tancat la connexió WebSocket immediatament")
            logger.error("   ❌ Possibles causes:")
            logger.error("      1. Webhook /elevenlabs/init NO configurat a ElevenLabs")
            logger.error("      2. Agent ID invàlid o agent no existeix")
            logger.error("      3. Agent no té activada la integració de Twilio Stream")
            logger.error("      4. Problemes d'autenticació amb ElevenLabs")
            logger.error("      5. Quota d'ElevenLabs exhaurida")
            logger.error("=" * 80)

    logger.info(f"📋 Status.values complet: {dict(request.values)}")
    logger.info(f"🔑 Status.headers: {dict(request.headers)}")

    if call_status == 'completed':
        logger.info(f"✅ Trucada completada: {call_sid}")
        if int(call_duration) < 5:
            logger.warning("⚠️" * 40)
            logger.warning(f"⚠️ TRUCADA MASSA CURTA! Només {call_duration}s")
            logger.warning(f"⚠️ Això indica que ElevenLabs ha tancat el WebSocket immediatament")
            logger.warning(f"⚠️ REVISA:")
            logger.warning(f"⚠️   1. Configura /elevenlabs/init a ElevenLabs com a 'Conversation Init Webhook'")
            logger.warning(f"⚠️   2. URL: https://web-production-261e.up.railway.app/elevenlabs/init")
            logger.warning(f"⚠️   3. Verifica que l'agent tingui activada la integració de Twilio")
            logger.warning("⚠️" * 40)
    elif call_status == 'failed':
        logger.error(f"❌ Trucada fallida: {call_sid}")
        logger.error(f"❌ Motiu: {error_message if error_message else 'Desconegut'}")
    elif call_status == 'busy':
        logger.warning(f"📵 Número ocupat: {phone}")
    elif call_status == 'no-answer':
        logger.warning(f"📵 No ha respost: {phone}")

    return jsonify({'status': 'ok'}), 200

# --------------------------------------------------------------------------
# CALLBACK QUAN L’USUARI PENJA
# --------------------------------------------------------------------------
@app.route('/voice/hangup', methods=['POST'])
def voice_hangup():
    """
    👋 Gestiona quan es penja la trucada
    """
    phone = request.values.get('From', '')
    call_sid = request.values.get('CallSid', '')
    call_duration = request.values.get('CallDuration', '0')

    logger.info(f"👋 Trucada penjada | De: {phone} | Duració: {call_duration}s")
    return jsonify({'status': 'ok'}), 200

# --------------------------------------------------------------------------
# CALLBACK D'ESDEVENIMENTS DEL WEBSOCKET STREAM
# --------------------------------------------------------------------------
@app.route('/voice/stream/events', methods=['POST'])
def voice_stream_events():
    """
    🔊 Captura esdeveniments del WebSocket Stream de Twilio
    Això ens dirà exactament què passa amb la connexió a ElevenLabs
    """
    try:
        # Intentar obtenir JSON
        data = request.get_json(force=True, silent=True) or {}

        event_type = data.get('event', request.values.get('event', 'unknown'))
        stream_sid = data.get('streamSid', request.values.get('StreamSid', ''))
        call_sid = request.values.get('CallSid', '')

        logger.info("🔊" * 40)
        logger.info(f"🔊 STREAM EVENT REBUT: {event_type}")
        logger.info(f"🔊 Stream SID: {stream_sid}")
        logger.info(f"🔊 Call SID: {call_sid}")
        logger.info(f"🔊 Data complet (JSON): {data}")
        logger.info(f"🔊 Values complet: {dict(request.values)}")
        logger.info(f"🔊 Headers: {dict(request.headers)}")
        logger.info("🔊" * 40)

        # Esdeveniments específics
        if event_type == 'connected':
            logger.info("✅ Stream WebSocket CONNECTAT a ElevenLabs!")
        elif event_type == 'start':
            logger.info("▶️ Stream WebSocket ha COMENÇAT!")
            logger.info(f"▶️ Metadata: {data.get('start', {})}")
        elif event_type == 'media':
            # No loguegem cada paquet de media (seria massa)
            pass
        elif event_type == 'stop':
            logger.warning("⏹️ Stream WebSocket ha PARAT!")
            logger.warning(f"⏹️ Stop info: {data.get('stop', {})}")
        elif event_type == 'closed':
            logger.error("❌ Stream WebSocket TANCAT!")
            logger.error(f"❌ Close info: {data}")
        else:
            logger.warning(f"⚠️ Event desconegut: {event_type}")

        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        logger.exception(f"❌ Error processant stream event: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ==========================================
# ELEVEN LABS - WEBHOOKS PER FUNCIONS
# ==========================================

@app.route('/elevenlabs/init', methods=['GET', 'POST'])
def elevenlabs_init():
    """
    Webhook cridat per ElevenLabs quan comença una conversa
    Retorna les dades del client (nom, idioma, data actual, telèfon)
    """
    logger.info("=" * 80)
    logger.info("🎉 " * 20)
    logger.info("🎉 ELEVENLABS /INIT CRIDAT! - ElevenLabs està connectant!")
    logger.info("🎉 " * 20)
    logger.info(f"🔄 [ELEVEN LABS INIT] Webhook cridat! Method: {request.method}")
    logger.info(f"🔄 [ELEVEN LABS INIT] URL: {request.url}")
    logger.info(f"🔄 [ELEVEN LABS INIT] Path: {request.path}")
    logger.info(f"🔄 [ELEVEN LABS INIT] Remote IP: {request.remote_addr}")
    logger.info(f"🔄 [ELEVEN LABS INIT] User Agent: {request.headers.get('User-Agent', 'N/A')}")
    logger.info("=" * 80)
    
    # Si és GET, retornar info de que el webhook està actiu
    if request.method == 'GET':
        logger.info("ℹ️ [ELEVEN LABS INIT] Request GET rebut - retornant status")
        return jsonify({
            'status': 'active',
            'endpoint': '/elevenlabs/init',
            'message': 'Webhook is ready to receive POST requests from ElevenLabs'
        }), 200
    
    try:
        # Intentar obtenir dades com JSON
        try:
            data = request.json
            logger.info(f"📋 [ELEVEN LABS INIT] Dades JSON rebudes: {data}")
        except Exception as json_error:
            logger.warning(f"⚠️ [ELEVEN LABS INIT] No es pot parsejar JSON: {json_error}")
            logger.info(f"📋 [ELEVEN LABS INIT] Raw data: {request.data}")
            logger.info(f"📋 [ELEVEN LABS INIT] Form data: {request.form}")
            data = {}
        
        logger.info(f"🔑 [ELEVEN LABS INIT] Headers: {dict(request.headers)}")
        logger.info(f"🔑 [ELEVEN LABS INIT] Content-Type: {request.content_type}")
        
        # Obtenir telèfon - ElevenLabs envia 'caller_id'
        phone = ''
        
        if isinstance(data, dict):
            # Format ElevenLabs (nou)
            phone = data.get('caller_id', '')
            
            # Format antic (per compatibilitat)
            if not phone:
                phone = data.get('call', {}).get('from', '')
        
        # Provar form/values com a fallback
        if not phone:
            phone = request.form.get('From', '') or request.values.get('From', '')
            logger.info(f"📞 [ELEVEN LABS INIT] Telèfon extret de form/values: {phone}")
        
        logger.info(f"📞 [ELEVEN LABS INIT] Telèfon d'ElevenLabs: {phone}")
        
        # Netejar prefixos però MANTENIR el +
        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '').replace('client:', '')
        
        logger.info(f"📞 [ELEVEN LABS INIT] Telèfon final: {clean_phone}")
        
        # Buscar client a la BD
        customer_name = appointment_manager.get_customer_name(clean_phone) if clean_phone else None
        language = appointment_manager.get_customer_language(clean_phone) if clean_phone else 'es'
        
        if not language:
            language = 'es'
        
        logger.info(f"👤 [ELEVEN LABS INIT] Client: {customer_name}")
        logger.info(f"🌐 [ELEVEN LABS INIT] Idioma: {language}")
        
        # Obtenir data actual
        from datetime import datetime
        import locale
        
        today = datetime.now()
        
        # Formatar segons idioma
        day_names = {
            'es': ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'],
            'ca': ['dilluns', 'dimarts', 'dimecres', 'dijous', 'divendres', 'dissabte', 'diumenge'],
            'en': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        }
        
        month_names = {
            'es': ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'],
            'ca': ['gener', 'febrer', 'març', 'abril', 'maig', 'juny', 'juliol', 'agost', 'setembre', 'octubre', 'novembre', 'desembre'],
            'en': ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
        }
        
        day_name = day_names.get(language, day_names['es'])[today.weekday()]
        month_name = month_names.get(language, month_names['es'])[today.month - 1]
        
        if language == 'en':
            today_formatted = f"{day_name}, {month_name} {today.day}, {today.year}"
        else:
            today_formatted = f"{day_name} {today.day} de {month_name} de {today.year}"
        
        today_iso = today.strftime('%Y-%m-%d')
        
        logger.info(f"📅 [ELEVEN LABS INIT] Data d'avui: {today_formatted} ({today_iso})")
        
        # Format correcte per ElevenLabs Conversation Initiation
        response_data = {
            "type": "conversation_initiation_client_data",
            "dynamic_variables": {
                "phone": clean_phone or '',
                "customer_name": customer_name or 'Cliente',
                "is_known_customer": bool(customer_name),
                "language": language,
                "today_date": today_iso,
                "today_formatted": today_formatted,
                "current_year": str(today.year)
            }
        }
        
        logger.info(f"✅ [ELEVEN LABS INIT] Retornant: {response_data}")
        logger.info("=" * 70)
        
        return jsonify(response_data), 200
    
    except Exception as e:
        logger.exception(f"❌ [ELEVEN LABS INIT] Error: {e}")
        from datetime import datetime
        today = datetime.now()
        fallback_data = {
            "type": "conversation_initiation_client_data",
            "dynamic_variables": {
                "phone": '',
                "customer_name": 'Cliente',
                "is_known_customer": False,
                "language": 'es',
                "today_date": today.strftime('%Y-%m-%d'),
                "today_formatted": f"lunes {today.day} de octubre de {today.year}",
                "current_year": str(today.year)
            }
        }
        logger.info(f"⚠️ [ELEVEN LABS INIT] Retornant fallback: {fallback_data}")
        return jsonify(fallback_data), 500

@app.route('/elevenlabs/tool/create_appointment', methods=['POST'])
def elevenlabs_create_appointment():
    """
    Webhook cridat per Eleven Labs quan vol crear una reserva
    """
    try:
        data = request.json
        logger.info(f"📞 [ELEVEN LABS] create_appointment cridat amb: {data}")
        logger.info(f"📞 [ELEVEN LABS CREATE] Dades rebudes: {data}")
        logger.info(f"📞 [ELEVEN LABS CREATE] Headers: {dict(request.headers)}")
        
        # Obtenir dades - PHONE ara ve directament del body (paràmetre obligatori de la tool)
        phone = data.get('phone', '')
        customer_name = data.get('customer_name')
        date = data.get('date')
        time = data.get('time')
        num_people = data.get('num_people', 2)

        logger.info(f"📋 [ELEVEN LABS CREATE] Phone: {phone}")
        logger.info(f"📋 [ELEVEN LABS CREATE] Name: {customer_name}")
        logger.info(f"📋 [ELEVEN LABS CREATE] Date: {date}")
        logger.info(f"📋 [ELEVEN LABS CREATE] Time: {time}")
        logger.info(f"📋 [ELEVEN LABS CREATE] People: {num_people}")
        
        # Validar camps obligatoris (incloent telèfon)
        if not all([phone, customer_name, date, time]):
            return jsonify({
                'success': False,
                'message': 'Falta informació. Necessito telèfon, nom, data i hora.'
            }), 400

        max_people = config.get_int('max_people_per_booking', 8)
        if num_people < 1 or num_people > max_people:
            return jsonify({
                'success': False,
                'message': f'Solo aceptamos reservas de 1 a {max_people} personas.'
            }), 400
        
        # Netejar només prefixos de plataforma (mantenir el + i els dígits)
        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '').strip()
        
        logger.info(f"🧹 [ELEVEN LABS CREATE] Telèfon per guardar a BD: {clean_phone}")
        
        # Guardar info del client
        appointment_manager.save_customer_info(clean_phone, customer_name)

        # Obtenir idioma del client
        language = appointment_manager.get_customer_language(clean_phone) or 'es'

        # Obtenir durada per defecte de configuració
        default_duration = config.get_float('default_booking_duration_hours', 1.0)

        # ⭐ Crear reserva amb alternatives
        result = appointment_manager.create_appointment_with_alternatives(
            phone=clean_phone,
            client_name=customer_name,
            date=date,
            time=time,
            num_people=num_people,
            duration_hours=default_duration
        )

        logger.info(f"📊 [ELEVEN LABS CREATE] Result: {result}")

        # Processar el resultat segons el tipus de resposta
        if result['success']:
            # ✅ Reserva creada correctament
            appointment = result['appointment']

            # Formatar data i hora de manera natural
            from utils.ai_processor_voice import format_date_natural, format_time_natural
            date_natural = format_date_natural(date, language)
            time_natural = format_time_natural(time, language)

            messages = {
                'es': f"Reserva confirmada para {num_people} personas el {date_natural} a las {time_natural}. ¡Nos vemos!",
                'ca': f"Reserva confirmada per {num_people} persones el {date_natural} a les {time_natural}. Ens veiem!",
                'en': f"Reservation confirmed for {num_people} people on {date_natural} at {time_natural}. See you!"
            }

            logger.info(f"✅ [ELEVEN LABS CREATE] Reserva creada amb èxit: ID {appointment['id']}")

            return jsonify({
                'success': True,
                'message': messages.get(language, messages['es'])
            }), 200

        else:
            # ❌ No hi ha disponibilitat - proposar alternatives
            if 'alternative' in result:
                alt = result['alternative']
                alt_date = alt['date']
                alt_time = alt['time']

                # Formatar alternativa de manera natural
                from utils.ai_processor_voice import format_date_natural, format_time_natural
                alt_date_natural = format_date_natural(alt_date, language)
                alt_time_natural = format_time_natural(alt_time, language)

                messages = {
                    'es': f"Lo siento, no hay disponibilidad el {format_date_natural(date, language)} a las {format_time_natural(time, language)}. Pero sí tenemos mesa el {alt_date_natural} a las {alt_time_natural}. ¿Te va bien esta alternativa?",
                    'ca': f"Ho sento, no hi ha disponibilitat el {format_date_natural(date, language)} a les {format_time_natural(time, language)}. Però sí que tenim taula el {alt_date_natural} a les {alt_time_natural}. Et va bé aquesta alternativa?",
                    'en': f"Sorry, no availability on {format_date_natural(date, language)} at {format_time_natural(time, language)}. But we have a table on {alt_date_natural} at {alt_time_natural}. Does this alternative work for you?"
                }

                logger.warning(f"⚠️ [ELEVEN LABS CREATE] No disponibilitat. Alternativa proposada: {alt_date} {alt_time}")

                return jsonify({
                    'success': False,
                    'message': messages.get(language, messages['es']),
                    'alternative_date': alt_date,
                    'alternative_time': alt_time
                }), 200  # 200 perquè l'agent processi la resposta

            else:
                # No hi ha alternatives en els propers dies
                messages = {
                    'es': f"Lo siento mucho, no tenemos disponibilidad para {num_people} personas en los próximos días. ¿Podrías probar con otra fecha más adelante?",
                    'ca': f"Ho sento molt, no tenim disponibilitat per {num_people} persones en els propers dies. Pots provar amb una altra data més endavant?",
                    'en': f"I'm very sorry, we don't have availability for {num_people} people in the coming days. Could you try another date further ahead?"
                }

                logger.warning(f"❌ [ELEVEN LABS CREATE] No hi ha disponibilitat en els propers dies")

                return jsonify({
                    'success': False,
                    'message': messages.get(language, messages['es'])
                }), 200  # 200 perquè l'agent processi la resposta
    
    except Exception as e:
        logger.exception(f"❌ Error en elevenlabs_create_appointment: {e}")
        return jsonify({
            'success': False,
            'message': 'Ha ocurrido un error. ¿Puedes repetir los datos?'
        }), 500


@app.route('/elevenlabs/tool/list_appointments', methods=['POST'])
def elevenlabs_list_appointments():
    """
    Webhook cridat per Eleven Labs quan vol llistar reserves
    """
    try:
        data = request.json
        logger.info(f"📞 [ELEVEN LABS] list_appointments cridat amb: {data}")
        
        phone = data.get('customer_phone', data.get('phone', ''))
        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '').strip()
        
        # Obtenir reserves
        appointments = appointment_manager.get_appointments(clean_phone)
        language = appointment_manager.get_customer_language(clean_phone) or 'es'
        
        if not appointments:
            messages = {
                'es': "No tienes reservas programadas.",
                'ca': "No tens reserves programades.",
                'en': "You don't have any scheduled reservations."
            }
            return jsonify({
                'success': True,
                'message': messages.get(language, messages['es']),
                'appointments': []
            }), 200

        # Formatar de manera natural
        from utils.ai_processor_voice import format_date_natural, format_time_natural

        # Preparar llista de reserves amb detalls
        appointments_list = []
        for apt in appointments:
            apt_id, name, date, start_time, end_time, num_people, table_num, capacity, status = apt
            date_natural = format_date_natural(date, language)
            time_natural = format_time_natural(start_time, language)

            appointments_list.append({
                'id': apt_id,
                'date': str(date),
                'time': start_time.strftime("%H:%M"),
                'num_people': num_people,
                'date_natural': date_natural,
                'time_natural': time_natural
            })

        # Construir missatge segons el nombre de reserves
        if len(appointments) == 1:
            apt = appointments_list[0]
            messages = {
                'es': f"Tienes una reserva: el {apt['date_natural']} a las {apt['time_natural']} para {apt['num_people']} personas.",
                'ca': f"Tens una reserva: el {apt['date_natural']} a les {apt['time_natural']} per {apt['num_people']} persones.",
                'en': f"You have one reservation: on {apt['date_natural']} at {apt['time_natural']} for {apt['num_people']} people."
            }
        else:
            # Múltiples reserves
            headers = {
                'es': f"Tienes {len(appointments)} reservas: ",
                'ca': f"Tens {len(appointments)} reserves: ",
                'en': f"You have {len(appointments)} reservations: "
            }
            message = headers.get(language, headers['es'])

            for i, apt in enumerate(appointments_list):
                if i > 0:
                    message += "; "
                message += f"el {apt['date_natural']} a {'las' if language == 'es' else 'les' if language == 'ca' else ''} {apt['time_natural']} para {apt['num_people']} personas"

            message += "."
            messages = {language: message}

        return jsonify({
            'success': True,
            'message': messages.get(language, messages['es']),
            'appointments': appointments_list  # IDs per ús intern de l'agent
        }), 200
    
    except Exception as e:
        logger.exception(f"❌ Error en elevenlabs_list_appointments: {e}")
        return jsonify({
            'success': False,
            'message': 'Error consultando reservas.'
        }), 500


@app.route('/elevenlabs/tool/update_appointment', methods=['POST'])
def elevenlabs_update_appointment():
    """
    Webhook cridat per Eleven Labs quan vol modificar una reserva
    Ara accepta date + time per identificar la reserva a modificar
    """
    try:
        data = request.json
        logger.info(f"📞 [ELEVEN LABS] update_appointment cridat amb: {data}")

        phone = data.get('customer_phone', data.get('phone', ''))
        date = data.get('date')  # Data actual de la reserva
        time = data.get('time')  # Hora actual de la reserva
        new_date = data.get('new_date')
        new_time = data.get('new_time')
        new_num_people = data.get('new_num_people')

        if not all([phone, date, time]):
            return jsonify({
                'success': False,
                'message': 'Necesito la fecha y hora actual de la reserva para modificarla.'
            }), 400

        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '').strip()
        language = appointment_manager.get_customer_language(clean_phone) or 'es'

        logger.info(f"🔍 [ELEVEN LABS UPDATE] Buscant reserva per {clean_phone} el {date} a les {time}")

        # Buscar la reserva per data i hora
        appointments = appointment_manager.get_appointments(clean_phone)

        if not appointments:
            messages = {
                'es': "No tienes ninguna reserva programada.",
                'ca': "No tens cap reserva programada.",
                'en': "You don't have any scheduled reservations."
            }
            return jsonify({
                'success': False,
                'message': messages.get(language, messages['es'])
            }), 404

        # Buscar la reserva que coincideixi
        apt_id = None
        for apt in appointments:
            apt_id_temp, name, apt_date, start_time, end_time, num_people, table_num, capacity, status = apt

            if str(apt_date) == date and start_time.strftime("%H:%M") == time:
                apt_id = apt_id_temp
                logger.info(f"✅ [ELEVEN LABS UPDATE] Reserva trobada: ID {apt_id}")
                break

        if not apt_id:
            from utils.ai_processor_voice import format_date_natural, format_time_natural
            date_natural = format_date_natural(date, language)
            time_natural = format_time_natural(time, language)

            messages = {
                'es': f"No encuentro ninguna reserva para el {date_natural} a las {time_natural}.",
                'ca': f"No trobo cap reserva pel {date_natural} a les {time_natural}.",
                'en': f"I can't find any reservation for {date_natural} at {time_natural}."
            }
            return jsonify({
                'success': False,
                'message': messages.get(language, messages['es'])
            }), 404

        # Actualitzar la reserva
        result = appointment_manager.update_appointment(
            phone=clean_phone,
            appointment_id=apt_id,
            new_date=new_date,
            new_time=new_time,
            new_num_people=new_num_people
        )

        if result:
            from utils.ai_processor_voice import format_date_natural, format_time_natural

            # Construir missatge segons què s'ha modificat
            changes = []
            if new_date:
                changes.append(f"fecha: {format_date_natural(new_date, language)}")
            if new_time:
                changes.append(f"hora: {format_time_natural(new_time, language)}")
            if new_num_people:
                changes.append(f"personas: {new_num_people}")

            changes_text = ", ".join(changes)

            messages = {
                'es': f"Reserva actualizada correctamente. Cambios: {changes_text}.",
                'ca': f"Reserva actualitzada correctament. Canvis: {changes_text}.",
                'en': f"Reservation updated successfully. Changes: {changes_text}."
            }

            logger.info(f"✅ [ELEVEN LABS UPDATE] Reserva {apt_id} actualitzada")

            return jsonify({
                'success': True,
                'message': messages.get(language, messages['es'])
            }), 200
        else:
            messages = {
                'es': "No se pudo actualizar la reserva. Puede que no haya mesas disponibles para los nuevos datos.",
                'ca': "No s'ha pogut actualitzar la reserva. Pot ser que no hi hagi taules disponibles per les noves dades.",
                'en': "Could not update the reservation. There might not be tables available for the new data."
            }

            logger.error(f"❌ [ELEVEN LABS UPDATE] Error actualitzant reserva {apt_id}")

            return jsonify({
                'success': False,
                'message': messages.get(language, messages['es'])
            }), 409

    except Exception as e:
        logger.exception(f"❌ Error en elevenlabs_update_appointment: {e}")
        return jsonify({
            'success': False,
            'message': 'Error actualizando la reserva.'
        }), 500


@app.route('/elevenlabs/tool/cancel_appointment', methods=['POST'])
def elevenlabs_cancel_appointment():
    """
    Webhook cridat per Eleven Labs quan vol cancel·lar una reserva
    Ara accepta date + time en lloc d'appointment_id per més naturalitat
    """
    try:
        data = request.json
        logger.info(f"📞 [ELEVEN LABS] cancel_appointment cridat amb: {data}")

        phone = data.get('customer_phone', data.get('phone', ''))
        date = data.get('date')  # YYYY-MM-DD
        time = data.get('time')  # HH:MM

        if not all([phone, date, time]):
            return jsonify({
                'success': False,
                'message': 'Necesito la fecha y hora de la reserva para cancelarla.'
            }), 400

        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '').strip()
        language = appointment_manager.get_customer_language(clean_phone) or 'es'

        logger.info(f"🔍 [ELEVEN LABS CANCEL] Buscant reserva per {clean_phone} el {date} a les {time}")

        # Buscar la reserva per data i hora
        appointments = appointment_manager.get_appointments(clean_phone)

        if not appointments:
            messages = {
                'es': "No tienes ninguna reserva programada.",
                'ca': "No tens cap reserva programada.",
                'en': "You don't have any scheduled reservations."
            }
            return jsonify({
                'success': False,
                'message': messages.get(language, messages['es'])
            }), 404

        # Buscar la reserva que coincideixi amb data i hora
        apt_id = None
        for apt in appointments:
            apt_id_temp, name, apt_date, start_time, end_time, num_people, table_num, capacity, status = apt

            # Comparar data i hora
            if str(apt_date) == date and start_time.strftime("%H:%M") == time:
                apt_id = apt_id_temp
                logger.info(f"✅ [ELEVEN LABS CANCEL] Reserva trobada: ID {apt_id}")
                break

        if not apt_id:
            from utils.ai_processor_voice import format_date_natural, format_time_natural
            date_natural = format_date_natural(date, language)
            time_natural = format_time_natural(time, language)

            messages = {
                'es': f"No encuentro ninguna reserva para el {date_natural} a las {time_natural}.",
                'ca': f"No trobo cap reserva pel {date_natural} a les {time_natural}.",
                'en': f"I can't find any reservation for {date_natural} at {time_natural}."
            }
            return jsonify({
                'success': False,
                'message': messages.get(language, messages['es'])
            }), 404

        # Cancel·lar la reserva
        success = appointment_manager.cancel_appointment(clean_phone, apt_id)

        if success:
            from utils.ai_processor_voice import format_date_natural, format_time_natural
            date_natural = format_date_natural(date, language)
            time_natural = format_time_natural(time, language)

            messages = {
                'es': f"Reserva del {date_natural} a las {time_natural} cancelada correctamente.",
                'ca': f"Reserva del {date_natural} a les {time_natural} cancel·lada correctament.",
                'en': f"Reservation for {date_natural} at {time_natural} cancelled successfully."
            }

            logger.info(f"✅ [ELEVEN LABS CANCEL] Reserva {apt_id} cancel·lada correctament")

            return jsonify({
                'success': True,
                'message': messages.get(language, messages['es'])
            }), 200
        else:
            messages = {
                'es': "No se pudo cancelar la reserva.",
                'ca': "No s'ha pogut cancel·lar la reserva.",
                'en': "Could not cancel the reservation."
            }

            logger.error(f"❌ [ELEVEN LABS CANCEL] Error cancel·lant reserva {apt_id}")

            return jsonify({
                'success': False,
                'message': messages.get(language, messages['es'])
            }), 400

    except Exception as e:
        logger.exception(f"❌ Error en elevenlabs_cancel_appointment: {e}")
        return jsonify({
            'success': False,
            'message': 'Error cancelando la reserva.'
        }), 500


# --------------------------------------------------------------------------
# CLIENT CONFIGURATION ENDPOINTS
# --------------------------------------------------------------------------

from utils.config import config

@app.route('/api/config', methods=['GET'])
@login_required
@admin_required
def get_client_config():
    """
    📋 Obtenir tota la configuració del restaurant amb metadades
    Només accessible per admin/owner
    """
    try:
        configs = config.get_all_with_metadata()

        logger.info(f"✅ Configuració obtinguda: {len(configs)} claus")

        return jsonify(configs), 200

    except Exception as e:
        logger.error(f"❌ Error obtenint configuració: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/<key>', methods=['PUT'])
@login_required
@admin_required
def update_client_config(key):
    """
    🔧 Actualitzar una clau de configuració
    Només accessible per admin/owner
    """
    try:
        data = request.json
        new_value = data.get('value')

        if new_value is None:
            return jsonify({'error': 'El camp "value" és obligatori'}), 400

        # Actualitzar configuració
        config.set(key, new_value)

        logger.info(f"✅ Configuració actualitzada: {key} = {new_value}")

        return jsonify({
            'message': 'Configuració actualitzada correctament',
            'key': key,
            'value': new_value
        }), 200

    except Exception as e:
        logger.error(f"❌ Error actualitzant configuració {key}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
if __name__ == '__main__':
    logger.info("🚀 Iniciant servidor Flask per Twilio Voice...")
    port = int(os.getenv('PORT', 5001))  # Port 5001 per evitar conflicte amb AirPlay
    app.run(host='0.0.0.0', port=port, debug=True)
