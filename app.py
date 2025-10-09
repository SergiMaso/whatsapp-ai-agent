from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
from dotenv import load_dotenv
from utils.transcription import transcribe_audio
from utils.appointments import AppointmentManager, ConversationManager
from utils.ai_processor import process_message_with_ai
import base64
from datetime import datetime

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
                   a.num_people, a.status, t.table_number, t.capacity, a.created_at, a.notes
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
                'notes': row[11]
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
        
        # Actualitzar
        result = appointment_manager.update_appointment(
            phone=phone,
            appointment_id=appointment_id,
            new_date=data.get('date'),
            new_time=data.get('time'),
            new_num_people=data.get('num_people')
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

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
