# 📊 ANÀLISI DE RENDIMENT - WhatsApp AI Agent

## 🔴 PROBLEMES CRÍTICS IDENTIFICATS

### 1. **N+1 PROBLEM en `check_availability()`** ⚠️ CRÍTIC

**Ubicació:** `utils/appointments.py:660-773`

**Problema:**
```python
# Línia 728-749: Bucle que crida find_combined_tables per CADA slot
for check_minutes in range(slot_start_minutes, slot_end_minutes - 60, 30):
    # ... crea check_datetime ...
    tables_result = self.find_combined_tables(check_datetime, end_datetime, num_people)
```

**Impacte:**
- Dinar (12:00-15:00) = 6 slots de 30 min
- Sopar (19:00-22:30) = 7 slots de 30 min
- **TOTAL: 13 crides a `find_combined_tables`**
- Cada crida fa **3 queries SQL** (occupied, no_pairing, with_pairing)
- **RESULTAT: 39 queries SQL per consultar disponibilitat d'un sol dia!**

**Temps estimat:** ~2-4 segons

**Solució:**
1. **Obtenir TOTES les reserves del dia amb UNA SOLA query**
2. **Calcular disponibilitat en memòria** per cada slot
3. **Reduir de 39 queries → 2 queries** (reserves + taules)

**Codi optimitzat:**
```python
def check_availability_optimized(self, date, num_people):
    # 1. Query única: obtenir TOTES les reserves del dia
    cursor.execute("""
        SELECT table_id, start_time, end_time
        FROM appointments
        WHERE date = %s AND status = 'confirmed'
    """, (date,))
    appointments = cursor.fetchall()

    # 2. Query única: obtenir TOTES les taules
    cursor.execute("""
        SELECT id, capacity, pairing FROM tables
        WHERE status = 'available'
    """)
    all_tables = cursor.fetchall()

    # 3. Calcular disponibilitat EN MEMÒRIA per cada slot
    available_slots = []
    for check_time in time_slots:
        occupied_table_ids = {
            apt[0] for apt in appointments
            if apt[1] <= check_time < apt[2]
        }

        # Algoritme de matching sense queries
        available = find_table_in_memory(all_tables, occupied_table_ids, num_people)
        available_slots.append({'time': check_time, 'available': available})

    return available_slots
```

**Millora esperada:** De 2-4s → **0.2-0.5s** (8-10x més ràpid)

---

### 2. **Connection Overhead en `find_combined_tables()`** 🔴

**Ubicació:** `utils/appointments.py:276-415`

**Problema:**
```python
def find_combined_tables(self, start_time, end_time, num_people):
    conn = self.get_connection()  # Nova connexió CADA vegada
    cursor = conn.cursor()

    # 3 queries separades...
    cursor.execute(...)  # Query 1: occupied
    cursor.execute(...)  # Query 2: no_pairing
    cursor.execute(...)  # Query 3: with_pairing

    cursor.close()
    conn.close()  # Tanca connexió
```

**Impacte:**
- Obre/tanca connexió PostgreSQL per cada crida
- Overhead de connexió: ~50-100ms per connexió
- Si es crida 13 vegades → **650-1300ms només en overhead**

**Solució:**
1. **Connection Pooling** amb `psycopg2.pool`
2. **Combinar les 3 queries en 1** amb JOIN/UNION
3. **Passar connexió com a paràmetre** per reusar-la

**Implementació:**
```python
from psycopg2 import pool

class AppointmentManager:
    def __init__(self):
        # Connection pool (reutilitza connexions)
        self.connection_pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=os.getenv('DATABASE_URL')
        )

    def get_connection(self):
        return self.connection_pool.getconn()

    def return_connection(self, conn):
        self.connection_pool.putconn(conn)
```

**Millora esperada:** -50% temps en operacions BD

---

### 3. **Clean Old Messages a cada save** 🟡

**Ubicació:** `utils/appointments.py:1451-1463`

**Problema:**
```python
def save_message(self, phone, role, content):
    self.clean_old_messages()  # CRIDA CADA VEGADA!

    conn = self.get_connection()
    cursor.execute("INSERT INTO conversations ...")
```

**Impacte:**
- Query DELETE innecessària a cada missatge
- Si 10 missatges/conversa → 10 DELETE queries
- Overhead: ~50-100ms per missatge

