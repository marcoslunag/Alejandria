-- Migration script: Rename PostgreSQL user from 'manga' to 'alejandria'
-- Run this ONCE on existing installations before updating docker-compose
--
-- Usage: docker compose exec -T postgres psql -U manga -d alejandria -f /docker-entrypoint-initdb.d/migrate-db-user.sql
-- Or:    docker compose exec -T postgres psql -U manga manga_arr < scripts/migrate-db-user.sql

-- Create new user if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'alejandria') THEN
        CREATE ROLE alejandria WITH LOGIN PASSWORD 'alejandria';
    END IF;
END
$$;

-- Grant all privileges
GRANT ALL PRIVILEGES ON DATABASE alejandria TO alejandria;

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO alejandria;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO alejandria;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO alejandria;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO alejandria;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO alejandria;

-- Transfer ownership of all tables
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
        EXECUTE format('ALTER TABLE public.%I OWNER TO alejandria', r.tablename);
    END LOOP;
END
$$;

-- Transfer ownership of all sequences
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'
    LOOP
        EXECUTE format('ALTER SEQUENCE public.%I OWNER TO alejandria', r.sequencename);
    END LOOP;
END
$$;
