-- Which migrations are in place? Read-only; safe to run at any time.
--
--   psql "$PGURL" -f database/checks/migration_status.sql
--
-- One row per thing a migration adds. Add rows here with every new migration.

WITH fk AS (
    -- every single-column foreign key, with its ON DELETE rule
    SELECT con.conrelid::regclass::text AS tbl,
           att.attname::text            AS col,
           CASE con.confdeltype WHEN 'c' THEN 'CASCADE' WHEN 'n' THEN 'SET NULL' ELSE 'NO ACTION' END AS on_delete
    FROM pg_constraint con
    JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = con.conkey[1]
    WHERE con.contype = 'f' AND array_length(con.conkey, 1) = 1
),
checks (migration, item, ok) AS (
    VALUES
        ('001', 'table users exists',
            to_regclass('public.users') IS NOT NULL),
        ('001', 'table records exists',
            to_regclass('public.records') IS NOT NULL),

        ('002', 'users.created_at',
            EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'created_at')),
        ('002', 'users.display_name',
            EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'display_name')),
        ('002', 'unique index on lower(email)',
            to_regclass('public.users_email_lower_key') IS NOT NULL),
        ('002', 'bins.user_id ON DELETE CASCADE',
            EXISTS (SELECT 1 FROM fk WHERE tbl = 'bins' AND col = 'user_id' AND on_delete = 'CASCADE')),
        ('002', 'setup_codes.user_id ON DELETE CASCADE',
            EXISTS (SELECT 1 FROM fk WHERE tbl = 'setup_codes' AND col = 'user_id' AND on_delete = 'CASCADE')),
        ('002', 'devices.owner_id ON DELETE SET NULL',
            EXISTS (SELECT 1 FROM fk WHERE tbl = 'devices' AND col = 'owner_id' AND on_delete = 'SET NULL')),
        ('002', 'device_bin_assn.bin_id ON DELETE CASCADE',
            EXISTS (SELECT 1 FROM fk WHERE tbl = 'device_bin_assn' AND col = 'bin_id' AND on_delete = 'CASCADE')),
        ('002', 'records.bin_id ON DELETE CASCADE',
            EXISTS (SELECT 1 FROM fk WHERE tbl = 'records' AND col = 'bin_id' AND on_delete = 'CASCADE')),
        ('002', 'bin_events.bin_id ON DELETE CASCADE',
            EXISTS (SELECT 1 FROM fk WHERE tbl = 'bin_events' AND col = 'bin_id' AND on_delete = 'CASCADE')),
        ('002', 'bin_events.reading_id ON DELETE SET NULL',
            EXISTS (SELECT 1 FROM fk WHERE tbl = 'bin_events' AND col = 'reading_id' AND on_delete = 'SET NULL'))
)
SELECT migration, item, CASE WHEN ok THEN 'applied' ELSE 'MISSING' END AS status
FROM checks
ORDER BY migration, item;
