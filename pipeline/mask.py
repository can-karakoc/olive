"""
Olive orchard masking module.

Version 1: NDVI threshold-based detection
- Simple but effective for MVP
- ~98% accuracy for young orchards (literature)

Future versions may use:
- CNN-based classification (TorchGeo)
- Individual tree detection (DeepForest, detectree2)
- SAM-based segmentation (segment-geospatial)
"""

import ee
import geemap
import geopandas as gpd
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape, mapping
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
import json


def create_ndvi_mask(
    img: ee.Image,
    ndvi_threshold: float = 0.4,
    min_area_sqm: float = 1000
) -> ee.Image:
    """
    Create binary olive orchard mask using NDVI threshold.

    Method:
    1. Compute NDVI
    2. Threshold at 0.4 (typical for healthy vegetation)
    3. Remove small patches (< min_area_sqm)

    Args:
        img: Sentinel-2 image
        ndvi_threshold: NDVI threshold for vegetation (0-1)
        min_area_sqm: Minimum patch area in square meters

    Returns:
        Binary mask (1 = likely olive orchard, 0 = other)
    """
    # Compute NDVI if not already present
    if 'NDVI' not in img.bandNames().getInfo():
        ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
        img = img.addBands(ndvi)

    # Threshold
    mask = img.select('NDVI').gte(ndvi_threshold)

    # Remove small patches
    # connectedPixelCount counts connected pixels
    # Keep only patches with area > min_area_sqm / 100 (since pixels are 10m x 10m = 100 sqm)
    min_pixels = int(min_area_sqm / 100)

    connected = mask.connectedPixelCount(maxSize=256)
    mask = mask.updateMask(connected.gte(min_pixels))

    return mask.rename('olive_mask')


def create_temporal_stable_mask(
    collection: ee.ImageCollection,
    ndvi_threshold: float = 0.4,
    stability_threshold: float = 0.7,
    min_area_sqm: float = 1000
) -> ee.Image:
    """
    Create olive mask from temporally stable NDVI.

    More robust than single-image threshold:
    - Requires high NDVI in multiple observations
    - Reduces false positives from annual crops

    Args:
        collection: Image collection with NDVI computed
        ndvi_threshold: NDVI threshold
        stability_threshold: Fraction of observations that must exceed threshold (0-1)
        min_area_sqm: Minimum patch area

    Returns:
        Binary mask
    """
    # Count images where NDVI > threshold
    def threshold_image(img):
        return img.select('NDVI').gte(ndvi_threshold)

    thresholded = collection.map(threshold_image)

    # Count how many times each pixel exceeds threshold
    count = thresholded.sum()

    # Total number of observations
    total = collection.size()

    # Fraction of observations exceeding threshold
    fraction = count.divide(total)

    # Stable vegetation: exceeds threshold in >stability_threshold of observations
    mask = fraction.gte(stability_threshold)

    # Remove small patches
    min_pixels = int(min_area_sqm / 100)
    connected = mask.connectedPixelCount(maxSize=256)
    mask = mask.updateMask(connected.gte(min_pixels))

    return mask.rename('olive_mask_stable')


def refine_mask_with_red_edge(
    img: ee.Image,
    base_mask: ee.Image,
    ndre_threshold: float = 0.3
) -> ee.Image:
    """
    Refine mask using red edge information.

    Olives have distinctive red edge response.
    Helps distinguish from other evergreen vegetation.

    Args:
        img: Sentinel-2 image with NDRE computed
        base_mask: Initial NDVI-based mask
        ndre_threshold: NDRE threshold

    Returns:
        Refined mask
    """
    # Compute NDRE if not present
    if 'NDRE' not in img.bandNames().getInfo():
        ndre = img.normalizedDifference(['B8', 'B5']).rename('NDRE')
        img = img.addBands(ndre)

    # Red edge criterion
    ndre_mask = img.select('NDRE').gte(ndre_threshold)

    # Combine with base mask
    refined = base_mask.And(ndre_mask)

    return refined.rename('olive_mask_refined')


def export_mask_as_raster(
    mask: ee.Image,
    aoi: ee.Geometry,
    output_path: str = "data/geo/olive_mask_v1.tif",
    scale: int = 10,
    crs: str = "EPSG:4326"
):
    """
    Export mask as GeoTIFF.

    Args:
        mask: Binary mask image
        aoi: Area of interest
        output_path: Output file path
        scale: Export resolution in meters
        crs: Coordinate reference system
    """
    # Export configuration
    task = ee.batch.Export.image.toDrive(
        image=mask.toByte(),  # Convert to uint8 to save space
        description='olive_mask_v1',
        folder='oliveintel',
        fileNamePrefix='olive_mask_v1',
        scale=scale,
        region=aoi,
        crs=crs,
        maxPixels=1e13,
        fileFormat='GeoTIFF',
        formatOptions={'cloudOptimized': True}
    )

    print(f"Starting export task...")
    print(f"  Output: {output_path}")
    print(f"  Scale: {scale}m")
    print(f"  CRS: {crs}")
    print("\nTo check status:")
    print("  ee.batch.Task.list()")
    print("\nTo start export:")
    print("  task.start()")

    return task


