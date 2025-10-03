"""
Migració: date+time → start_time+end_time (TIMESTAMP)
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def migrate_to_start_end():
    try:
        print("Connectant a la BD...")
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='appointments'
        """)
        columns = [row[0] for row in cursor.fetchall()]
        print(f"Columnes actuals: {columns}")
        
        # Afegir start_time
        if 'start_time' not in columns:
            print("\n1. Afegint columna 'start_time'...")
            cursor.execute("ALTER TABLE appointments ADD COLUMN start_time TIMESTAMP")
            
            if 'date' in columns and 'time' in columns:
                cursor.execute("""
                    UPDATE appointments 
                    SET start_time = (date::TEXT || ' ' || time::TEXT)::TIMESTAMP
                """)
                print("   Migrades dades: date+time -> start_time")
            conn.commit()
        
        # Afegir end_time
        if 'end_time' not in columns:
            print("\n2. Afegint columna 'end_time'...")
            cursor.execute("ALTER TABLE appointments ADD COLUMN end_time TIMESTAMP")
            
            cursor.execute("""
                UPDATE appointments 
                SET end_time = start_time + INTERVAL '2 hours'
                WHERE start_time IS NOT NULL
            """)
            print("   end_time = start_time + 2h")
            conn.commit()
        
        # Fer NOT NULL
        cursor.execute("SELECT COUNT(*) FROM appointments WHERE start_time IS NULL")
        if cursor.fetchone()[0] == 0:
            print("\n3. Fent start_time/end_time NOT NULL...")
            cursor.execute("ALTER TABLE appointments ALTER COLUMN start_time SET NOT NULL")
            cursor.execute("ALTER TABLE appointments ALTER COLUMN end_time SET NOT NULL")
            conn.commit()
        
        # Eliminar date i time
        if 'date' in columns:
            print("\n4. Eliminant columnes 'date' i 'time'...")
            cursor.execute("ALTER TABLE appointments DROP COLUMN IF EXISTS date")
            cursor.execute("ALTER TABLE appointments DROP COLUMN IF EXISTS time")
            conn.commit()
            print("   date i time eliminades")
        
        # Verificar language
        if 'language' not in columns:
            print("\n5. Afegint columna 'language'...")
            cursor.execute("ALTER TABLE appointments ADD COLUMN language VARCHAR(10)")
            conn.commit()
        
        # Estructura final
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name='appointments'
            ORDER BY ordinal_position
        """)
        print("\nEstructura FINAL:")
        for col_name, col_type in cursor.fetchall():
            print(f"   • {col_name}: {col_type}")
        
        cursor.close()
        conn.close()
        print("\nMigracio completada!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*60)
    print("MIGRACIO: date+time -> start_time+end_time")
    print("="*60)
    migrate_to_start_end()
