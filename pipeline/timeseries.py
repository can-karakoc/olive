"""
Time series processing module.

Handles:
- Gap-filling for missing observations (clouds, etc.)
- Smoothing (Savitzky-Golay, Gaussian Process)
- Phenology extraction (green-up, peak, senescence)
- Province-level aggregation
- Export to CSV/JSON for downstream analysis
"""

import ee
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from scipy.interpolate import interp1d
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import json


def extract_raw_time_series(
    collection: ee.ImageCollection,
    geometry: ee.Geometry,
    band_name: str = 'NDVI',
    reducer: str = 'mean',
    scale: int = 100
) -> pd.DataFrame:
    """
    Extract raw time series from image collection.

    Args:
        collection: Image collection
        geometry: Region to extract
        band_name: Band to extract
        reducer: Spatial aggregation ('mean', 'median', 'max')
        scale: Scale in meters

    Returns:
        DataFrame with columns: date, value
    """
    def extract_value(img):
        # Select reducer
        if reducer == 'mean':
            stat = img.select(band_name).reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=scale,
                maxPixels=1e13,
                bestEffort=True
            )
        elif reducer == 'median':
            stat = img.select(band_name).reduceRegion(
                reducer=ee.Reducer.median(),
                geometry=geometry,
                scale=scale,
                maxPixels=1e13,
                bestEffort=True
            )
        elif reducer == 'max':
            stat = img.select(band_name).reduceRegion(
                reducer=ee.Reducer.max(),
                geometry=geometry,
                scale=scale,
                maxPixels=1e13,
                bestEffort=True
            )

        value = stat.get(band_name)

        return ee.Feature(None, {
            'date': img.date().format('YYYY-MM-dd'),
            'timestamp': img.date().millis(),
            'value': value
        })

    # Map over collection
    features = collection.map(extract_value)

    # Convert to lists
    dates = features.aggregate_array('date').getInfo()
    timestamps = features.aggregate_array('timestamp').getInfo()
    values = features.aggregate_array('value').getInfo()

    # Create DataFrame
    df = pd.DataFrame({
        'date': pd.to_datetime(dates),
        'timestamp': timestamps,
        'value': values
    })

    # Remove null values
    df = df.dropna(subset=['value']).reset_index(drop=True)

    # Sort by date
    df = df.sort_values('date').reset_index(drop=True)

    return df


def gap_fill_linear(df: pd.DataFrame, max_gap_days: int = 30) -> pd.DataFrame:
    """
    Fill gaps using linear interpolation.

    Args:
        df: DataFrame with date, value columns
        max_gap_days: Maximum gap size to fill (days)

    Returns:
        Gap-filled DataFrame
    """
    # First, handle duplicate dates by taking the mean
    df_dedup = df.groupby('date')['value'].mean().reset_index()

    # Resample to daily frequency
    df_daily = df_dedup.set_index('date').resample('D').asfreq()

    # Interpolate, but only for gaps < max_gap_days
    df_daily['value'] = df_daily['value'].interpolate(
        method='linear',
        limit=max_gap_days,
        limit_area='inside'
    )

    # Reset index
    df_filled = df_daily.reset_index()

    # Remove remaining NaN
    df_filled = df_filled.dropna(subset=['value'])

    return df_filled


def smooth_savitzky_golay(
    df: pd.DataFrame,
    window_length: int = 11,
    polyorder: int = 2
) -> pd.DataFrame:
    """
    Apply Savitzky-Golay smoothing filter.

    Good for preserving peak values while removing noise.

    Args:
        df: DataFrame with date, value columns
        window_length: Window size (must be odd)
        polyorder: Polynomial order

    Returns:
        Smoothed DataFrame
    """
    # Ensure window length is odd
    if window_length % 2 == 0:
        window_length += 1

    # Ensure enough points
    if len(df) < window_length:
        print(f"Warning: Not enough points ({len(df)}) for window_length={window_length}")
        return df

    # Apply filter
    df_smooth = df.copy()
    df_smooth['value_smoothed'] = savgol_filter(
        df['value'],
        window_length=window_length,
        polyorder=polyorder
    )

    return df_smooth


