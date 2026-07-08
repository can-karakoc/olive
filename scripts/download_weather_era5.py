"""
Download ERA5-Land weather data for Aegean region.

ERA5-Land provides:
- Temperature (avg, min, max)
- Precipitation
- Solar radiation
- Wind speed

Required: CDS API key from Copernicus Climate Data Store
Register at: https://cds.climate.copernicus.eu/
"""

import cdsapi
import os
from pathlib import Path
from dotenv import load_dotenv
import numpy as np
import xarray as xr
import pandas as pd

# Load environment variables
load_dotenv()

# Aegean region bounds
BOUNDS = {
    'north': 40.5,
    'south': 36.5,
    'east': 29.5,
    'west': 26.0
}


def setup_cds_api():
    """
    Set up CDS API credentials.

    To get API key:
    1. Register at https://cds.climate.copernicus.eu/
    2. Go to https://cds.climate.copernicus.eu/api-how-to
    3. Copy your UID and API key
    4. Add to .env:
       CDS_UID=your_uid
       CDS_API_KEY=your_api_key
    """

    uid = os.getenv('CDS_UID')
    api_key = os.getenv('CDS_API_KEY')

    if not uid or not api_key:
        print("❌ CDS API credentials not found in .env")
        print("\nTo set up:")
        print("1. Register at: https://cds.climate.copernicus.eu/")
        print("2. Get API key from: https://cds.climate.copernicus.eu/api-how-to")
        print("3. Add to .env file:")
        print("   CDS_UID=your_uid_here")
        print("   CDS_API_KEY=your_api_key_here")
        return None

    # Create ~/.cdsapirc file (CDS API expects this)
    cdsapi_rc = Path.home() / '.cdsapirc'

    with open(cdsapi_rc, 'w') as f:
        f.write(f"url: https://cds.climate.copernicus.eu/api/v2\n")
        f.write(f"key: {uid}:{api_key}\n")

    print(f"✅ CDS API configured")

    return cdsapi.Client()


def download_era5_land(years, output_dir='data/weather'):
    """
    Download ERA5-Land data for specified years.

    Args:
        years: List of years (e.g., [2019, 2020, 2021])
        output_dir: Output directory
    """

    print(f"Downloading ERA5-Land for {len(years)} years: {years}")
    print(f"Region: {BOUNDS}")

    client = setup_cds_api()

    if not client:
        return False

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for year in years:
        output_file = output_path / f'era5_land_aegean_{year}.nc'

        if output_file.exists():
            print(f"  ⏭️  {year}: Already downloaded")
            continue

        print(f"\n  📥 Downloading {year}...")

        try:
            client.retrieve(
                'reanalysis-era5-land',
                {
                    'variable': [
                        '2m_temperature',
                        'total_precipitation',
                        '10m_u_component_of_wind',
                        '10m_v_component_of_wind',
                        'surface_solar_radiation_downwards',
                    ],
                    'year': str(year),
                    'month': [
                        '01', '02', '03', '04', '05', '06',
                        '07', '08', '09', '10', '11', '12'
                    ],
                    'day': [
                        '01', '02', '03', '04', '05', '06', '07', '08',
                        '09', '10', '11', '12', '13', '14', '15', '16',
                        '17', '18', '19', '20', '21', '22', '23', '24',
                        '25', '26', '27', '28', '29', '30', '31'
                    ],
                    'time': ['00:00', '12:00'],  # 2 times per day
                    'area': [
                        BOUNDS['north'], BOUNDS['west'],
                        BOUNDS['south'], BOUNDS['east']
                    ],
                    'format': 'netcdf',
                },
                str(output_file)
            )

            print(f"    ✅ {year} complete: {output_file}")

        except Exception as e:
            print(f"    ❌ {year} failed: {e}")
            return False

    return True


def process_weather_for_provinces(years, province_centroids):
    """
    Extract weather data for each province centroid.

    Args:
        years: List of years
        province_centroids: Dict of {province_name: (lon, lat)}

    Returns:
        DataFrame with weather data per province per day
    """

    print("\nProcessing weather data for provinces...")

    all_data = []

    for year in years:
        nc_file = Path(f'data/weather/era5_land_aegean_{year}.nc')

        if not nc_file.exists():
            print(f"  ⚠️  {year}: File not found, skipping")
            continue

        print(f"  Processing {year}...")

        # Load netCDF file
        ds = xr.open_dataset(nc_file)

        # For each province
        for province_name, (lon, lat) in province_centroids.items():
            # Extract data at province location (nearest grid point)
            province_data = ds.sel(longitude=lon, latitude=lat, method='nearest')

            # Convert to dataframe
            df = province_data.to_dataframe().reset_index()

            # Add province
            df['province'] = province_name
            df['year'] = year

            all_data.append(df)

    # Combine all
    weather_df = pd.concat(all_data, ignore_index=True)

    # Save
    output_file = Path('data/weather/weather_by_province.csv')
    weather_df.to_csv(output_file, index=False)

    print(f"\n✅ Processed weather data: {output_file}")
    print(f"   Shape: {weather_df.shape}")

    return weather_df


def main():
    print("OliveIntel - ERA5-Land Weather Data Download")
    print("=" * 60)

    # Years to download (2019-2024)
    years = [2019, 2020, 2021, 2022, 2023, 2024]

    # Download
    success = download_era5_land(years)

    if not success:
        print("\n❌ Download failed")
        print("Make sure CDS API credentials are set up")
        return

    # Province centroids (approximate)
    province_centroids = {
        'İzmir': (27.14, 38.42),
        'Aydın': (27.85, 37.85),
        'Balıkesir': (27.89, 39.65),
        'Manisa': (27.43, 38.61),
    }

    # Process for provinces
    weather_df = process_weather_for_provinces(years, province_centroids)

    print("\n" + "=" * 60)
    print("✅ Weather data ready!")
    print("\nNext steps:")
    print("1. Collect ground truth data (Google Earth)")
    print("2. Download TÜİK production labels")
    print("3. Train classification model")
    print("4. Train yield forecasting model")


if __name__ == '__main__':
    main()
