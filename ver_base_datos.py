"""
Script para ver datos de la base de datos
"""

from utils.appointments import AppointmentManager, ConversationManager
from datetime import datetime

# Inicializar
appointment_manager = AppointmentManager()
conversation_manager = ConversationManager()

print("=" * 60)
print("📊 ESTADO DE LA BASE DE DATOS")
print("=" * 60)

# Ver todas las reservas
try:
    conn = appointment_manager.get_connection()
    cursor = conn.cursor()
    
    # Contar reservas
    cursor.execute("SELECT COUNT(*) FROM appointments WHERE status = 'confirmed'")
    total_reservas = cursor.fetchone()[0]
    print(f"\n✅ Total de reservas confirmadas: {total_reservas}")
    
    # Ver reservas de hoy en adelante
    cursor.execute("""
        SELECT a.id, a.client_name, a.date, a.time, a.num_people, 
               t.table_number, a.status, a.phone
        FROM appointments a
        LEFT JOIN tables t ON a.table_id = t.id
        WHERE a.date >= CURRENT_DATE
        ORDER BY a.date, a.time
        LIMIT 10
    """)
    
    reservas = cursor.fetchall()
    
    if reservas:
        print("\n📅 PRÓXIMAS RESERVAS:")
        print("-" * 60)
        for r in reservas:
            apt_id, nombre, fecha, hora, personas, mesa, estado, phone = r
            print(f"ID {apt_id}: {nombre} - {fecha} {hora}")
            print(f"  👥 {personas} personas | 🪑 Mesa {mesa} | {estado}")
            print(f"  📱 {phone}")
            print("-" * 60)
    else:
        print("\n⚠️ No hay reservas futuras")
    
    # Ver clientes registrados
    cursor.execute("SELECT COUNT(*) FROM customers")
    total_clientes = cursor.fetchone()[0]
    print(f"\n👥 Total de clientes registrados: {total_clientes}")
    
    if total_clientes > 0:
        cursor.execute("""
            SELECT name, phone, last_visit
            FROM customers
            ORDER BY last_visit DESC
            LIMIT 5
        """)
        clientes = cursor.fetchall()
        print("\n👤 ÚLTIMOS CLIENTES:")
        print("-" * 60)
        for c in clientes:
            nombre, phone, ultima_visita = c
            print(f"{nombre} - {phone}")
            print(f"  Última visita: {ultima_visita}")
            print("-" * 60)
    
    # Ver ocupación de mesas
    cursor.execute("""
        SELECT 
            CASE WHEN capacity = 2 THEN 'Mesas de 2' ELSE 'Mesas de 4' END as tipo,
            COUNT(*) as total
        FROM tables
        GROUP BY capacity
    """)
    mesas_info = cursor.fetchall()
    print("\n🪑 CAPACIDAD DEL RESTAURANTE:")
    print("-" * 60)
    for tipo, total in mesas_info:
        print(f"{tipo}: {total}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ Consulta completada")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
