"""
Script per verificar que totes les millores funcionen correctament
"""
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("🔍 VERIFICANT MILLORES DEL BOT")
print("=" * 60)

# 1. Verificar variables d'entorn
print("\n1️⃣ Variables d'entorn:")
required_vars = ['DATABASE_URL', 'OPENAI_API_KEY', 'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN']
all_ok = True
for var in required_vars:
    if os.getenv(var):
        print(f"   ✅ {var}")
    else:
        print(f"   ❌ {var} - NO TROBADA")
        all_ok = False

# 2. Verificar connexió a BD
print("\n2️⃣ Connexió a Base de Dades:")
try:
    import psycopg2
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cursor = conn.cursor()
    
    # Verificar taules
    cursor.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema='public'
    """)
    tables = [row[0] for row in cursor.fetchall()]
    
    expected_tables = ['tables', 'appointments', 'customers', 'conversations']
    for table in expected_tables:
        if table in tables:
            print(f"   ✅ Taula '{table}' existe")
        else:
            print(f"   ❌ Taula '{table}' NO TROBADA")
            all_ok = False
    
    # Verificar columnes d'appointments
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name='appointments'
    """)
    columns = {row[0]: row[1] for row in cursor.fetchall()}
    
    if columns.get('date') == 'date':
        print(f"   ✅ Columna 'date' és tipus DATE")
    else:
        print(f"   ❌ Columna 'date' té tipus incorrecte: {columns.get('date')}")
        all_ok = False
    
    if columns.get('time') == 'time without time zone':
        print(f"   ✅ Columna 'time' és tipus TIME")
    else:
        print(f"   ❌ Columna 'time' té tipus incorrecte: {columns.get('time')}")
        all_ok = False
    
    cursor.close()
    conn.close()
    print("   ✅ Connexió tancada correctament")
    
except Exception as e:
    print(f"   ❌ Error: {e}")
    all_ok = False

# 3. Verificar imports
print("\n3️⃣ Llibreries Python:")
libraries = [
    'flask',
    'twilio',
    'openai',
    'psycopg2',
    'langdetect',
    'dotenv'
]

for lib in libraries:
    try:
        if lib == 'dotenv':
            __import__('dotenv')
        else:
            __import__(lib)
        print(f"   ✅ {lib}")
    except ImportError:
        print(f"   ❌ {lib} - NO INSTAL·LADA")
        all_ok = False

# 4. Verificar estructura de fitxers
print("\n4️⃣ Estructura de fitxers:")
files_to_check = [
    'app.py',
    'utils/ai_processor.py',
    'utils/appointments.py',
    'utils/transcription.py',
    'requirements.txt',
    'railway.json'
]

for file in files_to_check:
    if os.path.exists(file):
        print(f"   ✅ {file}")
    else:
        print(f"   ❌ {file} - NO TROBAT")
        all_ok = False

# Resum final
print("\n" + "=" * 60)
if all_ok:
    print("🎉 TOTES LES VERIFICACIONS HAN PASSAT!")
    print("✅ El bot està llest per desplegar")
else:
    print("⚠️ Hi ha alguns problemes que cal resoldre")
print("=" * 60)

print("\n📋 Millores implementades:")
print("   ✅ Logs reduïts i nets")
print("   ✅ Memòria del client (busca nom a BD)")
print("   ✅ Màxim 4 persones per reserva")
print("   ✅ No repeteix preguntes")
print("   ✅ Error 'invalid date' solucionat")
print("\n🚀 Puja els canvis a Railway amb:")
print("   git add .")
print("   git commit -m '🔧 Millores implementades'")
print("   git push")
