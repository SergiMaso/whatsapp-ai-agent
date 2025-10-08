import psycopg2
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

class AppointmentManager:
    """
    Gestor de reserves del restaurant
    
    Responsabilitats:
    - Crear/actualitzar/cancel·lar reserves
    - Trobar taules disponibles
    - Gestionar informació de clients
    """
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.ensure_tables_exist()
    
    def get_connection(self):
        """Crear connexió a PostgreSQL"""
        return psycopg2.connect(self.database_url)
    
    def ensure_tables_exist(self):
        """
        Crear totes les taules necessàries si no existeixen
        
        Taules:
        - tables: informació de les taules del restaurant
        - appointments: reserves dels clients
        - customers: informació dels clients (nom, idioma)
        - conversations: historial de converses
        """
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
                    date DATE NOT NULL,
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
    
    def find_available_table(self, start_time, end_time, num_people, exclude_appointment_id=None):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if exclude_appointment_id:
                cursor.execute("""
                    SELECT table_id FROM appointments 
                    WHERE status = 'confirmed' AND id != %s
                      AND ((start_time < %s AND end_time > %s) OR (start_time >= %s AND start_time < %s))
                """, (exclude_appointment_id, end_time, start_time, start_time, end_time))
            else:
                cursor.execute("""
                    SELECT table_id FROM appointments 
                    WHERE status = 'confirmed'
                      AND ((start_time < %s AND end_time > %s) OR (start_time >= %s AND start_time < %s))
                """, (end_time, start_time, start_time, end_time))
            
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
    
    def create_appointment(self, phone, client_name, date, time, num_people, duration_hours=1):
        try:
            # Convertir date i time a TIMESTAMP
            start_time = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            end_time = start_time + timedelta(hours=duration_hours)
            date_only = start_time.date()
            
            # Convertir a string per enviar a PostgreSQL
            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
            
            customer_language = self.get_customer_language(phone) or 'es'
            table = self.find_available_table(start_time, end_time, num_people)
            if not table:
                return None
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # IMPORTANT: Enviar com a string perquè PostgreSQL ho interpreti correctament
            cursor.execute("""
                INSERT INTO appointments 
                (phone, client_name, date, start_time, end_time, num_people, table_id, language, status)
                VALUES (%s, %s, %s, %s::timestamp, %s::timestamp, %s, %s, %s, %s)
                RETURNING id, start_time, end_time
            """, (phone, client_name, date_only, start_time_str, end_time_str, num_people, table['id'], customer_language, 'confirmed'))
            
            result = cursor.fetchone()
            appointment_id = result[0]
            saved_start = result[1]
            saved_end = result[2]
            
            # Debug: Verificar què s'ha guardat
            print(f"✅ Reserva creada: ID={appointment_id}")
            print(f"   Input: {start_time_str} -> Guardat: {saved_start}")
            print(f"   Tipus guardat: {type(saved_start)}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {'id': appointment_id, 'table': table, 'start': start_time, 'end': end_time}
        
        except Exception as e:
            print(f"❌ Error creando reserva: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def update_appointment(self, phone, appointment_id, new_date=None, new_time=None, new_num_people=None):
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
            
            duration = (current_end - current_start).total_seconds() / 3600
            new_end = new_start + timedelta(hours=duration)
            new_date_only = new_start.date()
            
            final_num_people = new_num_people if new_num_people else current_num_people
            
            table = self.find_available_table(new_start, new_end, final_num_people, exclude_appointment_id=appointment_id)
            if not table:
                cursor.close()
                conn.close()
                return None
            
            cursor.execute("""
                UPDATE appointments
                SET date = %s, start_time = %s, end_time = %s, num_people = %s, table_id = %s
                WHERE id = %s AND phone = %s
            """, (new_date_only, new_start, new_end, final_num_people, table['id'], appointment_id, phone))
            
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
                from_date = datetime.now().date()
            
            cursor.execute("""
                SELECT a.id, a.client_name, a.date, a.start_time, a.end_time, a.num_people, 
                       t.table_number, t.capacity, a.status
                FROM appointments a
                JOIN tables t ON a.table_id = t.id
                WHERE a.phone = %s AND a.date >= %s
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
                SELECT id, date, start_time, num_people
                FROM appointments
                WHERE phone = %s AND status = 'confirmed'
                ORDER BY created_at DESC LIMIT 1
            """, (phone,))
            
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if result:
                return {
                    'id': result[0], 
                    'date': result[1], 
                    'time': result[2].strftime("%H:%M"),
                    'num_people': result[3]
                }
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
        """
        Obtenir el nom d'un client si existeix
        
        Retorna None si el nom és TEMP (client temporal sense nom real)
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM customers WHERE phone = %s", (phone,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            # Retornar None si és TEMP (nom temporal)
            if result and result[0] != 'TEMP':
                return result[0]
            return None
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
        """
        Guardar l'idioma preferit d'un client
        
        Si el client no existeix, crea registre temporal amb nom 'TEMP'
        Quan faci la reserva, s'actualitzarà amb el nom real
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO customers (phone, name, language, last_visit)
                VALUES (%s, 'TEMP', %s, CURRENT_TIMESTAMP)
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
    
    def clean_old_messages(self):
        """
        Eliminar missatges de més de 10 minuts de TOTS els usuaris
        S'executa automàticament abans de guardar nous missatges
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Eliminar missatges creats fa més de 10 minuts
            cursor.execute("""
                DELETE FROM conversations 
                WHERE created_at < NOW() - INTERVAL '10 minutes'
            """)
            
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                print(f"🧹 Netejats {deleted_count} missatges antics (>10 min)")
            
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"❌ Error limpiando mensajes antiguos: {e}")
    
    def save_message(self, phone, role, content):
        """
        Guardar un missatge a l'historial
        
        Abans de guardar, neteja missatges antics automàticament
        """
        try:
            # IMPORTANT: Netejar missatges antics abans de guardar
            self.clean_old_messages()
            
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO conversations (phone, role, content) VALUES (%s, %s, %s)", (phone, role, content))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"❌ Error guardando mensaje: {e}")
    
    def get_history(self, phone, limit=10):
        """
        Obtenir historial de conversa NOMÉS dels últims 10 minuts
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Només obtenir missatges dels últims 10 minuts
            cursor.execute("""
                SELECT role, content 
                FROM conversations 
                WHERE phone = %s 
                  AND created_at > NOW() - INTERVAL '10 minutes'
                ORDER BY created_at DESC 
                LIMIT %s
            """, (phone, limit))
            
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
        """
        Comptar missatges dels últims 10 minuts
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Comptar només missatges dels últims 10 minuts
            cursor.execute("""
                SELECT COUNT(*) 
                FROM conversations 
                WHERE phone = %s 
                  AND role = 'user'
                  AND created_at > NOW() - INTERVAL '10 minutes'
            """, (phone,))
            
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return count
        except Exception as e:
            print(f"❌ Error contando mensajes: {e}")
            return 0
