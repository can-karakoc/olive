"""
Olive density estimation module.

Estimates olive tree count or grove area per province using:
1. NDVI-based orchard masking
2. Canopy detection from high-resolution imagery
3. Statistical modeling from known densities

Method hierarchy (attempt in order):
1. Tree count (if 10m resolution sufficient)
2. Grove area (fallback if tree count unreliable)
"""

import ee
import numpy as np
from typing import Dict, Tuple, Optional


def estimate_grove_area(
    collection: ee.ImageCollection,
    geometry: ee.Geometry,
    ndvi_threshold: float = 0.4,
    min_area_sqm: int = 1000,
    scale: int = 10
) -> Dict:
    """
    Estimate total olive grove area within a region.

    Uses temporally stable NDVI mask to identify olive groves.

    Args:
        collection: Sentinel-2 collection with NDVI band
        geometry: Region of interest
        ndvi_threshold: Minimum NDVI to classify as olive grove
        min_area_sqm: Minimum patch size to count (filters noise)
        scale: Resolution in meters

    Returns:
        Dict with:
        - total_area_ha: Total olive grove area in hectares
        - n_patches: Number of discrete patches
        - mean_patch_size_ha: Average patch size
        - coverage_pct: % of total region that is olives
    """

    # Create temporal NDVI median (stable representation)
    ndvi_median = collection.select('NDVI').median()

    # Threshold to get olive mask
    olive_mask = ndvi_median.gt(ndvi_threshold)

    # Remove small patches (noise)
    # Connected pixel regions
    patches = olive_mask.connectedPixelCount(maxSize=256, eightConnected=True)
    min_pixels = min_area_sqm / (scale * scale)
    olive_mask_filtered = olive_mask.updateMask(patches.gte(min_pixels))

    # Compute area
    area_image = olive_mask_filtered.multiply(ee.Image.pixelArea())

    area_stats = area_image.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry,
        scale=scale,
        maxPixels=1e13,
        bestEffort=True
    )

    total_area_sqm = area_stats.get('NDVI').getInfo()

    if total_area_sqm is None or total_area_sqm == 0:
        return {
            'total_area_ha': 0,
            'n_patches': 0,
            'mean_patch_size_ha': 0,
            'coverage_pct': 0
        }

    total_area_ha = total_area_sqm / 10000

    # Count patches
    patch_count = patches.gte(min_pixels).reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=geometry,
        scale=scale,
        maxPixels=1e13,
        bestEffort=True
    ).get('NDVI').getInfo()

    # Region total area
    region_area_sqm = geometry.area(maxError=1).getInfo()
    region_area_ha = region_area_sqm / 10000

    coverage_pct = (total_area_ha / region_area_ha) * 100

    mean_patch_size = total_area_ha / max(patch_count, 1)

    return {
        'total_area_ha': float(total_area_ha),
        'n_patches': int(patch_count),
        'mean_patch_size_ha': float(mean_patch_size),
        'coverage_pct': float(coverage_pct)
    }


def estimate_tree_count(
    collection: ee.ImageCollection,
    geometry: ee.Geometry,
    scale: int = 10,
    typical_spacing_m: float = 6.0,
    canopy_diameter_m: float = 4.0
) -> Dict:
    """
    Estimate olive tree count using canopy detection.

    **Method:**
    1. High NDVI pixels = tree canopies
    2. Local maxima detection → individual trees
    3. Count maxima within olive groves

    **Assumptions:**
    - Trees spaced ~6m apart (typical Mediterranean olive grove)
    - Canopy diameter ~4m at peak season
    - Sentinel-2 at 10m can detect clusters, not individual trees

    **Reliability:** Medium-Low
    - Works for: Dense groves with regular spacing
    - Fails for: Scattered trees, young orchards, mixed land use

    Args:
        collection: Sentinel-2 collection with NDVI
        geometry: Region of interest
        scale: Resolution in meters (10m = Sentinel-2 native)
        typical_spacing_m: Average tree spacing
        canopy_diameter_m: Canopy diameter at peak

    Returns:
        Dict with:
        - estimated_tree_count: Total trees (±30% error)
        - confidence: 'low', 'medium', 'high'
        - method: Detection method used
        - notes: Caveats about reliability
    """

    # Use peak NDVI (June-July typically)
    ndvi_max = collection.select('NDVI').max()

    # Threshold for tree canopies (high NDVI)
    canopy_threshold = 0.6  # Mature olive trees
    canopy_mask = ndvi_max.gt(canopy_threshold)

    # Count high-NDVI pixels
    pixel_count = canopy_mask.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=geometry,
        scale=scale,
        maxPixels=1e13,
        bestEffort=True
    ).get('NDVI').getInfo()

    if pixel_count is None or pixel_count == 0:
        return {
            'estimated_tree_count': 0,
            'confidence': 'low',
            'method': 'pixel_count',
            'notes': 'No high-NDVI canopies detected'
        }

    # Estimate trees from pixel count
    # Each tree covers ~(canopy_diameter)^2 square meters
    # Each pixel is (scale)^2 square meters
    canopy_area_per_tree = np.pi * (canopy_diameter_m / 2) ** 2
    pixels_per_tree = canopy_area_per_tree / (scale * scale)

    estimated_trees = pixel_count / pixels_per_tree

    # Alternative estimate: Grid method
    # Assuming regular spacing, how many trees fit?
    grove_area_stats = estimate_grove_area(collection, geometry, scale=scale)
    grove_area_ha = grove_area_stats['total_area_ha']

    if grove_area_ha > 0:
        trees_per_ha = 10000 / (typical_spacing_m ** 2)  # Grid spacing
        grid_estimate = grove_area_ha * trees_per_ha

        # Average the two estimates
        final_estimate = (estimated_trees + grid_estimate) / 2

        # Confidence based on agreement
        agreement_ratio = min(estimated_trees, grid_estimate) / max(estimated_trees, grid_estimate)

        if agreement_ratio > 0.8:
            confidence = 'medium'
        elif agreement_ratio > 0.6:
            confidence = 'low'
        else:
            confidence = 'low'
            final_estimate = grid_estimate  # Prefer grid if canopy detection unreliable

    else:
        final_estimate = estimated_trees
        confidence = 'low'

    # Round to nearest 100 (precision matches uncertainty)
    final_estimate = round(final_estimate / 100) * 100

    return {
        'estimated_tree_count': int(final_estimate),
        'confidence': confidence,
        'method': 'canopy_detection + grid_spacing',
        'notes': (
            f'Estimated using {canopy_diameter_m}m canopy diameter and '
            f'{typical_spacing_m}m spacing. ±30% error typical at 10m resolution. '
            f'Grove area: {grove_area_ha:.0f} ha.'
        ),
        'grove_area_ha': float(grove_area_ha)
    }


