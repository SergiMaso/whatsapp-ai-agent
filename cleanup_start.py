"""
Neteja final: eliminar columna 'start' antiga
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def cleanup_old_columns():
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
        
        # Eliminar columna 'start' antiga si existeix
        if 'start' in columns:
            print("\nEliminant columna 'start' antiga...")
            cursor.execute("ALTER TABLE appointments DROP COLUMN start")
            conn.commit()
            print("   Columna 'start' eliminada")
        
        # Verificar estructura final
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
        print("\nNeteja completada!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*60)
    print("NETEJA: Eliminar columna 'start' antiga")
    print("="*60)
    cleanup_old_columns()
