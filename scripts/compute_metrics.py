"""
Compute density and quality metrics for all provinces.

Reads processed time series JSON files and computes:
1. Olive density (tree count + grove area)
2. Quality scores (0-100) based on phenology

Outputs: Updated JSON files with metrics added.
"""

import json
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pipeline import access, indices, density, quality
import ee


def load_province_data(json_path):
    """Load province time series data from JSON."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_province_data(data, json_path):
    """Save updated province data to JSON."""
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compute_density_for_province(province_data, province_geojson_path):
    """
    Compute density metrics for a province.

    Args:
        province_data: Time series data dict
        province_geojson_path: Path to province boundary GeoJSON

    Returns:
        Dict with density metrics
    """

    print(f"\nComputing density for {province_data['province_name']}...")

    # Load province boundary
    with open(province_geojson_path, 'r', encoding='utf-8') as f:
        geojson = json.load(f)

    geometry = ee.Geometry(geojson['features'][0]['geometry'])

    # Reconstruct collection from date range
    start_date = '2024-04-01'  # Use 2024 for density
    end_date = '2024-10-31'

    collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(geometry)
                  .filterDate(start_date, end_date)
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)))

    # Compute indices
    collection_with_indices = indices.compute_indices_collection(collection, ['NDVI'])

    # Compute density
    density_metrics = density.compute_density_metrics(
        collection_with_indices,
        geometry,
        province_data['province_name'],
        scale=100  # Use 100m for consistency with time series
    )

    return density_metrics


def compute_quality_for_province(province_data, current_year=2024):
    """
    Compute quality score for a province.

    Args:
        province_data: Time series data dict with phenology_by_year
        current_year: Year to score

    Returns:
        Dict with quality metrics
    """

    print(f"\nComputing quality for {province_data['province_name']}...")

    # Get NDVI phenology (most important index)
    if 'NDVI' not in province_data.get('indices', {}):
        print(f"  ⚠️  No NDVI data found")
        return None

    ndvi_data = province_data['indices']['NDVI']
    phenology_by_year = ndvi_data.get('phenology_by_year', {})

    if not phenology_by_year:
        print(f"  ⚠️  No phenology data found")
        return None

    # Convert year keys to integers
    phenology_by_year = {int(k): v for k, v in phenology_by_year.items()}

    # Compute quality
    quality_metrics = quality.compute_quality_for_province(
        phenology_by_year,
        current_year=current_year
    )

    return quality_metrics


def main():
    print("OliveIntel - Metrics Computation")
    print("=" * 60)

    # Authenticate GEE
    access.authenticate_gee()

    # Find all province time series files
    data_dir = Path('data/interim/provinces')

    if not data_dir.exists():
        print(f"❌ Directory not found: {data_dir}")
        print("   Run scripts/process_provinces.py first")
        return

    json_files = list(data_dir.glob('*_timeseries.json'))

    if not json_files:
        print(f"❌ No time series files found in {data_dir}")
        return

    print(f"\nFound {len(json_files)} provinces to process")

    results = []

    for json_path in sorted(json_files):
        province_name = json_path.stem.replace('_timeseries', '').replace('i̇', 'i').title()

        print(f"\n{'='*60}")
        print(f"Processing: {province_name}")
        print(f"{'='*60}")

        try:
            # Load existing data
            province_data = load_province_data(json_path)

            # Find corresponding boundary file
            province_slug = json_path.stem.replace('_timeseries', '')
            boundary_path = Path(f'data/geo/{province_slug}_boundary.geojson')

            if not boundary_path.exists():
                print(f"  ⚠️  Boundary file not found: {boundary_path}")
                print(f"  Skipping density computation")
                density_metrics = None
            else:
                # Compute density
                density_metrics = compute_density_for_province(province_data, boundary_path)

                # Add to province data
                province_data['density'] = density_metrics

                print(f"\n  Density Results:")
                print(f"    Primary metric: {density_metrics['primary_metric']}")
                print(f"    Primary value: {density_metrics['primary_value']:,.0f}")
                print(f"    Grove area: {density_metrics['grove_area_ha']:,.0f} ha")
                if density_metrics.get('tree_count'):
                    print(f"    Tree count: ~{density_metrics['tree_count']:,} trees")
                    print(f"    Confidence: {density_metrics['tree_count_confidence']}")

            # Compute quality
            quality_metrics = compute_quality_for_province(province_data, current_year=2024)

            if quality_metrics:
                # Add to province data
                province_data['quality'] = quality_metrics

                print(f"\n  Quality Results:")
                print(f"    Score: {quality_metrics['total_score']}/100 ({quality_metrics['grade']})")
                print(f"    Badge: {quality_metrics['badge']}")
                print(f"    Components:")
                for comp_name, comp_data in quality_metrics['components'].items():
                    if isinstance(comp_data, dict) and 'score' in comp_data:
                        print(f"      {comp_name}: {comp_data['score']:.1f} pts ({comp_data.get('grade', 'N/A')})")

            # Save updated data
            save_province_data(province_data, json_path)

            print(f"\n  ✅ Updated: {json_path}")

            results.append({
                'province': province_name,
                'status': 'success',
                'density': density_metrics,
                'quality': quality_metrics
            })

        except Exception as e:
            print(f"\n  ❌ Error: {e}")
            import traceback
            traceback.print_exc()

            results.append({
                'province': province_name,
                'status': 'error',
                'error': str(e)
            })

    # Summary
    print("\n" + "=" * 60)
    print("METRICS COMPUTATION SUMMARY")
    print("=" * 60)

    success = [r for r in results if r['status'] == 'success']
    errors = [r for r in results if r['status'] == 'error']

    print(f"✅ Success: {len(success)}")
    print(f"❌ Errors: {len(errors)}")

    if success:
        print(f"\nProcessed provinces:")
        for r in success:
            print(f"\n  • {r['province']}:")

            if r['density']:
                d = r['density']
                print(f"    Density: {d['primary_value']:,.0f} {d['primary_metric'].replace('_', ' ')}")

            if r['quality']:
                q = r['quality']
                print(f"    Quality: {q['total_score']}/100 ({q['badge']})")

    if errors:
        print(f"\nErrors:")
        for r in errors:
            print(f"  • {r['province']}: {r['error']}")

    print("\n" + "=" * 60)
    print("Next steps:")
    print("1. Review updated JSON files in data/interim/provinces/")
    print("2. Load data to PostgreSQL: python scripts/load_data_to_db.py")
    print("3. Test Streamlit app: streamlit run app/streamlit_app.py")
    print("=" * 60)


if __name__ == '__main__':
    main()