**Solució:**
1. **Cridar clean_old_messages() NOMÉS 1 vegada per conversa** (primer missatge)
2. **O moure a tasca programada** (APScheduler cada hora)

```python
def save_message(self, phone, role, content):
    # Només netejar al primer missatge de la conversa
    if role == 'user':
        message_count = self.get_message_count(phone)
        if message_count == 0:
            self.clean_old_messages()

    # Continuar amb save...
```

**Millora esperada:** -10% temps de resposta

---

### 4. **OpenAI API Latency** 🟠

**Ubicació:** `utils/ai_processor.py:324-421`

**Problema:**
```python
response = client.chat.completions.create(
    model="gpt-5-mini",
    messages=messages,  # Envia TOT l'historial
    tools=[...]
)
# Espera resposta completa (blocking)
```

**Impacte:**
- Latència de xarxa: **2-5 segons**
- L'usuari no veu cap indicació de progrés
- Envia tot l'historial (pot ser innecessari)

**Solució:**
1. **Streaming response** (typing indicator)
2. **Limitar historial** a últims 5 missatges rellevants
3. **Parallel processing** si cal múltiples crides

```python
response = client.chat.completions.create(
    model="gpt-5-mini",
    messages=messages[-5:],  # Només últims 5 missatges
    tools=[...],
    stream=True  # Streaming!
)

# Enviar "typing..." a WhatsApp
send_typing_indicator(phone)

# Processar resposta chunk per chunk
for chunk in response:
    # Actualitzar resposta en temps real
    ...
```

**Millora esperada:** Percepció de -30% temps d'espera

---

### 5. **Falta d'índexs a la Base de Dades** 🔴

**Problema:**
Les queries no tenen índexs adequats, especialment:

```sql
-- Query freqüent SENSE índex:
SELECT table_id FROM appointments
WHERE status = 'confirmed'
AND ((start_time < %s AND end_time > %s)
     OR (start_time >= %s AND start_time < %s))
```

**Solució:**
```sql
-- Crear índexs compostos
CREATE INDEX idx_appointments_status_times
ON appointments(status, start_time, end_time);

CREATE INDEX idx_appointments_date_status
ON appointments(date, status);

CREATE INDEX idx_tables_status_capacity
ON tables(status, capacity);

CREATE INDEX idx_conversations_phone_created
ON conversations(phone, created_at DESC);
```

**Millora esperada:** -40% temps queries

---

### 6. **Timezone conversion repetida** 🟡

**Ubicació:** Multiple llocs (appointments.py, ai_processor.py)

**Problema:**
```python
# Creat múltiples vegades:
barcelona_tz = pytz.timezone('Europe/Madrid')
```

**Solució:**
```python
# Crear UNA SOLA VEGADA com a constant de classe
class AppointmentManager:
    BARCELONA_TZ = pytz.timezone('Europe/Madrid')

    def method(self):
        now = datetime.now(self.BARCELONA_TZ)
```

---

## 📊 RESUM D'OPTIMITZACIONS

| # | Problema | Impacte | Dificultat | Millora |
|---|----------|---------|------------|---------|
| 1 | N+1 queries en check_availability | CRÍTIC | Mitjana | 8-10x |
| 2 | Connection overhead | ALT | Fàcil | 2x |
| 3 | Clean messages cada save | MITJÀ | Fàcil | 1.1x |
| 4 | OpenAI latency | ALT | Mitjana | 1.3x percepció |
| 5 | Falta índexs BD | ALT | Fàcil | 1.5x |
| 6 | Timezone repetit | BAIX | Trivial | 1.05x |

**MILLORA TOTAL ESPERADA:** **10-15x més ràpid** en consultes de disponibilitat

---

## 🚀 PLA D'IMPLEMENTACIÓ RECOMANAT

### Fase 1: Quick Wins (1-2 hores)
1. ✅ Afegir índexs a PostgreSQL
2. ✅ Implementar Connection Pooling
3. ✅ Moure clean_old_messages a tasca programada
4. ✅ Timezone com a constant

**Resultat:** De 10-15s → **5-7s**

