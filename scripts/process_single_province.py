"""Process a single province (for retries)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scripts.process_provinces import process_province_timeseries, save_province_data, load_province_boundaries
from pipeline import access

province_name = sys.argv[1] if len(sys.argv) > 1 else 'Muğla'

print(f"Processing: {province_name}")
access.authenticate_gee()

provinces = load_province_boundaries()

if province_name not in provinces:
    print(f"Province not found: {province_name}")
    print(f"Available: {list(provinces.keys())}")
    exit(1)

province_info = provinces[province_name]

result = process_province_timeseries(
    province_name,
    province_info,
    start_date='2019-04-01',
    end_date='2024-10-31',
    indices_list=['NDVI', 'NDRE', 'EVI']
)

if result:
    save_province_data(result)
    print(f"\n✅ Success!")
else:
    print(f"\n❌ Failed")
