"""
Create Aegean province boundaries using Google Earth Engine's GADM dataset.

Uses Earth Engine's built-in GADM (Global Administrative Areas) dataset
to extract province boundaries without downloading large files.
"""

import ee
import json
from pathlib import Path
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pipeline import access

# Target provinces (English names in GADM)
TARGET_PROVINCES = {
    'Izmir': 'İzmir',
    'Aydin': 'Aydın',
    'Balikesir': 'Balıkesir',
    'Manisa': 'Manisa',
    'Mugla': 'Muğla'
}


def get_province_boundaries():
    """Fetch province boundaries from Earth Engine GADM dataset."""

    print("Fetching Turkey province boundaries from GEE...")

    # GADM level 1 (provinces)
    provinces = ee.FeatureCollection('FAO/GAUL/2015/level1')

    # Filter to Turkey
    turkey = provinces.filter(ee.Filter.eq('ADM0_NAME', 'Turkey'))

    print(f"Turkey provinces available in GADM")

    # Get list of province names
    names = turkey.aggregate_array('ADM1_NAME').getInfo()
    print(f"Found {len(names)} provinces")
    print(f"Sample names: {names[:10]}")

    return turkey


def filter_aegean_provinces(turkey_provinces):
    """Filter to target Aegean provinces."""

    print(f"\nFiltering to Aegean provinces...")

    aegean_features = []

    for gadm_name, turkish_name in TARGET_PROVINCES.items():
        print(f"  Looking for: {gadm_name}")

        # Try exact match first
        province = turkey_provinces.filter(ee.Filter.eq('ADM1_NAME', gadm_name))

        count = province.size().getInfo()
        if count == 0:
            # Try case-insensitive
            all_names = turkey_provinces.aggregate_array('ADM1_NAME').getInfo()
            matches = [n for n in all_names if gadm_name.lower() in n.lower()]
            if matches:
                print(f"    ⚠️  Not found. Similar: {matches}")
                province = turkey_provinces.filter(ee.Filter.eq('ADM1_NAME', matches[0]))
            else:
                print(f"    ❌ Not found")
                continue

        if province.size().getInfo() > 0:
            feature = ee.Feature(province.first())
            print(f"    ✅ Found: {feature.get('ADM1_NAME').getInfo()}")
            aegean_features.append(feature)

    # Create FeatureCollection
    aegean = ee.FeatureCollection(aegean_features)

    print(f"\n✅ Matched {len(aegean_features)} provinces")

    return aegean


def export_boundaries(aegean_fc, output_dir='data/geo'):
    """Export province boundaries to local files."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"\nExporting boundaries to {output_dir}...")

    # Get features as list
    features = aegean_fc.getInfo()['features']

    province_data = []

    for idx, feature in enumerate(features, 1):
        props = feature['properties']
        geom = feature['geometry']

        # Extract name
        gadm_name = props.get('ADM1_NAME', f'Province{idx}')
        turkish_name = TARGET_PROVINCES.get(gadm_name, gadm_name)

        print(f"\n  Processing: {turkish_name} ({gadm_name})")

        # Compute area (rough estimate from geometry bounds)
        coords = geom['coordinates']
        if geom['type'] == 'MultiPolygon':
            # Flatten MultiPolygon
            flat_coords = []
            for poly in coords:
                for ring in poly:
                    flat_coords.extend(ring)
        else:
            flat_coords = coords[0]

        lons = [c[0] for c in flat_coords]
        lats = [c[1] for c in flat_coords]

        # Rough area estimate (assumes ~100km per degree at this latitude)
        area_estimate_ha = (max(lons) - min(lons)) * (max(lats) - min(lats)) * 100 * 100 * 100

        province_info = {
            'province_id': idx,
            'name_en': turkish_name,
            'gadm_name': gadm_name,
            'area_ha': int(area_estimate_ha),
            'bounds': {
                'lon_min': min(lons),
                'lon_max': max(lons),
                'lat_min': min(lats),
                'lat_max': max(lats)
            }
        }

        province_data.append(province_info)

        # Save individual province file
        province_filename = turkish_name.lower().replace('ı', 'i').replace('ğ', 'g') + '_boundary.geojson'
        province_path = output_path / province_filename

        province_geojson = {
            'type': 'FeatureCollection',
            'features': [{
                'type': 'Feature',
                'properties': province_info,
                'geometry': geom
            }]
        }

        with open(province_path, 'w', encoding='utf-8') as f:
            json.dump(province_geojson, f, ensure_ascii=False, indent=2)

        print(f"    ✅ Saved: {province_path}")
        print(f"    Area: ~{area_estimate_ha:,.0f} ha")

    # Save combined file
    combined_geojson = {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'properties': info,
                'geometry': features[idx]['geometry']
            }
            for idx, info in enumerate(province_data)
        ]
    }

    combined_path = output_path / 'aegean_provinces.geojson'
    with open(combined_path, 'w', encoding='utf-8') as f:
        json.dump(combined_geojson, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Combined file saved: {combined_path}")

    # Save metadata CSV
    metadata_path = output_path / 'aegean_provinces_metadata.csv'
    with open(metadata_path, 'w', encoding='utf-8') as f:
        f.write('province_id,name_en,gadm_name,area_ha,lon_min,lon_max,lat_min,lat_max\n')
        for info in province_data:
            b = info['bounds']
            f.write(f"{info['province_id']},{info['name_en']},{info['gadm_name']},"
                   f"{info['area_ha']},{b['lon_min']:.4f},{b['lon_max']:.4f},"
                   f"{b['lat_min']:.4f},{b['lat_max']:.4f}\n")

    print(f"✅ Metadata saved: {metadata_path}")

    return province_data


def main():
    print("OliveIntel - Province Boundary Creation (GEE)")
    print("=" * 60)

    # Authenticate
    access.authenticate_gee()

    # Get Turkey provinces
    turkey = get_province_boundaries()

    # Filter to Aegean
    aegean = filter_aegean_provinces(turkey)

    # Export
    province_data = export_boundaries(aegean)

    print("\n" + "=" * 60)
    print("✅ Province boundaries ready!")
    print(f"\nExtracted {len(province_data)} provinces:")
    for info in province_data:
        print(f"  • {info['name_en']} (~{info['area_ha']:,.0f} ha)")

    print("\nNext steps:")
    print("1. Set up Neon PostgreSQL database")
    print("2. Run scripts/process_provinces.py to extract time series")
    print("3. Build Streamlit health map")


if __name__ == '__main__':
    main()
