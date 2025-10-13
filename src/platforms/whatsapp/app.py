from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
import sys
from dotenv import load_dotenv
from src.core.appointments import AppointmentManager, ConversationManager
from src.core.ai_processor import process_message_with_ai
from src.config.settings import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, DEBUG_MODE
from datetime import datetime

load_dotenv()

app = Flask(__name__)
CORS(app)  # Habilitar CORS per al frontend

# Twilio configuration imported from settings

if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
    print("❌ ERROR: Variables de Twilio no configuradas")
else:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    print("✅ Cliente Twilio inicializado correctamente")

# Initialize managers
appointment_manager = AppointmentManager()
conversation_manager = ConversationManager()

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
    
    if DEBUG_MODE:
        print(f"📱 WhatsApp Message from {from_number}: {incoming_msg}", flush=True)
        sys.stdout.flush()
    
    if DEBUG_MODE:
        print("=" * 50, flush=True)
        print("🔍 DEBUG: WhatsApp Webhook Data", flush=True)
        print(f"From: {from_number}", flush=True)
        print(f"Body: {incoming_msg}", flush=True)
        print(f"Media URL: {media_url}", flush=True)
        print(f"All request data: {dict(request.values)}", flush=True)
        print("=" * 50, flush=True)
        sys.stdout.flush()
    
    resp = MessagingResponse()
    
    try:
        # Audio transcription not implemented in this version
        if media_url:
            resp.message("Audio messages not supported yet. Please send a text message.")
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
        
        if DEBUG_MODE:
            print(f"🤖 Bot Response: {ai_response}", flush=True)
            print(f"📱 Twilio Response: {str(resp)}", flush=True)
            print("-" * 50, flush=True)
            sys.stdout.flush()
    
    except Exception as e:
        print(f"❌ Error en webhook: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
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
                   a.num_people, a.status, t.table_number, t.capacity, a.created_at, a.notes, a.table_id
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
                'table_id': row[12]
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
            SELECT id, table_number, capacity, status
            FROM tables
            ORDER BY table_number
        """)
        
        tables = []
        for row in cursor.fetchall():
            tables.append({
                'id': row[0],
                'table_number': row[1],
                'capacity': row[2],
                'status': row[3]
            })
        
        cursor.close()
        conn.close()
        
        return jsonify(tables), 200
    
    except Exception as e:
        print(f"❌ Error obtenint taules: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tables/<int:table_id>', methods=['PUT'])
def update_table_status(table_id):
    """Actualitzar status d'una taula"""
    try:
        data = request.json
        status = data.get('status')
        
        if status not in ['available', 'unavailable']:
            return jsonify({'error': 'Status invàlid. Usa: available, unavailable'}), 400
        
        conn = appointment_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE tables
            SET status = %s
            WHERE id = %s
        """, (status, table_id))
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Taula no trobada'}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'Status actualitzat correctament'}), 200
    
    except Exception as e:
        print(f"❌ Error actualitzant status: {e}")
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
        return jsonify({'error': 'Weekly defaults not implemented'}), 501
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
