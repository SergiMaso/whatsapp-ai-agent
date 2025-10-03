"""
Script per inicialitzar la base de dades amb totes les taules necessàries
Executa això si les taules no es creen automàticament
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def init_database():
    """Crear totes les taules necessàries"""
    try:
        print("🔗 Connectant a la base de dades...")
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        cursor = conn.cursor()
        
        print("\n📋 Creant taules...")
        
        # 1. Taula de mesas
        print("   → Taula 'tables'...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tables (
                id SERIAL PRIMARY KEY,
                table_number INTEGER UNIQUE NOT NULL,
                capacity INTEGER NOT NULL,
                status VARCHAR(20) DEFAULT 'available'
            )
        """)
        
        # 2. Taula de reservas
        print("   → Taula 'appointments'...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(50) NOT NULL,
                client_name VARCHAR(100),
                date DATE NOT NULL,
                time TIME NOT NULL,
                num_people INTEGER NOT NULL,
                table_id INTEGER REFERENCES tables(id),
                language VARCHAR(10) DEFAULT 'es',
                status VARCHAR(20) DEFAULT 'confirmed',
                reminder_sent BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 3. Taula de clients
        print("   → Taula 'customers'...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                last_visit TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 4. Taula de conversacions
        print("   → Taula 'conversations'...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(50) NOT NULL,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        print("\n✅ Totes les taules creades!")
        
        # Inicialitzar mesas si no existeixen
        print("\n🪑 Inicialitzant mesas...")
        cursor.execute("SELECT COUNT(*) FROM tables")
        count = cursor.fetchone()[0]
        
        if count == 0:
            print("   → Creant 20 mesas de 4 persones (mesas 1-20)...")
            for i in range(1, 21):
                cursor.execute("""
                    INSERT INTO tables (table_number, capacity) 
                    VALUES (%s, 4)
                """, (i,))
            
            print("   → Creant 8 mesas de 2 persones (mesas 21-28)...")
            for i in range(21, 29):
                cursor.execute("""
                    INSERT INTO tables (table_number, capacity) 
                    VALUES (%s, 2)
                """, (i,))
            
            conn.commit()
            print("\n✅ 28 mesas inicialitzades!")
        else:
            print(f"   ℹ️  Ja existeixen {count} mesas")
        
        # Mostrar resum
        print("\n" + "="*60)
        print("📊 RESUM DE LA BASE DE DADES")
        print("="*60)
        
        cursor.execute("SELECT COUNT(*) FROM tables")
        print(f"   🪑 Mesas: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM appointments WHERE status='confirmed'")
        print(f"   📅 Reserves actives: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM customers")
        print(f"   👥 Clients registrats: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM conversations")
        print(f"   💬 Missatges guardats: {cursor.fetchone()[0]}")
        
        print("="*60)
        
        cursor.close()
        conn.close()
        print("\n✅ Base de dades inicialitzada correctament!")
        print("🚀 El bot està llest per funcionar!")
        
    except Exception as e:
        print(f"\n❌ Error inicialitzant la base de dades:")
        print(f"   {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*60)
    print("🗄️  INICIALITZACIÓ DE LA BASE DE DADES")
    print("="*60)
    init_database()
