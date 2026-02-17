-- Migration: Add geocoding_status to locations
-- Date: 2026-02-05
-- Description: Tracks the status of geocoding attempts for each location

ALTER TABLE locations
ADD COLUMN IF NOT EXISTS geocoding_status VARCHAR(20);

-- Optional: Add index for filtering by geocoding status
CREATE INDEX IF NOT EXISTS idx_locations_geocoding_status ON locations(geocoding_status);

COMMENT ON COLUMN locations.geocoding_status IS 'Status of geocoding: null (not attempted), success, not_found, error';
