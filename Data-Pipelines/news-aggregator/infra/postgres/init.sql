-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- for fast text search

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE news_aggregator TO news;
