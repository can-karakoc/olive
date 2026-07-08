"""Quick test: Extract time series for just İzmir province."""

import ee
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pipeline import access, indices, timeseries
import json

print("Testing single province extraction...")
print("=" * 60)

# Authenticate
access.authenticate_gee()

# Load İzmir boundary
with open('data/geo/i̇zmir_boundary.geojson', 'r', encoding='utf-8') as f:
    geojson = json.load(f)

geometry = ee.Geometry(geojson['features'][0]['geometry'])
print(f"✅ Loaded İzmir boundary")

# Get small sample collection (just 2024)
print("\nFetching Sentinel-2 images (2024 only)...")
collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
              .filterBounds(geometry)
              .filterDate('2024-04-01', '2024-10-31')
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)))

count = collection.size().getInfo()
print(f"Found {count} images")

# Compute NDVI
print("\nComputing NDVI...")
collection_ndvi = indices.compute_indices_collection(collection, indices=['NDVI'])

# Extract time series
print("\nExtracting time series...")
df = timeseries.extract_raw_time_series(
    collection_ndvi,
    geometry,
    band_name='NDVI',
    reducer='mean',
    scale=100
)

print(f"\n✅ Extracted {len(df)} observations")
print(f"Date range: {df['date'].min()} to {df['date'].max()}")
print(f"NDVI range: {df['value'].min():.3f} to {df['value'].max():.3f}")

# Gap-fill
df_filled = timeseries.gap_fill_linear(df, max_gap_days=30)
print(f"After gap-fill: {len(df_filled)} observations")

# Smooth
df_smooth = timeseries.smooth_savitzky_golay(df_filled, window_length=11)
print(f"After smoothing: {len(df_smooth)} observations")

# Phenology
phenology = timeseries.detect_phenology_simple(df_smooth, value_col='value_smoothed')
print(f"\n📊 Phenology:")
print(f"  Peak: {phenology['peak_date']} (NDVI={phenology['peak_value']:.3f})")
print(f"  Season length: {phenology['season_length_days']} days")

print("\n✅ Test complete!")
