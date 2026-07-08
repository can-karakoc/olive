"""
Download Turkey administrative boundaries from GADM.

GADM (Global Administrative Areas) provides high-quality administrative
boundaries for all countries. This script downloads Turkey's NUTS-3 level
provinces and saves them as GeoJSON.

Source: https://gadm.org/download_country.html
License: Academic use allowed with attribution
"""

import requests
from pathlib import Path
import geopandas as gpd
import json


def download_turkey_provinces():
    """Download and process Turkey province boundaries from GADM."""

    print("Downloading Turkey administrative boundaries from GADM...")

    # GADM download URL for Turkey (level 1 = provinces)
    # Format: gpkg (GeoPackage) is more efficient than shapefile
    url = "https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_TUR.gpkg"

    output_dir = Path("data/geo")
    output_dir.mkdir(parents=True, exist_ok=True)

    temp_file = output_dir / "turkey_gadm.gpkg"
    output_file = output_dir / "turkey_provinces.geojson"

    try:
        # Download GADM GeoPackage
        print(f"Downloading from {url}...")
        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(temp_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"Downloaded to {temp_file}")

        # Read provinces (level 1 = ADM_1)
        print("Reading province boundaries...")
        gdf = gpd.read_file(temp_file, layer='ADM_ADM_1')

        # Simplify geometry to reduce file size (tolerance ~100m)
        print("Simplifying geometries...")
        gdf['geometry'] = gdf['geometry'].simplify(0.001, preserve_topology=True)

        # Add custom fields
        print("Processing province data...")

        # Map provinces to regions (simplified)
        def assign_region(name):
            aegean = ["İzmir", "Aydın", "Manisa", "Muğla", "Balıkesir", "Çanakkale", "Denizli", "Uşak"]
            marmara = ["İstanbul", "Bursa", "Kocaeli", "Tekirdağ", "Edirne", "Bilecik", "Sakarya", "Yalova", "Kırklareli"]
            mediterranean = ["Antalya", "Mersin", "Adana", "Hatay", "Isparta", "Burdur", "Osmaniye"]
            se_anatolia = ["Gaziantep", "Şanlıurfa", "Diyarbakır", "Mardin", "Kilis", "Adıyaman", "Batman", "Siirt", "Şırnak"]

            if name in aegean:
                return "Aegean"
            elif name in marmara:
                return "Marmara"
            elif name in mediterranean:
                return "Mediterranean"
            elif name in se_anatolia:
                return "Southeast Anatolia"
            else:
                return "Other"

        gdf['region'] = gdf['NAME_1'].apply(assign_region)

        # Rename columns for consistency
        gdf = gdf.rename(columns={
            'NAME_1': 'name_en',
            'VARNAME_1': 'name_variants',
            'GID_1': 'gid',
        })

        # Select relevant columns
        columns_to_keep = ['name_en', 'region', 'gid', 'geometry']
        gdf = gdf[columns_to_keep]

        # Save as GeoJSON
        print(f"Saving to {output_file}...")
        gdf.to_file(output_file, driver='GeoJSON')

        # Print summary
        print(f"\n✅ Downloaded {len(gdf)} provinces")
        print(f"   Aegean: {len(gdf[gdf['region'] == 'Aegean'])}")
        print(f"   Marmara: {len(gdf[gdf['region'] == 'Marmara'])}")
        print(f"   Mediterranean: {len(gdf[gdf['region'] == 'Mediterranean'])}")
        print(f"   Southeast Anatolia: {len(gdf[gdf['region'] == 'Southeast Anatolia'])}")
        print(f"   Other: {len(gdf[gdf['region'] == 'Other'])}")

        # Clean up temp file
        temp_file.unlink()
        print(f"\nCleaned up temporary file: {temp_file}")

    except Exception as e:
        print(f"❌ Error: {e}")
        if temp_file.exists():
            temp_file.unlink()
        raise


if __name__ == "__main__":
    download_turkey_provinces()
