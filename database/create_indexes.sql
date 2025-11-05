-- ============================================================
-- ÍNDEXS PER OPTIMITZACIÓ DE RENDIMENT
-- WhatsApp AI Agent - Restaurant Booking System
-- ============================================================

-- 1. APPOINTMENTS - Índexs per queries de disponibilitat
-- Millora queries de find_combined_tables i check_availability
CREATE INDEX IF NOT EXISTS idx_appointments_status_times
ON appointments(status, start_time, end_time)
WHERE status = 'confirmed';

CREATE INDEX IF NOT EXISTS idx_appointments_date_status
ON appointments(date, status)
WHERE status = 'confirmed';

CREATE INDEX IF NOT EXISTS idx_appointments_table_time
ON appointments(table_id, start_time, end_time)
WHERE status = 'confirmed';

-- 2. TABLES - Índexs per buscar taules disponibles
CREATE INDEX IF NOT EXISTS idx_tables_status_capacity
ON tables(status, capacity)
WHERE status = 'available';

CREATE INDEX IF NOT EXISTS idx_tables_pairing
ON tables(pairing)
WHERE pairing IS NOT NULL;

-- 3. CONVERSATIONS - Índex per historial de conversa
CREATE INDEX IF NOT EXISTS idx_conversations_phone_created
ON conversations(phone, created_at DESC);

-- Índex per clean_old_messages
CREATE INDEX IF NOT EXISTS idx_conversations_created_at
ON conversations(created_at)
WHERE created_at < NOW() - INTERVAL '15 days';

-- 4. CUSTOMERS - Índexs per lookup ràpid
CREATE INDEX IF NOT EXISTS idx_customers_phone
ON customers(phone);

CREATE INDEX IF NOT EXISTS idx_customers_language
ON customers(language);

-- 5. OPENING_HOURS - Índex per queries de disponibilitat
CREATE INDEX IF NOT EXISTS idx_opening_hours_date
ON opening_hours(date);

CREATE INDEX IF NOT EXISTS idx_opening_hours_status
ON opening_hours(status)
WHERE status != 'closed';

-- 6. USERS - Índexs per autenticació
CREATE INDEX IF NOT EXISTS idx_users_email
ON users(email);

CREATE INDEX IF NOT EXISTS idx_users_role
ON users(role);

-- ============================================================
-- ANÀLISI D'ÍNDEXS
-- Executa aquestes queries per verificar que s'usen:
-- ============================================================

-- EXPLAIN ANALYZE SELECT table_id FROM appointments
-- WHERE status = 'confirmed'
-- AND start_time < '2025-11-05 21:00:00'
-- AND end_time > '2025-11-05 20:00:00';

-- EXPLAIN ANALYZE SELECT * FROM conversations
-- WHERE phone = '+34696978421'
-- AND created_at > NOW() - INTERVAL '10 minutes'
-- ORDER BY created_at DESC LIMIT 10;

-- ============================================================
-- NOTES:
-- - Tots els índexs usen IF NOT EXISTS per evitar errors
-- - Índexs parcials (WHERE) per reduir mida i millorar rendiment
-- - Ordre de columnes optimitzat per queries més freqüents
-- ============================================================