def mask_to_vector(
    mask_path: str,
    output_path: str = "data/geo/olive_mask_v1.geojson",
    simplify_tolerance: float = 0.001
) -> gpd.GeoDataFrame:
    """
    Convert raster mask to vector polygons.

    Args:
        mask_path: Path to mask GeoTIFF
        output_path: Output GeoJSON path
        simplify_tolerance: Simplification tolerance (degrees)

    Returns:
        GeoDataFrame with orchard polygons
    """
    print(f"Converting mask to vector...")

    # Read raster
    with rasterio.open(mask_path) as src:
        mask_array = src.read(1)
        transform = src.transform
        crs = src.crs

        # Extract shapes
        mask_shapes = shapes(mask_array, mask=(mask_array == 1), transform=transform)

    # Convert to GeoDataFrame
    geoms = []
    values = []

    for geom, value in mask_shapes:
        geoms.append(shape(geom))
        values.append(value)

    gdf = gpd.GeoDataFrame({'value': values}, geometry=geoms, crs=crs)

    # Simplify geometries
    if simplify_tolerance > 0:
        gdf['geometry'] = gdf['geometry'].simplify(simplify_tolerance, preserve_topology=True)

    # Calculate area in hectares
    gdf_proj = gdf.to_crs('EPSG:32635')  # UTM zone 35N (Turkey)
    gdf['area_ha'] = gdf_proj.geometry.area / 10000

    # Filter out very small patches (< 0.1 ha)
    gdf = gdf[gdf['area_ha'] >= 0.1].reset_index(drop=True)

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output_path, driver='GeoJSON')

    print(f"✅ Saved {len(gdf)} orchard polygons to {output_path}")
    print(f"   Total area: {gdf['area_ha'].sum():.1f} hectares")

    return gdf


def validate_mask(
    mask: ee.Image,
    aoi: ee.Geometry,
    sample_points: int = 100
) -> dict:
    """
    Generate validation statistics for mask.

    Args:
        mask: Binary mask
        aoi: Area of interest
        sample_points: Number of random points to sample

    Returns:
        Dictionary with coverage statistics
    """
    # Calculate mask coverage
    area_stats = mask.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=aoi,
        scale=10,
        maxPixels=1e13
    )

    # Total pixels in AOI
    total_stats = ee.Image(1).reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=aoi,
        scale=10,
        maxPixels=1e13
    )

    masked_pixels = area_stats.getInfo().get('olive_mask', 0)
    total_pixels = total_stats.getInfo().get('constant', 1)

    # Calculate statistics
    stats = {
        'masked_pixels': int(masked_pixels),
        'total_pixels': int(total_pixels),
        'coverage_fraction': masked_pixels / total_pixels if total_pixels > 0 else 0,
        'area_hectares': (masked_pixels * 100) / 10000,  # pixels * 100 sqm / 10000 = ha
        'area_km2': (masked_pixels * 100) / 1_000_000
    }

    return stats


def visualize_mask(
    img: ee.Image,
    mask: ee.Image,
    aoi: ee.Geometry,
    output_path: str = "data/interim/olive_mask_visualization.html"
):
    """
    Create interactive visualization of mask overlay.

    Args:
        img: Sentinel-2 image (for context)
        mask: Binary mask
        aoi: Area of interest
        output_path: Output HTML path
    """
    import geemap

    # Create map
    Map = geemap.Map()
    Map.centerObject(aoi, 10)

    # Add RGB image
    Map.addLayer(
        img.select(['B4', 'B3', 'B2']),
        {'min': 0, 'max': 3000},
        'RGB'
    )

    # Add NDVI for context
    Map.addLayer(
        img.select('NDVI'),
        {'min': 0, 'max': 0.8, 'palette': ['red', 'yellow', 'green']},
        'NDVI',
        False  # Hidden by default
    )

    # Add mask overlay (semi-transparent)
    Map.addLayer(
        mask.updateMask(mask),
        {'palette': ['green'], 'opacity': 0.6},
        'Olive Mask'
    )

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Map.to_html(output_path)

    print(f"✅ Mask visualization saved to {output_path}")


def main():
    """Example usage of masking module."""
    print("OliveIntel - Olive Orchard Masking Module")
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

    # Get growing season collection (2023 Apr-Oct)
    print("\nFetching Sentinel-2 collection...")
    collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(aoi)
                  .filterDate('2023-04-01', '2023-10-31')
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)))

    # Compute NDVI for collection
    def add_ndvi(img):
        return img.addBands(img.normalizedDifference(['B8', 'B4']).rename('NDVI'))

    collection = collection.map(add_ndvi)

    print(f"Found {collection.size().getInfo()} images")

    # Create temporally stable mask
    print("\nCreating temporally stable olive mask...")
    mask = create_temporal_stable_mask(
        collection,
        ndvi_threshold=0.4,
        stability_threshold=0.7,
        min_area_sqm=1000
    )

    # Validate mask
    print("\nValidating mask...")
    stats = validate_mask(mask, aoi)

    print(f"\nMask statistics:")
    print(f"  Coverage: {stats['coverage_fraction']*100:.2f}%")
    print(f"  Area: {stats['area_hectares']:.1f} hectares ({stats['area_km2']:.1f} km²)")

    # Visualize
    print("\nGenerating visualization...")
    sample_img = ee.Image(collection.first())
    visualize_mask(sample_img, mask, aoi)

    print("\n✅ Masking complete!")
    print("\nTo export mask:")
    print("  task = export_mask_as_raster(mask, aoi)")
    print("  task.start()")


if __name__ == "__main__":
    main()
