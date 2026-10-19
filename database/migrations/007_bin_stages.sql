-- 007_bin_stages.sql - the compost stage the model predicted for each bin, hour by hour.
--
-- Saved when readings arrive (POST /records), one row per bin per hour that
-- had readings, so the Historical Stats tab can show how a bin's stage changed.
-- An hour is saved once and never overwritten: it keeps the prediction made
-- at the time. Deleted with the bin.
--
-- Applies on top of 006_research_keys.sql. Safe to run more than once.
--   local:  docker compose exec -T db psql -U compostiq -d compostiq < database/migrations/007_bin_stages.sql
--   VM:     psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/migrations/007_bin_stages.sql

BEGIN;

CREATE TABLE IF NOT EXISTS bin_stages (
    bin_id uuid NOT NULL REFERENCES bins (id) ON DELETE CASCADE,
    hour timestamptz NOT NULL,
    stage_id smallint NOT NULL,
    stage text NOT NULL,
    confidence real NOT NULL,
    PRIMARY KEY (bin_id, hour)
);

COMMIT;
