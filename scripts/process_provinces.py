"""
Process Sentinel-2 time series for Aegean provinces.

Extracts NDVI, NDRE, and EVI time series for each province over the
2019-2024 period (5 years for baseline + current year).

Stores results in data/interim/ as JSON files for database loading.
"""

import ee
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pipeline import access, preprocess, indices, timeseries


def load_province_boundaries(geojson_path='data/geo/aegean_provinces.geojson'):
    """Load province boundaries from GeoJSON."""

    print(f"Loading province boundaries from {geojson_path}...")

    with open(geojson_path, 'r', encoding='utf-8') as f:
        geojson = json.load(f)

    provinces = {}

    for feature in geojson['features']:
        props = feature['properties']
        geom = feature['geometry']

        province_id = props['province_id']
        name = props['name_en']

        # Convert to EE geometry
        ee_geom = ee.Geometry(geom)

        provinces[name] = {
            'id': province_id,
            'name': name,
            'geometry': ee_geom,
            'area_ha': props.get('area_ha', 0)
        }

    print(f"✅ Loaded {len(provinces)} provinces: {', '.join(provinces.keys())}")

    return provinces


def process_province_timeseries(
    province_name,
    province_info,
    start_date='2019-04-01',
    end_date='2024-10-31',
    indices_list=None
):
    """
    Extract time series for a single province.

    Args:
        province_name: Province name
        province_info: Dict with id, geometry, area_ha
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        indices_list: List of indices to extract

    Returns:
        Dict with time series data
    """

    if indices_list is None:
        indices_list = ['NDVI', 'NDRE', 'EVI']

    print(f"\n{'='*60}")
    print(f"Processing: {province_name}")
    print(f"{'='*60}")

    geometry = province_info['geometry']

    # Get Sentinel-2 collection
    print(f"Fetching Sentinel-2 images ({start_date} to {end_date})...")

    collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(geometry)
                  .filterDate(start_date, end_date)
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)))

    count = collection.size().getInfo()
    print(f"  Found {count} images")

    if count == 0:
        print("  ⚠️  No images found, skipping")
        return None

    # Compute indices
    print("Computing spectral indices...")
    collection_with_indices = indices.compute_indices_collection(
        collection, indices=indices_list
    )

    # Extract time series for each index
    province_data = {
        'province_id': province_info['id'],
        'province_name': province_name,
        'area_ha': province_info['area_ha'],
        'date_range': {'start': start_date, 'end': end_date},
        'indices': {}
    }

    for index_name in indices_list:
        print(f"\n  Extracting {index_name} time series...")

        try:
            # Extract raw time series
            df_raw = timeseries.extract_raw_time_series(
                collection_with_indices,
                geometry,
                band_name=index_name,
                reducer='mean',
                scale=100  # Use 100m for large provinces
            )

            print(f"    Raw observations: {len(df_raw)}")

            if len(df_raw) < 10:
                print(f"    ⚠️  Too few observations ({len(df_raw)}), skipping")
                continue

            # Gap-fill
            df_filled = timeseries.gap_fill_linear(df_raw, max_gap_days=30)
            print(f"    After gap-fill: {len(df_filled)}")

            # Smooth
            if len(df_filled) >= 11:
                df_smooth = timeseries.smooth_savitzky_golay(df_filled, window_length=11)
                print(f"    Smoothed: {len(df_smooth)}")

                # Extract phenology per year
                phenology_by_year = {}

                for year in range(2019, 2025):
                    year_start = f"{year}-04-01"
                    year_end = f"{year}-10-31"

                    df_year = df_smooth[
                        (df_smooth['date'] >= year_start) &
                        (df_smooth['date'] <= year_end)
                    ].copy()

                    if len(df_year) >= 20:  # Need enough points
                        try:
                            phenology = timeseries.detect_phenology_simple(
                                df_year, value_col='value_smoothed'
                            )
                            phenology_by_year[year] = phenology
                            print(f"      {year}: peak={phenology['peak_value']:.3f} on {phenology['peak_date']}")
                        except Exception as e:
                            print(f"      {year}: Phenology extraction failed ({e})")

                # Store results
                province_data['indices'][index_name] = {
                    'time_series': df_smooth.to_dict('records'),
                    'phenology_by_year': phenology_by_year,
                    'stats': {
                        'n_observations': len(df_raw),
                        'n_filled': len(df_filled),
                        'date_min': df_smooth['date'].min().strftime('%Y-%m-%d'),
                        'date_max': df_smooth['date'].max().strftime('%Y-%m-%d'),
                        'value_min': float(df_smooth['value_smoothed'].min()),
                        'value_max': float(df_smooth['value_smoothed'].max()),
                        'value_mean': float(df_smooth['value_smoothed'].mean())
                    }
                }

                print(f"    ✅ {index_name} complete")

            else:
                print(f"    ⚠️  Not enough points for smoothing ({len(df_filled)})")

        except Exception as e:
            print(f"    ❌ Error processing {index_name}: {e}")
            import traceback
            traceback.print_exc()

    return province_data


def save_province_data(province_data, output_dir='data/interim/provinces'):
    """Save province time series data to JSON."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    province_name = province_data['province_name']
    filename = f"{province_name.lower().replace('ı', 'i')}_timeseries.json"
    file_path = output_path / filename

    # Convert dates to strings for JSON serialization
    def convert_dates(obj):
        if isinstance(obj, pd.Timestamp):
            return obj.strftime('%Y-%m-%d')
        elif isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d')
        return obj

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(province_data, f, ensure_ascii=False, indent=2, default=convert_dates)

    print(f"\n✅ Saved to: {file_path}")

    return file_path


def main():
    print("OliveIntel - Province Time Series Processing")
    print("=" * 60)

    # Authenticate GEE
    access.authenticate_gee()

    # Load province boundaries
    provinces = load_province_boundaries()

    # Process each province
    results = []

    for province_name, province_info in provinces.items():
        try:
            province_data = process_province_timeseries(
                province_name,
                province_info,
                start_date='2019-04-01',  # 5 years for baseline
                end_date='2024-10-31',
                indices_list=['NDVI', 'NDRE', 'EVI']
            )

            if province_data:
                file_path = save_province_data(province_data)
                results.append({
                    'province': province_name,
                    'status': 'success',
                    'file': str(file_path)
                })
            else:
                results.append({
                    'province': province_name,
                    'status': 'skipped',
                    'reason': 'No data'
                })

        except Exception as e:
            print(f"\n❌ Error processing {province_name}: {e}")
            import traceback
            traceback.print_exc()

            results.append({
                'province': province_name,
                'status': 'error',
                'error': str(e)
            })

    # Summary
    print("\n" + "=" * 60)
    print("PROCESSING SUMMARY")
    print("=" * 60)

    success = [r for r in results if r['status'] == 'success']
    errors = [r for r in results if r['status'] == 'error']
    skipped = [r for r in results if r['status'] == 'skipped']

    print(f"✅ Success: {len(success)}")
    print(f"❌ Errors: {len(errors)}")
    print(f"⏭️  Skipped: {len(skipped)}")

    if success:
        print(f"\nProcessed provinces:")
        for r in success:
            print(f"  • {r['province']}: {r['file']}")

    if errors:
        print(f"\nErrors:")
        for r in errors:
            print(f"  • {r['province']}: {r['error']}")

    print("\n" + "=" * 60)
    print("Next steps:")
    print("1. Set up Neon PostgreSQL database")
    print("2. Load time series into database")
    print("3. Build Streamlit health map")
    print("=" * 60)


if __name__ == '__main__':
    main()
