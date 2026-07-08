"""
Feature engineering module for olive yield prediction.

Assembles province×season feature table from:
- Spectral indices time series (NDVI, NDRE, etc.)
- Phenology metrics (green-up, peak, AUC)
- Weather covariates (rainfall, temperature, GDD)
- On/off year cycle flag (MANDATORY)
- Spatial features (province, region)

Output: Ready-for-ML feature table in data/processed/
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import json


def load_phenology_features(
    timeseries_dir: str = "data/interim",
    provinces: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Load phenology features from time series JSON files.

    Args:
        timeseries_dir: Directory with province time series files
        provinces: List of provinces to load (None = all)

    Returns:
        DataFrame with phenology features per province-year
    """
    ts_path = Path(timeseries_dir)

    if not ts_path.exists():
        raise FileNotFoundError(f"Time series directory not found: {timeseries_dir}")

    # Find all time series files
    ts_files = list(ts_path.glob("*_timeseries.json"))

    if len(ts_files) == 0:
        raise FileNotFoundError(f"No time series files found in {timeseries_dir}")

    rows = []

    for ts_file in ts_files:
        # Extract province name from filename
        province_name = ts_file.stem.replace('_timeseries', '')

        if provinces and province_name not in provinces:
            continue

        # Load data
        with open(ts_file, 'r') as f:
            data = json.load(f)

        # Extract phenology for each index
        for index_name, index_data in data['indices'].items():
            if 'phenology' not in index_data:
                continue

            phenology = index_data['phenology']

            # Extract year from peak_date
            year = pd.to_datetime(phenology['peak_date']).year

            # Create feature row
            row = {
                'province': province_name,
                'year': year,
                f'{index_name}_peak_value': phenology['peak_value'],
                f'{index_name}_integral_auc': phenology['integral_auc'],
                f'{index_name}_season_length': phenology.get('season_length_days'),
                f'{index_name}_min_value': phenology['min_value'],
                f'{index_name}_max_value': phenology['max_value'],
            }

            # Add dates as day-of-year
            if phenology.get('greenup_date'):
                greenup_doy = pd.to_datetime(phenology['greenup_date']).dayofyear
                row[f'{index_name}_greenup_doy'] = greenup_doy

            if phenology.get('peak_date'):
                peak_doy = pd.to_datetime(phenology['peak_date']).dayofyear
                row[f'{index_name}_peak_doy'] = peak_doy

            if phenology.get('senescence_date'):
                senescence_doy = pd.to_datetime(phenology['senescence_date']).dayofyear
                row[f'{index_name}_senescence_doy'] = senescence_doy

            rows.append(row)

    # Convert to DataFrame
    df = pd.DataFrame(rows)

    # Aggregate multiple indices per province-year
    # (Different indices may give slightly different years; take first)
    df_agg = df.groupby(['province', 'year']).first().reset_index()

    return df_agg


def add_on_off_year_flag(
    df: pd.DataFrame,
    baseline_file: str = "data/labels/on_off_year_cycle.csv"
) -> pd.DataFrame:
    """
    Add on/off year flag to features.

    CRITICAL FEATURE for olive yield prediction.

    Args:
        df: Feature DataFrame with 'year' column
        baseline_file: CSV with year, classification columns

    Returns:
        DataFrame with on_off_year column added
    """
    # Load on/off year classifications
    if not Path(baseline_file).exists():
        print(f"Warning: {baseline_file} not found. Inferring from pattern...")

        # Simple inference: alternate starting from known year
        # 2024 = on, 2023 = on, 2022 = off, 2021 = off, ...
        # (This is a fallback; should use actual data)
        def infer_on_off(year):
            # Start from 2024 (known on-year from brief)
            offset = year - 2024
            if offset % 2 == 0:
                return 'on'
            else:
                return 'off'

        df['on_off_year'] = df['year'].apply(infer_on_off)

    else:
        # Load from file
        on_off = pd.read_csv(baseline_file)

        # Merge
        df = df.merge(
            on_off[['year', 'classification']],
            on='year',
            how='left'
        )

        df['on_off_year'] = df['classification']
        df = df.drop(columns=['classification'])

    # Convert to binary (for ML)
    df['on_off_year_binary'] = (df['on_off_year'] == 'on').astype(int)

    return df


def add_weather_features(
    df: pd.DataFrame,
    weather_dir: str = "data/interim/weather"
) -> pd.DataFrame:
    """
    Add weather covariates from ERA5-Land.

    Features:
    - Growing season total rainfall (mm)
    - Growing season mean temperature (°C)
    - Growing season GDD (Growing Degree Days)

    Args:
        df: Feature DataFrame with province, year
        weather_dir: Directory with weather data

    Returns:
        DataFrame with weather features added
    """
    weather_path = Path(weather_dir)

    if not weather_path.exists():
        print(f"Warning: Weather directory not found: {weather_dir}")
        print("Skipping weather features (add later)")
        return df

    # Load weather data for each province
    weather_files = list(weather_path.glob("*_weather.csv"))

    if len(weather_files) == 0:
        print(f"Warning: No weather files found in {weather_dir}")
        return df

    weather_dfs = []

    for weather_file in weather_files:
        province_name = weather_file.stem.replace('_weather', '')
        weather_data = pd.read_csv(weather_file)

        # Assuming weather CSV has: year, rainfall_mm, temp_mean_c, gdd
        weather_data['province'] = province_name
        weather_dfs.append(weather_data)

    # Combine all weather data
    weather_combined = pd.concat(weather_dfs, ignore_index=True)

    # Merge with features
    df = df.merge(
        weather_combined,
        on=['province', 'year'],
        how='left'
    )

    return df


