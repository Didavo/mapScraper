-- Event Scraper Database Schema
-- PostgreSQL

-- Extension für UUID-Generierung
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ===========================================
-- SOURCES: Welche Websites werden gescraped
-- ===========================================
CREATE TABLE sources (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,           -- z.B. "Mulfingen"
    base_url        VARCHAR(500) NOT NULL,           -- z.B. "https://www.mulfingen.de"
    scraper_class   VARCHAR(100) NOT NULL,           -- z.B. "MulfingenScraper"
    is_active       BOOLEAN DEFAULT TRUE,
    last_scraped_at TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(base_url)
);

-- ===========================================
-- LOCATIONS: Normalisierte Veranstaltungsorte
-- ===========================================
CREATE TABLE locations (
    id              SERIAL PRIMARY KEY,

    -- Referenz zur Source (Location gehört zu einer Gemeinde/Source)
    source_id       INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,

    -- Originalname aus dem Scraping
    raw_name        VARCHAR(500) NOT NULL,           -- z.B. "Turnhalle Mulfingen"

    -- Manuell gepflegte Daten
    display_name    VARCHAR(500),                    -- z.B. "Turnhalle der Gemeinde Mulfingen"
    street          VARCHAR(255),
    house_number    VARCHAR(20),
    postal_code     VARCHAR(10),
    city            VARCHAR(100),
    country         VARCHAR(100) DEFAULT 'Deutschland',

    -- Geocoding
    latitude        DECIMAL(10, 8),
    longitude       DECIMAL(11, 8),
    geocoding_status VARCHAR(20),                    -- null, success, not_found, error

    -- Status für den Workflow
    status          VARCHAR(20) DEFAULT 'pending',   -- pending, confirmed, ignored

    -- Timestamps
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Unique: gleicher Name kann in verschiedenen Sources existieren
    UNIQUE(source_id, raw_name)
);

-- Index für schnelles Matching
CREATE INDEX idx_locations_source_raw_name ON locations(source_id, raw_name);
CREATE INDEX idx_locations_status ON locations(status);

-- ===========================================
-- EVENTS: Die eigentlichen Veranstaltungen
-- ===========================================
CREATE TABLE events (
    id              SERIAL PRIMARY KEY,

    -- Referenzen
    source_id       INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    location_id     INTEGER REFERENCES locations(id) ON DELETE SET NULL,

    -- Deduplizierung: externe ID von der Quell-Website
    external_id     VARCHAR(255) NOT NULL,           -- z.B. URL-Slug oder ID aus der URL

    -- Event-Daten (Basis)
    title           VARCHAR(500) NOT NULL,
    event_date      DATE NOT NULL,
    event_time      TIME,                            -- Optional: Uhrzeit
    event_end_date  DATE,                            -- Optional: für mehrtägige Events
    event_end_time  TIME,

    -- URL zur Detailseite
    url             VARCHAR(1000),

    -- Location als Fallback (falls noch nicht in locations-Tabelle)
    raw_location    VARCHAR(500),

    -- Timestamps
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at      TIMESTAMP WITH TIME ZONE,        -- Soft-Delete

    -- Unique Constraint: Ein Event pro Quelle
    UNIQUE(source_id, external_id)
);

-- Indices für häufige Queries
CREATE INDEX idx_events_date ON events(event_date);
CREATE INDEX idx_events_source ON events(source_id);
CREATE INDEX idx_events_location ON events(location_id);
CREATE INDEX idx_events_deleted ON events(deleted_at) WHERE deleted_at IS NULL;

-- ===========================================
-- SCRAPE_LOGS: Protokollierung der Scrape-Läufe
-- ===========================================
CREATE TABLE scrape_logs (
    id              SERIAL PRIMARY KEY,
    source_id       INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,

    started_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at     TIMESTAMP WITH TIME ZONE,

    status          VARCHAR(20) NOT NULL,            -- running, success, failed
    events_found    INTEGER DEFAULT 0,
    events_new      INTEGER DEFAULT 0,
    events_updated  INTEGER DEFAULT 0,

    -- Geocoding Statistiken
    geocoding_success   INTEGER DEFAULT 0,
    geocoding_multiple  INTEGER DEFAULT 0,
    geocoding_not_found INTEGER DEFAULT 0,
    geocoding_errors    INTEGER DEFAULT 0,

    error_message   TEXT,

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_scrape_logs_source ON scrape_logs(source_id);

-- ===========================================
-- TRIGGER: Automatisches updated_at
-- ===========================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_sources_updated_at
    BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_locations_updated_at
    BEFORE UPDATE ON locations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_events_updated_at
    BEFORE UPDATE ON events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
