-- Alejandria Database Initialization Script
-- This script is executed when the PostgreSQL container first starts

-- Create database if it doesn't exist (already created by postgres image)
-- CREATE DATABASE alejandria;

-- Connect to the database
\c alejandria;

-- Enable extensions if needed
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE alejandria TO manga;

-- The tables will be created automatically by SQLAlchemy on first startup