def add_spatial_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add spatial categorical features.

    Features:
    - region (Aegean, Marmara, etc.)
    - province_encoded (label encoding for ML)

    Args:
        df: Feature DataFrame with province column

    Returns:
        DataFrame with spatial features
    """
    from pipeline.utils import province_to_nuts3, get_olive_provinces

    # Region mapping (from brief)
    region_map = {
        'İzmir': 'Aegean',
        'Aydın': 'Aegean',
        'Balıkesir': 'Aegean',
        'Manisa': 'Aegean',
        'Muğla': 'Aegean',
        'Çanakkale': 'Aegean',
        'Bursa': 'Marmara',
        'Edirne': 'Marmara',
        'Antalya': 'Mediterranean',
        'Mersin': 'Mediterranean',
        'Hatay': 'Mediterranean',
        'Gaziantep': 'Southeast Anatolia',
        'Kilis': 'Southeast Anatolia',
        'Şanlıurfa': 'Southeast Anatolia',
        'Kahramanmaraş': 'Southeast Anatolia',
        'Mardin': 'Southeast Anatolia',
    }

    df['region'] = df['province'].map(region_map)

    # NUTS-3 code
    df['nuts3_code'] = df['province'].apply(province_to_nuts3)

    # Province encoding (for tree-based models)
    province_encoding = {prov: i for i, prov in enumerate(sorted(df['province'].unique()))}
    df['province_encoded'] = df['province'].map(province_encoding)

    return df


def load_labels(
    label_file: str = "data/labels/turkey_olive_production.csv"
) -> pd.DataFrame:
    """
    Load ground truth production labels.

    Args:
        label_file: Path to production CSV

    Returns:
        DataFrame with province, year, production_tonnes
    """
    if not Path(label_file).exists():
        raise FileNotFoundError(
            f"Label file not found: {label_file}\n"
            f"Please create this file following PROVENANCE.md instructions."
        )

    labels = pd.read_csv(label_file)

    # Standardize column names
    if 'production_tonnes' not in labels.columns:
        # Try alternative column names
        prod_col = [c for c in labels.columns if 'production' in c.lower()][0]
        labels = labels.rename(columns={prod_col: 'production_tonnes'})

    return labels[['province', 'year', 'production_tonnes']]


def assemble_feature_table(
    timeseries_dir: str = "data/interim",
    label_file: str = "data/labels/turkey_olive_production.csv",
    weather_dir: str = "data/interim/weather",
    output_file: str = "data/processed/features_province_season.csv"
) -> pd.DataFrame:
    """
    Assemble complete feature table for ML.

    Args:
        timeseries_dir: Directory with time series JSON files
        label_file: Ground truth production labels
        weather_dir: Weather covariate directory
        output_file: Output CSV path

    Returns:
        Feature DataFrame ready for ML
    """
    print("OliveIntel - Feature Engineering")
    print("=" * 50)

    # 1. Load phenology features
    print("\n1. Loading phenology features...")
    df = load_phenology_features(timeseries_dir)
    print(f"   Loaded {len(df)} province-year observations")

    # 2. Add on/off year flag (MANDATORY)
    print("\n2. Adding on/off year flag...")
    df = add_on_off_year_flag(df)
    on_years = (df['on_off_year'] == 'on').sum()
    off_years = (df['on_off_year'] == 'off').sum()
    print(f"   On-years: {on_years}, Off-years: {off_years}")

    # 3. Add weather features
    print("\n3. Adding weather features...")
    df = add_weather_features(df, weather_dir)

    # 4. Add spatial features
    print("\n4. Adding spatial features...")
    df = add_spatial_features(df)

    # 5. Load and merge labels
    print("\n5. Loading production labels...")
    try:
        labels = load_labels(label_file)
        print(f"   Loaded {len(labels)} labeled observations")

        df = df.merge(labels, on=['province', 'year'], how='left')

        labeled = df['production_tonnes'].notna().sum()
        unlabeled = df['production_tonnes'].isna().sum()
        print(f"   Matched: {labeled} labeled, {unlabeled} unlabeled")

    except FileNotFoundError as e:
        print(f"   Warning: {e}")
        print("   Proceeding without labels (features-only mode)")

    # 6. Save
    print(f"\n6. Saving feature table to {output_file}...")
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_file, index=False)

    print(f"✅ Feature table created: {len(df)} rows, {len(df.columns)} columns")

    # Summary
    print("\n" + "=" * 50)
    print("Feature Summary:")
    print(f"  Provinces: {df['province'].nunique()}")
    print(f"  Years: {df['year'].nunique()}")
    print(f"  Features: {len(df.columns)}")
    if 'production_tonnes' in df.columns:
        print(f"  Labeled observations: {df['production_tonnes'].notna().sum()}")

    return df


def main():
    """Assemble feature table."""
    df = assemble_feature_table()

    # Display sample
    print("\nSample rows:")
    print(df.head())

    print("\nColumn names:")
    print(df.columns.tolist())


if __name__ == "__main__":
    main()
