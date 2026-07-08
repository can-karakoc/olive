"""Convert Google Earth KML to GeoJSON for training data."""

import sys
from pathlib import Path
import json
import xml.etree.ElementTree as ET

def parse_kml_to_geojson(kml_path, output_path=None):
    """
    Convert KML from Google Earth to GeoJSON.

    Args:
        kml_path: Path to KML file
        output_path: Output GeoJSON path (optional)

    Returns:
        GeoJSON dict
    """

    if output_path is None:
        output_path = Path(kml_path).with_suffix('.geojson')

    print(f"Converting {kml_path} to GeoJSON...")

    # Parse KML
    tree = ET.parse(kml_path)
    root = tree.getroot()

    # Handle KML namespace
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}

    features = []

    # Find all Placemarks
    for placemark in root.findall('.//kml:Placemark', ns):
        name = placemark.find('kml:name', ns)
        desc = placemark.find('kml:description', ns)
        polygon = placemark.find('.//kml:Polygon', ns)

        if polygon is None:
            continue

        # Get coordinates
        coords_elem = polygon.find('.//kml:coordinates', ns)

        if coords_elem is None:
            continue

        coords_text = coords_elem.text.strip()
        coords = []

        for coord in coords_text.split():
            parts = coord.split(',')
            if len(parts) >= 2:
                lon, lat = float(parts[0]), float(parts[1])
                coords.append([lon, lat])

        if len(coords) < 3:
            continue

        # Parse description for class
        properties = {
            'name': name.text if name is not None else 'unknown',
            'class': 'Unknown'
        }

        if desc is not None and desc.text:
            # Parse "class=Olive, province=İzmir" format
            for part in desc.text.split(','):
                if '=' in part:
                    key, value = part.strip().split('=', 1)
                    properties[key.strip()] = value.strip()

        # Create GeoJSON feature
        feature = {
            'type': 'Feature',
            'properties': properties,
            'geometry': {
                'type': 'Polygon',
                'coordinates': [coords]  # Wrap in array for Polygon
            }
        }

        features.append(feature)

    # Create GeoJSON
    geojson = {
        'type': 'FeatureCollection',
        'features': features
    }

    # Save
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    # Summary
    class_counts = {}
    for f in features:
        cls = f['properties'].get('class', 'Unknown')
        class_counts[cls] = class_counts.get(cls, 0) + 1

    print(f"\n✅ Converted {len(features)} polygons")
    print(f"   Output: {output_path}")
    print(f"\n   Class distribution:")
    for cls, count in sorted(class_counts.items()):
        print(f"     {cls}: {count}")

    return geojson


def main():
    if len(sys.argv) < 2:
        print("Usage: python convert_kml_to_geojson.py <kml_file>")
        print("\nExample:")
        print("  python scripts/convert_kml_to_geojson.py data/ground_truth/training_samples.kml")
        return

    kml_path = sys.argv[1]

    if not Path(kml_path).exists():
        print(f"❌ File not found: {kml_path}")
        return

    parse_kml_to_geojson(kml_path)

    print("\n✅ Ready for classifier training!")
    print("   Next: python scripts/train_classifier.py")


if __name__ == '__main__':
    main()
