"""
Script per migrar la base de dades:
1. Eliminar columna 'language' d'appointments (no serveix)
2. Assegurar que 'time' és tipus TIME correcte
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def migrate_database():
    """Migrar la base de dades"""
    try:
        print("🔗 Connectant a la base de dades...")
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        cursor = conn.cursor()
        
        # 1. Verificar si existeix la columna language
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='appointments' AND column_name='language'
        """)
        
        if cursor.fetchone():
            print("🗑️  Eliminant columna 'language' d'appointments...")
            cursor.execute("ALTER TABLE appointments DROP COLUMN IF EXISTS language")
            conn.commit()
            print("✅ Columna 'language' eliminada")
        else:
            print("ℹ️  La columna 'language' ja no existeix")
        
        # 2. Verificar tipus de columna time
        cursor.execute("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name='appointments' AND column_name='time'
        """)
        
        result = cursor.fetchone()
        if result:
            current_type = result[0]
            print(f"ℹ️  Tipus actual de 'time': {current_type}")
            
            if current_type != 'time without time zone':
                print("⚠️  El tipus no és correcte, cal arreglar-ho manualment")
                print("   Executa: ALTER TABLE appointments ALTER COLUMN time TYPE TIME USING time::TIME;")
        
        # 3. Mostrar resum
        print("\n" + "="*60)
        print("📊 RESUM DE LA BASE DE DADES")
        print("="*60)
        
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name='appointments'
            ORDER BY ordinal_position
        """)
        
        print("\n📋 Columnes de 'appointments':")
        for col_name, col_type in cursor.fetchall():
            print(f"   • {col_name}: {col_type}")
        
        cursor.execute("SELECT COUNT(*) FROM appointments WHERE status='confirmed'")
        print(f"\n📅 Reserves actives: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM customers")
        print(f"👥 Clients registrats: {cursor.fetchone()[0]}")
        
        print("="*60)
        
        cursor.close()
        conn.close()
        print("\n✅ Migració completada!")
        
    except Exception as e:
        print(f"\n❌ Error durant la migració:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*60)
    print("🔧 MIGRACIÓ DE LA BASE DE DADES")
    print("="*60)
    migrate_database()
