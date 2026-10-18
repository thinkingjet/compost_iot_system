-- 006_research_keys.sql - API keys for researcher accounts.
--
-- A researcher makes keys in the dashboard (up to 5, each with a name) and
-- uses them for the research endpoints only. Only the SHA-256 hash is
-- stored, like device keys. Deleting a key deletes its row, so it stops
-- working at once; deleting the account deletes its keys.
--
-- Applies on top of 005_user_roles.sql. Safe to run more than once.
--   local:  docker compose exec -T db psql -U compostiq -d compostiq < database/migrations/006_research_keys.sql
--   VM:     psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/migrations/006_research_keys.sql

BEGIN;

CREATE TABLE IF NOT EXISTS research_apikeys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name text NOT NULL,
    api_key_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS research_apikeys_user_id_idx ON research_apikeys (user_id);

COMMIT;
