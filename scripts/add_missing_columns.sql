-- Add density and quality columns to provinces table
-- (These were added to schema.sql but need to be applied to existing database)

ALTER TABLE provinces
ADD COLUMN IF NOT EXISTS olive_area_ha NUMERIC(12, 2),
ADD COLUMN IF NOT EXISTS olive_tree_count INT,
ADD COLUMN IF NOT EXISTS tree_count_confidence VARCHAR(20),
ADD COLUMN IF NOT EXISTS olive_coverage_pct NUMERIC(5, 2),
ADD COLUMN IF NOT EXISTS density_last_updated DATE,
ADD COLUMN IF NOT EXISTS quality_score INT,
ADD COLUMN IF NOT EXISTS quality_grade VARCHAR(5),
ADD COLUMN IF NOT EXISTS quality_badge VARCHAR(50),
ADD COLUMN IF NOT EXISTS quality_last_updated DATE;
