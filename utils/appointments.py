import psycopg2
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

class AppointmentManager:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.ensure_tables_exist()
    
    def get_connection(self):
        return psycopg2.connect(self.database_url)
    
    def ensure_tables_exist(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tables (
                    id SERIAL PRIMARY KEY,
                    table_number INTEGER UNIQUE NOT NULL,
                    capacity INTEGER NOT NULL,
                    status VARCHAR(20) DEFAULT 'available'
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS appointments (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) NOT NULL,
                    client_name VARCHAR(100),
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP NOT NULL,
                    num_people INTEGER NOT NULL,
                    table_id INTEGER REFERENCES tables(id),
                    language VARCHAR(10),
                    status VARCHAR(20) DEFAULT 'confirmed',
                    reminder_sent BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) UNIQUE NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    language VARCHAR(10) DEFAULT 'es',
                    last_visit TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='customers' AND column_name='language'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE customers ADD COLUMN language VARCHAR(10) DEFAULT 'es'")
                conn.commit()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("SELECT COUNT(*) FROM tables")
            if cursor.fetchone()[0] == 0:
                for i in range(1, 21):
                    cursor.execute("INSERT INTO tables (table_number, capacity) VALUES (%s, 4)", (i,))
                for i in range(21, 29):
                    cursor.execute("INSERT INTO tables (table_number, capacity) VALUES (%s, 2)", (i,))
            
            conn.commit()
            cursor.close()
            conn.close()
            print("✅ Base de datos lista")
        
        except Exception as e:
            print(f"❌ Error creando tablas: {e}")
    
    def find_available_table(self, start, end, num_people, exclude_appointment_id=None):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if exclude_appointment_id:
                cursor.execute("""
                    SELECT table_id FROM appointments 
                    WHERE status = 'confirmed' AND id != %s
                      AND ((start_time < %s AND end_time > %s) OR (start_time >= %s AND start_time < %s))
                """, (exclude_appointment_id, end, start, start, end))
            else:
                cursor.execute("""
                    SELECT table_id FROM appointments 
                    WHERE status = 'confirmed'
                      AND ((start_time < %s AND end_time > %s) OR (start_time >= %s AND start_time < %s))
                """, (end, start, start, end))
            
            reserved_ids = [row[0] for row in cursor.fetchall()]
            
            if num_people <= 2:
                cursor.execute("""
                    SELECT id, table_number, capacity FROM tables 
                    WHERE capacity = 2 AND id NOT IN %s ORDER BY table_number LIMIT 1
                """, (tuple(reserved_ids) if reserved_ids else (0,),))
                result = cursor.fetchone()
                
                if not result:
                    cursor.execute("""
                        SELECT id, table_number, capacity FROM tables 
                        WHERE capacity = 4 AND id NOT IN %s ORDER BY table_number LIMIT 1
                    """, (tuple(reserved_ids) if reserved_ids else (0,),))
                    result = cursor.fetchone()
            else:
                cursor.execute("""
                    SELECT id, table_number, capacity FROM tables 
                    WHERE capacity >= %s AND id NOT IN %s ORDER BY capacity, table_number LIMIT 1
                """, (num_people, tuple(reserved_ids) if reserved_ids else (0,)))
                result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                return {'id': result[0], 'number': result[1], 'capacity': result[2]}
            return None
        
        except Exception as e:
            print(f"❌ Error buscando mesa: {e}")
            return None
    
    def create_appointment(self, phone, client_name, date_str, time_str, num_people, duration_hours=2):
        try:
            start = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            end = start + timedelta(hours=duration_hours)
            
            customer_language = self.get_customer_language(phone) or 'es'
            table = self.find_available_table(start, end, num_people)
            if not table:
                return None
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO appointments 
                (phone, client_name, start_time, end_time, num_people, table_id, language, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmed')
                RETURNING id
            """, (phone, client_name, start, end, num_people, table['id'], customer_language))
            
            appointment_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()
            
            return {'id': appointment_id, 'table': table, 'start': start, 'end': end}
        
        except Exception as e:
            print(f"❌ Error creando reserva: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def update_appointment(self, phone, appointment_id, new_date=None, new_time=None, new_num_people=None, new_duration=None):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT start_time, end_time, num_people FROM appointments
                WHERE id = %s AND phone = %s AND status = 'confirmed'
            """, (appointment_id, phone))
            
            result = cursor.fetchone()
            if not result:
                cursor.close()
                conn.close()
                return None
            
            current_start, current_end, current_num_people = result
            
            if new_date or new_time:
                date_part = new_date if new_date else current_start.strftime("%Y-%m-%d")
                time_part = new_time if new_time else current_start.strftime("%H:%M")
                new_start = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M")
            else:
                new_start = current_start
            
            if new_duration:
                new_end = new_start + timedelta(hours=new_duration)
            else:
                current_duration = (current_end - current_start).total_seconds() / 3600
                new_end = new_start + timedelta(hours=current_duration)
            
            final_num_people = new_num_people if new_num_people else current_num_people
            
            table = self.find_available_table(new_start, new_end, final_num_people, exclude_appointment_id=appointment_id)
            if not table:
                cursor.close()
                conn.close()
                return None
            
            cursor.execute("""
                UPDATE appointments
                SET start_time = %s, end_time = %s, num_people = %s, table_id = %s
                WHERE id = %s AND phone = %s
            """, (new_start, new_end, final_num_people, table['id'], appointment_id, phone))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {'id': appointment_id, 'table': table, 'start': new_start, 'end': new_end}
        
        except Exception as e:
            print(f"❌ Error actualizando reserva: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_appointments(self, phone, from_date=None):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if from_date is None:
                from_date = datetime.now()
            
            cursor.execute("""
                SELECT a.id, a.client_name, a.start_time, a.end_time, a.num_people, 
                       t.table_number, t.capacity, a.status
                FROM appointments a
                JOIN tables t ON a.table_id = t.id
                WHERE a.phone = %s AND a.start_time >= %s
                ORDER BY a.start_time
            """, (phone, from_date))
            
            appointments = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return appointments
        
        except Exception as e:
            print(f"❌ Error obteniendo reservas: {e}")
            return []
    
    def get_latest_appointment(self, phone):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, start_time, end_time, num_people
                FROM appointments
                WHERE phone = %s AND status = 'confirmed'
                ORDER BY created_at DESC LIMIT 1
            """, (phone,))
            
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if result:
                return {'id': result[0], 'start': result[1], 'end': result[2], 'num_people': result[3]}
            return None
        
        except Exception as e:
            print(f"❌ Error obteniendo última reserva: {e}")
            return None
    
    def cancel_appointment(self, phone, appointment_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE appointments SET status = 'cancelled' WHERE id = %s AND phone = %s", (appointment_id, phone))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Error cancelando reserva: {e}")
            return False
    
    def save_customer_info(self, phone, name, language=None):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if language:
                cursor.execute("""
                    INSERT INTO customers (phone, name, language, last_visit)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (phone) 
                    DO UPDATE SET name = EXCLUDED.name, language = EXCLUDED.language, last_visit = CURRENT_TIMESTAMP
                """, (phone, name, language))
            else:
                cursor.execute("""
                    INSERT INTO customers (phone, name, last_visit)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (phone) 
                    DO UPDATE SET name = EXCLUDED.name, last_visit = CURRENT_TIMESTAMP
                """, (phone, name))
            
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"❌ Error guardando cliente: {e}")
    
    def get_customer_name(self, phone):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM customers WHERE phone = %s", (phone,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            print(f"❌ Error obteniendo nombre: {e}")
            return None
    
    def get_customer_language(self, phone):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT language FROM customers WHERE phone = %s", (phone,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            print(f"❌ Error obteniendo idioma: {e}")
            return None
    
    def save_customer_language(self, phone, language):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO customers (phone, name, language, last_visit)
                VALUES (%s, 'Usuario', %s, CURRENT_TIMESTAMP)
                ON CONFLICT (phone) 
                DO UPDATE SET language = EXCLUDED.language, last_visit = CURRENT_TIMESTAMP
            """, (phone, language))
            
            conn.commit()
            cursor.close()
            conn.close()
            print(f"🌍 Idioma guardado: {phone} → {language}")
        except Exception as e:
            print(f"❌ Error guardando idioma: {e}")


class ConversationManager:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
    
    def get_connection(self):
        return psycopg2.connect(self.database_url)
    
    def save_message(self, phone, role, content):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO conversations (phone, role, content) VALUES (%s, %s, %s)", (phone, role, content))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"❌ Error guardando mensaje: {e}")
    
    def get_history(self, phone, limit=10):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT role, content FROM conversations WHERE phone = %s ORDER BY created_at DESC LIMIT %s", (phone, limit))
            messages = cursor.fetchall()
            cursor.close()
            conn.close()
            return [{"role": role, "content": content} for role, content in reversed(messages)]
        except Exception as e:
            print(f"❌ Error obteniendo historial: {e}")
            return []
    
    def clear_history(self, phone):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversations WHERE phone = %s", (phone,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"❌ Error limpiando historial: {e}")
    
    def get_message_count(self, phone):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM conversations WHERE phone = %s AND role = 'user'", (phone,))
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return count
        except Exception as e:
            print(f"❌ Error contando mensajes: {e}")
            return 0