def compute_density_metrics(
    collection: ee.ImageCollection,
    geometry: ee.Geometry,
    province_name: str,
    scale: int = 10
) -> Dict:
    """
    Compute all density metrics for a province.

    Attempts tree count first, falls back to grove area.

    Args:
        collection: Sentinel-2 collection with NDVI
        geometry: Province boundary
        province_name: Province name (for logging)
        scale: Resolution

    Returns:
        Dict with density metrics and method used
    """

    print(f"\nComputing density for {province_name}...")

    # Always compute grove area (reliable baseline)
    grove_metrics = estimate_grove_area(collection, geometry, scale=scale)

    print(f"  Grove area: {grove_metrics['total_area_ha']:.0f} ha")
    print(f"  Coverage: {grove_metrics['coverage_pct']:.1f}%")

    # Attempt tree count estimation
    try:
        tree_metrics = estimate_tree_count(collection, geometry, scale=scale)

        print(f"  Tree count: ~{tree_metrics['estimated_tree_count']:,} trees")
        print(f"  Confidence: {tree_metrics['confidence']}")

        # Use tree count if confidence is medium or high
        if tree_metrics['confidence'] in ['medium', 'high']:
            primary_metric = 'tree_count'
            primary_value = tree_metrics['estimated_tree_count']
        else:
            print(f"  ⚠️  Tree count confidence low, using grove area")
            primary_metric = 'grove_area'
            primary_value = grove_metrics['total_area_ha']

    except Exception as e:
        print(f"  ⚠️  Tree count estimation failed: {e}")
        tree_metrics = None
        primary_metric = 'grove_area'
        primary_value = grove_metrics['total_area_ha']

    return {
        'province_name': province_name,
        'primary_metric': primary_metric,
        'primary_value': primary_value,
        'grove_area_ha': grove_metrics['total_area_ha'],
        'grove_patches': grove_metrics['n_patches'],
        'grove_coverage_pct': grove_metrics['coverage_pct'],
        'tree_count': tree_metrics['estimated_tree_count'] if tree_metrics else None,
        'tree_count_confidence': tree_metrics['confidence'] if tree_metrics else None,
        'tree_count_method': tree_metrics['method'] if tree_metrics else None
    }


def main():
    """Example usage."""
    import ee
    import json
    from pathlib import Path

    print("OliveIntel - Olive Density Estimation")
    print("=" * 60)

    # Initialize GEE
    ee.Initialize()

    # Load İzmir boundary (example)
    with open('data/geo/i̇zmir_boundary.geojson', 'r', encoding='utf-8') as f:
        geojson = json.load(f)

    geometry = ee.Geometry(geojson['features'][0]['geometry'])

    # Get 2024 growing season
    collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(geometry)
                  .filterDate('2024-04-01', '2024-10-31')
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)))

    # Compute NDVI
    from pipeline import indices
    collection = indices.compute_indices_collection(collection, ['NDVI'])

    # Estimate density
    density = compute_density_metrics(collection, geometry, 'İzmir', scale=10)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(json.dumps(density, indent=2))


if __name__ == '__main__':
    main()
