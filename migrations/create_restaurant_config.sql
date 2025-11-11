-- Crear taula de configuració del restaurant
CREATE TABLE IF NOT EXISTS restaurant_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    value_type VARCHAR(20) NOT NULL, -- 'string', 'int', 'float', 'bool', 'json'
    category VARCHAR(50) NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Crear trigger per actualitzar updated_at automàticament
CREATE OR REPLACE FUNCTION update_restaurant_config_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER restaurant_config_updated
    BEFORE UPDATE ON restaurant_config
    FOR EACH ROW
    EXECUTE FUNCTION update_restaurant_config_timestamp();

-- Insertar valors per defecte
INSERT INTO restaurant_config (key, value, value_type, category, description) VALUES
    -- Restaurant
    ('restaurant_name', 'Amaru', 'string', 'restaurant', 'Nom del restaurant'),
    ('max_people_per_booking', '8', 'int', 'restaurant', 'Màxim de persones per reserva'),
    ('supported_languages', 'ca,es,en', 'string', 'restaurant', 'Idiomes suportats (separats per comes)'),

    -- Reserves
    ('time_slots_mode', 'interval', 'string', 'booking', 'Mode de time slots: "interval" (cada X minuts) o "fixed" (horaris fixos)'),
    ('time_slot_interval_minutes', '30', 'int', 'booking', 'Interval entre franges horàries en minuts (només si mode=interval)'),
    ('fixed_time_slots_lunch', '13:00,15:00', 'string', 'booking', 'Horaris fixos per dinar (només si mode=fixed). Format: HH:MM,HH:MM'),
    ('fixed_time_slots_dinner', '20:00,21:30', 'string', 'booking', 'Horaris fixos per sopar (només si mode=fixed). Format: HH:MM,HH:MM'),
    ('default_booking_duration_hours', '1', 'float', 'booking', 'Durada per defecte d''una reserva (hores)'),
    ('search_window_days', '7', 'int', 'booking', 'Dies endavant per buscar disponibilitat'),

    -- Manteniment
    ('generate_schedule_days_ahead', '90', 'int', 'maintenance', 'Dies endavant per generar horaris automàticament'),
    ('delete_old_data_days', '28', 'int', 'maintenance', 'Dies abans d''esborrar dades antigues'),

    -- Converses
    ('conversation_history_minutes', '20', 'int', 'conversations', 'Minuts de retenció d''historial de conversa'),
    ('conversation_history_limit', '10', 'int', 'conversations', 'Nombre màxim de missatges a l''historial'),
    ('cleanup_messages_days', '15', 'int', 'conversations', 'Dies abans de netejar missatges antics')
ON CONFLICT (key) DO NOTHING;
