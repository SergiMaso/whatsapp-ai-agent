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

load_dotenv()

app = Flask(__name__)
CORS(app)  # Habilitar CORS per al frontend

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

# ========================================
# API REST ENDPOINTS
# ========================================

@app.route('/api/appointments', methods=['GET'])
def get_appointments():
    """Obtenir totes les reserves"""
    try:
        conn = appointment_manager.get_connection()
        cursor = conn.cursor()
        
        # Obtenir reserves amb informació de taula i notes
        cursor.execute("""
            SELECT a.id, a.phone, a.client_name, a.date, a.start_time, a.end_time, 
                   a.num_people, a.status, t.table_number, t.capacity, a.created_at, a.notes, a.table_id,
                   a.seated_at, a.left_at, a.duration_minutes, a.no_show, a.delay_minutes
            FROM appointments a
            LEFT JOIN tables t ON a.table_id = t.id
            ORDER BY a.start_time DESC
        """)
        
        appointments = []
        for row in cursor.fetchall():
            appointments.append({
                'id': row[0],
                'phone': row[1],
                'client_name': row[2],
                'date': row[3].isoformat() if row[3] else None,
                'start_time': row[4].isoformat() if row[4] else None,
                'end_time': row[5].isoformat() if row[5] else None,
                'num_people': row[6],
                'status': row[7],
                'table_number': row[8],
                'table_capacity': row[9],
                'created_at': row[10].isoformat() if row[10] else None,
                'notes': row[11],
                'table_id': row[12],
                'seated_at': row[13].isoformat() if row[13] else None,
                'left_at': row[14].isoformat() if row[14] else None,
                'duration_minutes': row[15],
                'no_show': row[16],
                'delay_minutes': row[17]
            })
        
        cursor.close()
        conn.close()
        
        return jsonify(appointments), 200
    
    except Exception as e:
        print(f"❌ Error obtenint reserves: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/appointments/<int:appointment_id>', methods=['GET'])
def get_appointment(appointment_id):
    """Obtenir una reserva específica"""
    try:
        conn = appointment_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT a.id, a.phone, a.client_name, a.date, a.start_time, a.end_time, 
                   a.num_people, a.status, t.table_number, t.capacity
            FROM appointments a
            LEFT JOIN tables t ON a.table_id = t.id
            WHERE a.id = %s
        """, (appointment_id,))
        
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not row:
            return jsonify({'error': 'Reserva no trobada'}), 404
        
        appointment = {
            'id': row[0],
            'phone': row[1],
            'client_name': row[2],
            'date': row[3].isoformat() if row[3] else None,
            'start_time': row[4].isoformat() if row[4] else None,
            'end_time': row[5].isoformat() if row[5] else None,
            'num_people': row[6],
            'status': row[7],
            'table_number': row[8],
            'table_capacity': row[9]
        }
        
        return jsonify(appointment), 200
    
    except Exception as e:
        print(f"❌ Error obtenint reserva: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/appointments', methods=['POST'])
def create_appointment_api():
    """Crear nova reserva des del frontend"""
    try:
        data = request.json
        
        # Validació
        required = ['phone', 'client_name', 'date', 'time', 'num_people']
        for field in required:
            if field not in data:
                return jsonify({'error': f'Camp obligatori: {field}'}), 400
        
        # Crear reserva
        result = appointment_manager.create_appointment(
            phone=data['phone'],
            client_name=data['client_name'],
            date=data['date'],
            time=data['time'],
            num_people=data['num_people'],
            duration_hours=data.get('duration_hours', 1)
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
def update_appointment_api(appointment_id):
    """Actualitzar una reserva"""
    try:
        data = request.json
        
        # Obtenir phone de la reserva existent
        conn = appointment_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT phone FROM appointments WHERE id = %s", (appointment_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not row:
            return jsonify({'error': 'Reserva no trobada'}), 404
        
        phone = row[0]
        
        # Actualitzar (ara incloent table_id)
        result = appointment_manager.update_appointment(
            phone=phone,
            appointment_id=appointment_id,
            new_date=data.get('date'),
            new_time=data.get('time'),
            new_num_people=data.get('num_people'),
            new_table_id=data.get('table_id')
        )
        
        if not result:
            return jsonify({'error': 'No s\'ha pogut actualitzar la reserva'}), 409
        
        return jsonify({
            'message': 'Reserva actualitzada correctament',
            'appointment_id': result['id'],
            'table': result['table']
        }), 200
    
    except Exception as e:
        print(f"❌ Error actualitzant reserva: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/appointments/<int:appointment_id>', methods=['DELETE'])
def delete_appointment_api(appointment_id):
    """Cancel·lar una reserva"""
    try:
        # Obtenir phone de la reserva
        conn = appointment_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT phone FROM appointments WHERE id = %s", (appointment_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
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
        conn = appointment_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT phone FROM appointments WHERE id = %s", (appointment_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
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
        conn = appointment_manager.get_connection()
        cursor = conn.cursor()
        
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
        
        cursor.close()
        conn.close()
        
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
        
        conn = appointment_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM tables WHERE table_number = %s", (data['table_number'],))
        if cursor.fetchone():
            cursor.close()
            conn.close()
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
        cursor.close()
        conn.close()
        
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
        
        conn = appointment_manager.get_connection()
        cursor = conn.cursor()
        
        # Obtenir pairing actual abans de l'actualització
        cursor.execute("SELECT pairing, table_number FROM tables WHERE id = %s", (table_id,))
        result = cursor.fetchone()
        if not result:
            cursor.close()
            conn.close()
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
                cursor.close()
                conn.close()
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
                cursor.close()
                conn.close()
                return jsonify({'error': 'Status invàlid'}), 400
            updates.append("status = %s")
            values.append(data['status'])
        
        new_pairing = None
        if 'pairing' in data:
            new_pairing = data['pairing']
            updates.append("pairing = %s")
            values.append(new_pairing)
        
        if not updates:
            cursor.close()
            conn.close()
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
        cursor.close()
        conn.close()
        
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
        conn = appointment_manager.get_connection()
        cursor = conn.cursor()
        
        # Obtenir info de la taula
        cursor.execute("SELECT table_number, pairing FROM tables WHERE id = %s", (table_id,))
        result = cursor.fetchone()
        if not result:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Taula no trobada'}), 404
        
        table_number = result[0]
        pairing = result[1] if result[1] else []
        
        # Verificar reserves futures
        cursor.execute("""
            SELECT COUNT(*) FROM appointments
            WHERE table_id = %s AND status = 'confirmed' AND date >= CURRENT_DATE
        """, (table_id,))
        
        count = cursor.fetchone()[0]
        
        if count > 0:
            cursor.close()
            conn.close()
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
        cursor.close()
        conn.close()
        
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
        conn = appointment_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT phone, name, language, visit_count, last_visit
            FROM customers
            WHERE name != 'TEMP'
            ORDER BY visit_count DESC, last_visit DESC
        """)
        
        customers = []
        for row in cursor.fetchall():
            customers.append({
                'phone': row[0],
                'name': row[1],
                'language': row[2],
                'visit_count': row[3],
                'last_visit': row[4].isoformat() if row[4] else None
            })
        
        cursor.close()
        conn.close()
        
        return jsonify(customers), 200
    
    except Exception as e:
        print(f"❌ Error obtenint clients: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/conversations/<phone>', methods=['GET'])
def get_conversations(phone):
    """Obtenir historial de conversa d'un client (sense missatges system)"""
    try:
        conn = conversation_manager.get_connection()
        cursor = conn.cursor()
        
        # Netejar prefix whatsapp: o telegram: si existeix
        clean_phone = phone.replace('whatsapp:', '').replace('telegram:', '')
        
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
        
        cursor.close()
        conn.close()
        
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


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