def detect_phenology_simple(
    df: pd.DataFrame,
    value_col: str = 'value_smoothed',
    percentile_greenup: float = 0.2,
    percentile_senescence: float = 0.8
) -> Dict:
    """
    Extract simple phenology metrics from time series.

    Metrics:
    - green_up_date: Date when value crosses percentile_greenup threshold (ascending)
    - peak_date: Date of maximum value
    - peak_value: Maximum value
    - senescence_date: Date when value crosses percentile_senescence threshold (descending)
    - season_length: Days from green-up to senescence
    - integral: Area under curve (season total)

    Args:
        df: DataFrame with date and value columns
        value_col: Column name for values
        percentile_greenup: Greenup threshold (0-1)
        percentile_senescence: Senescence threshold (0-1)

    Returns:
        Dictionary with phenology metrics
    """
    if value_col not in df.columns:
        value_col = 'value'

    # Find min and max values
    min_val = df[value_col].min()
    max_val = df[value_col].max()
    value_range = max_val - min_val

    # Thresholds
    greenup_threshold = min_val + value_range * percentile_greenup
    senescence_threshold = min_val + value_range * percentile_senescence

    # Green-up date (first crossing upward)
    greenup_idx = df[df[value_col] >= greenup_threshold].index
    greenup_date = df.loc[greenup_idx[0], 'date'] if len(greenup_idx) > 0 else None

    # Peak
    peak_idx = df[value_col].idxmax()
    peak_date = df.loc[peak_idx, 'date']
    peak_value = df.loc[peak_idx, value_col]

    # Senescence date (first crossing downward after peak)
    post_peak = df[df.index > peak_idx]
    senescence_idx = post_peak[post_peak[value_col] <= senescence_threshold].index
    senescence_date = df.loc[senescence_idx[0], 'date'] if len(senescence_idx) > 0 else None

    # Season length
    if greenup_date and senescence_date:
        season_length = (senescence_date - greenup_date).days
    else:
        season_length = None

    # Integral (area under curve) - trapezoidal rule
    # Approximates total photosynthetic activity
    try:
        integral = np.trapezoid(df[value_col], dx=1)  # NumPy 2.0+
    except AttributeError:
        integral = np.trapz(df[value_col], dx=1)  # NumPy <2.0

    metrics = {
        'greenup_date': greenup_date.strftime('%Y-%m-%d') if greenup_date else None,
        'peak_date': peak_date.strftime('%Y-%m-%d'),
        'peak_value': float(peak_value),
        'senescence_date': senescence_date.strftime('%Y-%m-%d') if senescence_date else None,
        'season_length_days': season_length,
        'integral_auc': float(integral),
        'min_value': float(min_val),
        'max_value': float(max_val),
    }

    return metrics


def process_province_time_series(
    collection: ee.ImageCollection,
    province_geometries: Dict[str, ee.Geometry],
    indices: List[str] = None,
    output_dir: str = "data/interim",
    smooth: bool = True
) -> Dict[str, pd.DataFrame]:
    """
    Process time series for multiple provinces.

    Args:
        collection: Image collection with computed indices
        province_geometries: Dict of {province_name: geometry}
        indices: List of indices to process
        output_dir: Output directory
        smooth: Whether to apply smoothing

    Returns:
        Dictionary of {province_name: DataFrame}
    """
    if indices is None:
        indices = ['NDVI', 'NDRE', 'EVI']

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = {}

    for province_name, geometry in province_geometries.items():
        print(f"\nProcessing {province_name}...")

        province_data = {
            'province': province_name,
            'indices': {}
        }

        for index_name in indices:
            print(f"  - {index_name}...", end=' ')

            # Extract raw time series
            df = extract_raw_time_series(
                collection, geometry, band_name=index_name, reducer='mean'
            )

            print(f"{len(df)} obs", end=' ')

            if len(df) < 5:
                print("(insufficient data)")
                continue

            # Gap-fill
            df_filled = gap_fill_linear(df, max_gap_days=30)

            # Smooth
            if smooth and len(df_filled) >= 11:
                df_smooth = smooth_savitzky_golay(df_filled, window_length=11)
                df_smooth['value_raw'] = df['value']  # Keep raw for comparison
            else:
                df_smooth = df_filled.copy()
                df_smooth['value_smoothed'] = df_smooth['value']

            # Detect phenology
            phenology = detect_phenology_simple(df_smooth)

            print(f"peak={phenology['peak_value']:.2f} on {phenology['peak_date']}")

            # Store
            province_data['indices'][index_name] = {
                'time_series': df_smooth.to_dict('records'),
                'phenology': phenology
            }

            results[province_name] = df_smooth

        # Save to file
        output_file = output_path / f"{province_name}_timeseries.json"
        with open(output_file, 'w') as f:
            # Convert dates to strings for JSON serialization
            def convert_dates(obj):
                if isinstance(obj, pd.Timestamp):
                    return obj.strftime('%Y-%m-%d')
                return obj

            json.dump(province_data, f, indent=2, default=convert_dates)

        print(f"✅ Saved to {output_file}")

    return results


