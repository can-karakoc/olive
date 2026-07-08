"""
Preprocessing module for Sentinel-2 imagery.

Handles:
- Cloud and shadow masking using s2cloudless
- Atmospheric correction (if using L1C -> L2A)
- Temporal compositing (median, mean, percentile)
- Quality assessment and visualization
"""

import ee
import geemap
import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple
import json
from datetime import datetime


def add_cloud_bands(img: ee.Image) -> ee.Image:
    """
    Add s2cloudless cloud probability band to Sentinel-2 image.

    s2cloudless is a LightGBM-based cloud detection model trained on
    Sentinel-2 imagery. More accurate than the default QA60 band.

    Args:
        img: Sentinel-2 L2A image

    Returns:
        Image with 'probability' band added (0-100 cloud probability)
    """
    # Get s2cloudless cloud probability
    cloud_prob = ee.Image(img.get('s2cloudless')).select('probability')
    return img.addBands(cloud_prob)


def add_shadow_bands(img: ee.Image) -> ee.Image:
    """
    Add cloud shadow mask band.

    Estimates cloud shadows by:
    1. Projecting clouds in sun direction
    2. Finding dark pixels (low NIR)
    3. Intersecting projected clouds with dark pixels

    Args:
        img: Sentinel-2 image with cloud probability band

    Returns:
        Image with 'cloud_shadow' band added (1=shadow, 0=clear)
    """
    # Cloud probability threshold
    cloud_prob_thresh = 50
    clouds = img.select('probability').gt(cloud_prob_thresh)

    # NIR dark pixel threshold
    dark_pixels = img.select('B8').lt(2000)

    # Get sun azimuth and zenith
    mean_azimuth = img.get('MEAN_SOLAR_AZIMUTH_ANGLE')
    mean_zenith = img.get('MEAN_SOLAR_ZENITH_ANGLE')

    # Project cloud shadows
    # Assume cloud height of 200m and calculate shadow offset
    shadow_azimuth = ee.Number(90).subtract(ee.Number(mean_azimuth))
    cloud_proj_dist = (
        ee.Number(200)  # Cloud height in meters
        .multiply(ee.Number(mean_zenith).divide(180).multiply(3.14159).tan())
    )

    # Project clouds in sun direction
    # Cast to int for directionalDistanceTransform
    cloud_proj = clouds.directionalDistanceTransform(
        shadow_azimuth,
        cloud_proj_dist.round().int()
    )
    cloud_proj = cloud_proj.reproject(crs=img.select('B8').projection(), scale=10)
    cloud_proj = cloud_proj.select('distance').mask()

    # Identify cloud shadows
    shadows = cloud_proj.multiply(dark_pixels).rename('cloud_shadow')

    return img.addBands(shadows)


def mask_clouds_and_shadows(img: ee.Image, cloud_prob_thresh: int = 40) -> ee.Image:
    """
    Apply cloud and shadow mask to image.

    Args:
        img: Sentinel-2 image with cloud probability and shadow bands
        cloud_prob_thresh: Cloud probability threshold (0-100)

    Returns:
        Masked image
    """
    # Mask clouds
    clouds = img.select('probability').lt(cloud_prob_thresh)

    # Mask shadows
    shadows = img.select('cloud_shadow').Not()

    # Combine masks
    mask = clouds.And(shadows)

    return img.updateMask(mask)


def get_s2_sr_cld_col(
    aoi: ee.Geometry,
    start_date: str,
    end_date: str,
    cloud_filter: int = 60
) -> ee.ImageCollection:
    """
    Get Sentinel-2 Surface Reflectance collection with s2cloudless.

    Joins Sentinel-2 SR with s2cloudless cloud probability.

    Args:
        aoi: Area of interest geometry
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        cloud_filter: Maximum cloud cover percentage for pre-filtering

    Returns:
        Image collection with cloud probability bands
    """
    # Sentinel-2 Surface Reflectance
    s2_sr_col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                 .filterBounds(aoi)
                 .filterDate(start_date, end_date)
                 .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', cloud_filter)))

    # s2cloudless cloud probability
    s2_cloudless_col = (ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
                        .filterBounds(aoi)
                        .filterDate(start_date, end_date))

    # Join collections based on system:index
    joined = ee.Join.saveFirst('s2cloudless').apply(
        primary=s2_sr_col,
        secondary=s2_cloudless_col,
        condition=ee.Filter.equals(
            leftField='system:index',
            rightField='system:index'
        )
    )

    return ee.ImageCollection(joined)


def create_composite(
    collection: ee.ImageCollection,
    method: str = 'median',
    clip_to_aoi: bool = True,
    aoi: Optional[ee.Geometry] = None
) -> ee.Image:
    """
    Create temporal composite from image collection.

    Args:
        collection: Preprocessed image collection (clouds masked)
        method: Compositing method ('median', 'mean', 'max', 'percentile_10', etc.)
        clip_to_aoi: Whether to clip result to AOI
        aoi: Area of interest geometry (required if clip_to_aoi=True)

    Returns:
        Composite image
    """
    if method == 'median':
        composite = collection.median()
    elif method == 'mean':
        composite = collection.mean()
    elif method == 'max':
        composite = collection.max()
    elif method.startswith('percentile_'):
        percentile = int(method.split('_')[1])
        composite = collection.reduce(ee.Reducer.percentile([percentile]))
    else:
        raise ValueError(f"Unknown composite method: {method}")

    if clip_to_aoi and aoi:
        composite = composite.clip(aoi)

    return composite


