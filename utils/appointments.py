import psycopg2
from psycopg2 import pool
from datetime import datetime, timedelta
from contextlib import contextmanager
import os
from dotenv import load_dotenv
import pytz  # IMPORTANT: Per gestionar timezones
from utils.config import config

load_dotenv()

class AppointmentManager:
    """
    Gestor de reserves del restaurant

    Responsabilitats:
    - Crear/actualitzar/cancel·lar reserves
    - Trobar taules disponibles
    - Gestionar informació de clients

    Optimitzacions:
    - Connection Pooling per reutilitzar connexions
    - Timezone com a constant de classe
    """

    # CONSTANTS DE CLASSE
    BARCELONA_TZ = pytz.timezone('Europe/Madrid')
    _connection_pool = None

    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')

        # Inicialitzar connection pool (singleton)
        if AppointmentManager._connection_pool is None:
            AppointmentManager._connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                dsn=self.database_url
            )

        self.ensure_tables_exist()

    def get_connection(self):
        """Obtenir connexió del pool amb timezone correcte"""
        conn = AppointmentManager._connection_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("SET timezone TO 'Europe/Madrid'")
        cursor.close()
        return conn

    def return_connection(self, conn):
        """Retornar connexió al pool"""
        if conn:
            AppointmentManager._connection_pool.putconn(conn)

    @contextmanager
    def get_db_connection(self):
        """
        Context manager per gestionar connexions automàticament

        Ús:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ...")
                # Connexió es retorna automàticament al sortir del with
        """
        conn = None
        try:
            conn = self.get_connection()
            yield conn
        finally:
            if conn:
                self.return_connection(conn)

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
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:

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
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name='appointments' AND column_name='delay_minutes'
                    """)
                    if not cursor.fetchone():
                        cursor.execute("ALTER TABLE appointments ADD COLUMN delay_minutes INTEGER")
                        print("✅ Columna delay_minutes afegida a appointments")
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
                    print("✅ Base de datos lista")

        except Exception as e:
            print(f"❌ Error creando tablas: {e}")
    
    def find_available_table(self, start_time, end_time, num_people, exclude_appointment_id=None):
        try:
            with self.get_db_connection() as conn:
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

                    if result:
                        return {'id': result[0], 'number': result[1], 'capacity': result[2]}
                    return None

        except Exception as e:
            print(f"❌ Error buscando mesa: {e}")
            return None
    
    def find_combined_tables(self, start_time, end_time, num_people, exclude_appointment_id=None):
        """
        ⚡ OPTIMITZAT: Buscar taules amb context manager (connexió sempre es retorna al pool)
        Retorna: {'tables': [taula1, taula2, ...], 'total_capacity': X}
        """
        try:
            with self.get_db_connection() as conn:
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
                # ⚡ Connexió es retorna automàticament al sortir del 'with'
            
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
    


    def find_next_available_slot(self, requested_date, requested_time, num_people, max_days_ahead=None):
        """
        Buscar el proper slot disponible a partir d'una data/hora donada

        Estratègia:
        1. Comprovar si la data/hora sol·licitada és vàlida i en el futur
        2. Comprovar si el restaurant està obert en aquella hora
        3. Buscar taules disponibles en aquella hora
        4. Si no n'hi ha, buscar la següent hora disponible el MATEIX DIA
        5. Si no hi ha cap hora disponible aquell dia, buscar en dies següents

        Retorna:
        {
            'date': 'YYYY-MM-DD',
            'time': 'HH:MM',
            'is_requested': True/False,  # True si és la hora sol·licitada, False si és alternativa
            'reason': 'Motiu si no és disponible'
        }
        o None si no hi ha disponibilitat
        """
        # Obtenir max_days_ahead de configuració si no s'ha especificat
        if max_days_ahead is None:
            max_days_ahead = config.get_int('search_window_days', 7)

        try:
            now = datetime.now(self.BARCELONA_TZ)
            
            # Parsejar data/hora sol·licitada
            requested_datetime_naive = datetime.strptime(f"{requested_date} {requested_time}", "%Y-%m-%d %H:%M")
            requested_datetime = self.BARCELONA_TZ.localize(requested_datetime_naive)
            
            print(f"🔍 [FIND SLOT] Buscant disponibilitat per {num_people} persones")
            print(f"🔍 [FIND SLOT] Data sol·licitada: {requested_datetime}")
            print(f"🔍 [FIND SLOT] Ara mateix: {now}")
            
            # VALIDACIÓ 1: Comprovar si és en el passat
            if requested_datetime <= now:
                print(f"❌ [FIND SLOT] La data/hora sol·licitada és en el passat!")
                # Buscar el proper slot disponible des d'ara mateix
                requested_datetime = now + timedelta(minutes=30)  # Afegir 30 min de marge
                requested_date = requested_datetime.strftime("%Y-%m-%d")
                requested_time = requested_datetime.strftime("%H:%M")
                print(f"🔄 [FIND SLOT] Ajustant a: {requested_datetime}")
            
            # Buscar en el dia sol·licitat primer
            slot = self._find_slot_on_date(requested_date, requested_time, num_people, now)
            if slot:
                return slot
            
            # Si no hi ha disponibilitat aquell dia, buscar en els propers dies
            print(f"🔍 [FIND SLOT] No hi ha disponibilitat el {requested_date}, buscant en dies següents...")
            
            for days_ahead in range(1, max_days_ahead + 1):
                next_date = (datetime.strptime(requested_date, "%Y-%m-%d") + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
                
                # Buscar a partir de la mateixa hora sol·licitada
                slot = self._find_slot_on_date(next_date, requested_time, num_people, now)
                if slot:
                    return slot
            
            print(f"❌ [FIND SLOT] No s'ha trobat cap disponibilitat en els propers {max_days_ahead} dies")
            return None
            
        except Exception as e:
            print(f"❌ Error buscant slot disponible: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _find_slot_on_date(self, date, start_time, num_people, now):
        """
        Buscar un slot disponible en una data específica
        Prova primer l'hora sol·licitada, després busca altres hores disponibles

        Retorna el primer slot disponible o None
        """
        try:
            
            print(f"🔍 [SLOT] Buscant en data: {date} a partir de {start_time}")
            
            # Obtenir horaris d'obertura
            hours = self.get_opening_hours(date)
            
            # VALIDACIÓ 2: Comprovar si el restaurant està tancat
            if hours['status'] == 'closed':
                print(f"❌ [SLOT] Restaurant tancat el {date}")
                return None
            
            # Obtenir intervals d'horari (dinar i/o sopar)
            time_slots = []
            
            if hours['status'] in ['full_day', 'lunch_only'] and hours['lunch_start'] and hours['lunch_end']:
                time_slots.append({
                    'start': hours['lunch_start'],
                    'end': hours['lunch_end'],
                    'name': 'lunch'
                })
            
            if hours['status'] in ['full_day', 'dinner_only'] and hours['dinner_start'] and hours['dinner_end']:
                time_slots.append({
                    'start': hours['dinner_start'],
                    'end': hours['dinner_end'],
                    'name': 'dinner'
                })
            
            if not time_slots:
                print(f"❌ [SLOT] No hi ha horaris definits per {date}")
                return None
            
            print(f"🕐 [SLOT] Intervals disponibles: {time_slots}")

            # Convertir hora sol·licitada a minuts
            start_time_parts = start_time.split(':')
            requested_minutes = int(start_time_parts[0]) * 60 + int(start_time_parts[1])

            # Obtenir mode de time slots i configuració
            time_slots_mode = config.get_str('time_slots_mode', 'interval')

            # Determinar els temps a comprovar segons el mode
            times_to_check = []

            if time_slots_mode == 'fixed':
                # Mode fixed: utilitzar horaris fixos definits
                for slot in time_slots:
                    if slot['name'] == 'lunch':
                        fixed_times = config.get_list('fixed_time_slots_lunch', ['13:00', '15:00'])
                    else:  # dinner
                        fixed_times = config.get_list('fixed_time_slots_dinner', ['20:00', '21:30'])

                    slot_start_parts = slot['start'].split(':')
                    slot_start_minutes = int(slot_start_parts[0]) * 60 + int(slot_start_parts[1])
                    slot_end_parts = slot['end'].split(':')
                    slot_end_minutes = int(slot_end_parts[0]) * 60 + int(slot_end_parts[1])

                    # Només afegir els temps fixos que cauen dins del rang del slot i després de l'hora sol·licitada
                    for time_str in fixed_times:
                        time_parts = time_str.split(':')
                        time_minutes = int(time_parts[0]) * 60 + int(time_parts[1])
                        if slot_start_minutes <= time_minutes <= slot_end_minutes and time_minutes >= requested_minutes:
                            times_to_check.append((time_minutes, slot))
            else:
                # Mode interval: generar temps cada N minuts
                time_slot_interval = config.get_int('time_slot_interval_minutes', 30)

                for slot in time_slots:
                    slot_start_parts = slot['start'].split(':')
                    slot_start_minutes = int(slot_start_parts[0]) * 60 + int(slot_start_parts[1])
                    slot_end_parts = slot['end'].split(':')
                    slot_end_minutes = int(slot_end_parts[0]) * 60 + int(slot_end_parts[1])

                    # Començar des de l'hora sol·licitada o l'inici de l'interval
                    start_checking_from = max(requested_minutes, slot_start_minutes)

                    # Arrodonir al proper interval
                    if start_checking_from % time_slot_interval != 0:
                        start_checking_from = ((start_checking_from // time_slot_interval) + 1) * time_slot_interval

                    # Generar temps cada N minuts
                    for check_minutes in range(start_checking_from, slot_end_minutes + 1, time_slot_interval):
                        times_to_check.append((check_minutes, slot))

            # Ordenar els temps per ordre cronològic
            times_to_check.sort(key=lambda x: x[0])

            # Comprovar cada temps
            for check_minutes, slot in times_to_check:
                check_hour = check_minutes // 60
                check_minute = check_minutes % 60
                check_time = f"{check_hour:02d}:{check_minute:02d}"

                # Crear datetime per aquesta hora
                check_datetime_naive = datetime.strptime(f"{date} {check_time}", "%Y-%m-%d %H:%M")
                check_datetime = self.BARCELONA_TZ.localize(check_datetime_naive)

                # VALIDACIÓ 3: Assegurar que no sigui en el passat
                if check_datetime <= now:
                    print(f"⏭️  [SLOT] {check_time} és en el passat, saltant...")
                    continue

                # VALIDACIÓ 4: Comprovar disponibilitat de taules
                end_datetime = check_datetime + timedelta(hours=1)
                tables_result = self.find_combined_tables(check_datetime, end_datetime, num_people)

                if tables_result:
                    is_requested = (check_time == start_time)
                    print(f"✅ [SLOT] Trobat slot disponible: {date} {check_time} (sol·licitat: {is_requested})")

                    return {
                        'date': date,
                        'time': check_time,
                        'is_requested': is_requested,
                        'reason': None if is_requested else f"L'hora sol·licitada ({start_time}) no està disponible"
                    }
                else:
                    print(f"❌ [SLOT] {check_time} - No hi ha taules per {num_people} persones")
            
            print(f"❌ [SLOT] No s'ha trobat cap hora disponible el {date}")
            return None
            
        except Exception as e:
            print(f"❌ Error buscant slot en data: {e}")
            import traceback
            traceback.print_exc()
            return None

    def create_appointment_with_alternatives(self, phone, client_name, date, time, num_people, duration_hours=1, notes=None):
        """
        Crear una reserva amb validacions i propostes d'alternatives si no hi ha disponibilitat
        
        Retorna:
        - Si hi ha disponibilitat: {'success': True, 'appointment': {...}, 'is_requested_time': True/False}
        - Si no hi ha disponibilitat: {'success': False, 'alternatives': [...], 'reason': '...'}
        """
        try:
            print(f"📞 [CREATE] Sol·licitud de reserva: {date} {time} per {num_people} persones")
            
            # Buscar el millor slot disponible
            slot = self.find_next_available_slot(date, time, num_people)
            
            if not slot:
                print(f"❌ [CREATE] No hi ha disponibilitat en els propers 7 dies")
                return {
                    'success': False,
                    'reason': 'No hi ha disponibilitat en els propers 7 dies',
                    'alternatives': []
                }
            
            # Si el slot trobat NO és l'hora sol·licitada, retornar com a alternativa
            if not slot['is_requested']:
                print(f"⚠️  [CREATE] Hora sol·licitada no disponible. Proposant alternativa: {slot['date']} {slot['time']}")
                return {
                    'success': False,
                    'reason': slot['reason'],
                    'alternative': {
                        'date': slot['date'],
                        'time': slot['time']
                    }
                }
            
            # Si el slot trobat ÉS l'hora sol·licitada, crear la reserva
            print(f"✅ [CREATE] Hora sol·licitada disponible! Creant reserva...")
            
            result = self.create_appointment(
                phone=phone,
                client_name=client_name,
                date=slot['date'],
                time=slot['time'],
                num_people=num_people,
                duration_hours=duration_hours,
                notes=notes
            )
            
            if result:
                return {
                    'success': True,
                    'appointment': result,
                    'is_requested_time': True
                }
            else:
                print(f"❌ [CREATE] Error crític: find_next_available_slot va dir que hi havia taules però create_appointment ha fallat")
                return {
                    'success': False,
                    'reason': 'Error intern creant la reserva',
                    'alternatives': []
                }
            
        except Exception as e:
            print(f"❌ Error en create_appointment_with_alternatives: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'reason': 'Error del sistema',
                'alternatives': []
            }

    def _find_tables_in_memory(self, all_tables, occupied_ids, num_people):
        """
        ⚡ OPTIMITZAT: Buscar taules disponibles EN MEMÒRIA (sense queries)
        Replica la lògica de find_combined_tables però treballa amb dades ja carregades

        Args:
            all_tables: Llista de tuples (id, table_number, capacity, pairing, status)
            occupied_ids: Set d'IDs de taules ocupades
            num_people: Nombre de persones

        Returns:
            {'tables': [...], 'total_capacity': X} o None
        """
        # Filtrar taules disponibles (no ocupades i status='available')
        available_tables = [t for t in all_tables if t[0] not in occupied_ids and t[4] == 'available']

        # Separar taules sense i amb pairing
        tables_no_pairing = [t for t in available_tables if t[3] is None]
        tables_with_pairing = [t for t in available_tables if t[3] is not None]

        # 1. PRIORITAT MÀXIMA: Taula SENSE PAIRING amb capacitat EXACTA
        for table in tables_no_pairing:
            if table[2] == num_people:
                return {
                    'tables': [{'id': table[0], 'number': table[1], 'capacity': table[2]}],
                    'total_capacity': table[2]
                }

        # 2. Taula SENSE PAIRING amb capacitat mínima suficient (prioritzar la més petita)
        suitable_tables = [t for t in tables_no_pairing if t[2] >= num_people]
        if suitable_tables:
            # Ordenar per capacitat ascendent i agafar la més petita
            best_table = min(suitable_tables, key=lambda t: t[2])
            return {
                'tables': [{'id': best_table[0], 'number': best_table[1], 'capacity': best_table[2]}],
                'total_capacity': best_table[2]
            }

        # 3. Taula AMB PAIRING amb capacitat EXACTA
        for table in tables_with_pairing:
            if table[2] == num_people:
                return {
                    'tables': [{'id': table[0], 'number': table[1], 'capacity': table[2]}],
                    'total_capacity': table[2]
                }

        # 4. Taula AMB PAIRING amb capacitat mínima suficient (prioritzar la més petita)
        suitable_tables = [t for t in tables_with_pairing if t[2] >= num_people]
        if suitable_tables:
            # Ordenar per capacitat ascendent i agafar la més petita
            best_table = min(suitable_tables, key=lambda t: t[2])
            return {
                'tables': [{'id': best_table[0], 'number': best_table[1], 'capacity': best_table[2]}],
                'total_capacity': best_table[2]
            }

        # 5. ÚLTIM RECURS: Intentar combinar taules amb pairing
        for table in available_tables:
            table_id, table_num, capacity, pairing, status = table

            if not pairing:
                continue

            paired_tables = []
            total_cap = capacity

            for paired_num in pairing:
                paired_table = next((t for t in available_tables if t[1] == paired_num), None)

                if paired_table:
                    paired_tables.append({
                        'id': paired_table[0],
                        'number': paired_table[1],
                        'capacity': paired_table[2]
                    })
                    total_cap += paired_table[2]

                    if total_cap >= num_people:
                        return {
                            'tables': [{'id': table_id, 'number': table_num, 'capacity': capacity}] + paired_tables,
                            'total_capacity': total_cap
                        }

        return None

    def check_availability(self, date, num_people, preferred_time=None):
        """
        ⚡ OPTIMITZAT: Consultar disponibilitat amb BATCH QUERIES (2 queries en lloc de 39)
        Retorna una llista de slots disponibles (sense crear cap reserva)

        Args:
            date: Data en format YYYY-MM-DD
            num_people: Nombre de persones
            preferred_time: Hora preferida (opcional, en format HH:MM)

        Retorna:
            {
                'available': True/False,
                'slots': [{'time': 'HH:MM', 'available': True}, ...],
                'message': 'Missatge descriptiu'
            }
        """
        try:
            now = datetime.now(self.BARCELONA_TZ)
            print(f"🔍 [CHECK OPTIMIZED] Consultant disponibilitat per {date} - {num_people} persones")

            # Obtenir horaris d'obertura
            hours = self.get_opening_hours(date)

            if hours['status'] == 'closed':
                print(f"❌ [CHECK] Restaurant tancat el {date}")
                return {
                    'available': False,
                    'slots': [],
                    'message': f'El restaurant està tancat el {date}'
                }

            # Obtenir intervals d'horari
            time_slots = []
            if hours['status'] in ['full_day', 'lunch_only'] and hours['lunch_start'] and hours['lunch_end']:
                time_slots.append({
                    'start': hours['lunch_start'],
                    'end': hours['lunch_end'],
                    'name': 'lunch'
                })

            if hours['status'] in ['full_day', 'dinner_only'] and hours['dinner_start'] and hours['dinner_end']:
                time_slots.append({
                    'start': hours['dinner_start'],
                    'end': hours['dinner_end'],
                    'name': 'dinner'
                })

            if not time_slots:
                return {
                    'available': False,
                    'slots': [],
                    'message': f'No hi ha horaris definits per {date}'
                }

            # ⚡ OPTIMITZACIÓ: Query única per obtenir TOTES les reserves del dia
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT table_id, start_time, end_time
                        FROM appointments
                        WHERE date = %s AND status = 'confirmed'
                    """, (date,))
                    daily_appointments = cursor.fetchall()

                    # ⚡ OPTIMITZACIÓ: Query única per obtenir TOTES les taules
                    cursor.execute("""
                        SELECT id, table_number, capacity, pairing, status
                        FROM tables
                        ORDER BY capacity ASC, table_number
                    """)
                    all_tables = cursor.fetchall()

                    print(f"📊 [CHECK] Carregades {len(daily_appointments)} reserves i {len(all_tables)} taules")

                    # Obtenir mode de time slots i configuració
                    time_slots_mode = config.get_str('time_slots_mode', 'interval')

                    # Determinar els temps a comprovar segons el mode
                    times_to_check = []  # Format: (time_minutes, period_name)

                    if time_slots_mode == 'fixed':
                        # Mode fixed: utilitzar horaris fixos definits
                        for slot in time_slots:
                            if slot['name'] == 'lunch':
                                fixed_times = config.get_list('fixed_time_slots_lunch', ['13:00', '15:00'])
                            else:  # dinner
                                fixed_times = config.get_list('fixed_time_slots_dinner', ['20:00', '21:30'])

                            slot_start_parts = slot['start'].split(':')
                            slot_start_minutes = int(slot_start_parts[0]) * 60 + int(slot_start_parts[1])
                            slot_end_parts = slot['end'].split(':')
                            slot_end_minutes = int(slot_end_parts[0]) * 60 + int(slot_end_parts[1])

                            # Només afegir els temps fixos que cauen dins del rang del slot
                            for time_str in fixed_times:
                                time_parts = time_str.split(':')
                                time_minutes = int(time_parts[0]) * 60 + int(time_parts[1])
                                if slot_start_minutes <= time_minutes <= slot_end_minutes:
                                    times_to_check.append((time_minutes, slot['name']))
                    else:
                        # Mode interval: generar temps cada N minuts
                        time_slot_interval = config.get_int('time_slot_interval_minutes', 30)

                        for slot in time_slots:
                            slot_start_parts = slot['start'].split(':')
                            slot_start_minutes = int(slot_start_parts[0]) * 60 + int(slot_start_parts[1])
                            slot_end_parts = slot['end'].split(':')
                            slot_end_minutes = int(slot_end_parts[0]) * 60 + int(slot_end_parts[1])

                            # Generar temps cada N minuts
                            for check_minutes in range(slot_start_minutes, slot_end_minutes + 1, time_slot_interval):
                                times_to_check.append((check_minutes, slot['name']))

                    # Generar llista de slots disponibles
                    available_slots = []

                    for check_minutes, period_name in times_to_check:
                        check_hour = check_minutes // 60
                        check_minute = check_minutes % 60
                        check_time = f"{check_hour:02d}:{check_minute:02d}"

                        # Crear datetime per aquesta hora
                        check_datetime_naive = datetime.strptime(f"{date} {check_time}", "%Y-%m-%d %H:%M")
                        check_datetime = self.BARCELONA_TZ.localize(check_datetime_naive)

                        # Saltar si és en el passat
                        if check_datetime <= now:
                            continue

                        # ⚡ OPTIMITZACIÓ: Calcular taules ocupades EN MEMÒRIA
                        end_datetime = check_datetime + timedelta(hours=1)

                        occupied_ids = {
                            apt[0] for apt in daily_appointments
                            if apt[1] < end_datetime and apt[2] > check_datetime
                        }

                        # ⚡ OPTIMITZACIÓ: Buscar taules disponibles EN MEMÒRIA (sense queries)
                        tables_result = self._find_tables_in_memory(all_tables, occupied_ids, num_people)

                        available_slots.append({
                            'time': check_time,
                            'available': tables_result is not None,
                            'period': period_name
                        })

                    # Filtrar només disponibles
                    available_only = [s for s in available_slots if s['available']]

                    print(f"✅ [CHECK OPTIMIZED] Trobats {len(available_only)} slots disponibles de {len(available_slots)} comprovats")
                    print(f"⚡ PERFORMANCE: 2 queries (abans: ~{len(available_slots) * 3} queries)")

                    return {
                        'available': len(available_only) > 0,
                        'slots': available_slots,
                        'available_slots': available_only,
                        'date': date,
                        'num_people': num_people,
                        'message': f'Disponibilitat per {num_people} persones el {date}'
                    }

        except Exception as e:
            print(f"❌ Error consultant disponibilitat: {e}")
            import traceback
            traceback.print_exc()
            return {
                'available': False,
                'slots': [],
                'message': 'Error consultant disponibilitat'
            }


    def create_appointment(self, phone, client_name, date, time, num_people, duration_hours=1, notes=None):
        try:
            # Parsejar la data/hora com a NAIVE
            naive_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            print(f"🕐 [TIMEZONE DEBUG] Input rebut: date={date}, time={time}")
            print(f"🕐 [TIMEZONE DEBUG] Datetime NAIVE creat: {naive_datetime}")

            # Convertir a timezone-aware (Barcelona)
            start_time = self.BARCELONA_TZ.localize(naive_datetime)
            print(f"🕐 [TIMEZONE DEBUG] Datetime AWARE (després localize): {start_time}")
            print(f"🕐 [TIMEZONE DEBUG] Timezone info: {start_time.tzinfo}")
            print(f"🕐 [TIMEZONE DEBUG] ISO format: {start_time.isoformat()}")
            
            end_time = start_time + timedelta(hours=duration_hours)
            print(f"🕐 [TIMEZONE DEBUG] End time: {end_time.isoformat()}")
            
            date_only = start_time.date()
            print(f"🕐 [TIMEZONE DEBUG] Date only: {date_only}")
            
            # IMPORTANT: Assegurar que el client existeix a customers
            self.save_customer_info(phone, client_name)
            
            customer_language = self.get_customer_language(phone) or 'es'
            
            # Buscar taules (individuals o combinades)
            tables_result = self.find_combined_tables(start_time, end_time, num_people)

            if not tables_result:
                return None

            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # Generar un booking_group_id únic per aquesta reserva
                    cursor.execute("SELECT gen_random_uuid()")
                    booking_group_id = cursor.fetchone()[0]

                    # Crear una reserva per cada taula, totes amb el mateix booking_group_id
                    appointment_ids = []
                    for table in tables_result['tables']:
                        print(f"🕐 [TIMEZONE DEBUG] Abans d'inserir a BD:")
                        print(f"🕐 [TIMEZONE DEBUG]   - start_time que s'enviarà: {start_time} (type: {type(start_time)})")
                        print(f"🕐 [TIMEZONE DEBUG]   - end_time que s'enviarà: {end_time} (type: {type(end_time)})")
                        print(f"🕐 [BOOKING GROUP] booking_group_id: {booking_group_id}")

                        cursor.execute("""
                            INSERT INTO appointments
                            (phone, client_name, date, start_time, end_time, num_people, table_id, language, notes, status, booking_group_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id, start_time, end_time
                        """, (phone, client_name, date_only, start_time, end_time, num_people, table['id'], customer_language, notes, 'confirmed', booking_group_id))

                        result = cursor.fetchone()
                        appointment_ids.append(result[0])

                        print(f"🕐 [TIMEZONE DEBUG] Després d'inserir (retornat per BD):")
                        print(f"🕐 [TIMEZONE DEBUG]   - ID: {result[0]}")
                        print(f"🕐 [TIMEZONE DEBUG]   - start_time desde BD: {result[1]}")
                        print(f"🕐 [TIMEZONE DEBUG]   - end_time desde BD: {result[2]}")

                    # Incrementar visit_count del client
                    cursor.execute("""
                        UPDATE customers
                        SET visit_count = visit_count + 1, last_visit = CURRENT_TIMESTAMP
                        WHERE phone = %s
                    """, (phone,))

                    print(f"✅ Reserva creada: IDs={appointment_ids} - {len(tables_result['tables'])} taules")

                    conn.commit()

                    return {
                        'id': appointment_ids[0],  # ID principal
                        'ids': appointment_ids,
                        'booking_group_id': str(booking_group_id),  # UUID del grup de reserves
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
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT start_time, end_time, num_people, table_id FROM appointments
                        WHERE id = %s AND phone = %s AND status = 'confirmed'
                    """, (appointment_id, phone))

                    result = cursor.fetchone()
                    if not result:
                        return None

                    current_start, current_end, current_num_people, current_table_id = result

                    if new_date or new_time:
                        date_part = new_date if new_date else current_start.strftime("%Y-%m-%d")
                        time_part = new_time if new_time else current_start.strftime("%H:%M")

                        print(f"🕐 [TIMEZONE DEBUG UPDATE] Input rebut: date={date_part}, time={time_part}")

                        # Parsejar com a NAIVE
                        naive_datetime = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M")
                        print(f"🕐 [TIMEZONE DEBUG UPDATE] Datetime NAIVE: {naive_datetime}")

                        # Convertir a timezone-aware (Barcelona)
                        new_start = self.BARCELONA_TZ.localize(naive_datetime)
                        print(f"🕐 [TIMEZONE DEBUG UPDATE] Datetime AWARE: {new_start}")
                        print(f"🕐 [TIMEZONE DEBUG UPDATE] ISO format: {new_start.isoformat()}")
                    else:
                        new_start = current_start
                        print(f"🕐 [TIMEZONE DEBUG UPDATE] Mantenint hora actual: {new_start}")

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
                            return None

                        if table_row[3] != 'available':
                            return None

                        cursor.execute("""
                            SELECT id FROM appointments
                            WHERE table_id = %s
                              AND status = 'confirmed'
                              AND id != %s
                              AND ((start_time < %s AND end_time > %s) OR (start_time >= %s AND start_time < %s))
                        """, (new_table_id, appointment_id, new_end, new_start, new_start, new_end))

                        if cursor.fetchone():
                            return None

                        table = {'id': table_row[0], 'number': table_row[1], 'capacity': table_row[2]}
                    else:
                        table = self.find_available_table(new_start, new_end, final_num_people, exclude_appointment_id=appointment_id)
                        if not table:
                            return None

                    cursor.execute("""
                        UPDATE appointments
                        SET date = %s, start_time = %s, end_time = %s, num_people = %s, table_id = %s
                        WHERE id = %s AND phone = %s
                    """, (new_date_only, new_start, new_end, final_num_people, table['id'], appointment_id, phone))

                    conn.commit()

                    return {'id': appointment_id, 'table': table, 'start': new_start, 'end': new_end}

        except Exception as e:
            print(f"❌ Error actualizando reserva: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_appointments(self, phone, from_date=None):
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
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
                    return appointments

        except Exception as e:
            print(f"❌ Error obteniendo reservas: {e}")
            return []
    
    def get_latest_appointment(self, phone):
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, date, start_time, num_people
                        FROM appointments
                        WHERE phone = %s AND status = 'confirmed'
                        ORDER BY created_at DESC LIMIT 1
                    """, (phone,))

                    result = cursor.fetchone()

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
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # Obtenir el booking_group_id de la reserva
                    cursor.execute("""
                        SELECT booking_group_id FROM appointments
                        WHERE id = %s AND phone = %s AND status = 'confirmed'
                    """, (appointment_id, phone))

                    result = cursor.fetchone()
                    if not result:
                        return False

                    booking_group_id = result[0]

                    # Cancel·lar TOTES les reserves del mateix booking_group_id
                    # Això permet cancel·lar reserves multi-taula d'un cop
                    if booking_group_id:
                        cursor.execute("""
                            UPDATE appointments
                            SET status = 'cancelled'
                            WHERE booking_group_id = %s AND phone = %s AND status = 'confirmed'
                        """, (booking_group_id, phone))
                        num_cancelled = cursor.rowcount
                        print(f"✅ Cancel·lades {num_cancelled} reserves del grup {booking_group_id}")
                    else:
                        # Fallback per reserves antigues sense booking_group_id
                        cursor.execute("""
                            UPDATE appointments
                            SET status = 'cancelled'
                            WHERE id = %s AND phone = %s AND status = 'confirmed'
                        """, (appointment_id, phone))
                        num_cancelled = cursor.rowcount

                    if num_cancelled > 0:
                        cursor.execute("""
                            UPDATE customers
                            SET visit_count = GREATEST(visit_count - 1, 0)
                            WHERE phone = %s
                        """, (phone,))

                    conn.commit()
                    return num_cancelled > 0
        except Exception as e:
            print(f"❌ Error cancelando reserva: {e}")
            return False
    
    def add_notes_to_appointment(self, phone, appointment_id, notes):
        """Afegir notes a una reserva existent"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE appointments
                        SET notes = %s
                        WHERE id = %s AND phone = %s AND status = 'confirmed'
                    """, (notes, appointment_id, phone))

                    affected = cursor.rowcount
                    conn.commit()
                    return affected > 0
        except Exception as e:
            print(f"❌ Error afegint notes: {e}")
            return False
    
    def save_customer_info(self, phone, name, language=None):
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
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
        except Exception as e:
            print(f"❌ Error guardando cliente: {e}")
    
    def get_customer_name(self, phone):
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT name FROM customers WHERE phone = %s", (phone,))
                    result = cursor.fetchone()
                    if result and result[0] != 'TEMP':
                        return result[0]
                    return None
        except Exception as e:
            print(f"❌ Error obteniendo nombre: {e}")
            return None
    
    def get_customer_language(self, phone):
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT language FROM customers WHERE phone = %s", (phone,))
                    result = cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            print(f"❌ Error obteniendo idioma: {e}")
            return None
    
    def save_customer_language(self, phone, language):
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO customers (phone, name, language, last_visit)
                        VALUES (%s, 'TEMP', %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (phone)
                        DO UPDATE SET language = EXCLUDED.language, last_visit = CURRENT_TIMESTAMP
                    """, (phone, language))

                    conn.commit()
                    print(f"🌍 Idioma guardado: {phone} → {language}")
        except Exception as e:
            print(f"❌ Error guardando idioma: {e}")
    
    # ========================================
    # MÈTODES PER OPENING_HOURS
    # ========================================
    
    def get_opening_hours(self, date):
        """
        ⚡ OPTIMITZAT: Obtenir horaris amb context manager
        Si no existeix a opening_hours, retorna els defaults de weekly_defaults
        """
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT status, lunch_start, lunch_end, dinner_start, dinner_end, notes, is_custom
                    FROM opening_hours
                    WHERE date = %s
                """, (date,))

                result = cursor.fetchone()

                if result:
                    cursor.close()
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
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
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
                    return True
        except Exception as e:
            print(f"❌ Error guardando horarios: {e}")
            return False
    
    def get_opening_hours_range(self, start_date, end_date):
        """Obtenir horaris per un rang de dates"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT date, status, lunch_start, lunch_end, dinner_start, dinner_end, notes, is_custom
                        FROM opening_hours
                        WHERE date >= %s AND date <= %s
                        ORDER BY date
                    """, (start_date, end_date))

                    results = cursor.fetchall()

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
        """Marcar que el client s'ha assentat i calcular retraso"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # Configurar timezone local
                    cursor.execute("SET timezone TO 'Europe/Madrid'")

                    cursor.execute("""
                        UPDATE appointments
                        SET seated_at = CURRENT_TIMESTAMP,
                            delay_minutes = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - start_time))/60
                        WHERE id = %s AND status = 'confirmed' AND seated_at IS NULL
                        RETURNING delay_minutes
                    """, (appointment_id,))

                    result = cursor.fetchone()
                    conn.commit()

                    if result:
                        delay = int(result[0])
                        print(f"🪑 Client assentat: Reserva ID {appointment_id} - Retraso: {delay} min")
                        return True, delay
                    return False, None
        except Exception as e:
            print(f"❌ Error marcant seated: {e}")
            return False, None
    
    def mark_left(self, appointment_id):
        """Marcar que el client ha marxat i calcular durada"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # Configurar timezone local
                    cursor.execute("SET timezone TO 'Europe/Madrid'")

                    cursor.execute("""
                        UPDATE appointments
                        SET left_at = CURRENT_TIMESTAMP,
                            duration_minutes = EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - seated_at))/60,
                            status = 'completed'
                        WHERE id = %s AND status = 'confirmed' AND seated_at IS NOT NULL AND left_at IS NULL
                        RETURNING duration_minutes
                    """, (appointment_id,))

                    result = cursor.fetchone()
                    conn.commit()

                    if result:
                        duration = int(result[0])
                        print(f"👋 Client ha marxat: Reserva ID {appointment_id} - Durada: {duration} min - Status: completed")
                        return True, duration
                    return False, None
        except Exception as e:
            print(f"❌ Error marcant left: {e}")
            return False, None
    
    def mark_no_show(self, appointment_id, phone):
        """Marcar no-show i incrementar contador del client"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
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

                    print(f"❌ No-show registrat: Reserva ID {appointment_id}")
                    return True
        except Exception as e:
            print(f"❌ Error marcant no-show: {e}")
            return False
    
    def get_customer_stats(self, phone):
        """Obtenir estadístiques d'un client"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # Obtenir info bàsica del client
                    cursor.execute("""
                        SELECT name, visit_count, no_show_count, last_visit
                        FROM customers
                        WHERE phone = %s
                    """, (phone,))

                    customer = cursor.fetchone()

                    if not customer:
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
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
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
    """
    Gestor de l'historial de converses

    Optimitzacions:
    - Usa el mateix connection pool que AppointmentManager
    - clean_old_messages NO es crida a cada save (només via scheduler)
    """

    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')

    def get_connection(self):
        """Obtenir connexió del pool compartit"""
        if AppointmentManager._connection_pool is None:
            # Si no està inicialitzat, crear-lo
            AppointmentManager._connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                dsn=self.database_url
            )
        conn = AppointmentManager._connection_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("SET timezone TO 'Europe/Madrid'")
        cursor.close()
        return conn

    def return_connection(self, conn):
        """Retornar connexió al pool"""
        if conn:
            AppointmentManager._connection_pool.putconn(conn)

    @contextmanager
    def get_db_connection(self):
        """
        Context manager per gestionar connexions automàticament
        Comparteix el pool amb AppointmentManager
        """
        conn = None
        try:
            conn = self.get_connection()
            yield conn
        finally:
            if conn:
                self.return_connection(conn)

    def clean_old_messages(self):
        """
        Eliminar missatges antics de TOTS els usuaris
        NOTA: Aquesta funció només s'hauria de cridar des del scheduler, NO a cada save!
        """
        cleanup_days = config.get_int('cleanup_messages_days', 15)

        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"""
                        DELETE FROM conversations
                        WHERE created_at < NOW() - INTERVAL '{cleanup_days} days'
                    """)

                    deleted_count = cursor.rowcount
                    if deleted_count > 0:
                        print(f"🧹 Netejats {deleted_count} missatges antics (>{cleanup_days} dies)")

                    conn.commit()
        except Exception as e:
            print(f"❌ Error limpiando mensajes antiguos: {e}")

    def save_message(self, phone, role, content):
        """
        Guardar un missatge a l'historial
        OPTIMITZAT: NO crida clean_old_messages (es fa via scheduler)
        """
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO conversations (phone, role, content) VALUES (%s, %s, %s)", (phone, role, content))
                    conn.commit()
        except Exception as e:
            print(f"❌ Error guardando mensaje: {e}")

    def get_history(self, phone, limit=None):
        """Obtenir historial de conversa recent"""
        if limit is None:
            limit = config.get_int('conversation_history_limit', 10)
        history_minutes = config.get_int('conversation_history_minutes', 20)

        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"""
                        SELECT role, content
                        FROM conversations
                        WHERE phone = %s
                          AND created_at > NOW() - INTERVAL '{history_minutes} minutes'
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (phone, limit))

                    messages = cursor.fetchall()
                    return [{"role": role, "content": content} for role, content in reversed(messages)]
        except Exception as e:
            print(f"❌ Error obteniendo historial: {e}")
            return []

    def clear_history(self, phone):
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM conversations WHERE phone = %s", (phone,))
                    conn.commit()
        except Exception as e:
            print(f"❌ Error limpiando historial: {e}")

    def get_message_count(self, phone):
        """Comptar missatges recents"""
        history_minutes = config.get_int('conversation_history_minutes', 20)

        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"""
                        SELECT COUNT(*)
                        FROM conversations
                        WHERE phone = %s
                          AND role = 'user'
                          AND created_at > NOW() - INTERVAL '{history_minutes} minutes'
                    """, (phone,))

                    count = cursor.fetchone()[0]
                    return count
        except Exception as e:
            print(f"❌ Error contando mensajes: {e}")
            return 0
