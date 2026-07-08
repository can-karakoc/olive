"""
Download Turkish province boundaries from GADM.

Fetches admin level 1 (province) boundaries for Turkey and filters to
the 5 target Aegean provinces: İzmir, Aydın, Balıkesir, Manisa, Muğla.
"""

import requests
import geopandas as gpd
import json
from pathlib import Path

# Target provinces
TARGET_PROVINCES = ['İzmir', 'Aydın', 'Balıkesir', 'Manisa', 'Muğla']

def download_turkey_provinces():
    """Download Turkey admin level 1 boundaries from GADM."""

    # GADM API for Turkey level 1 (provinces)
    url = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_TUR_1.json"

    print("Downloading Turkey province boundaries from GADM...")
    print(f"URL: {url}")

    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()

        print(f"✅ Downloaded {len(response.content) / 1024:.1f} KB")

        # Parse GeoJSON
        geojson = response.json()

        # Convert to GeoDataFrame
        gdf = gpd.GeoDataFrame.from_features(geojson['features'])

        print(f"Total provinces: {len(gdf)}")
        print(f"Columns: {gdf.columns.tolist()}")

        return gdf

    except requests.exceptions.RequestException as e:
        print(f"❌ Download failed: {e}")
        raise


def filter_aegean_provinces(gdf):
    """Filter to target Aegean provinces."""

    # GADM uses NAME_1 for province names
    print(f"\nFiltering to Aegean provinces: {', '.join(TARGET_PROVINCES)}")

    # Filter
    aegean = gdf[gdf['NAME_1'].isin(TARGET_PROVINCES)].copy()

    print(f"Matched provinces: {len(aegean)}")
    print(f"  {', '.join(aegean['NAME_1'].tolist())}")

    if len(aegean) < len(TARGET_PROVINCES):
        missing = set(TARGET_PROVINCES) - set(aegean['NAME_1'])
        print(f"⚠️  Missing provinces: {missing}")
        print(f"Available names: {sorted(gdf['NAME_1'].unique())[:10]}...")

    # Simplify geometry to reduce file size (tolerance ~100m)
    print("\nSimplifying geometries...")
    aegean['geometry'] = aegean['geometry'].simplify(tolerance=0.001)

    # Add useful columns
    aegean['province_id'] = range(1, len(aegean) + 1)
    aegean['name_en'] = aegean['NAME_1']

    # Compute area in hectares
    aegean_proj = aegean.to_crs('EPSG:32635')  # UTM 35N (covers Aegean)
    aegean['area_ha'] = aegean_proj.geometry.area / 10000

    print(f"Area statistics (ha):")
    for _, row in aegean.iterrows():
        print(f"  {row['name_en']}: {row['area_ha']:,.0f} ha")

    return aegean


def save_outputs(gdf, output_dir='data/geo'):
    """Save province boundaries in multiple formats."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # GeoJSON (for GEE/web)
    geojson_path = output_path / 'aegean_provinces.geojson'
    gdf.to_file(geojson_path, driver='GeoJSON')
    print(f"✅ Saved GeoJSON: {geojson_path}")

    # CSV with metadata (geometry as WKT)
    csv_path = output_path / 'aegean_provinces_metadata.csv'
    metadata = gdf[['province_id', 'name_en', 'area_ha']].copy()
    metadata.to_csv(csv_path, index=False)
    print(f"✅ Saved metadata: {csv_path}")

    # Individual province files (for testing)
    for _, row in gdf.iterrows():
        province_name = row['name_en'].lower().replace('ı', 'i')
        province_path = output_path / f'{province_name}_boundary.geojson'

        # Create single-feature GeoJSON
        province_geojson = {
            'type': 'FeatureCollection',
            'features': [{
                'type': 'Feature',
                'properties': {
                    'province_id': int(row['province_id']),
                    'name': row['name_en'],
                    'area_ha': float(row['area_ha'])
                },
                'geometry': row['geometry'].__geo_interface__
            }]
        }

        with open(province_path, 'w') as f:
            json.dump(province_geojson, f)

        print(f"   → {province_path}")

    print(f"\n✅ All province boundaries saved to {output_dir}/")


def main():
    print("OliveIntel - Province Boundary Download")
    print("=" * 60)

    # Download Turkey provinces
    gdf_turkey = download_turkey_provinces()

    # Filter to Aegean
    gdf_aegean = filter_aegean_provinces(gdf_turkey)

    # Save outputs
    save_outputs(gdf_aegean)

    print("\n" + "=" * 60)
    print("✅ Province boundaries ready for pipeline processing")
    print("\nNext steps:")
    print("1. Set up Neon PostgreSQL database")
    print("2. Run scripts/process_provinces.py to extract time series")
    print("3. Build Streamlit app")


if __name__ == '__main__':
    main()
