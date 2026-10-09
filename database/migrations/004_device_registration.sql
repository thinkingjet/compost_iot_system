-- 004_device_registration.sql - devices registered without pairing.
--
-- Besides pairing (003), a device can join an account straight from the
-- dashboard: POST /devices names it, puts it in a bin and returns its API key
-- once, and the user copies the key onto the device by hand. Nothing is
-- learnt from the hardware, so such a device has no MAC address. The unique
-- index on upper(mac) from 003 already lets any number of devices have none.
--
-- Applies on top of 003_device_pairing.sql. Safe to run more than once.
--   local:  docker compose exec -T db psql -U compostiq -d compostiq < database/migrations/004_device_registration.sql
--   VM:     psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/migrations/004_device_registration.sql

BEGIN;

ALTER TABLE devices ALTER COLUMN mac DROP NOT NULL;

COMMIT;
