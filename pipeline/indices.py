"""
Spectral indices calculation module.

Uses spyndex library for standardized computation of vegetation indices
from Sentinel-2 imagery. Focuses on indices relevant to olive tree health:
- NDVI: Normalized Difference Vegetation Index
- NDRE: Normalized Difference Red Edge (critical for olives)
- EVI: Enhanced Vegetation Index
- GNDVI: Green Normalized Difference Vegetation Index
- MSAVI2: Modified Soil Adjusted Vegetation Index
"""

import ee
import spyndex
import numpy as np
import xarray as xr
from typing import List, Dict, Optional
import json
from pathlib import Path


# Sentinel-2 band mapping for spyndex
S2_BANDS = {
    'B': 'B2',   # Blue (490 nm)
    'G': 'B3',   # Green (560 nm)
    'R': 'B4',   # Red (665 nm)
    'RE1': 'B5', # Red Edge 1 (705 nm)
    'RE2': 'B6', # Red Edge 2 (740 nm)
    'RE3': 'B7', # Red Edge 3 (783 nm)
    'N': 'B8',   # NIR (842 nm)
    'N2': 'B8A', # Narrow NIR (865 nm)
    'S1': 'B11', # SWIR 1 (1610 nm)
    'S2': 'B12', # SWIR 2 (2190 nm)
}

# Indices critical for olive monitoring
OLIVE_INDICES = ['NDVI', 'NDRE', 'EVI', 'GNDVI', 'MSAVI2']


def compute_ndvi(img: ee.Image) -> ee.Image:
    """
    Compute NDVI (Normalized Difference Vegetation Index).

    NDVI = (NIR - Red) / (NIR + Red)

    Standard vegetation index, range: -1 to 1
    Values > 0.4 typically indicate healthy vegetation.

    Args:
        img: Sentinel-2 image

    Returns:
        Image with NDVI band
    """
    ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
    return img.addBands(ndvi)


def compute_ndre(img: ee.Image) -> ee.Image:
    """
    Compute NDRE (Normalized Difference Red Edge).

    NDRE = (NIR - RedEdge) / (NIR + RedEdge)

    More sensitive to chlorophyll content than NDVI.
    Critical for olive tree stress detection.
    Uses Red Edge band 1 (705nm).

    Args:
        img: Sentinel-2 image

    Returns:
        Image with NDRE band
    """
    ndre = img.normalizedDifference(['B8', 'B5']).rename('NDRE')
    return img.addBands(ndre)


def compute_evi(img: ee.Image) -> ee.Image:
    """
    Compute EVI (Enhanced Vegetation Index).

    EVI = 2.5 * ((NIR - Red) / (NIR + 6*Red - 7.5*Blue + 1))

    Reduces atmospheric and soil background effects.
    Better for dense canopy monitoring.

    Args:
        img: Sentinel-2 image

    Returns:
        Image with EVI band
    """
    nir = img.select('B8')
    red = img.select('B4')
    blue = img.select('B2')

    evi = nir.subtract(red).divide(
        nir.add(red.multiply(6)).subtract(blue.multiply(7.5)).add(1)
    ).multiply(2.5).rename('EVI')

    return img.addBands(evi)


def compute_gndvi(img: ee.Image) -> ee.Image:
    """
    Compute GNDVI (Green Normalized Difference Vegetation Index).

    GNDVI = (NIR - Green) / (NIR + Green)

    More sensitive to chlorophyll concentration than NDVI.
    Useful for detecting early stress.

    Args:
        img: Sentinel-2 image

    Returns:
        Image with GNDVI band
    """
    gndvi = img.normalizedDifference(['B8', 'B3']).rename('GNDVI')
    return img.addBands(gndvi)


def compute_msavi2(img: ee.Image) -> ee.Image:
    """
    Compute MSAVI2 (Modified Soil Adjusted Vegetation Index).

    MSAVI2 = (2*NIR + 1 - sqrt((2*NIR + 1)^2 - 8*(NIR - Red))) / 2

    Minimizes soil brightness effects.
    Useful for sparse vegetation or young orchards.

    Args:
        img: Sentinel-2 image

    Returns:
        Image with MSAVI2 band
    """
    nir = img.select('B8')
    red = img.select('B4')

    msavi2 = (
        nir.multiply(2).add(1)
        .subtract(
            nir.multiply(2).add(1).pow(2)
            .subtract(nir.subtract(red).multiply(8))
            .sqrt()
        )
    ).divide(2).rename('MSAVI2')

    return img.addBands(msavi2)


def compute_all_indices(img: ee.Image, indices: List[str] = None) -> ee.Image:
    """
    Compute multiple spectral indices.

    Args:
        img: Sentinel-2 image
        indices: List of index names (default: OLIVE_INDICES)

    Returns:
        Image with all index bands added
    """
    if indices is None:
        indices = OLIVE_INDICES

    # Compute each requested index
    for index_name in indices:
        if index_name == 'NDVI':
            img = compute_ndvi(img)
        elif index_name == 'NDRE':
            img = compute_ndre(img)
        elif index_name == 'EVI':
            img = compute_evi(img)
        elif index_name == 'GNDVI':
            img = compute_gndvi(img)
        elif index_name == 'MSAVI2':
            img = compute_msavi2(img)
        else:
            print(f"Warning: Unknown index '{index_name}', skipping")

    return img


def compute_indices_collection(
    collection: ee.ImageCollection,
    indices: List[str] = None
) -> ee.ImageCollection:
    """
    Compute indices for entire image collection.

    Args:
        collection: Sentinel-2 image collection
        indices: List of index names

    Returns:
        Collection with index bands added to each image
    """
    if indices is None:
        indices = OLIVE_INDICES

    return collection.map(lambda img: compute_all_indices(img, indices))


