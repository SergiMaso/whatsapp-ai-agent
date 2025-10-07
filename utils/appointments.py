import psycopg2
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

import logging
from typing import List, Dict, Optional

# Configuració bàsica del logger
logging.basicConfig(level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

load_dotenv()


class AppointmentManager:
    """
    Gestor de reserves del restaurant

    ```
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
        """Crear totes les taules necessàries si no existeixen"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
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

                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS customers (
                            id SERIAL PRIMARY KEY,
                            phone VARCHAR(50) UNIQUE NOT NULL,
                            name VARCHAR(100),
                            language VARCHAR(10),
                            last_visit TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS conversations (
                            id SERIAL PRIMARY KEY,
                            phone VARCHAR(50) NOT NULL,
                            role VARCHAR(20) NOT NULL,
                            content TEXT NOT NULL,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Inicialitzar taules del restaurant (només si no existeixen)
                    cursor.execute("SELECT COUNT(*) FROM tables")
                    if cursor.fetchone()[0] == 0:
                        for i in range(1, 21):
                            cursor.execute("INSERT INTO tables (table_number, capacity) VALUES (%s, 4)", (i,))
                        for i in range(21, 29):
                            cursor.execute("INSERT INTO tables (table_number, capacity) VALUES (%s, 2)", (i,))
                    conn.commit()
                    logging.info("✅ Base de dades inicialitzada correctament")
        except Exception as e:
            logging.error(f"❌ Error creant taules: {e}", exc_info=True)

    def find_available_table(self, start_time, end_time, num_people, exclude_appointment_id=None):
        """Buscar una taula disponible per a una reserva"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
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
                    reserved_tuple = tuple(reserved_ids) if reserved_ids else (0,)

                    if num_people <= 2:
                        cursor.execute("""
                            SELECT id, table_number, capacity FROM tables 
                            WHERE capacity = 2 AND id NOT IN %s ORDER BY table_number LIMIT 1
                        """, (reserved_tuple,))
                        result = cursor.fetchone()
                        if not result:
                            cursor.execute("""
                                SELECT id, table_number, capacity FROM tables 
                                WHERE capacity = 4 AND id NOT IN %s ORDER BY table_number LIMIT 1
                            """, (reserved_tuple,))
                            result = cursor.fetchone()
                    else:
                        cursor.execute("""
                            SELECT id, table_number, capacity FROM tables 
                            WHERE capacity >= %s AND id NOT IN %s ORDER BY capacity, table_number LIMIT 1
                        """, (num_people, reserved_tuple))
                        result = cursor.fetchone()

                    if result:
                        return {'id': result[0], 'number': result[1], 'capacity': result[2]}
                    return None
        except Exception as e:
            logging.error(f"❌ Error buscant taula: {e}", exc_info=True)
            return None

    def create_appointment(self, phone, client_name, date, time, num_people, duration_hours=1):
        """Crear una nova reserva"""
        try:
            start_time = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            end_time = start_time + timedelta(hours=duration_hours)
            date_only = start_time.date()

            customer_language = self.get_customer_language(phone) or 'es'
            table = self.find_available_table(start_time, end_time, num_people)
            if not table:
                return None

            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO appointments 
                        (phone, client_name, date, start_time, end_time, num_people, table_id, language, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (phone, client_name, date_only, start_time, end_time, num_people, table['id'], customer_language, 'confirmed'))
                    appointment_id = cursor.fetchone()[0]
                    conn.commit()
                    return {'id': appointment_id, 'table': table, 'start': start_time, 'end': end_time}
        except Exception as e:
            logging.error(f"❌ Error creant reserva: {e}", exc_info=True)
            return None

    def update_appointment(self, phone, appointment_id, new_date=None, new_time=None, new_num_people=None):
        """Actualitzar una reserva existent"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT start_time, end_time, num_people FROM appointments
                        WHERE id = %s AND phone = %s AND status = 'confirmed'
                    """, (appointment_id, phone))
                    result = cursor.fetchone()
                    if not result:
                        return None

                    current_start, current_end, current_num_people = result
                    date_part = new_date or current_start.strftime("%Y-%m-%d")
                    time_part = new_time or current_start.strftime("%H:%M")
                    new_start = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M")
                    duration = (current_end - current_start).total_seconds() / 3600
                    new_end = new_start + timedelta(hours=duration)
                    final_num_people = new_num_people or current_num_people
                    table = self.find_available_table(new_start, new_end, final_num_people, exclude_appointment_id=appointment_id)
                    if not table:
                        return None

                    cursor.execute("""
                        UPDATE appointments
                        SET date = %s, start_time = %s, end_time = %s, num_people = %s, table_id = %s
                        WHERE id = %s AND phone = %s
                    """, (new_start.date(), new_start, new_end, final_num_people, table['id'], appointment_id, phone))
                    conn.commit()
                    return {'id': appointment_id, 'table': table, 'start': new_start, 'end': new_end}
        except Exception as e:
            logging.error(f"❌ Error actualitzant reserva: {e}", exc_info=True)
            return None

    def get_customer_name(self, phone):
        """Obtenir el nom d'un client si existeix"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT name FROM customers WHERE phone = %s", (phone,))
                    result = cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            logging.error(f"❌ Error obtenint nom: {e}", exc_info=True)
            return None

    def get_customer_language(self, phone):
        """Obtenir l'idioma preferit d'un client si existeix"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT language FROM customers WHERE phone = %s", (phone,))
                    result = cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            logging.error(f"❌ Error obtenint idioma: {e}", exc_info=True)
            return None

    def save_customer_language(self, phone, language):
        """Guardar l'idioma preferit d'un client"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO customers (phone, name, language, last_visit)
                        VALUES (%s, 'Usuario', %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (phone) 
                        DO UPDATE SET language = EXCLUDED.language, last_visit = CURRENT_TIMESTAMP
                    """, (phone, language))
                    conn.commit()
                    logging.info(f"🌍 Idioma actualitzat per {phone} → {language}")
        except Exception as e:
            logging.error(f"❌ Error guardant idioma: {e}", exc_info=True)





class ConversationManager:
    """
    Gestor de l'historial de converses.
    
    Responsabilitats:
    - Guardar missatges de l'usuari i del bot
    - Recuperar historial per mantenir context
    - Netejar historial després de reserves exitoses
    """

    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')

    def get_connection(self) -> psycopg2.extensions.connection:
        """Crear connexió a PostgreSQL"""
        return psycopg2.connect(self.database_url)

    def save_message(self, phone: str, role: str, content: str) -> None:
        """Guardar un missatge a l'historial"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO conversations (phone, role, content) VALUES (%s, %s, %s)",
                        (phone, role, content)
                    )
                    conn.commit()
        except Exception as e:
            logging.error(f"Error guardando mensaje: {e}")

    def get_history(self, phone: str, limit: int = 10) -> List[Dict[str, str]]:
        """Obtenir historial de conversa"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT role, content FROM conversations WHERE phone = %s ORDER BY created_at DESC LIMIT %s",
                        (phone, limit)
                    )
                    messages = cursor.fetchall()
            return [{"role": role, "content": content} for role, content in reversed(messages)]
        except Exception as e:
            logging.error(f"Error obteniendo historial: {e}")
            return []

    def clear_history(self, phone: str) -> None:
        """Netejar tot l'historial d'un client"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM conversations WHERE phone = %s", (phone,))
                    conn.commit()
        except Exception as e:
            logging.error(f"Error limpiando historial: {e}")

    def get_message_count(self, phone: str) -> Optional[int]:
        """
        Comptar quants missatges ha enviat l'usuari.
        Utilitzat per determinar si és el primer missatge.
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM conversations WHERE phone = %s AND role = 'user'",
                        (phone,)
                    )
                    count = cursor.fetchone()[0]
            return count
        except Exception as e:
            logging.error(f"Error contando mensajes: {e}")
            return None