def preprocess_collection(
    collection: ee.ImageCollection,
    cloud_prob_thresh: int = 40
) -> ee.ImageCollection:
    """
    Apply full preprocessing pipeline to collection.

    Args:
        collection: Sentinel-2 SR + s2cloudless joined collection
        cloud_prob_thresh: Cloud probability threshold

    Returns:
        Preprocessed collection with clouds/shadows masked
    """
    # Add cloud probability
    collection = collection.map(add_cloud_bands)

    # Add shadow mask
    collection = collection.map(add_shadow_bands)

    # Apply cloud and shadow mask
    collection = collection.map(
        lambda img: mask_clouds_and_shadows(img, cloud_prob_thresh)
    )

    return collection


def create_periodic_composites(
    aoi: ee.Geometry,
    start_date: str,
    end_date: str,
    days_per_composite: int = 10,
    cloud_prob_thresh: int = 40,
    composite_method: str = 'median'
) -> List[Tuple[str, str, ee.Image]]:
    """
    Create periodic composites (e.g., 10-day composites).

    Args:
        aoi: Area of interest
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        days_per_composite: Days per composite period
        cloud_prob_thresh: Cloud probability threshold
        composite_method: Compositing method

    Returns:
        List of (start_date, end_date, composite_image) tuples
    """
    from datetime import datetime, timedelta

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    composites = []
    current = start

    while current < end:
        next_date = current + timedelta(days=days_per_composite)
        if next_date > end:
            next_date = end

        period_start = current.strftime("%Y-%m-%d")
        period_end = next_date.strftime("%Y-%m-%d")

        # Get collection for this period
        collection = get_s2_sr_cld_col(aoi, period_start, period_end)

        # Preprocess
        collection = preprocess_collection(collection, cloud_prob_thresh)

        # Create composite
        composite = create_composite(collection, method=composite_method, aoi=aoi)

        # Add metadata
        composite = composite.set({
            'system:time_start': ee.Date(period_start).millis(),
            'composite_start': period_start,
            'composite_end': period_end,
            'days': days_per_composite
        })

        composites.append((period_start, period_end, composite))

        current = next_date

    return composites


def visualize_cloud_masking(
    img_before: ee.Image,
    img_after: ee.Image,
    aoi: ee.Geometry,
    output_path: str = "data/interim/cloud_masking_comparison.html"
):
    """
    Create side-by-side visualization of before/after cloud masking.

    Args:
        img_before: Original image
        img_after: Cloud-masked image
        aoi: Area to visualize
        output_path: Output HTML file path
    """
    import geemap

    # Create map
    Map = geemap.Map()
    Map.centerObject(aoi, 10)

    # Visualization parameters for RGB
    vis_params = {
        'min': 0,
        'max': 3000,
        'bands': ['B4', 'B3', 'B2']  # RGB
    }

    # Add layers
    Map.addLayer(img_before, vis_params, 'Before Cloud Masking')
    Map.addLayer(img_after, vis_params, 'After Cloud Masking')

    # Add cloud probability if available
    if 'probability' in img_before.bandNames().getInfo():
        Map.addLayer(
            img_before.select('probability'),
            {'min': 0, 'max': 100, 'palette': ['white', 'black']},
            'Cloud Probability'
        )

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Map.to_html(output_path)
    print(f"✅ Cloud masking visualization saved to {output_path}")


def export_preprocessing_stats(
    collection_before: ee.ImageCollection,
    collection_after: ee.ImageCollection,
    output_path: str = "data/interim/preprocessing_stats.json"
) -> dict:
    """
    Export statistics comparing before/after preprocessing.

    Args:
        collection_before: Original collection
        collection_after: Preprocessed collection
        output_path: Output JSON path

    Returns:
        Statistics dictionary
    """
    stats = {
        'images_before': collection_before.size().getInfo(),
        'images_after': collection_after.size().getInfo(),
        'images_removed': (
            collection_before.size().subtract(collection_after.size()).getInfo()
        ),
        'removal_percentage': (
            collection_before.size().subtract(collection_after.size())
            .divide(collection_before.size()).multiply(100).getInfo()
        )
    }

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(stats, f, indent=2)

    print(f"✅ Preprocessing stats saved to {output_path}")
    return stats


def main():
    """Example usage of preprocessing functions."""
    print("OliveIntel - Preprocessing Module")
    print("=" * 50)

    # Initialize GEE
    try:
        ee.Initialize()
    except:
        print("Authenticating with GEE...")
        ee.Authenticate()
        ee.Initialize()

    # Load AOI
    with open("data/geo/aegean_aoi.geojson", 'r') as f:
        aoi_geojson = json.load(f)
    aoi_coords = aoi_geojson['features'][0]['geometry']['coordinates']
    aoi = ee.Geometry.Polygon(aoi_coords)

    # Get collection with cloud probability
    print("\nFetching Sentinel-2 collection...")
    collection = get_s2_sr_cld_col(
        aoi=aoi,
        start_date="2023-07-01",
        end_date="2023-07-31",
        cloud_filter=60
    )
    print(f"Found {collection.size().getInfo()} images")

    # Preprocess
    print("\nApplying cloud/shadow masking...")
    collection_preprocessed = preprocess_collection(collection, cloud_prob_thresh=40)

    # Create composite
    print("\nCreating monthly composite...")
    composite = create_composite(collection_preprocessed, method='median', aoi=aoi)

    # Visualize (example with first image)
    print("\nGenerating visualization...")
    img_before = ee.Image(collection.first())
    img_after = ee.Image(collection_preprocessed.first())
    visualize_cloud_masking(img_before, img_after, aoi)

    print("\n✅ Preprocessing complete!")


if __name__ == "__main__":
    main()