### Fase 2: Optimitzacions Crítiques (3-4 hores)
1. ✅ Reescriure `check_availability()` amb batch queries
2. ✅ Optimitzar `find_combined_tables()` amb query única
3. ✅ Implementar streaming d'OpenAI

**Resultat:** De 5-7s → **1-2s**

### Fase 3: Cache & Polish (2-3 hores)
1. ✅ Redis cache per disponibilitat (TTL 5 min)
2. ✅ Pre-calcular slots disponibles per dies propers
3. ✅ Websocket per actualitzacions en temps real

**Resultat:** De 1-2s → **<0.5s**

---

## 📈 MÈTRIQUES ACTUALS vs OPTIMITZADES

| Operació | Actual | Optimitzat | Millora |
|----------|--------|------------|---------|
| Consultar disponibilitat | 2-4s | 0.2-0.5s | **8-10x** |
| Crear reserva | 1-2s | 0.5-1s | **2x** |
| Processar missatge IA | 3-5s | 2-3s | **1.5x** |
| **TOTAL resposta bot** | **10-15s** | **2-4s** | **4-5x** |

---

## 🔧 CODI D'EXEMPLE: check_availability_optimized()

```python
def check_availability_optimized(self, date, num_people):
    """
    Versió optimitzada amb UNA SOLA consulta per totes les reserves
    """
    try:
        conn = self.get_connection()
        cursor = conn.cursor()

        # QUERY 1: Obtenir TOTES les reserves del dia (UNA SOLA VEZ)
        cursor.execute("""
            SELECT table_id, start_time, end_time
            FROM appointments
            WHERE date = %s AND status = 'confirmed'
        """, (date,))
        daily_appointments = cursor.fetchall()

        # QUERY 2: Obtenir TOTES les taules (UNA SOLA VEZ)
        cursor.execute("""
            SELECT id, table_number, capacity, pairing
            FROM tables
            WHERE status = 'available'
        """)
        all_tables = cursor.fetchall()

        cursor.close()
        self.return_connection(conn)

        # Crear mapa de taules per lookup ràpid
        tables_map = {t[0]: t for t in all_tables}

        # Calcular disponibilitat EN MEMÒRIA per cada slot
        available_slots = []

        for slot_time in self._generate_time_slots(date):
            # Obtenir taules ocupades en aquest slot (EN MEMÒRIA)
            occupied_ids = {
                apt[0] for apt in daily_appointments
                if apt[1] <= slot_time < apt[2]
            }

            # Trobar taula disponible EN MEMÒRIA (sense queries)
            available = self._find_table_in_memory(
                all_tables,
                occupied_ids,
                num_people
            )

            available_slots.append({
                'time': slot_time.strftime('%H:%M'),
                'available': available is not None
            })

        return {
            'available': any(s['available'] for s in available_slots),
            'slots': available_slots
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        return {'available': False, 'slots': []}

def _find_table_in_memory(self, all_tables, occupied_ids, num_people):
    """
    Troba taula disponible EN MEMÒRIA (sense queries)
    Replica lògica de find_combined_tables però sense BD
    """
    available_tables = [t for t in all_tables if t[0] not in occupied_ids]

    # 1. Buscar taula sense pairing amb capacitat exacta
    for table in available_tables:
        if table[3] is None and table[2] == num_people:
            return table

    # 2. Buscar taula sense pairing amb capacitat suficient
    for table in available_tables:
        if table[3] is None and table[2] >= num_people:
            return table

    # 3. Buscar taules amb pairing...
    # ... (continuar amb lògica similar)

    return None
```

---

## 💡 ALTRES RECOMANACIONS

### Monitoring
1. Afegir **timing logs** per cada operació crítica
2. Implementar **APM** (Application Performance Monitoring)
3. Alertes per temps de resposta > 5s

### Arquitectura
1. Considerar **microserveis** per separar bot de API
2. **Message Queue** (Redis/RabbitMQ) per processar missatges async
3. **Serverless functions** per webhooks de Twilio

### Escalabilitat
1. **Horizontal scaling** amb múltiples workers
2. **Read replicas** de PostgreSQL per queries pesades
3. **CDN** per media (ja tens Cloudinary ✅)

---

**Data d'anàlisi:** 2025-11-05
**Versió del codi:** claude/fix-reservations-bot-calls-011CUpa9sLN1XvVNks47acp4
