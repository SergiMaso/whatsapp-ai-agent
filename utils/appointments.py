import psycopg2
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

class AppointmentManager:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.ensure_table_exists()
    
    def get_connection(self):
        """Crear conexión a la base de datos"""
        return psycopg2.connect(self.database_url)
    
    def ensure_table_exists(self):
        """Crear la tabla de citas si no existe"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS appointments (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) NOT NULL,
                    client_name VARCHAR(100),
                    date DATE NOT NULL,
                    time TIME NOT NULL,
                    service VARCHAR(200),
                    language VARCHAR(10) DEFAULT 'es',
                    status VARCHAR(20) DEFAULT 'confirmed',
                    reminder_sent BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            cursor.close()
            conn.close()
            print("✅ Tabla de citas creada/verificada")
        
        except Exception as e:
            print(f"Error creando tabla: {e}")
    
    def create_appointment(self, phone, client_name, date, time, service, language='es'):
        """Crear una nueva cita"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO appointments 
                (phone, client_name, date, time, service, language, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'confirmed')
                RETURNING id
            """, (phone, client_name, date, time, service, language))
            
            appointment_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()
            
            return appointment_id
        
        except Exception as e:
            print(f"Error creando cita: {e}")
            return None
    
    def get_appointments(self, phone, from_date=None):
        """Obtener citas de un usuario"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if from_date is None:
                from_date = datetime.now().date()
            
            cursor.execute("""
                SELECT id, client_name, date, time, service, status
                FROM appointments
                WHERE phone = %s AND date >= %s
                ORDER BY date, time
            """, (phone, from_date))
            
            appointments = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return appointments
        
        except Exception as e:
            print(f"Error obteniendo citas: {e}")
            return []
    
    def cancel_appointment(self, phone, appointment_id):
        """Cancelar una cita"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE appointments
                SET status = 'cancelled'
                WHERE id = %s AND phone = %s
            """, (appointment_id, phone))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
        
        except Exception as e:
            print(f"Error cancelando cita: {e}")
            return False