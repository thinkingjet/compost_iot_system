-- Minimal development seed, loaded by compose.yaml after the schema.
-- Fixed UUIDs so tests and local tools can refer to these rows.
--
-- No password hash and no device API key are seeded:
--   * users.password_hash is a placeholder until POST /auth/register exists
--     (the API will hash with argon2, not SHA-256)
--   * device keys are created per test / per developer, never committed
--
-- Replaces database/dummy_records.sql for local use (that file re-creates the
-- records table and cannot be loaded after the schema).

INSERT INTO users (id, email, password_hash)
VALUES ('00000000-0000-4000-8000-000000000001', 'dev@compostiq.local', '!placeholder-no-login');

INSERT INTO bins (id, location, user_id, name)
VALUES ('00000000-0000-4000-8000-000000000101', 'Mataram, Lombok, Indonesia',
        '00000000-0000-4000-8000-000000000001', 'UNRAM Bin 1');

INSERT INTO devices (id, mac, owner_id, is_active)
VALUES ('00000000-0000-4000-8000-000000000201', '02:00:00:00:00:01',
        '00000000-0000-4000-8000-000000000001', true);

INSERT INTO device_bin_assn (device_id, bin_id)
VALUES ('00000000-0000-4000-8000-000000000201', '00000000-0000-4000-8000-000000000101');
