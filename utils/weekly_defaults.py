"""
Gestió de configuració setmanal per defecte dels horaris d'obertura
"""
import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
import traceback

load_dotenv()

class WeeklyDefaultsManager:
    """
    Classe per gestionar els horaris setmanals per defecte.
    Permet crear la taula, llegir i actualitzar els horaris.
    """

    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.ensure_table_exists()

    def get_connection(self):
        """Obté una connexió a la base de dades PostgreSQL"""
        return psycopg2.connect(self.database_url)

    def ensure_table_exists(self):
        """Crea la taula weekly_defaults si no existeix i inicialitza els valors per defecte"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Crear la taula amb DEFAULT correctes per a TIME
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS weekly_defaults (
                            id SERIAL PRIMARY KEY,
                            day_of_week INTEGER UNIQUE NOT NULL,
                            day_name VARCHAR(20) NOT NULL,
                            status VARCHAR(20) NOT NULL DEFAULT 'full_day',
                            lunch_start TIME DEFAULT '12:00:00',
                            lunch_end TIME DEFAULT '15:00:00',
                            dinner_start TIME DEFAULT '19:00:00',
                            dinner_end TIME DEFAULT '22:30:00',
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Trigger per actualitzar updated_at automàticament
                    cursor.execute("""
                        CREATE OR REPLACE FUNCTION update_timestamp()
                        RETURNS TRIGGER AS $$
                        BEGIN
                            NEW.updated_at = CURRENT_TIMESTAMP;
                            RETURN NEW;
                        END;
                        $$ LANGUAGE plpgsql;

                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_trigger WHERE tgname = 'update_weekly_defaults_timestamp'
                            ) THEN
                                CREATE TRIGGER update_weekly_defaults_timestamp
                                BEFORE UPDATE ON weekly_defaults
                                FOR EACH ROW
                                EXECUTE FUNCTION update_timestamp();
                            END IF;
                        END;
                        $$;
                    """)

                    # Inicialitzar valors per defecte si la taula està buida
                    cursor.execute("SELECT COUNT(*) FROM weekly_defaults")
                    if cursor.fetchone()[0] == 0:
                        day_names = ['Dilluns', 'Dimarts', 'Dimecres', 'Dijous', 
                                     'Divendres', 'Dissabte', 'Diumenge']
                        for day_num, day_name in enumerate(day_names):
                            cursor.execute("""
                                INSERT INTO weekly_defaults 
                                (day_of_week, day_name, status, lunch_start, lunch_end, dinner_start, dinner_end)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """, (day_num, day_name, 'full_day', '12:00:00', '15:00:00', '19:00:00', '22:30:00'))
                        
                        print("✅ Configuració setmanal inicialitzada correctament.")
                    else:
                        print("ℹ️ La taula weekly_defaults ja conté dades.")

                conn.commit()

        except Exception as e:
            print(f"❌ Error creant la taula weekly_defaults: {e}")
            traceback.print_exc()

    def get_all_defaults(self):
        """Retorna tots els horaris per defecte de la setmana"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT day_of_week, day_name, status, lunch_start, lunch_end, 
                               dinner_start, dinner_end
                        FROM weekly_defaults
                        ORDER BY day_of_week
                    """)
                    return [
                        {
                            'day_of_week': row[0],
                            'day_name': row[1],
                            'status': row[2],
                            'lunch_start': str(row[3]),
                            'lunch_end': str(row[4]),
                            'dinner_start': str(row[5]),
                            'dinner_end': str(row[6])
                        } for row in cursor.fetchall()
                    ]
        except Exception as e:
            print(f"❌ Error obtenint configuració setmanal: {e}")
            traceback.print_exc()
            return []

    def get_default_for_day(self, day_of_week):
        """Retorna els horaris per defecte d’un dia concret"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT status, lunch_start, lunch_end, dinner_start, dinner_end
                        FROM weekly_defaults
                        WHERE day_of_week = %s
                    """, (day_of_week,))
                    row = cursor.fetchone()
                    if row:
                        return {
                            'status': row[0],
                            'lunch_start': str(row[1]),
                            'lunch_end': str(row[2]),
                            'dinner_start': str(row[3]),
                            'dinner_end': str(row[4])
                        }
                    else:
                        # Retorn per defecte si no existeix
                        return {
                            'status': 'full_day',
                            'lunch_start': '12:00:00',
                            'lunch_end': '15:00:00',
                            'dinner_start': '19:00:00',
                            'dinner_end': '22:30:00'
                        }
        except Exception as e:
            print(f"❌ Error obtenint configuració del dia {day_of_week}: {e}")
            traceback.print_exc()
            return None

    def update_default(self, day_of_week, status, lunch_start=None, lunch_end=None, 
                       dinner_start=None, dinner_end=None):
        """
        Actualitza la configuració d’un dia i aplica els canvis a dies futurs sense notes.
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Actualitzar weekly_defaults
                    cursor.execute("""
                        UPDATE weekly_defaults
                        SET status=%s, lunch_start=%s, lunch_end=%s,
                            dinner_start=%s, dinner_end=%s, updated_at=CURRENT_TIMESTAMP
                        WHERE day_of_week=%s
                    """, (status, lunch_start, lunch_end, dinner_start, dinner_end, day_of_week))

                    # Aplicar a dies futurs d'opening_hours sense notes
                    today = datetime.now().date()
                    postgres_dow = day_of_week + 1  # PostgreSQL: 1=dilluns

                    cursor.execute("""
                        UPDATE opening_hours
                        SET status=%s, lunch_start=%s, lunch_end=%s,
                            dinner_start=%s, dinner_end=%s, updated_at=CURRENT_TIMESTAMP
                        WHERE date >= %s
                          AND EXTRACT(ISODOW FROM date) = %s
                          AND (notes IS NULL OR notes = '')
                    """, (status, lunch_start, lunch_end, dinner_start, dinner_end,
                          today.isoformat(), postgres_dow))

                    days_updated = cursor.rowcount
                    conn.commit()

                    print(f"✅ Dia {day_of_week} actualitzat correctament. Dies futurs modificats: {days_updated}")

                    return {'success': True, 'days_updated': days_updated}

        except Exception as e:
            print(f"❌ Error actualitzant configuració setmanal: {e}")
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
