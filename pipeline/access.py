"""
Google Earth Engine access module for Sentinel-2 imagery.

This module handles:
- GEE authentication
- Sentinel-2 L2A image collection access
- AOI and date filtering
- Cloud probability filtering
- Image export to local storage or GCS
"""

import ee
import geemap
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple, Dict
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def authenticate_gee():
    """
    Authenticate with Google Earth Engine.

    Uses service account credentials from environment variables:
    - GEE_SERVICE_ACCOUNT_EMAIL
    - GEE_PRIVATE_KEY_PATH

    Falls back to standard authentication if service account not configured.
    """
    service_account = os.getenv('GEE_SERVICE_ACCOUNT_EMAIL')
    key_path = os.getenv('GEE_PRIVATE_KEY_PATH')

    if service_account and key_path and Path(key_path).exists():
        # Service account authentication (production)
        print(f"Authenticating with service account: {service_account}")
        credentials = ee.ServiceAccountCredentials(service_account, key_path)
        ee.Initialize(credentials)
        print("✅ GEE initialized with service account")
    else:
        # Standard authentication (development)
        print("Service account not configured, using standard authentication")
        try:
            # Initialize with high-volume endpoint (uses earthengine credentials)
            ee.Initialize(opt_url='https://earthengine-highvolume.googleapis.com')
            print("✅ GEE initialized with cached credentials")
        except Exception as e:
            print(f"❌ GEE initialization failed: {e}")
            print("\nTo fix:")
            print("1. Run: earthengine authenticate")
            print("2. Run: earthengine set_project YOUR_PROJECT_ID")
            raise


def get_sentinel2_collection(
    aoi_path: str = "data/geo/aegean_aoi.geojson",
    start_date: str = "2018-01-01",
    end_date: str = "2024-12-31",
    max_cloud_probability: int = 20,
    product: str = "L2A"
) -> ee.ImageCollection:
    """
    Get Sentinel-2 image collection for specified AOI and date range.

    Args:
        aoi_path: Path to AOI GeoJSON file
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        max_cloud_probability: Maximum cloud probability (0-100)
        product: Sentinel-2 product type ("L2A" or "L1C")

    Returns:
        ee.ImageCollection filtered by AOI, dates, and cloud probability
    """
    # Load AOI
    with open(aoi_path, 'r') as f:
        aoi_geojson = json.load(f)

    # Convert to EE geometry
    aoi_coords = aoi_geojson['features'][0]['geometry']['coordinates']
    aoi_ee = ee.Geometry.Polygon(aoi_coords)

    # Select collection
    if product == "L2A":
        collection_id = "COPERNICUS/S2_SR_HARMONIZED"  # Surface Reflectance (L2A)
    elif product == "L1C":
        collection_id = "COPERNICUS/S2_HARMONIZED"     # Top-of-Atmosphere (L1C)
    else:
        raise ValueError(f"Unknown product: {product}. Use 'L2A' or 'L1C'")

    # Filter collection
    collection = (ee.ImageCollection(collection_id)
                  .filterBounds(aoi_ee)
                  .filterDate(start_date, end_date)
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloud_probability)))

    print(f"✅ Found {collection.size().getInfo()} Sentinel-2 {product} images")
    print(f"   AOI: {Path(aoi_path).name}")
    print(f"   Date range: {start_date} to {end_date}")
    print(f"   Max cloud: {max_cloud_probability}%")

    return collection


