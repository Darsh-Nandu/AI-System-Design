DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'medical') THEN
    CREATE ROLE medical WITH LOGIN PASSWORD 'medical';
  END IF;
END
$$;
GRANT ALL PRIVILEGES ON DATABASE medical_rag TO medical;
