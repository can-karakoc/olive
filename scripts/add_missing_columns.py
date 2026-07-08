"""Add missing density and quality columns to provinces table."""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

print("Adding missing columns to provinces table...")

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

try:
    cursor.execute("""
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
    """)

    conn.commit()
    print("✅ Columns added successfully")

except Exception as e:
    print(f"❌ Error: {e}")
    conn.rollback()

finally:
    cursor.close()
    conn.close()

print("\nNow run: python scripts/load_data_to_db.py")
