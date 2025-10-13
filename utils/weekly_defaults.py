"""
Gestió de configuració setmanal per defecte per horaris d'obertura
ACTUALITZAT: Ara inicialitza opening_hours amb 3 mesos per endavant
"""
import psycopg2
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

class WeeklyDefaultsManager:
    """
    Gestiona els horaris per defecte per cada dia de la setmana
    """
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.ensure_table_exists()
    
    def get_connection(self):
        return psycopg2.connect(self.database_url)
    
    def ensure_table_exists(self):
        """Crear taula weekly_defaults si no existeix"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Crear taula weekly_defaults
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS weekly_defaults (
                    id SERIAL PRIMARY KEY,
                    day_of_week INTEGER UNIQUE NOT NULL,
                    day_name VARCHAR(20) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'full_day',
                    lunch_start TIME DEFAULT '12:00',
                    lunch_end TIME DEFAULT '15:00',
                    dinner_start TIME DEFAULT '19:00',
                    dinner_end TIME DEFAULT '22:30',
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Inicialitzar amb valors per defecte si està buida
            cursor.execute("SELECT COUNT(*) FROM weekly_defaults")
            if cursor.fetchone()[0] == 0:
                day_names = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                for day_num, day_name in enumerate(day_names):
                    cursor.execute("""
                        INSERT INTO weekly_defaults 
                        (day_of_week, day_name, status, lunch_start, lunch_end, dinner_start, dinner_end)
                        VALUES (%s, %s, 'full_day', '12:00', '15:00', '19:00', '22:30')
                    """, (day_num, day_name))
                
                print("✅ Configuración semanal por defecto inicializada")
                conn.commit()
            
            # IMPORTANT: Afegir columna is_custom a opening_hours si no existeix
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name='opening_hours' AND column_name='is_custom'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE opening_hours ADD COLUMN is_custom BOOLEAN DEFAULT FALSE")
                print("✅ Columna is_custom afegida a opening_hours")
                conn.commit()
            
            # Generar opening_hours per 3 mesos si està buit
            cursor.execute("SELECT COUNT(*) FROM opening_hours")
            if cursor.fetchone()[0] == 0:
                self._generate_opening_hours_3_months(cursor)
                print("✅ Opening hours generat per 3 mesos")
                conn.commit()
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"❌ Error creant taula weekly_defaults: {e}")
            import traceback
            traceback.print_exc()
    
    def _generate_opening_hours_3_months(self, cursor):
        """
        Generar opening_hours per als propers 3 mesos basant-se en weekly_defaults
        """
        try:
            today = datetime.now().date()
            end_date = today + timedelta(days=90)  # 3 mesos
            
            # Obtenir tots els defaults
            cursor.execute("""
                SELECT day_of_week, status, lunch_start, lunch_end, dinner_start, dinner_end
                FROM weekly_defaults
                ORDER BY day_of_week
            """)
            defaults = {row[0]: row[1:] for row in cursor.fetchall()}
            
            current_date = today
            count = 0
            
            while current_date <= end_date:
                day_of_week = current_date.weekday()  # 0=dilluns, 6=diumenge
                
                if day_of_week in defaults:
                    status, lunch_start, lunch_end, dinner_start, dinner_end = defaults[day_of_week]
                    
                    cursor.execute("""
                        INSERT INTO opening_hours 
                        (date, status, lunch_start, lunch_end, dinner_start, dinner_end, is_custom)
                        VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                        ON CONFLICT (date) DO NOTHING
                    """, (current_date, status, lunch_start, lunch_end, dinner_start, dinner_end))
                    
                    count += 1
                
                current_date += timedelta(days=1)
            
            print(f"📅 Generat opening_hours per {count} dies")
            
        except Exception as e:
            print(f"❌ Error generant opening_hours: {e}")
            raise
    
    def generate_next_month(self):
        """
        Generar opening_hours pel mes següent
        (Executar automàticament cada mes o manualment)
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Trobar l'última data a opening_hours
            cursor.execute("SELECT MAX(date) FROM opening_hours")
            last_date = cursor.fetchone()[0]
            
            if not last_date:
                last_date = datetime.now().date()
            
            # Generar el mes següent
            start_date = last_date + timedelta(days=1)
            end_date = start_date + timedelta(days=30)
            
            # Obtenir defaults
            cursor.execute("""
                SELECT day_of_week, status, lunch_start, lunch_end, dinner_start, dinner_end
                FROM weekly_defaults
                ORDER BY day_of_week
            """)
            defaults = {row[0]: row[1:] for row in cursor.fetchall()}
            
            current_date = start_date
            count = 0
            
            while current_date <= end_date:
                day_of_week = current_date.weekday()
                
                if day_of_week in defaults:
                    status, lunch_start, lunch_end, dinner_start, dinner_end = defaults[day_of_week]
                    
                    cursor.execute("""
                        INSERT INTO opening_hours 
                        (date, status, lunch_start, lunch_end, dinner_start, dinner_end, is_custom)
                        VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                        ON CONFLICT (date) DO NOTHING
                    """, (current_date, status, lunch_start, lunch_end, dinner_start, dinner_end))
                    
                    count += 1
                
                current_date += timedelta(days=1)
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"✅ Generat {count} dies addicionals")
            return count
            
        except Exception as e:
            print(f"❌ Error generant mes següent: {e}")
            return 0
    
    def get_all_defaults(self):
        """Obtenir configuració per defecte per tots els dies"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT day_of_week, day_name, status, lunch_start, lunch_end, 
                       dinner_start, dinner_end
                FROM weekly_defaults
                ORDER BY day_of_week
            """)
            
            defaults = []
            for row in cursor.fetchall():
                defaults.append({
                    'day_of_week': row[0],
                    'day_name': row[1],
                    'status': row[2],
                    'lunch_start': str(row[3]) if row[3] else None,
                    'lunch_end': str(row[4]) if row[4] else None,
                    'dinner_start': str(row[5]) if row[5] else None,
                    'dinner_end': str(row[6]) if row[6] else None
                })
            
            cursor.close()
            conn.close()
            
            return defaults
        
        except Exception as e:
            print(f"❌ Error obtenint configuració setmanal: {e}")
            return []
    
    def get_default_for_day(self, day_of_week):
        """Obtenir configuració per defecte d'un dia específic"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT status, lunch_start, lunch_end, dinner_start, dinner_end
                FROM weekly_defaults
                WHERE day_of_week = %s
            """, (day_of_week,))
            
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                return {
                    'status': row[0],
                    'lunch_start': str(row[1]) if row[1] else None,
                    'lunch_end': str(row[2]) if row[2] else None,
                    'dinner_start': str(row[3]) if row[3] else None,
                    'dinner_end': str(row[4]) if row[4] else None
                }
            else:
                return {
                    'status': 'full_day',
                    'lunch_start': '12:00',
                    'lunch_end': '15:00',
                    'dinner_start': '19:00',
                    'dinner_end': '22:30'
                }
        
        except Exception as e:
            print(f"❌ Error obtenint configuració del dia: {e}")
            return None
    
    def update_default(self, day_of_week, status, lunch_start=None, lunch_end=None, 
                      dinner_start=None, dinner_end=None):
        """
        Actualitzar configuració per defecte d'un dia de la setmana
        I aplicar als dies futurs que NO siguin personalitzats (is_custom=FALSE)
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Actualitzar weekly_defaults
            cursor.execute("""
                UPDATE weekly_defaults
                SET status = %s, lunch_start = %s, lunch_end = %s, 
                    dinner_start = %s, dinner_end = %s, updated_at = CURRENT_TIMESTAMP
                WHERE day_of_week = %s
            """, (status, lunch_start, lunch_end, dinner_start, dinner_end, day_of_week))
            
            # Convertir day_of_week: Python usa 0=dilluns, PostgreSQL ISODOW usa 1=dilluns
            postgres_dow = day_of_week + 1  # 0->1, 1->2, ..., 6->7
            today = datetime.now().date()
            
            # Comptar quants dies personalitzats NO s'actualitzaran
            cursor.execute("""
                SELECT COUNT(*)
                FROM opening_hours
                WHERE date >= %s
                  AND EXTRACT(ISODOW FROM date) = %s
                  AND is_custom = TRUE
            """, (today, postgres_dow))
            
            custom_count = cursor.fetchone()[0]
            
            # Aplicar canvis als dies futurs NO personalitzats
            cursor.execute("""
                UPDATE opening_hours
                SET status = %s, lunch_start = %s, lunch_end = %s,
                    dinner_start = %s, dinner_end = %s, updated_at = CURRENT_TIMESTAMP
                WHERE date >= %s
                  AND EXTRACT(ISODOW FROM date) = %s
                  AND is_custom = FALSE
            """, (status, lunch_start, lunch_end, dinner_start, dinner_end, 
                  today, postgres_dow))
            
            days_updated = cursor.rowcount
            
            day_names = ['Dilluns', 'Dimarts', 'Dimecres', 'Dijous', 'Divendres', 'Dissabte', 'Diumenge']
            day_name = day_names[day_of_week]
            
            print(f"✅ Configuració setmanal actualitzada: {day_name}")
            print(f"   - Status: {status}")
            print(f"   - Dies futurs actualitzats: {days_updated}")
            if custom_count > 0:
                print(f"   ⚠️  Dies personalitzats NO afectats: {custom_count}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            message = f'Configuració actualitzada i aplicada a {days_updated} dies futurs'
            if custom_count > 0:
                message += f'. {custom_count} dies personalitzats no han estat afectats'
            
            return {
                'success': True,
                'days_updated': days_updated,
                'days_custom': custom_count,
                'message': message
            }
        
        except Exception as e:
            print(f"❌ Error actualitzant configuració setmanal: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
