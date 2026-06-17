-- Loop detection schema bootstrap
-- SQLAlchemy create_all() handles full DDL; this file only creates
-- the database role used by the app when the container first starts.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'loop') THEN
    CREATE ROLE loop WITH LOGIN PASSWORD 'loop';
  END IF;
END
$$;

GRANT ALL PRIVILEGES ON DATABASE loop_detection TO loop;
