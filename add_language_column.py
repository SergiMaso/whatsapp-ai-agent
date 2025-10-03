"""
Script per afegir columna language a customers
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def add_language_column():
    """Afegir columna language a customers"""
    try:
        print("🔗 Connectant a la base de dades...")
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        cursor = conn.cursor()
        
        # Verificar si existeix la columna language
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='customers' AND column_name='language'
        """)
        
        if cursor.fetchone():
            print("ℹ️  La columna 'language' ja existeix")
        else:
            print("➕ Afegint columna 'language' a customers...")
            cursor.execute("ALTER TABLE customers ADD COLUMN language VARCHAR(10) DEFAULT 'es'")
            conn.commit()
            print("✅ Columna 'language' afegida correctament")
        
        # Mostrar estructura actual
        cursor.execute("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns 
            WHERE table_name='customers'
            ORDER BY ordinal_position
        """)
        
        print("\n📋 Estructura de 'customers':")
        for col_name, col_type, col_default in cursor.fetchall():
            default_str = f" (default: {col_default})" if col_default else ""
            print(f"   • {col_name}: {col_type}{default_str}")
        
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
    print("🌍 AFEGIR COLUMNA LANGUAGE A CUSTOMERS")
    print("="*60)
    add_language_column()
