-- OliveIntel Database Schema for Neon PostgreSQL
-- Milestone 1: Health monitoring with 5-year baselines

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================================
-- PROVINCES TABLE
-- ============================================================================
CREATE TABLE provinces (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    name_tr VARCHAR(100),  -- Turkish name with proper characters
    gadm_name VARCHAR(100),  -- GADM database name
    geometry GEOMETRY(MultiPolygon, 4326),  -- WGS84 coordinates
    area_ha NUMERIC(12, 2),
    elevation_m INT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Spatial index for geometry queries
CREATE INDEX idx_provinces_geom ON provinces USING GIST(geometry);

-- ============================================================================
-- TIME SERIES TABLE
-- ============================================================================
CREATE TABLE timeseries (
    id SERIAL PRIMARY KEY,
    province_id INT NOT NULL REFERENCES provinces(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    ndvi NUMERIC(6, 4),  -- -1 to 1, 4 decimal places
    ndre NUMERIC(6, 4),
    evi NUMERIC(6, 4),
    gndvi NUMERIC(6, 4),
    msavi2 NUMERIC(6, 4),
    cloud_free_pixels INT,  -- Quality indicator
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(province_id, date)  -- One record per province per day
);

-- Indexes for fast queries
CREATE INDEX idx_timeseries_province_date ON timeseries(province_id, date DESC);
CREATE INDEX idx_timeseries_date ON timeseries(date DESC);

-- ============================================================================
-- PHENOLOGY TABLE
-- ============================================================================
CREATE TABLE phenology (
    id SERIAL PRIMARY KEY,
    province_id INT NOT NULL REFERENCES provinces(id) ON DELETE CASCADE,
    year INT NOT NULL,
    index_name VARCHAR(20) NOT NULL,  -- NDVI, NDRE, EVI
    greenup_date DATE,
    greenup_doy INT,  -- Day of year (1-365)
    peak_date DATE NOT NULL,
    peak_doy INT,
    peak_value NUMERIC(6, 4),
    senescence_date DATE,
    senescence_doy INT,
    season_length_days INT,
    integral_auc NUMERIC(10, 2),  -- Area under curve
    min_value NUMERIC(6, 4),
    max_value NUMERIC(6, 4),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(province_id, year, index_name)
);

-- Indexes
CREATE INDEX idx_phenology_province_year ON phenology(province_id, year DESC);
CREATE INDEX idx_phenology_year ON phenology(year DESC);

-- ============================================================================
-- FORECASTS TABLE (Milestone 2)
-- ============================================================================
CREATE TABLE forecasts (
    id SERIAL PRIMARY KEY,
    province_id INT NOT NULL REFERENCES provinces(id) ON DELETE CASCADE,
    year INT NOT NULL,
    predicted_yield_tonnes NUMERIC(12, 2),
    ci_lower NUMERIC(12, 2),  -- 10th percentile
    ci_upper NUMERIC(12, 2),  -- 90th percentile
    confidence VARCHAR(20),  -- 'high', 'medium', 'low'
    on_year_flag BOOLEAN,  -- Alternate bearing: true = on year, false = off year
    model_version VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(province_id, year)
);

CREATE INDEX idx_forecasts_province_year ON forecasts(province_id, year DESC);

-- ============================================================================
-- ALERTS TABLE
-- ============================================================================
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    province_id INT NOT NULL REFERENCES provinces(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    severity VARCHAR(20) NOT NULL,  -- 'low', 'medium', 'high', 'critical'
    anomaly_type VARCHAR(50) NOT NULL,  -- 'vegetation_stress', 'drought', 'frost', etc.
    index_name VARCHAR(20) NOT NULL,  -- Which index triggered alert
    current_value NUMERIC(6, 4),
    baseline_value NUMERIC(6, 4),  -- 5-year average
    z_score NUMERIC(6, 2),  -- Standard deviations from baseline
    message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_alerts_province_date ON alerts(province_id, date DESC);
CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_alerts_date ON alerts(date DESC);

-- ============================================================================
-- GROUND TRUTH LABELS (Milestone 2)
-- ============================================================================
CREATE TABLE ground_truth (
    id SERIAL PRIMARY KEY,
    province_id INT NOT NULL REFERENCES provinces(id) ON DELETE CASCADE,
    year INT NOT NULL,
    production_tonnes NUMERIC(12, 2) NOT NULL,
    area_harvested_ha NUMERIC(12, 2),
    yield_tonnes_per_ha NUMERIC(8, 4),  -- production / area
    source VARCHAR(100),  -- e.g., 'TUIK', 'FAO'
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(province_id, year, source)
);

CREATE INDEX idx_ground_truth_province_year ON ground_truth(province_id, year DESC);

-- ============================================================================
-- WEATHER DATA (Milestone 2)
-- ============================================================================
CREATE TABLE weather (
    id SERIAL PRIMARY KEY,
    province_id INT NOT NULL REFERENCES provinces(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    temp_avg_c NUMERIC(5, 2),
    temp_min_c NUMERIC(5, 2),
    temp_max_c NUMERIC(5, 2),
    precip_mm NUMERIC(7, 2),
    gdd_base10 NUMERIC(6, 2),  -- Growing degree days (base 10°C)
    source VARCHAR(50) DEFAULT 'ERA5-Land',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(province_id, date)
);

CREATE INDEX idx_weather_province_date ON weather(province_id, date DESC);

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- Current health status (latest NDVI vs 5-year baseline)
CREATE OR REPLACE VIEW v_current_health AS
WITH current AS (
    SELECT
        province_id,
        ndvi as current_ndvi,
        date as current_date,
        ROW_NUMBER() OVER (PARTITION BY province_id ORDER BY date DESC) as rn
    FROM timeseries
    WHERE ndvi IS NOT NULL
),
baseline AS (
    SELECT
        province_id,
        AVG(ndvi) as baseline_ndvi,
        STDDEV(ndvi) as baseline_stddev,
        COUNT(*) as n_observations
    FROM timeseries
    WHERE ndvi IS NOT NULL
      AND date >= CURRENT_DATE - INTERVAL '5 years'
      AND EXTRACT(DOY FROM date) BETWEEN
          EXTRACT(DOY FROM CURRENT_DATE) - 7 AND
          EXTRACT(DOY FROM CURRENT_DATE) + 7
    GROUP BY province_id
)
SELECT
    p.id as province_id,
    p.name as province_name,
    c.current_ndvi,
    c.current_date,
    b.baseline_ndvi,
    b.baseline_stddev,
    (c.current_ndvi - b.baseline_ndvi) / NULLIF(b.baseline_stddev, 0) as z_score,
    ((c.current_ndvi - b.baseline_ndvi) / NULLIF(b.baseline_ndvi, 0)) * 100 as pct_change,
    CASE
        WHEN (c.current_ndvi - b.baseline_ndvi) / NULLIF(b.baseline_stddev, 0) < -3 THEN 'critical'
        WHEN (c.current_ndvi - b.baseline_ndvi) / NULLIF(b.baseline_stddev, 0) < -2 THEN 'warning'
        WHEN (c.current_ndvi - b.baseline_ndvi) / NULLIF(b.baseline_stddev, 0) < -1 THEN 'fair'
        ELSE 'good'
    END as health_status
FROM provinces p
JOIN current c ON p.id = c.province_id AND c.rn = 1
LEFT JOIN baseline b ON p.id = b.province_id;

-- Seasonal phenology summary
CREATE OR REPLACE VIEW v_seasonal_phenology AS
SELECT
    p.name as province_name,
    ph.year,
    ph.index_name,
    ph.greenup_date,
    ph.peak_date,
    ph.peak_value,
    ph.senescence_date,
    ph.season_length_days,
    ph.integral_auc,
    -- Compare to 5-year average
    AVG(ph2.peak_value) OVER (
        PARTITION BY ph.province_id, ph.index_name
        ORDER BY ph2.year
        ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING
    ) as peak_value_5yr_avg,
    AVG(ph2.season_length_days) OVER (
        PARTITION BY ph.province_id, ph.index_name
        ORDER BY ph2.year
        ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING
    ) as season_length_5yr_avg
FROM phenology ph
JOIN provinces p ON ph.province_id = p.id
LEFT JOIN phenology ph2 ON ph.province_id = ph2.province_id
    AND ph.index_name = ph2.index_name
ORDER BY ph.year DESC, p.name, ph.index_name;

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to compute health score (0-100)
CREATE OR REPLACE FUNCTION compute_health_score(current_ndvi NUMERIC, baseline_ndvi NUMERIC, baseline_stddev NUMERIC)
RETURNS INT AS $$
DECLARE
    z_score NUMERIC;
    score INT;
BEGIN
    -- Z-score normalization
    z_score := (current_ndvi - baseline_ndvi) / NULLIF(baseline_stddev, 0);

    -- Convert to 0-100 scale
    -- z_score of -3 = 0, 0 = 75, +2 = 100
    score := GREATEST(0, LEAST(100, 75 + (z_score * 12.5)));

    RETURN score;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE provinces IS 'Administrative boundaries (province level)';
COMMENT ON TABLE timeseries IS 'Daily vegetation index time series per province';
COMMENT ON TABLE phenology IS 'Seasonal phenology metrics (greenup, peak, senescence)';
COMMENT ON TABLE forecasts IS 'ML-based yield predictions (Milestone 2)';
COMMENT ON TABLE alerts IS 'Anomaly detection alerts (current vs baseline)';
COMMENT ON TABLE ground_truth IS 'Historical production data from TÜİK/FAO';
COMMENT ON TABLE weather IS 'Daily weather data from ERA5-Land (Milestone 2)';

COMMENT ON VIEW v_current_health IS 'Latest NDVI vs 5-year baseline (+/- 7 days)';
COMMENT ON VIEW v_seasonal_phenology IS 'Phenology metrics with 5-year rolling averages';

-- ============================================================================
-- INITIAL DATA
-- ============================================================================

-- Insert Aegean provinces (will be populated from GeoJSON)
-- Use scripts/load_provinces_to_db.py to load geometries

-- Example queries:
-- SELECT * FROM v_current_health WHERE health_status IN ('warning', 'critical');
-- SELECT * FROM v_seasonal_phenology WHERE year = 2024 AND index_name = 'NDVI';
-- SELECT province_name, AVG(ndvi) as avg_ndvi FROM timeseries t JOIN provinces p ON t.province_id = p.id WHERE date >= '2024-04-01' GROUP BY province_name;
