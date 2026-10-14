-- 005_user_roles.sql - what kind of account each user has.
--
-- Two kinds of account:
--   'owner'       has compost bins and devices, and uses the dashboard
--   'researcher'  reads the public research data with an API key
-- One role per account. It is chosen when the account is created; until
-- sign-up asks for it, every account is an owner, so existing accounts and
-- the current POST /auth/register carry on as they are.
--
-- Applies on top of 004_device_registration.sql. Safe to run more than once.
--   local:  docker compose exec -T db psql -U compostiq -d compostiq < database/migrations/005_user_roles.sql
--   VM:     psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/migrations/005_user_roles.sql

BEGIN;

-- the default fills in every existing account
ALTER TABLE users ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'owner';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_role_check') THEN
        ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('owner', 'researcher'));
    END IF;
END
$$;

COMMIT;
