-- Afegir variables de configuració per time slots fixos
INSERT INTO restaurant_config (key, value, value_type, category, description) VALUES
    ('time_slots_mode', 'interval', 'string', 'booking', 'Mode de time slots: "interval" (cada X minuts) o "fixed" (horaris fixos)'),
    ('fixed_time_slots_lunch', '13:00,15:00', 'string', 'booking', 'Horaris fixos per dinar (només si mode=fixed). Format: HH:MM,HH:MM'),
    ('fixed_time_slots_dinner', '20:00,21:30', 'string', 'booking', 'Horaris fixos per sopar (només si mode=fixed). Format: HH:MM,HH:MM')
ON CONFLICT (key) DO NOTHING;
