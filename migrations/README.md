# Migracions de Base de Dades

Aquest directori conté les migracions SQL per actualitzar l'esquema de la base de dades.

## Migració: Combinació d'IDs de Taules

### Fitxer: `convert_table_id_to_array.sql`

Aquesta migració canvia el sistema de reserves per utilitzar **una sola reserva** per combinacions de taules, en lloc de crear múltiples reserves vinculades.

### Què fa aquesta migració?

**Abans:**
- Quan es combinaven taules (ex: Taula 5 + Taula 6), es creaven **2 files** a la base de dades
- Cada fila tenia el seu propi `id` únic
- Les files es vinculaven amb un `booking_group_id` compartit

**Després:**
- Es crea **1 sola fila** per reserva, independentment del nombre de taules
- La columna `table_ids` és un array que conté els IDs de totes les taules
- Les cancel·lacions i modificacions ara només afecten una reserva

### Beneficis

1. **Simplicitat**: Una reserva = una fila a la base de dades
2. **Fàcil gestió**: Cancel·lar o modificar només requereix actualitzar un ID
3. **Millor rendiment**: Menys files per processar
4. **Més intuïtiu**: El concepte de "reserva" és més clar

### Com executar la migració

#### Opció 1: Utilitzant psql (recomanat)

```bash
psql -U username -d database_name -f migrations/convert_table_id_to_array.sql
```

#### Opció 2: Des de l'aplicació Python

```python
import psycopg2

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

with open('migrations/convert_table_id_to_array.sql', 'r') as f:
    sql = f.read()
    cursor.execute(sql)

conn.commit()
cursor.close()
conn.close()
```

#### Opció 3: Executar directament a PostgreSQL

```sql
\i /path/to/migrations/convert_table_id_to_array.sql
```

### Què fa la migració pas a pas

1. **Afegeix columna `table_ids`**: Array d'integers per guardar múltiples IDs de taula
2. **Migra reserves individuals**: Converteix `table_id` singular a `table_ids` array
3. **Combina reserves amb múltiples taules**:
   - Agrupa reserves pel mateix `booking_group_id`
   - Crea un array amb tots els `table_ids`
   - Actualitza la primera reserva amb l'array complet
   - Elimina les reserves duplicades
4. **Crea índex GIN**: Per consultes ràpides amb arrays
5. **Conserva `table_id`**: Per compatibilitat (pots eliminar-lo manualment després)

### Verificació després de la migració

```sql
-- Comprovar que no hi ha reserves duplicades amb el mateix booking_group_id
SELECT booking_group_id, COUNT(*) as count
FROM appointments
WHERE booking_group_id IS NOT NULL
GROUP BY booking_group_id
HAVING COUNT(*) > 1;
-- Hauria de retornar 0 files

-- Comprovar reserves amb múltiples taules
SELECT id, client_name, table_ids, array_length(table_ids, 1) as num_tables
FROM appointments
WHERE array_length(table_ids, 1) > 1;
```

### Rollback (revertir la migració)

**ATENCIÓ**: El rollback no és trivial perquè s'eliminen files duplicades.
És recomanable fer un **backup** abans d'executar la migració.

```sql
-- Backup abans de migrar
pg_dump -U username database_name > backup_before_migration.sql

-- Per restaurar si cal
psql -U username -d database_name < backup_before_migration.sql
```

### Notes importants

- ⚠️ **Fes un backup abans d'executar la migració**
- La migració és **idempotent**: pots executar-la múltiples vegades sense problemes
- Les reserves existents es mantenen intactes (només canvia l'estructura)
- El codi del backend ja està actualitzat per treballar amb `table_ids`

### Impacte en el frontend

Si tens un frontend que interactua amb l'API, necessitaràs actualitzar:

1. **Endpoint GET /api/appointments**: Ara retorna `table_ids` (array) i `table_numbers` (string "5+6")
2. **Endpoint PUT /api/appointments**: Ara accepta `table_ids` en lloc de `table_id`
3. **Visualització**: Les taules combinades es mostren com "5+6" en lloc de dues reserves separades

### Contacte

Si tens problemes amb la migració, revisa els logs de PostgreSQL:

```bash
tail -f /var/log/postgresql/postgresql-*.log
```
