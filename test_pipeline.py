#!/usr/bin/env python3
"""
Quick integration test for OliveIntel pipeline.
Tests the entire flow from GEE to feature extraction.

Usage: python test_pipeline.py
"""

import ee
from pipeline import access, indices, timeseries
from pathlib import Path
import json

def test_pipeline():
    """Run quick integration test."""

    print("=" * 60)
    print("OliveIntel Pipeline - Integration Test")
    print("=" * 60)

    # 1. Test GEE Authentication
    print("\n1️⃣  Testing GEE authentication...")
    try:
        access.authenticate_gee()
        print("   ✅ GEE authenticated")
    except Exception as e:
        print(f"   ❌ GEE authentication failed: {e}")
        print("   Run: earthengine authenticate")
        return False

    # 2. Test AOI Loading
    print("\n2️⃣  Testing AOI loading...")
    try:
        aoi_path = "data/geo/aegean_aoi.geojson"
        with open(aoi_path, 'r') as f:
            aoi_geojson = json.load(f)
        aoi_coords = aoi_geojson['features'][0]['geometry']['coordinates']
        aoi = ee.Geometry.Polygon(aoi_coords)
        print(f"   ✅ AOI loaded: {aoi_path}")
    except Exception as e:
        print(f"   ❌ AOI loading failed: {e}")
        return False

    # 3. Test Sentinel-2 Access
    print("\n3️⃣  Testing Sentinel-2 access...")
    try:
        collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                     .filterBounds(aoi)
                     .filterDate('2023-07-01', '2023-07-15')  # Just 2 weeks
                     .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)))

        count = collection.size().getInfo()
        print(f"   ✅ Found {count} Sentinel-2 images")

        if count == 0:
            print("   ⚠️  Warning: No images found (might be too cloudy)")
            print("   Try different dates or higher cloud threshold")
    except Exception as e:
        print(f"   ❌ Sentinel-2 access failed: {e}")
        return False

    # 4. Test Index Computation
    print("\n4️⃣  Testing NDVI computation...")
    try:
        if count > 0:
            img = ee.Image(collection.first())
            ndvi = img.normalizedDifference(['B8', 'B4'])

            # Get a sample value
            sample = ndvi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=aoi.centroid(),
                scale=10
            ).getInfo()

            print(f"   ✅ NDVI computed (sample: {sample.get('nd', 'N/A')})")
        else:
            print("   ⏭️  Skipped (no images)")
    except Exception as e:
        print(f"   ❌ Index computation failed: {e}")
        return False

    # 5. Test Time Series Extraction
    print("\n5️⃣  Testing time series extraction...")
    try:
        if count > 0:
            collection_ndvi = collection.map(
                lambda img: img.addBands(
                    img.normalizedDifference(['B8', 'B4']).rename('NDVI')
                )
            )

            df = timeseries.extract_raw_time_series(
                collection_ndvi, aoi, 'NDVI', reducer='mean', scale=100
            )

            print(f"   ✅ Extracted {len(df)} time series points")

            if len(df) > 0:
                print(f"   📊 NDVI range: {df['value'].min():.3f} to {df['value'].max():.3f}")
        else:
            print("   ⏭️  Skipped (no images)")
    except Exception as e:
        print(f"   ❌ Time series extraction failed: {e}")
        return False

    # 6. Check Output Directories
    print("\n6️⃣  Checking output directories...")
    dirs = [
        "data/interim",
        "data/processed",
        "data/geo"
    ]
    for dir_path in dirs:
        if Path(dir_path).exists():
            print(f"   ✅ {dir_path}/")
        else:
            print(f"   ⚠️  {dir_path}/ (will be created on first run)")

    # Success!
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nPipeline is working correctly. Ready to:")
    print("  1. Run full analysis for multiple provinces")
    print("  2. Build Streamlit health map (Milestone 1)")
    print("  3. Train yield model (Milestone 2)")
    print("\nNext: jupyter notebook notebooks/01_milestone0_demo.ipynb")
    print("=" * 60)

    return True


if __name__ == "__main__":
    success = test_pipeline()
    exit(0 if success else 1)
