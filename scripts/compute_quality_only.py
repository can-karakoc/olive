"""Compute only quality scores (skip density - memory intensive)."""

import json
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from pipeline import quality

data_dir = Path('data/interim/provinces')
json_files = list(data_dir.glob('*_timeseries.json'))

print("Computing quality scores only...")
print("=" * 60)

for json_path in sorted(json_files):
    with open(json_path, 'r') as f:
        data = json.load(f)

    province_name = data['province_name']

    if 'NDVI' not in data.get('indices', {}):
        print(f"⏭️  {province_name}: No NDVI data")
        continue

    print(f"\n{province_name}:")

    phenology_by_year = data['indices']['NDVI'].get('phenology_by_year', {})
    phenology_by_year = {int(k): v for k, v in phenology_by_year.items()}

    quality_metrics = quality.compute_quality_for_province(phenology_by_year, 2024)

    data['quality'] = quality_metrics

    print(f"  Score: {quality_metrics['total_score']}/100 ({quality_metrics['badge']})")

    with open(json_path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  ✅ Updated")

print("\n" + "=" * 60)
print("✅ Quality scores computed")
print("Next: python scripts/load_data_to_db.py")
