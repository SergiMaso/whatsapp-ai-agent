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
            
            # TAULA 1: TABLES (taules del restaurant)
            # Cada taula té un número únic i una capacitat (2 o 4 persones)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tables (
                    id SERIAL PRIMARY KEY,
                    table_number INTEGER UNIQUE NOT NULL,
                    capacity INTEGER NOT NULL,
                    status VARCHAR(20) DEFAULT 'available'
                )
            """)
            
            # TAULA 2: APPOINTMENTS (reserves)
            # Camps importants:
            # - start_time i end_time són TIMESTAMP per calcular solapaments de temps
            # - table_id referència a la taula assignada
            # - status pot ser 'confirmed' o 'cancelled'
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
                    status VARCHAR(20) DEFAULT 'confirmed',
                    reminder_sent BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # TAULA 3: CUSTOMERS (clients)
            # Guardem el nom i l'idioma preferit de cada client
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) UNIQUE NOT NULL,
                    name VARCHAR(100),
                    language VARCHAR(10),
                    last_visit TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Verificar si la columna 'language' existeix (per bases de dades antigues)
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='customers' AND column_name='language'
            """)
            if not cursor.fetchone():
                # Si no existeix, afegir-la
                cursor.execute("ALTER TABLE customers ADD COLUMN language VARCHAR(10)")
                conn.commit()
            
            # TAULA 4: CONVERSATIONS (historial de converses)
            # Guardem tots els missatges per mantenir context
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # INICIALITZAR TAULES DEL RESTAURANT (només la primera vegada)
            cursor.execute("SELECT COUNT(*) FROM tables")
            if cursor.fetchone()[0] == 0:
                # Crear 20 taules de 4 persones (taules 1-20)
                for i in range(1, 21):
                    cursor.execute("INSERT INTO tables (table_number, capacity) VALUES (%s, 4)", (i,))
                # Crear 8 taules de 2 persones (taules 21-28)
                for i in range(21, 29):
                    cursor.execute("INSERT INTO tables (table_number, capacity) VALUES (%s, 2)", (i,))
            
            conn.commit()
            cursor.close()
            conn.close()
            print("✅ Base de datos lista")
        
        except Exception as e:
            print(f"❌ Error creando tablas: {e}")
    
    def find_available_table(self, start_time, end_time, num_people, exclude_appointment_id=None):
        """
        Buscar una taula disponible per a una reserva
        
        Paràmetres:
        - start_time: TIMESTAMP d'inici de la reserva
        - end_time: TIMESTAMP de fi de la reserva
        - num_people: número de persones
        - exclude_appointment_id: ID de reserva a excloure (per actualitzacions)
        
        Lògica:
        1. Buscar totes les taules reservades en aquest rang de temps
        2. Trobar una taula lliure que s'ajusti al número de persones
        3. Prioritzar taules del tamany exacte (2 persones → taula de 2)
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # STEP 1: Trobar taules ja reservades en aquest rang de temps
            # Detectem solapament si:
            # - La nova reserva comença abans que una existent acabi
            # - La nova reserva acaba després que una existent comenci
            if exclude_appointment_id:
                # Si estem actualitzant, excloure la reserva actual
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
            
            # IDs de taules ja reservades
            reserved_ids = [row[0] for row in cursor.fetchall()]
            
            # STEP 2: Buscar taula disponible segons el número de persones
            if num_people <= 2:
                # Per 1-2 persones: primer buscar taula de 2
                cursor.execute("""
                    SELECT id, table_number, capacity FROM tables 
                    WHERE capacity = 2 AND id NOT IN %s ORDER BY table_number LIMIT 1
                """, (tuple(reserved_ids) if reserved_ids else (0,),))
                result = cursor.fetchone()
                
                # Si no hi ha taules de 2, buscar taula de 4
                if not result:
                    cursor.execute("""
                        SELECT id, table_number, capacity FROM tables 
                        WHERE capacity = 4 AND id NOT IN %s ORDER BY table_number LIMIT 1
                    """, (tuple(reserved_ids) if reserved_ids else (0,),))
                    result = cursor.fetchone()
            else:
                # Per 3-4 persones: buscar taula de 4 (o més gran)
                cursor.execute("""
                    SELECT id, table_number, capacity FROM tables 
                    WHERE capacity >= %s AND id NOT IN %s ORDER BY capacity, table_number LIMIT 1
                """, (num_people, tuple(reserved_ids) if reserved_ids else (0,)))
                result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                # Retornar informació de la taula trobada
                return {'id': result[0], 'number': result[1], 'capacity': result[2]}
            return None
        
        except Exception as e:
            print(f"❌ Error buscando mesa: {e}")
            return None
    
    def create_appointment(self, phone, client_name, date, time, num_people, duration_hours=1):
        """
        Crear una nova reserva
        
        Paràmetres:
        - phone: telèfon del client
        - client_name: nom del client
        - date: data en format YYYY-MM-DD
        - time: hora en format HH:MM
        - num_people: número de persones (1-4)
        - duration_hours: durada de la reserva (per defecte 1 hora)
        
        Procés:
        1. Convertir date + time a TIMESTAMP
        2. Buscar taula disponible
        3. Crear la reserva a la BD
        4. Retornar informació de la reserva creada
        """
        try:
            # STEP 1: Convertir date i time a TIMESTAMP
            start_time = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            end_time = start_time + timedelta(hours=duration_hours)
            date_only = start_time.date()
            
            # STEP 2: Obtenir idioma del client
            customer_language = self.get_customer_language(phone) or 'es'
            
            # STEP 3: Buscar taula disponible
            table = self.find_available_table(start_time, end_time, num_people)
            if not table:
                # No hi ha taules disponibles
                return None
            
            # STEP 4: Inserir reserva a la BD
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # IMPORTANT: 9 columnes = 9 valors (%s)
            cursor.execute("""
                INSERT INTO appointments 
                (phone, client_name, date, start_time, end_time, num_people, table_id, language, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (phone, client_name, date_only, start_time, end_time, num_people, table['id'], customer_language, 'confirmed'))
            
            appointment_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()
            
            # STEP 5: Retornar informació de la reserva creada
            return {'id': appointment_id, 'table': table, 'start': start_time, 'end': end_time}
        
        except Exception as e:
            print(f"❌ Error creando reserva: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def update_appointment(self, phone, appointment_id, new_date=None, new_time=None, new_num_people=None):
        """
        Actualitzar una reserva existent (canviar data, hora o número de persones)
        
        Paràmetres:
        - phone: telèfon del client (per seguretat)
        - appointment_id: ID de la reserva a modificar
        - new_date: nova data (opcional)
        - new_time: nova hora (opcional)
        - new_num_people: nou número de persones (opcional)
        
        Procés:
        1. Obtenir reserva actual
        2. Calcular nous valors (usar valors actuals si no es proporcionen nous)
        3. Buscar taula disponible per als nous valors
        4. Actualitzar la reserva
        
        IMPORTANT: Aquesta funció NO cancel·la la reserva, només la modifica
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # STEP 1: Obtenir reserva actual
            cursor.execute("""
                SELECT start_time, end_time, num_people FROM appointments
                WHERE id = %s AND phone = %s AND status = 'confirmed'
            """, (appointment_id, phone))
            
            result = cursor.fetchone()
            if not result:
                # Reserva no trobada o ja cancel·lada
                cursor.close()
                conn.close()
                return None
            
            current_start, current_end, current_num_people = result
            
            # STEP 2: Calcular nous valors
            if new_date or new_time:
                # Si canviem data o hora, recalcular start_time
                date_part = new_date if new_date else current_start.strftime("%Y-%m-%d")
                time_part = new_time if new_time else current_start.strftime("%H:%M")
                new_start = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M")
            else:
                # Mantenir data i hora actual
                new_start = current_start
            
            # Mantenir la mateixa durada
            duration = (current_end - current_start).total_seconds() / 3600
            new_end = new_start + timedelta(hours=duration)
            new_date_only = new_start.date()
            
            # Determinar número de persones
            final_num_people = new_num_people if new_num_people else current_num_people
            
            # STEP 3: Buscar taula disponible per als nous valors
            # IMPORTANT: Excloure la reserva actual per no considerar-la com a conflicte
            table = self.find_available_table(new_start, new_end, final_num_people, exclude_appointment_id=appointment_id)
            if not table:
                # No hi ha taules disponibles per als nous valors
                cursor.close()
                conn.close()
                return None
            
            # STEP 4: Actualitzar la reserva
            cursor.execute("""
                UPDATE appointments
                SET date = %s, start_time = %s, end_time = %s, num_people = %s, table_id = %s
                WHERE id = %s AND phone = %s
            """, (new_date_only, new_start, new_end, final_num_people, table['id'], appointment_id, phone))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            # STEP 5: Retornar informació de la reserva actualitzada
            return {'id': appointment_id, 'table': table, 'start': new_start, 'end': new_end}
        
        except Exception as e:
            print(f"❌ Error actualizando reserva: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_appointments(self, phone, from_date=None):
        """
        Obtenir totes les reserves d'un client
        
        Paràmetres:
        - phone: telèfon del client
        - from_date: data a partir de la qual buscar (per defecte: avui)
        
        Retorna: llista de reserves ordenades per data/hora
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if from_date is None:
                from_date = datetime.now().date()
            
            # Obtenir reserves amb informació de la taula assignada
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
        """
        Obtenir la darrera reserva activa d'un client
        
        Utilitzat per:
        - Mostrar context a GPT sobre reserves actives
        - Permetre modificar la reserva més recent
        
        Retorna: dict amb id, date, time, num_people o None
        """
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
        """
        Cancel·lar una reserva (marca com 'cancelled')
        
        IMPORTANT: No esborra la reserva, només canvia l'estat
        """
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
        """
        Guardar informació d'un client
        
        Si el client ja existeix, actualitza el nom i l'idioma
        Si no existeix, crea un nou registre
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if language:
                # Guardar amb idioma
                cursor.execute("""
                    INSERT INTO customers (phone, name, language, last_visit)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (phone) 
                    DO UPDATE SET name = EXCLUDED.name, language = EXCLUDED.language, last_visit = CURRENT_TIMESTAMP
                """, (phone, name, language))
            else:
                # Guardar sense idioma (mantenir l'existent)
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
        """Obtenir el nom d'un client si existeix"""
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
        """Obtenir l'idioma preferit d'un client si existeix"""
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
        
        Si el client no existeix, crea un registre amb nom 'Usuario'
        (després es pot actualitzar amb el nom real)
        """
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
    """
    Gestor de l'historial de converses
    
    Responsabilitats:
    - Guardar missatges de l'usuari i del bot
    - Recuperar historial per mantenir context
    - Netejar historial després de reserves exitoses
    """
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
    
    def get_connection(self):
        """Crear connexió a PostgreSQL"""
        return psycopg2.connect(self.database_url)
    
    def save_message(self, phone, role, content):
        """
        Guardar un missatge a l'historial
        
        Paràmetres:
        - phone: telèfon del client
        - role: 'user' o 'assistant'
        - content: text del missatge
        """
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
        """
        Obtenir historial de conversa
        
        Paràmetres:
        - phone: telèfon del client
        - limit: número màxim de missatges a retornar
        
        Retorna: llista de missatges en format [{role, content}]
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT role, content FROM conversations WHERE phone = %s ORDER BY created_at DESC LIMIT %s", (phone, limit))
            messages = cursor.fetchall()
            cursor.close()
            conn.close()
            # Retornar en ordre cronològic (invertir la llista)
            return [{"role": role, "content": content} for role, content in reversed(messages)]
        except Exception as e:
            print(f"❌ Error obteniendo historial: {e}")
            return []
    
    def clear_history(self, phone):
        """
        Netejar tot l'historial d'un client
        
        S'usa després de completar una reserva exitosament
        per començar una conversa nova neta
        """
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
        Comptar quants missatges ha enviat l'usuari
        
        Utilitzat per determinar si és el primer missatge
        (per aplicar lògica d'idioma per defecte)
        """
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