def get_date_ranges(
    start_date: str,
    end_date: str,
    composite_days: int = 10
) -> List[Tuple[str, str]]:
    """
    Generate date ranges for composite generation.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        composite_days: Days per composite period

    Returns:
        List of (start, end) date tuples
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    ranges = []
    current = start

    while current < end:
        next_date = current + timedelta(days=composite_days)
        if next_date > end:
            next_date = end

        ranges.append((
            current.strftime("%Y-%m-%d"),
            next_date.strftime("%Y-%m-%d")
        ))

        current = next_date

    return ranges


def select_olive_season_images(
    collection: ee.ImageCollection,
    year: int,
    month_start: int = 4,
    month_end: int = 10
) -> ee.ImageCollection:
    """
    Filter collection to olive growing season (April-October).

    Args:
        collection: Sentinel-2 image collection
        year: Year to filter
        month_start: Growing season start month (1-12)
        month_end: Growing season end month (1-12)

    Returns:
        Filtered image collection
    """
    start_date = f"{year}-{month_start:02d}-01"

    # Calculate last day of end month
    if month_end == 12:
        end_date = f"{year}-12-31"
    else:
        end_year = year if month_end < 12 else year + 1
        end_month = month_end if month_end < 12 else 1
        end_date = f"{end_year}-{end_month:02d}-01"

    return collection.filterDate(start_date, end_date)


def export_image_to_drive(
    image: ee.Image,
    description: str,
    folder: str = "oliveintel",
    scale: int = 10,
    region: Optional[ee.Geometry] = None,
    crs: str = "EPSG:4326"
) -> ee.batch.Task:
    """
    Export Earth Engine image to Google Drive.

    Args:
        image: EE image to export
        description: Export task description
        folder: Google Drive folder name
        scale: Export resolution in meters
        region: Export region (defaults to image geometry)
        crs: Coordinate reference system

    Returns:
        Export task (call .start() to begin export)
    """
    task = ee.batch.Export.image.toDrive(
        image=image,
        description=description,
        folder=folder,
        scale=scale,
        region=region,
        crs=crs,
        maxPixels=1e13,
        fileFormat='GeoTIFF',
        formatOptions={'cloudOptimized': True}  # Create COG
    )

    return task


def export_collection_stats(
    collection: ee.ImageCollection,
    output_path: str = "data/interim/collection_stats.json"
) -> Dict:
    """
    Export collection metadata and statistics.

    Args:
        collection: Image collection
        output_path: Output JSON file path

    Returns:
        Dictionary with collection statistics
    """
    stats = {
        'count': collection.size().getInfo(),
        'date_range': {
            'start': ee.Date(collection.first().get('system:time_start')).format().getInfo(),
            'end': ee.Date(collection.sort('system:time_start', False).first().get('system:time_start')).format().getInfo()
        },
        'images': []
    }

    # Get list of all images
    image_list = collection.toList(collection.size())

    for i in range(min(stats['count'], 1000)):  # Limit to 1000 images
        try:
            img = ee.Image(image_list.get(i))
            info = {
                'id': img.id().getInfo(),
                'date': ee.Date(img.get('system:time_start')).format().getInfo(),
                'cloud_cover': img.get('CLOUDY_PIXEL_PERCENTAGE').getInfo()
            }
            stats['images'].append(info)
        except Exception as e:
            print(f"Warning: Could not get info for image {i}: {e}")
            continue

    # Save to file
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(stats, f, indent=2)

    print(f"✅ Saved collection stats to {output_path}")

    return stats


def main():
    """Example usage of GEE access functions."""
    print("OliveIntel - GEE Access Module")
    print("=" * 50)

    # Authenticate
    authenticate_gee()

    # Get Sentinel-2 collection for Aegean region
    collection = get_sentinel2_collection(
        aoi_path="data/geo/aegean_aoi.geojson",
        start_date="2023-01-01",
        end_date="2023-12-31",
        max_cloud_probability=20
    )

    # Export collection statistics
    stats = export_collection_stats(collection)
    print(f"\nCollection summary:")
    print(f"  Total images: {stats['count']}")
    print(f"  Date range: {stats['date_range']['start']} to {stats['date_range']['end']}")

    # Example: Get growing season only
    growing_season = select_olive_season_images(collection, 2023, month_start=4, month_end=10)
    print(f"\nGrowing season (Apr-Oct 2023): {growing_season.size().getInfo()} images")


if __name__ == "__main__":
    main()
