import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

try:
    print("🔍 Intentando conectar a la base de datos...")
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    print("✅ ¡Conexión exitosa a PostgreSQL!")
    
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    db_version = cursor.fetchone()
    print(f"📊 Versión de PostgreSQL: {db_version[0]}")
    
    cursor.close()
    conn.close()
    print("🔌 Conexión cerrada correctamente")
    
except Exception as e:
    print(f"❌ Error conectando: {e}")