"""
Utility functions for the OliveIntel pipeline.
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import geopandas as gpd
from shapely.geometry import shape, mapping


def load_aoi(aoi_path: str = "data/geo/aegean_aoi.geojson") -> Dict:
    """
    Load Area of Interest (AOI) GeoJSON.

    Args:
        aoi_path: Path to AOI GeoJSON file

    Returns:
        GeoJSON feature collection as dict
    """
    with open(aoi_path, 'r') as f:
        return json.load(f)


def get_aoi_bounds(aoi_path: str = "data/geo/aegean_aoi.geojson") -> Tuple[float, float, float, float]:
    """
    Get bounding box coordinates from AOI.

    Args:
        aoi_path: Path to AOI GeoJSON file

    Returns:
        (min_lon, min_lat, max_lon, max_lat)
    """
    gdf = gpd.read_file(aoi_path)
    bounds = gdf.total_bounds  # (minx, miny, maxx, maxy)
    return tuple(bounds)


def load_provinces(
    provinces_path: str = "data/geo/turkey_provinces.geojson",
    region_filter: Optional[str] = None
) -> gpd.GeoDataFrame:
    """
    Load Turkish province boundaries.

    Args:
        provinces_path: Path to provinces GeoJSON
        region_filter: Optional region name to filter (e.g., "Aegean")

    Returns:
        GeoDataFrame with province geometries
    """
    gdf = gpd.read_file(provinces_path)

    if region_filter:
        gdf = gdf[gdf['region'].str.lower() == region_filter.lower()]

    return gdf


def geojson_to_ee_geometry(geojson_path: str):
    """
    Convert GeoJSON file to Earth Engine Geometry.

    Args:
        geojson_path: Path to GeoJSON file

    Returns:
        ee.Geometry object
    """
    try:
        import ee
    except ImportError:
        raise ImportError("earthengine-api not installed. Run: pip install earthengine-api")

    with open(geojson_path, 'r') as f:
        geojson = json.load(f)

    # Get first feature's geometry
    if geojson['type'] == 'FeatureCollection':
        coords = geojson['features'][0]['geometry']['coordinates']
        geom_type = geojson['features'][0]['geometry']['type']
    else:
        coords = geojson['geometry']['coordinates']
        geom_type = geojson['geometry']['type']

    if geom_type == 'Polygon':
        return ee.Geometry.Polygon(coords)
    elif geom_type == 'MultiPolygon':
        return ee.Geometry.MultiPolygon(coords)
    else:
        raise ValueError(f"Unsupported geometry type: {geom_type}")


def create_output_dirs():
    """Create all required output directories if they don't exist."""
    dirs = [
        "data/raw",
        "data/interim",
        "data/processed",
        "data/labels",
        "data/geo",
        "models/artifacts",
    ]

    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    print(f"Created {len(dirs)} output directories")


def get_olive_provinces() -> List[str]:
    """
    Get list of major olive-producing provinces in Turkey.

    Returns:
        List of province names
    """
    return [
        # Aegean (primary oil production)
        "İzmir",
        "Aydın",
        "Balıkesir",
        "Manisa",
        "Muğla",
        "Çanakkale",

        # Marmara (table olives)
        "Bursa",
        "Edirne",

        # Mediterranean
        "Antalya",
        "Mersin",
        "Hatay",

        # Southeast Anatolia (oil)
        "Gaziantep",
        "Kilis",
        "Şanlıurfa",
        "Kahramanmaraş",
        "Mardin",
    ]


def province_to_nuts3(province_name: str) -> Optional[str]:
    """
    Map province name to NUTS-3 code.

    Args:
        province_name: Turkish province name

    Returns:
        NUTS-3 code or None if not found
    """
    # Aegean region codes (TR3)
    mapping = {
        "İzmir": "TR31",
        "Aydın": "TR32",
        "Manisa": "TR33",
        "Muğla": "TR32",  # Part of Aydın subregion
        "Balıkesir": "TR22",  # Balıkesir subregion
        "Çanakkale": "TR22",

        # Marmara
        "Bursa": "TR41",
        "Edirne": "TR21",

        # Mediterranean
        "Antalya": "TR61",
        "Mersin": "TR62",
        "Hatay": "TR63",

        # Southeast Anatolia
        "Gaziantep": "TRC1",
        "Kilis": "TRC2",
        "Şanlıurfa": "TRC2",
        "Kahramanmaraş": "TRC3",
        "Mardin": "TRC3",
    }

    return mapping.get(province_name)
