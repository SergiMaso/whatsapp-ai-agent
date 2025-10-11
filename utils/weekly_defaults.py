"""
Gestió de configuració setmanal per defecte per horaris d'obertura
"""
import psycopg2
import os
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
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"❌ Error creant taula weekly_defaults: {e}")
    
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
                # Retornar configuració per defecte si no existeix
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
        I aplicar als dies futurs que NO tinguin configuració customitzada
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
            
            # Aplicar canvis als dies futurs d'opening_hours que NO tinguin notes (no customitzats)
            # Només futurs, no passat
            from datetime import datetime
            today = datetime.now().date()
            
            # Trobar tots els dies futurs d'aquest day_of_week sense notes
            # Convertir day_of_week: Python usa 0=dilluns, PostgreSQL EXTRACT(ISODOW) usa 1=dilluns
            postgres_dow = day_of_week + 1  # 0->1 (dilluns), 1->2 (dimarts), etc.
            
            cursor.execute("""
                UPDATE opening_hours
                SET status = %s, lunch_start = %s, lunch_end = %s,
                    dinner_start = %s, dinner_end = %s, updated_at = CURRENT_TIMESTAMP
                WHERE date >= %s
                  AND EXTRACT(ISODOW FROM date) = %s
                  AND (notes IS NULL OR notes = '')
            """, (status, lunch_start, lunch_end, dinner_start, dinner_end, 
                  today.isoformat(), postgres_dow))  # ISODOW: 1=dilluns, 7=diumenge
            
            days_updated = cursor.rowcount
            
            print(f"✅ Configuració setmanal actualitzada: {day_of_week}")
            print(f"   - Status: {status}")
            print(f"   - Dies futurs actualitzats: {days_updated}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                'success': True,
                'days_updated': days_updated,
                'message': f'Configuració actualitzada i aplicada a {days_updated} dies futurs'
            }
        
        except Exception as e:
            print(f"❌ Error actualitzant configuració setmanal: {e}")
            return {
                'success': False,
                'error': str(e)
            }
