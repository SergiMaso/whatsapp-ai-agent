-- Migració per combinar IDs de taules en reserves amb taules combinades
-- En lloc de crear múltiples files per reserves amb múltiples taules,
-- ara guardem totes les taules en un array en una sola reserva

-- 1. Afegir nova columna table_ids com a array d'integers
ALTER TABLE appointments
ADD COLUMN IF NOT EXISTS table_ids INTEGER[];

-- 2. Migrar dades existents: convertir table_id a array table_ids
-- Per reserves individuals (sense booking_group_id duplicat)
UPDATE appointments a1
SET table_ids = ARRAY[table_id]
WHERE table_id IS NOT NULL
  AND table_ids IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM appointments a2
    WHERE a2.booking_group_id = a1.booking_group_id
      AND a2.id != a1.id
      AND a2.booking_group_id IS NOT NULL
  );

-- 3. Per reserves amb múltiples taules (mateix booking_group_id):
--    Combinar totes les taules en la primera reserva i eliminar les altres
DO $$
DECLARE
    group_rec RECORD;
    table_ids_array INTEGER[];
    first_appointment_id INTEGER;
BEGIN
    -- Per cada booking_group_id que té múltiples reserves
    FOR group_rec IN
        SELECT booking_group_id, COUNT(*) as cnt
        FROM appointments
        WHERE booking_group_id IS NOT NULL
        GROUP BY booking_group_id
        HAVING COUNT(*) > 1
    LOOP
        -- Obtenir totes les table_ids del grup
        SELECT ARRAY_AGG(table_id ORDER BY id) INTO table_ids_array
        FROM appointments
        WHERE booking_group_id = group_rec.booking_group_id
          AND table_id IS NOT NULL;

        -- Obtenir l'ID de la primera reserva del grup
        SELECT MIN(id) INTO first_appointment_id
        FROM appointments
        WHERE booking_group_id = group_rec.booking_group_id;

        -- Actualitzar la primera reserva amb totes les taules
        UPDATE appointments
        SET table_ids = table_ids_array
        WHERE id = first_appointment_id;

        -- Eliminar les altres reserves del grup
        DELETE FROM appointments
        WHERE booking_group_id = group_rec.booking_group_id
          AND id != first_appointment_id;

        RAISE NOTICE 'Combinades % taules per booking_group_id % en reserva ID %',
                     array_length(table_ids_array, 1),
                     group_rec.booking_group_id,
                     first_appointment_id;
    END LOOP;
END $$;

-- 4. Crear índex per millorar rendiment de queries amb table_ids
CREATE INDEX IF NOT EXISTS idx_appointments_table_ids ON appointments USING GIN(table_ids);

-- 5. Ara podem eliminar la columna table_id (opcional, comentat per seguretat)
-- ALTER TABLE appointments DROP COLUMN IF EXISTS table_id;

-- 6. El booking_group_id ja no és necessari per agrupar múltiples files,
--    però el mantenim per compatibilitat amb dades antigues
-- ALTER TABLE appointments DROP COLUMN IF EXISTS booking_group_id;

-- Comentari: A partir d'ara, cada reserva té una sola fila amb table_ids[]
-- que pot contenir una o múltiples taules
