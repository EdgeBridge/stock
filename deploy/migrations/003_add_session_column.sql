-- Add session column to orders table for extended hours tracking
-- Values: regular, pre_market, after_hours, extended_nxt
ALTER TABLE orders ADD COLUMN IF NOT EXISTS session VARCHAR(20) DEFAULT 'regular';
