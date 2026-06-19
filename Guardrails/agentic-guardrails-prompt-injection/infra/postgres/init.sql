DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'guardrails') THEN
    CREATE ROLE guardrails WITH LOGIN PASSWORD 'guardrails';
  END IF;
END
$$;
GRANT ALL PRIVILEGES ON DATABASE guardrails TO guardrails;
