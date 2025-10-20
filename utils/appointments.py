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
        - opening_hours: horaris d'obertura (ACTUALITZAT amb is_custom)
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tables (
                    id SERIAL PRIMARY KEY,
                    table_number INTEGER UNIQUE NOT NULL,
                    capacity INTEGER NOT NULL,
                    status VARCHAR(20) DEFAULT 'available',
                    pairing INTEGER[]
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS appointments (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) NOT NULL,
                    client_name VARCHAR(100),
                    date DATE NOT NULL,
                    start_time TIMESTAMPTZ NOT NULL,
                    end_time TIMESTAMPTZ NOT NULL,
                    num_people INTEGER NOT NULL,
                    table_id INTEGER REFERENCES tables(id),
                    language VARCHAR(10),
                    notes TEXT,
                    status VARCHAR(20) DEFAULT 'confirmed',
                    reminder_sent BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Afegir columna notes si no existeix
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='appointments' AND column_name='notes'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE appointments ADD COLUMN notes TEXT")
                print("✅ Columna notes afegida a appointments")
                conn.commit()
            
            # Afegir columnes per tracking de temps i no-shows
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='appointments' AND column_name='seated_at'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE appointments ADD COLUMN seated_at TIMESTAMPTZ")
                print("✅ Columna seated_at afegida a appointments")
                conn.commit()
            
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='appointments' AND column_name='left_at'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE appointments ADD COLUMN left_at TIMESTAMPTZ")
                print("✅ Columna left_at afegida a appointments")
                conn.commit()
            
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='appointments' AND column_name='duration_minutes'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE appointments ADD COLUMN duration_minutes INTEGER")
                print("✅ Columna duration_minutes afegida a appointments")
                conn.commit()
            
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='appointments' AND column_name='no_show'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE appointments ADD COLUMN no_show BOOLEAN DEFAULT FALSE")
                print("✅ Columna no_show afegida a appointments")
                conn.commit()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) UNIQUE NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    language VARCHAR(10) DEFAULT 'es',
                    visit_count INTEGER DEFAULT 0,
                    last_visit TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Afegir columna visit_count si no existeix
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='customers' AND column_name='visit_count'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE customers ADD COLUMN visit_count INTEGER DEFAULT 0")
                print("✅ Columna visit_count afegida a customers")
                conn.commit()
            
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='customers' AND column_name='language'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE customers ADD COLUMN language VARCHAR(10) DEFAULT 'es'")
                conn.commit()
            
            # Afegir columna no_show_count
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='customers' AND column_name='no_show_count'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE customers ADD COLUMN no_show_count INTEGER DEFAULT 0")
                print("✅ Columna no_show_count afegida a customers")
                conn.commit()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Crear taula opening_hours amb is_custom
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS opening_hours (
                    id SERIAL PRIMARY KEY,
                    date DATE UNIQUE NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    lunch_start TIME,
                    lunch_end TIME,
                    dinner_start TIME,
                    dinner_end TIME,
                    is_custom BOOLEAN DEFAULT FALSE,
                    notes TEXT,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("✅ Taula opening_hours creada/verificada")
            
            # Afegir columna is_custom si no existeix
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='opening_hours' AND column_name='is_custom'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE opening_hours ADD COLUMN is_custom BOOLEAN DEFAULT FALSE")
                print("✅ Columna is_custom afegida a opening_hours")
                conn.commit()
            
            cursor.execute("SELECT COUNT(*) FROM tables")
            if cursor.fetchone()[0] == 0:
                # 12 taules de 4 persones
                for i in range(1, 13):
                    cursor.execute("INSERT INTO tables (table_number, capacity, pairing) VALUES (%s, 4, NULL)", (i,))
                # 5 taules de 2 persones
                for i in range(13, 18):
                    cursor.execute("INSERT INTO tables (table_number, capacity, pairing) VALUES (%s, 2, NULL)", (i,))
                print("✅ Taules per defecte creades: 12 de 4 + 5 de 2")
            
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
                    WHERE capacity = 2 AND status = 'available' AND id NOT IN %s ORDER BY table_number LIMIT 1
                """, (tuple(reserved_ids) if reserved_ids else (0,),))
                result = cursor.fetchone()
                
                if not result:
                    cursor.execute("""
                        SELECT id, table_number, capacity FROM tables 
                        WHERE capacity = 4 AND status = 'available' AND id NOT IN %s ORDER BY table_number LIMIT 1
                    """, (tuple(reserved_ids) if reserved_ids else (0,),))
                    result = cursor.fetchone()
            else:
                cursor.execute("""
                    SELECT id, table_number, capacity FROM tables 
                    WHERE capacity >= %s AND status = 'available' AND id NOT IN %s ORDER BY capacity, table_number LIMIT 1
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
    
    def find_combined_tables(self, start_time, end_time, num_people, exclude_appointment_id=None):
        """
        Buscar taules individuals o combinades per una reserva
        Retorna: {'tables': [taula1, taula2, ...], 'total_capacity': X}
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Obtenir taules ocupades en aquest horari
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
            
            occupied_ids = [row[0] for row in cursor.fetchall()]
            
            # Obtenir taules SENSE PAIRING
            cursor.execute("""
                SELECT id, table_number, capacity, pairing FROM tables 
                WHERE status = 'available' AND id NOT IN %s AND pairing IS NULL
                ORDER BY capacity ASC, table_number
            """, (tuple(occupied_ids) if occupied_ids else (0,),))
            
            tables_no_pairing = cursor.fetchall()
            
            # Obtenir taules AMB PAIRING
            cursor.execute("""
                SELECT id, table_number, capacity, pairing FROM tables 
                WHERE status = 'available' AND id NOT IN %s AND pairing IS NOT NULL
                ORDER BY capacity ASC, table_number
            """, (tuple(occupied_ids) if occupied_ids else (0,),))
            
            tables_with_pairing = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            # 1. PRIORITAT MÀXIMA: Taula SENSE PAIRING amb capacitat EXACTA
            for table in tables_no_pairing:
                if table[2] == num_people:
                    return {
                        'tables': [{
                            'id': table[0],
                            'number': table[1],
                            'capacity': table[2]
                        }],
                        'total_capacity': table[2]
                    }
            
            # 2. Taula SENSE PAIRING amb capacitat mínima suficient (la més petita possible)
            for table in tables_no_pairing:
                if table[2] >= num_people:
                    return {
                        'tables': [{
                            'id': table[0],
                            'number': table[1],
                            'capacity': table[2]
                        }],
                        'total_capacity': table[2]
                    }
            
            # 3. Taula AMB PAIRING amb capacitat EXACTA
            for table in tables_with_pairing:
                if table[2] == num_people:
                    return {
                        'tables': [{
                            'id': table[0],
                            'number': table[1],
                            'capacity': table[2]
                        }],
                        'total_capacity': table[2]
                    }
            
            # 4. Taula AMB PAIRING amb capacitat mínima suficient
            for table in tables_with_pairing:
                if table[2] >= num_people:
                    return {
                        'tables': [{
                            'id': table[0],
                            'number': table[1],
                            'capacity': table[2]
                        }],
                        'total_capacity': table[2]
                    }
            
            # 5. ÚLTIM RECURS: Intentar combinar taules amb pairing
            all_tables = tables_no_pairing + tables_with_pairing
            for table in all_tables:
                table_id, table_num, capacity, pairing = table
                
                if not pairing:
                    continue
                
                # Buscar taules del pairing que estiguin disponibles
                paired_tables = []
                total_cap = capacity
                
                for paired_num in pairing:
                    # Buscar si la taula paired està disponible
                    paired_table = next(
                        (t for t in all_tables if t[1] == paired_num),
                        None
                    )
                    
                    if paired_table:
                        paired_tables.append({
                            'id': paired_table[0],
                            'number': paired_table[1],
                            'capacity': paired_table[2]
                        })
                        total_cap += paired_table[2]
                        
                        # Si ja tenim prou capacitat, retornar
                        if total_cap >= num_people:
                            return {
                                'tables': [{
                                    'id': table_id,
                                    'number': table_num,
                                    'capacity': capacity
                                }] + paired_tables,
                                'total_capacity': total_cap
                            }
            
            # No s'ha trobat cap taula disponible
            return None
            
        except Exception as e:
            print(f"❌ Error buscant taules combinades: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def create_appointment(self, phone, client_name, date, time, num_people, duration_hours=1, notes=None):
        try:
            start_time = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            end_time = start_time + timedelta(hours=duration_hours)
            date_only = start_time.date()
            
            customer_language = self.get_customer_language(phone) or 'es'
            
            # Buscar taules (individuals o combinades)
            tables_result = self.find_combined_tables(start_time, end_time, num_people)
            
            if not tables_result:
                return None
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Crear una reserva per cada taula
            appointment_ids = []
            for table in tables_result['tables']:
                cursor.execute("""
                    INSERT INTO appointments 
                    (phone, client_name, date, start_time, end_time, num_people, table_id, language, notes, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, start_time, end_time
                """, (phone, client_name, date_only, start_time, end_time, num_people, table['id'], customer_language, notes, 'confirmed'))
                
                result = cursor.fetchone()
                appointment_ids.append(result[0])
            
            # Incrementar visit_count del client
            cursor.execute("""
                UPDATE customers 
                SET visit_count = visit_count + 1, last_visit = CURRENT_TIMESTAMP
                WHERE phone = %s
            """, (phone,))
            
            print(f"✅ Reserva creada: IDs={appointment_ids} - {len(tables_result['tables'])} taules")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                'id': appointment_ids[0],  # ID principal
                'ids': appointment_ids,
                'table': tables_result['tables'][0] if len(tables_result['tables']) == 1 else {
                    'number': f"{tables_result['tables'][0]['number']}+{tables_result['tables'][1]['number']}",
                    'capacity': tables_result['total_capacity'],
                    'combined': True
                },
                'tables': tables_result['tables'],
                'start': start_time,
                'end': end_time
            }
        
        except Exception as e:
            print(f"❌ Error creando reserva: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def update_appointment(self, phone, appointment_id, new_date=None, new_time=None, new_num_people=None, new_table_id=None):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT start_time, end_time, num_people, table_id FROM appointments
                WHERE id = %s AND phone = %s AND status = 'confirmed'
            """, (appointment_id, phone))
            
            result = cursor.fetchone()
            if not result:
                cursor.close()
                conn.close()
                return None
            
            current_start, current_end, current_num_people, current_table_id = result
            
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
            
            if new_table_id is not None:
                cursor.execute("""
                    SELECT id, table_number, capacity, status FROM tables
                    WHERE id = %s
                """, (new_table_id,))
                table_row = cursor.fetchone()
                
                if not table_row:
                    cursor.close()
                    conn.close()
                    return None
                
                if table_row[3] != 'available':
                    cursor.close()
                    conn.close()
                    return None
                
                cursor.execute("""
                    SELECT id FROM appointments
                    WHERE table_id = %s
                      AND status = 'confirmed'
                      AND id != %s
                      AND ((start_time < %s AND end_time > %s) OR (start_time >= %s AND start_time < %s))
                """, (new_table_id, appointment_id, new_end, new_start, new_start, new_end))
                
                if cursor.fetchone():
                    cursor.close()
                    conn.close()
                    return None
                
                table = {'id': table_row[0], 'number': table_row[1], 'capacity': table_row[2]}
            else:
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
                WHERE a.phone = %s AND a.date >= %s AND a.status = 'confirmed'
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
            
            cursor.execute("""
                UPDATE customers 
                SET visit_count = GREATEST(visit_count - 1, 0)
                WHERE phone = %s
            """, (phone,))
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Error cancelando reserva: {e}")
            return False
    
    def add_notes_to_appointment(self, phone, appointment_id, notes):
        """Afegir notes a una reserva existent"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE appointments 
                SET notes = %s 
                WHERE id = %s AND phone = %s AND status = 'confirmed'
            """, (notes, appointment_id, phone))
            
            affected = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()
            return affected > 0
        except Exception as e:
            print(f"❌ Error afegint notes: {e}")
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
    
    # ========================================
    # MÈTODES PER OPENING_HOURS
    # ========================================
    
    def get_opening_hours(self, date):
        """
        Obtenir els horaris d'obertura per una data específica
        Si no existeix a opening_hours, retorna els defaults de weekly_defaults
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT status, lunch_start, lunch_end, dinner_start, dinner_end, notes, is_custom
                FROM opening_hours
                WHERE date = %s
            """, (date,))
            
            result = cursor.fetchone()
            
            if result:
                cursor.close()
                conn.close()
                return {
                    'status': result[0],
                    'lunch_start': str(result[1]) if result[1] else None,
                    'lunch_end': str(result[2]) if result[2] else None,
                    'dinner_start': str(result[3]) if result[3] else None,
                    'dinner_end': str(result[4]) if result[4] else None,
                    'notes': result[5],
                    'is_custom': result[6]
                }
            else:
                # No existeix: buscar a weekly_defaults
                date_obj = datetime.strptime(date, '%Y-%m-%d').date() if isinstance(date, str) else date
                day_of_week = date_obj.weekday()
                
                cursor.execute("""
                    SELECT status, lunch_start, lunch_end, dinner_start, dinner_end
                    FROM weekly_defaults
                    WHERE day_of_week = %s
                """, (day_of_week,))
                
                default = cursor.fetchone()
                cursor.close()
                conn.close()
                
                if default:
                    return {
                        'status': default[0],
                        'lunch_start': str(default[1]) if default[1] else None,
                        'lunch_end': str(default[2]) if default[2] else None,
                        'dinner_start': str(default[3]) if default[3] else None,
                        'dinner_end': str(default[4]) if default[4] else None,
                        'notes': None,
                        'is_custom': False
                    }
                else:
                    return {
                        'status': 'full_day',
                        'lunch_start': '12:00',
                        'lunch_end': '15:00',
                        'dinner_start': '19:00',
                        'dinner_end': '22:30',
                        'notes': None,
                        'is_custom': False
                    }
        except Exception as e:
            print(f"❌ Error obteniendo horarios: {e}")
            return {
                'status': 'full_day',
                'lunch_start': '12:00',
                'lunch_end': '15:00',
                'dinner_start': '19:00',
                'dinner_end': '22:30',
                'notes': None,
                'is_custom': False
            }
    
    def set_opening_hours(self, date, status, lunch_start=None, lunch_end=None, dinner_start=None, dinner_end=None, notes=None, is_custom=True):
        """
        Establir els horaris d'obertura per una data
        Si s'edita manualment, is_custom=True per defecte
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO opening_hours (date, status, lunch_start, lunch_end, dinner_start, dinner_end, notes, is_custom, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (date) 
                DO UPDATE SET 
                    status = EXCLUDED.status,
                    lunch_start = EXCLUDED.lunch_start,
                    lunch_end = EXCLUDED.lunch_end,
                    dinner_start = EXCLUDED.dinner_start,
                    dinner_end = EXCLUDED.dinner_end,
                    notes = EXCLUDED.notes,
                    is_custom = EXCLUDED.is_custom,
                    updated_at = CURRENT_TIMESTAMP
            """, (date, status, lunch_start, lunch_end, dinner_start, dinner_end, notes, is_custom))
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"❌ Error guardando horarios: {e}")
            return False
    
    def get_opening_hours_range(self, start_date, end_date):
        """Obtenir horaris per un rang de dates"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT date, status, lunch_start, lunch_end, dinner_start, dinner_end, notes, is_custom
                FROM opening_hours
                WHERE date >= %s AND date <= %s
                ORDER BY date
            """, (start_date, end_date))
            
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            hours_list = []
            for row in results:
                hours_list.append({
                    'date': row[0].isoformat() if row[0] else None,
                    'status': row[1],
                    'lunch_start': str(row[2]) if row[2] else None,
                    'lunch_end': str(row[3]) if row[3] else None,
                    'dinner_start': str(row[4]) if row[4] else None,
                    'dinner_end': str(row[5]) if row[5] else None,
                    'notes': row[6],
                    'is_custom': row[7]
                })
            
            return hours_list
        except Exception as e:
            print(f"❌ Error obteniendo rango de horarios: {e}")
            return []
    
    def is_restaurant_open(self, date, time):
        """Verificar si el restaurant està obert en una data i hora específiques"""
        try:
            hours = self.get_opening_hours(date)
            
            if hours['status'] == 'closed':
                return False, "Restaurant tancat"
            
            time_parts = time.split(':')
            time_minutes = int(time_parts[0]) * 60 + int(time_parts[1])
            
            if hours['status'] in ['full_day', 'lunch_only'] and hours['lunch_start'] and hours['lunch_end']:
                lunch_start_parts = hours['lunch_start'].split(':')
                lunch_start_minutes = int(lunch_start_parts[0]) * 60 + int(lunch_start_parts[1])
                lunch_end_parts = hours['lunch_end'].split(':')
                lunch_end_minutes = int(lunch_end_parts[0]) * 60 + int(lunch_end_parts[1])
                
                if lunch_start_minutes <= time_minutes < lunch_end_minutes:
                    return True, "Dinar"
            
            if hours['status'] in ['full_day', 'dinner_only'] and hours['dinner_start'] and hours['dinner_end']:
                dinner_start_parts = hours['dinner_start'].split(':')
                dinner_start_minutes = int(dinner_start_parts[0]) * 60 + int(dinner_start_parts[1])
                dinner_end_parts = hours['dinner_end'].split(':')
                dinner_end_minutes = int(dinner_end_parts[0]) * 60 + int(dinner_end_parts[1])
                
                if dinner_start_minutes <= time_minutes < dinner_end_minutes:
                    return True, "Sopar"
            
            return False, "Fora d'horari"
        except Exception as e:
            print(f"❌ Error verificando si está abierto: {e}")
            return True, "Error - assumint obert"
    
    # ========================================
    # MÈTODES PER TRACKING DE CLIENTS (SEATED, LEFT, NO-SHOW)
    # ========================================
    
    def mark_seated(self, appointment_id):
        """Marcar que el client s'ha assentat"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE appointments 
                SET seated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'confirmed' AND seated_at IS NULL
            """, (appointment_id,))
            
            affected = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()
            
            if affected > 0:
                print(f"🪑 Client assentat: Reserva ID {appointment_id}")
                return True
            return False
        except Exception as e:
            print(f"❌ Error marcant seated: {e}")
            return False
    
    def mark_left(self, appointment_id):
        """Marcar que el client ha marxat i calcular durada"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE appointments 
                SET left_at = CURRENT_TIMESTAMP,
                    duration_minutes = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - seated_at))/60
                WHERE id = %s AND status = 'confirmed' AND seated_at IS NOT NULL AND left_at IS NULL
                RETURNING duration_minutes
            """, (appointment_id,))
            
            result = cursor.fetchone()
            conn.commit()
            cursor.close()
            conn.close()
            
            if result:
                duration = int(result[0])
                print(f"👋 Client ha marxat: Reserva ID {appointment_id} - Durada: {duration} min")
                return True, duration
            return False, None
        except Exception as e:
            print(f"❌ Error marcant left: {e}")
            return False, None
    
    def mark_no_show(self, appointment_id, phone):
        """Marcar no-show i incrementar contador del client"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Marcar reserva com a no-show
            cursor.execute("""
                UPDATE appointments 
                SET no_show = TRUE, status = 'no_show'
                WHERE id = %s AND status = 'confirmed'
            """, (appointment_id,))
            
            # Incrementar contador de no-shows del client
            cursor.execute("""
                UPDATE customers 
                SET no_show_count = no_show_count + 1
                WHERE phone = %s
            """, (phone,))
            
            # Decrementar visit_count ja que no ha vingut
            cursor.execute("""
                UPDATE customers 
                SET visit_count = GREATEST(visit_count - 1, 0)
                WHERE phone = %s
            """, (phone,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"❌ No-show registrat: Reserva ID {appointment_id}")
            return True
        except Exception as e:
            print(f"❌ Error marcant no-show: {e}")
            return False
    
    def get_customer_stats(self, phone):
        """Obtenir estadístiques d'un client"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Obtenir info bàsica del client
            cursor.execute("""
                SELECT name, visit_count, no_show_count, last_visit
                FROM customers
                WHERE phone = %s
            """, (phone,))
            
            customer = cursor.fetchone()
            
            if not customer:
                cursor.close()
                conn.close()
                return None
            
            # Obtenir durada mitjana de les visites
            cursor.execute("""
                SELECT AVG(duration_minutes) as avg_duration,
                       COUNT(*) as completed_visits
                FROM appointments
                WHERE phone = %s 
                  AND duration_minutes IS NOT NULL
                  AND no_show = FALSE
            """, (phone,))
            
            stats = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return {
                'name': customer[0],
                'total_visits': customer[1],
                'no_shows': customer[2],
                'last_visit': customer[3].isoformat() if customer[3] else None,
                'avg_duration': int(stats[0]) if stats[0] else None,
                'completed_visits': stats[1]
            }
        except Exception as e:
            print(f"❌ Error obtenint estadístiques: {e}")
            return None
    
    def get_global_stats(self):
        """Obtenir estadístiques globals del restaurant"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Durada mitjana global
            cursor.execute("""
                SELECT AVG(duration_minutes) as avg_duration,
                       MIN(duration_minutes) as min_duration,
                       MAX(duration_minutes) as max_duration,
                       COUNT(*) as total_completed
                FROM appointments
                WHERE duration_minutes IS NOT NULL AND no_show = FALSE
            """)
            
            duration_stats = cursor.fetchone()
            
            # Total de no-shows
            cursor.execute("""
                SELECT COUNT(*) as total_no_shows
                FROM appointments
                WHERE no_show = TRUE
            """)
            
            no_show_count = cursor.fetchone()[0]
            
            # Top clients
            cursor.execute("""
                SELECT c.name, c.phone, c.visit_count, c.no_show_count,
                       AVG(a.duration_minutes) as avg_duration
                FROM customers c
                LEFT JOIN appointments a ON c.phone = a.phone AND a.duration_minutes IS NOT NULL
                GROUP BY c.id, c.name, c.phone, c.visit_count, c.no_show_count
                ORDER BY c.visit_count DESC
                LIMIT 10
            """)
            
            top_customers = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return {
                'avg_duration': int(duration_stats[0]) if duration_stats[0] else 0,
                'min_duration': int(duration_stats[1]) if duration_stats[1] else 0,
                'max_duration': int(duration_stats[2]) if duration_stats[2] else 0,
                'total_completed': duration_stats[3],
                'total_no_shows': no_show_count,
                'top_customers': [
                    {
                        'name': row[0],
                        'phone': row[1],
                        'visits': row[2],
                        'no_shows': row[3],
                        'avg_duration': int(row[4]) if row[4] else None
                    }
                    for row in top_customers
                ]
            }
        except Exception as e:
            print(f"❌ Error obtenint estadístiques globals: {e}")
            return None


class ConversationManager:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
    
    def get_connection(self):
        return psycopg2.connect(self.database_url)
    
    def clean_old_messages(self):
        """Eliminar missatges de més de 15 dies de TOTS els usuaris"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM conversations 
                WHERE created_at < NOW() - INTERVAL '15 days'
            """)
            
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                print(f"🧹 Netejats {deleted_count} missatges antics (>15 dies)")
            
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"❌ Error limpiando mensajes antiguos: {e}")
    
    def save_message(self, phone, role, content):
        """Guardar un missatge a l'historial"""
        try:
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
        """Obtenir historial de conversa NOMÉS dels últims 10 minuts"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
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
        """Comptar missatges dels últims 10 minuts"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
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
