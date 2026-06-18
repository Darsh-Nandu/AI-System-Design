-- Eval pipeline schema bootstrap
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eval') THEN
    CREATE ROLE eval WITH LOGIN PASSWORD 'eval';
  END IF;
END
$$;

GRANT ALL PRIVILEGES ON DATABASE eval_pipeline TO eval;
