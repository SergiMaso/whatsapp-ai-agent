"""
Migració: date+time → start+end (TIMESTAMP)
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def migrate_to_start_end():
    try:
        print("🔗 Connectant a la BD...")
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        cursor = conn.cursor()
        
        # Verificar columnes actuals
        cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='appointments'
        """)
        columns = [row[0] for row in cursor.fetchall()]
        print(f"📋 Columnes actuals: {columns}")
        
        # Afegir start si no existeix
        if 'start' not in columns:
            print("\n1️⃣ Afegint columna 'start'...")
            cursor.execute("ALTER TABLE appointments ADD COLUMN start TIMESTAMP")
            
            if 'date' in columns and 'time' in columns:
                cursor.execute("""
                    UPDATE appointments 
                    SET start = (date::TEXT || ' ' || time::TEXT)::TIMESTAMP
                """)
                print("   ✅ Migrades dades: date+time → start")
            conn.commit()
        
        # Afegir end si no existeix
        if 'end' not in columns:
            print("\n2️⃣ Afegint columna 'end'...")
            cursor.execute("ALTER TABLE appointments ADD COLUMN end TIMESTAMP")
            
            # end = start + 2 hores per defecte
            cursor.execute("""
                UPDATE appointments 
                SET end = start + INTERVAL '2 hours'
                WHERE start IS NOT NULL
            """)
            print("   ✅ end = start + 2h")
            conn.commit()
        
        # Fer NOT NULL
        cursor.execute("SELECT COUNT(*) FROM appointments WHERE start IS NULL")
        if cursor.fetchone()[0] == 0:
            print("\n3️⃣ Fent start/end NOT NULL...")
            cursor.execute("ALTER TABLE appointments ALTER COLUMN start SET NOT NULL")
            cursor.execute("ALTER TABLE appointments ALTER COLUMN end SET NOT NULL")
            conn.commit()
            print("   ✅ start/end són NOT NULL")
        
        # Eliminar date i time
        if 'date' in columns and 'start' in columns:
            print("\n4️⃣ Eliminant columnes 'date' i 'time'...")
            cursor.execute("ALTER TABLE appointments DROP COLUMN date")
            cursor.execute("ALTER TABLE appointments DROP COLUMN time")
            conn.commit()
            print("   ✅ date i time eliminades")
        
        # Verificar language existeix
        if 'language' not in columns:
            print("\n5️⃣ Afegint columna 'language'...")
            cursor.execute("ALTER TABLE appointments ADD COLUMN language VARCHAR(10)")
            conn.commit()
            print("   ✅ language afegida")
        
        # Mostrar estructura final
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name='appointments'
            ORDER BY ordinal_position
        """)
        print("\n📋 Estructura FINAL:")
        for col_name, col_type in cursor.fetchall():
            print(f"   • {col_name}: {col_type}")
        
        cursor.close()
        conn.close()
        print("\n✅ Migració completada!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*60)
    print("🔄 MIGRACIÓ: date+time → start+end")
    print("="*60)
    migrate_to_start_end()
