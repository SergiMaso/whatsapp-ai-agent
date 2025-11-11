-- Afegir camp booking_group_id per agrupar reserves amb múltiples taules
ALTER TABLE appointments
ADD COLUMN IF NOT EXISTS booking_group_id UUID;

-- Crear índex per millorar rendiment de queries que filtren per booking_group_id
CREATE INDEX IF NOT EXISTS idx_appointments_booking_group_id ON appointments(booking_group_id);

-- Generar booking_group_id per reserves existents que encara no en tenen
-- Cada reserva individual tindrà el seu propi booking_group_id
UPDATE appointments
SET booking_group_id = gen_random_uuid()
WHERE booking_group_id IS NULL;

-- Comentari: A partir d'ara, quan es crea una reserva amb múltiples taules,
-- totes les files compartiran el mateix booking_group_id