def aggregate_to_seasonal(
    df: pd.DataFrame,
    season_months: Tuple[int, int] = (4, 10)
) -> pd.DataFrame:
    """
    Aggregate daily time series to seasonal statistics.

    Args:
        df: Daily time series DataFrame
        season_months: (start_month, end_month) for growing season

    Returns:
        DataFrame with seasonal statistics per year
    """
    # Add year and month columns
    df['year'] = df['date'].dt.year
    df['month'] = df['date'].dt.month

    # Filter to growing season
    start_month, end_month = season_months
    df_season = df[
        (df['month'] >= start_month) & (df['month'] <= end_month)
    ].copy()

    # Aggregate by year
    seasonal = df_season.groupby('year').agg({
        'value': ['mean', 'max', 'min', 'std'],
        'date': ['min', 'max', 'count']
    }).reset_index()

    # Flatten column names
    seasonal.columns = [
        'year', 'mean', 'max', 'min', 'std',
        'season_start', 'season_end', 'obs_count'
    ]

    return seasonal


def export_time_series_csv(
    df: pd.DataFrame,
    output_path: str,
    metadata: Optional[Dict] = None
):
    """
    Export time series to CSV with metadata header.

    Args:
        df: Time series DataFrame
        output_path: Output CSV path
        metadata: Optional metadata dict
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        # Write metadata as comments
        if metadata:
            f.write(f"# Generated: {datetime.now().isoformat()}\n")
            for key, value in metadata.items():
                f.write(f"# {key}: {value}\n")
            f.write("#\n")

        # Write DataFrame
        df.to_csv(f, index=False)

    print(f"✅ Exported to {output_path}")


def main():
    """Example usage of time series module."""
    print("OliveIntel - Time Series Processing Module")
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

    # Get collection (2023 growing season)
    print("\nFetching Sentinel-2 collection...")
    collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(aoi)
                  .filterDate('2023-04-01', '2023-10-31')
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)))

    # Compute NDVI
    def add_ndvi(img):
        return img.addBands(img.normalizedDifference(['B8', 'B4']).rename('NDVI'))

    collection = collection.map(add_ndvi)

    print(f"Found {collection.size().getInfo()} images")

    # Extract time series for entire AOI
    print("\nExtracting NDVI time series...")
    df = extract_raw_time_series(collection, aoi, 'NDVI')

    print(f"Raw observations: {len(df)}")

    # Gap-fill
    print("Gap-filling...")
    df_filled = gap_fill_linear(df, max_gap_days=30)
    print(f"After gap-fill: {len(df_filled)}")

    # Smooth
    print("Smoothing...")
    df_smooth = smooth_savitzky_golay(df_filled, window_length=11)

    # Detect phenology
    print("\nDetecting phenology...")
    phenology = detect_phenology_simple(df_smooth)

    print("\nPhenology metrics:")
    for key, value in phenology.items():
        print(f"  {key}: {value}")

    # Export
    print("\nExporting time series...")
    export_time_series_csv(
        df_smooth[['date', 'value', 'value_smoothed']],
        'data/interim/aegean_ndvi_timeseries_2023.csv',
        metadata={
            'region': 'Aegean',
            'index': 'NDVI',
            'year': 2023,
            'season': 'Apr-Oct'
        }
    )

    print("\n✅ Time series processing complete!")


if __name__ == "__main__":
    main()