def extract_index_time_series(
    collection: ee.ImageCollection,
    geometry: ee.Geometry,
    index_name: str,
    reducer: str = 'mean',
    scale: int = 10
) -> List[Dict]:
    """
    Extract time series of an index over a region.

    Args:
        collection: Image collection with computed indices
        geometry: Region to extract (e.g., province boundary)
        index_name: Name of index band
        reducer: Spatial aggregation method ('mean', 'median', 'max')
        scale: Scale in meters

    Returns:
        List of {date, value} dictionaries
    """
    def extract_value(img):
        # Select reducer
        if reducer == 'mean':
            stats = img.select(index_name).reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=scale,
                maxPixels=1e9
            )
        elif reducer == 'median':
            stats = img.select(index_name).reduceRegion(
                reducer=ee.Reducer.median(),
                geometry=geometry,
                scale=scale,
                maxPixels=1e9
            )
        elif reducer == 'max':
            stats = img.select(index_name).reduceRegion(
                reducer=ee.Reducer.max(),
                geometry=geometry,
                scale=scale,
                maxPixels=1e9
            )
        else:
            raise ValueError(f"Unknown reducer: {reducer}")

        # Extract value
        value = stats.get(index_name)

        # Return feature with date and value
        return ee.Feature(None, {
            'date': img.date().format('YYYY-MM-dd'),
            'value': value
        })

    # Extract time series
    time_series = collection.map(extract_value)

    # Convert to list
    ts_list = time_series.aggregate_array('date').getInfo()
    values = time_series.aggregate_array('value').getInfo()

    # Combine into list of dicts
    result = [
        {'date': date, 'value': val}
        for date, val in zip(ts_list, values)
        if val is not None  # Filter out null values
    ]

    return result


def export_index_time_series(
    collection: ee.ImageCollection,
    geometries: Dict[str, ee.Geometry],
    indices: List[str] = None,
    output_dir: str = "data/interim",
    reducer: str = 'mean'
):
    """
    Export index time series for multiple regions.

    Args:
        collection: Image collection with computed indices
        geometries: Dict of {region_name: geometry}
        indices: List of indices to export
        output_dir: Output directory
        reducer: Spatial aggregation method
    """
    if indices is None:
        indices = OLIVE_INDICES

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for region_name, geometry in geometries.items():
        region_data = {
            'region': region_name,
            'reducer': reducer,
            'indices': {}
        }

        print(f"\nExtracting time series for {region_name}...")

        for index_name in indices:
            print(f"  - {index_name}...", end=' ')

            time_series = extract_index_time_series(
                collection, geometry, index_name, reducer
            )

            region_data['indices'][index_name] = time_series
            print(f"{len(time_series)} observations")

        # Save to JSON
        output_file = output_path / f"{region_name}_indices.json"
        with open(output_file, 'w') as f:
            json.dump(region_data, f, indent=2)

        print(f"✅ Saved to {output_file}")


def visualize_index(
    img: ee.Image,
    index_name: str,
    aoi: ee.Geometry,
    output_path: str = None
):
    """
    Create visualization of a spectral index.

    Args:
        img: Image with computed index
        index_name: Name of index to visualize
        aoi: Area of interest
        output_path: Optional output HTML path
    """
    import geemap

    # Color palettes for different indices
    palettes = {
        'NDVI': ['red', 'yellow', 'green'],
        'NDRE': ['red', 'yellow', 'green'],
        'EVI': ['red', 'yellow', 'green'],
        'GNDVI': ['red', 'yellow', 'green'],
        'MSAVI2': ['red', 'yellow', 'green'],
    }

    # Value ranges
    ranges = {
        'NDVI': {'min': -0.2, 'max': 0.8},
        'NDRE': {'min': -0.2, 'max': 0.8},
        'EVI': {'min': -0.2, 'max': 1.0},
        'GNDVI': {'min': -0.2, 'max': 0.8},
        'MSAVI2': {'min': -0.2, 'max': 0.8},
    }

    # Create map
    Map = geemap.Map()
    Map.centerObject(aoi, 10)

    # Add index layer
    vis_params = {
        'min': ranges[index_name]['min'],
        'max': ranges[index_name]['max'],
        'palette': palettes[index_name]
    }

    Map.addLayer(img.select(index_name), vis_params, index_name)

    # Add RGB for context
    Map.addLayer(
        img.select(['B4', 'B3', 'B2']),
        {'min': 0, 'max': 3000},
        'RGB',
        False  # Hidden by default
    )

    # Save or display
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Map.to_html(output_path)
        print(f"✅ Visualization saved to {output_path}")
    else:
        return Map


def main():
    """Example usage of indices module."""
    print("OliveIntel - Spectral Indices Module")
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

    # Get a sample image
    print("\nFetching sample Sentinel-2 image...")
    img = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
           .filterBounds(aoi)
           .filterDate('2023-07-01', '2023-07-31')
           .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
           .first())

    # Compute all indices
    print("\nComputing spectral indices...")
    img = compute_all_indices(img, OLIVE_INDICES)

    print(f"Computed indices: {', '.join(OLIVE_INDICES)}")

    # Visualize NDVI
    print("\nGenerating NDVI visualization...")
    visualize_index(img, 'NDVI', aoi, 'data/interim/ndvi_visualization.html')

    print("\n✅ Indices computation complete!")


if __name__ == "__main__":
    main()
