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
        """Crear conexión a la base de datos"""
        return psycopg2.connect(self.database_url)
    
    def ensure_tables_exist(self):
        """Crear todas las tablas necesarias"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Tabla de mesas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tables (
                    id SERIAL PRIMARY KEY,
                    table_number INTEGER UNIQUE NOT NULL,
                    capacity INTEGER NOT NULL,
                    status VARCHAR(20) DEFAULT 'available'
                )
            """)
            
            # Tabla de reservas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS appointments (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) NOT NULL,
                    client_name VARCHAR(100),
                    date DATE NOT NULL,
                    time TIME NOT NULL,
                    num_people INTEGER NOT NULL,
                    table_id INTEGER REFERENCES tables(id),
                    language VARCHAR(10) DEFAULT 'es',
                    status VARCHAR(20) DEFAULT 'confirmed',
                    reminder_sent BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla de clientes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) UNIQUE NOT NULL,
                    name VARCHAR(100),
                    language VARCHAR(10) DEFAULT 'ca',
                    last_visit TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Verificar si existe la columna language
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='customers' AND column_name='language'
            """)
            
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE customers ADD COLUMN language VARCHAR(10) DEFAULT 'ca'")
                print("✅ Columna language agregada a customers")
            
            # Inicializar mesas si no existen
            cursor.execute("SELECT COUNT(*) FROM tables")
            if cursor.fetchone()[0] == 0:
                # Crear 20 mesas de 4 personas (mesas 1-20)
                for i in range(1, 21):
                    cursor.execute("""
                        INSERT INTO tables (table_number, capacity) 
                        VALUES (%s, 4)
                    """, (i,))
                
                # Crear 8 mesas de 2 personas (mesas 21-28)
                for i in range(21, 29):
                    cursor.execute("""
                        INSERT INTO tables (table_number, capacity) 
                        VALUES (%s, 2)
                    """, (i,))
                
                print("✅ Mesas inicializadas: 20 de 4 personas, 8 de 2 personas")
            
            conn.commit()
            cursor.close()
            conn.close()
            print("✅ Tablas del restaurante creadas/verificadas")
        
        except Exception as e:
            print(f"Error creando tablas: {e}")
    
    def find_available_table(self, date, time, num_people):
        """
        Buscar mesa disponible que se ajuste al número de personas
        Prioriza mesas del tamaño exacto, luego más grandes
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Buscar mesas ya reservadas en esa fecha/hora
            cursor.execute("""
                SELECT table_id 
                FROM appointments 
                WHERE date = %s 
                  AND time = %s 
                  AND status = 'confirmed'
            """, (date, time))
            
            reserved_table_ids = [row[0] for row in cursor.fetchall()]
            
            # Buscar mesa disponible del tamaño adecuado
            if num_people <= 2:
                # Buscar mesa de 2 primero
                cursor.execute("""
                    SELECT id, table_number, capacity 
                    FROM tables 
                    WHERE capacity = 2 
                      AND id NOT IN %s
                    ORDER BY table_number
                    LIMIT 1
                """, (tuple(reserved_table_ids) if reserved_table_ids else (0,),))
                
                result = cursor.fetchone()
                
                # Si no hay mesas de 2, buscar de 4
                if not result:
                    cursor.execute("""
                        SELECT id, table_number, capacity 
                        FROM tables 
                        WHERE capacity = 4 
                          AND id NOT IN %s
                        ORDER BY table_number
                        LIMIT 1
                    """, (tuple(reserved_table_ids) if reserved_table_ids else (0,),))
                    result = cursor.fetchone()
            else:
                # Para 3-4 personas, buscar mesa de 4
                cursor.execute("""
                    SELECT id, table_number, capacity 
                    FROM tables 
                    WHERE capacity >= %s 
                      AND id NOT IN %s
                    ORDER BY capacity, table_number
                    LIMIT 1
                """, (num_people, tuple(reserved_table_ids) if reserved_table_ids else (0,)))
                result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                return {'id': result[0], 'number': result[1], 'capacity': result[2]}
            else:
                return None
        
        except Exception as e:
            print(f"Error buscando mesa: {e}")
            return None
    
    def create_appointment(self, phone, client_name, date, time, num_people, language='es'):
        """Crear una nueva reserva con asignación de mesa"""
        try:
            # Buscar mesa disponible
            table = self.find_available_table(date, time, num_people)
            
            if not table:
                return None
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO appointments 
                (phone, client_name, date, time, num_people, table_id, language, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'confirmed')
                RETURNING id
            """, (phone, client_name, date, time, num_people, table['id'], language))
            
            appointment_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            conn.close()
            
            return {'id': appointment_id, 'table': table}
        
        except Exception as e:
            print(f"Error creando reserva: {e}")
            return None
    
    def get_appointments(self, phone, from_date=None):
        """Obtener reservas de un usuario"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if from_date is None:
                from_date = datetime.now().date()
            
            cursor.execute("""
                SELECT a.id, a.client_name, a.date, a.time, a.num_people, 
                       t.table_number, t.capacity, a.status
                FROM appointments a
                JOIN tables t ON a.table_id = t.id
                WHERE a.phone = %s AND a.date >= %s
                ORDER BY a.date, a.time
            """, (phone, from_date))
            
            appointments = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return appointments
        
        except Exception as e:
            print(f"Error obteniendo reservas: {e}")
            return []
    
    def cancel_appointment(self, phone, appointment_id):
        """Cancelar una reserva"""
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
            print(f"Error cancelando reserva: {e}")
            return False
    
    def save_customer_info(self, phone, name, language='ca'):
        """Guardar información del cliente incluyendo idioma"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if name:
                cursor.execute("""
                    INSERT INTO customers (phone, name, language, last_visit)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (phone) 
                    DO UPDATE SET 
                        name = EXCLUDED.name, 
                        language = EXCLUDED.language,
                        last_visit = CURRENT_TIMESTAMP
                """, (phone, name, language))
            else:
                # Solo guardar idioma sin nombre
                cursor.execute("""
                    INSERT INTO customers (phone, language, last_visit)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (phone) 
                    DO UPDATE SET 
                        language = EXCLUDED.language,
                        last_visit = CURRENT_TIMESTAMP
                """, (phone, language))
            
            conn.commit()
            cursor.close()
            conn.close()
        
        except Exception as e:
            print(f"Error guardando cliente: {e}")
    
    def get_customer_language(self, phone):
        """Obtener idioma del cliente"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT language FROM customers WHERE phone = %s
            """, (phone,))
            
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            return result[0] if result else None
        
        except Exception as e:
            print(f"Error obteniendo idioma: {e}")
            return None
    
    def update_customer_language(self, phone, language):
        """Actualizar solo el idioma del cliente"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO customers (phone, language, last_visit)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (phone) 
                DO UPDATE SET 
                    language = EXCLUDED.language,
                    last_visit = CURRENT_TIMESTAMP
            """, (phone, language))
            
            conn.commit()
            cursor.close()
            conn.close()
        
        except Exception as e:
            print(f"Error actualizando idioma: {e}")
    
    def get_customer_name(self, phone):
        """Obtener nombre de cliente si existe"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name FROM customers WHERE phone = %s
            """, (phone,))
            
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            return result[0] if result else None
        
        except Exception as e:
            print(f"Error obteniendo nombre: {e}")
            return None


class ConversationManager:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.ensure_tables_exist()
    
    def get_connection(self):
        """Crear conexión a la base de datos"""
        return psycopg2.connect(self.database_url)
    
    def ensure_tables_exist(self):
        """Crear todas las tablas necesarias"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Tabla de conversaciones
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla de mesas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tables (
                    id SERIAL PRIMARY KEY,
                    table_number INTEGER UNIQUE NOT NULL,
                    capacity INTEGER NOT NULL,
                    status VARCHAR(20) DEFAULT 'available'
                )
            """)
            
            # Tabla de reservas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS appointments (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) NOT NULL,
                    client_name VARCHAR(100),
                    date DATE NOT NULL,
                    time TIME NOT NULL,
                    language VARCHAR(10) DEFAULT 'es',
                    status VARCHAR(20) DEFAULT 'confirmed',
                    reminder_sent BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Verificar si existen las columnas nuevas
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='appointments'
            """)
            
            existing_columns = [row[0] for row in cursor.fetchall()]
            
            # Agregar num_people si no existe
            if 'num_people' not in existing_columns:
                cursor.execute("ALTER TABLE appointments ADD COLUMN num_people INTEGER DEFAULT 2")
                print("✅ Columna num_people agregada")
            
            # Agregar table_id si no existe
            if 'table_id' not in existing_columns:
                cursor.execute("ALTER TABLE appointments ADD COLUMN table_id INTEGER REFERENCES tables(id)")
                print("✅ Columna table_id agregada")
            
            # Eliminar service si existe
            if 'service' in existing_columns:
                cursor.execute("ALTER TABLE appointments DROP COLUMN service")
                print("✅ Columna service eliminada")
            
            conn.commit()
            
            # Tabla de clientes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(50) UNIQUE NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    last_visit TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Inicializar mesas si no existen
            cursor.execute("SELECT COUNT(*) FROM tables")
            if cursor.fetchone()[0] == 0:
                for i in range(1, 21):
                    cursor.execute("INSERT INTO tables (table_number, capacity) VALUES (%s, 4)", (i,))
                
                for i in range(21, 29):
                    cursor.execute("INSERT INTO tables (table_number, capacity) VALUES (%s, 2)", (i,))
                
                print("✅ Mesas inicializadas: 20 de 4 personas, 8 de 2 personas")
            
            conn.commit()
            cursor.close()
            conn.close()
            print("✅ Tablas del restaurante creadas/verificadas")
        
        except Exception as e:
            print(f"Error creando tablas: {e}")
    
    def save_message(self, phone, role, content):
        """Guardar un mensaje en el historial"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO conversations (phone, role, content)
                VALUES (%s, %s, %s)
            """, (phone, role, content))
            
            conn.commit()
            cursor.close()
            conn.close()
        
        except Exception as e:
            print(f"Error guardando mensaje: {e}")
    
    def get_history(self, phone, limit=10):
        """Obtener historial de conversación de un usuario"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT role, content
                FROM conversations
                WHERE phone = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (phone, limit))
            
            messages = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return [{"role": role, "content": content} for role, content in reversed(messages)]
        
        except Exception as e:
            print(f"Error obteniendo historial: {e}")
            return []
    
    def clear_history(self, phone):
        """Limpiar historial de un usuario"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM conversations
                WHERE phone = %s
            """, (phone,))
            
            conn.commit()
            cursor.close()
            conn.close()
        
        except Exception as e:
            print(f"Error limpiando historial: {e}")