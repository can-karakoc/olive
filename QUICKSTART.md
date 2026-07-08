# OliveIntel Türkiye - Quick Start Guide

Get the data pipeline running in under 10 minutes.

## Prerequisites

- Python 3.11+
- Google account (for Earth Engine)
- Git (optional)

## 1. Setup Environment (2 minutes)

```bash
cd ~/Projects/oliveintel

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .
```

## 2. Authenticate with Google Earth Engine (3 minutes)

### Option A: Standard Authentication (Easiest)
```bash
earthengine authenticate
```
Follow the prompts to authenticate with your Google account.

### Option B: Service Account (Production)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Earth Engine API
4. Create service account → Download JSON key
5. Save key as `gee-service-account.json`
6. Add to `.env`:
   ```
   GEE_SERVICE_ACCOUNT_EMAIL=your-sa@project.iam.gserviceaccount.com
   GEE_PRIVATE_KEY_PATH=./gee-service-account.json
   ```

## 3. Download Province Boundaries (1 minute)

```bash
python scripts/download_turkey_boundaries.py
```

This downloads Turkish province boundaries from GADM and saves them to `data/geo/turkey_provinces.geojson`.

## 4. Test the Pipeline (4 minutes)

### Quick Test: Single Module
```bash
# Test GEE access
python -m pipeline.access

# Test indices computation
python -m pipeline.indices
```

### Full Demo: Jupyter Notebook
```bash
jupyter notebook notebooks/01_milestone0_demo.ipynb
```

Run all cells to see:
- Cloud masking visualization
- NDVI maps
- Olive orchard mask
- Time series plots
- Phenology metrics

## 5. Run Your First Analysis

```python
import ee
from pipeline import access, indices

# Initialize GEE
access.authenticate_gee()

# Get Sentinel-2 for Aegean region (July 2023)
collection = access.get_sentinel2_collection(
    aoi_path='data/geo/aegean_aoi.geojson',
    start_date='2023-07-01',
    end_date='2023-07-31',
    max_cloud_probability=20
)

print(f"Found {collection.size().getInfo()} images")

# Compute NDVI
collection_ndvi = indices.compute_indices_collection(
    collection, indices=['NDVI']
)

# Extract time series
from pipeline import timeseries
df = timeseries.extract_raw_time_series(
    collection_ndvi,
    ee.Geometry.Polygon([[[26, 36.5], [29.5, 36.5], [29.5, 40.5], [26, 40.5], [26, 36.5]]]),
    'NDVI'
)

print(df.head())
```

## Common Issues

### "earthengine-api not found"
```bash
pip install earthengine-api
```

### "GEE authentication failed"
```bash
earthengine authenticate --force
```

### "GDAL/rasterio installation fails"
On Mac:
```bash
brew install gdal
pip install rasterio
```

On Ubuntu:
```bash
sudo apt-get install gdal-bin libgdal-dev
pip install rasterio
```

## What's Next?

### Explore the Modules
- **`pipeline/access.py`** - Fetch Sentinel-2 imagery
- **`pipeline/preprocess.py`** - Cloud masking
- **`pipeline/indices.py`** - Vegetation indices
- **`pipeline/mask.py`** - Olive orchard detection
- **`pipeline/timeseries.py`** - Time series analysis
- **`pipeline/features.py`** - Feature engineering

### Run Full Pipeline for a Province
```python
from pipeline import access, preprocess, indices, timeseries

# 1. Get imagery for İzmir province (need boundaries first)
# 2. Preprocess (cloud mask)
# 3. Compute indices
# 4. Extract time series
# 5. Export to CSV

# See notebooks/01_milestone0_demo.ipynb for full example
```

### Customize for Your Region
1. Edit `data/geo/aegean_aoi.geojson` or create new AOI
2. Update date ranges in pipeline calls
3. Adjust NDVI thresholds in `mask.py` (default: 0.4)

## Tips

- **Start small:** Test with 1 month of data before running full seasons
- **Check GEE quotas:** Free tier = 5TB/month, plenty for MVP
- **Save outputs:** Pipeline modules automatically create `data/interim/` files
- **Visualize first:** Use `geemap` visualizations to validate before scaling

## Getting Help

- **Documentation:** See `README.md` for detailed setup
- **Issues:** Check `MILESTONE_0_COMPLETE.md` for known limitations
- **Examples:** All modules have `main()` functions demonstrating usage

## Quick Reference: File Locations

| What | Where |
|------|-------|
| AOI definitions | `data/geo/*.geojson` |
| Province boundaries | `data/geo/turkey_provinces.geojson` |
| Imagery (downloaded) | `data/raw/` |
| Time series | `data/interim/*_timeseries.json` |
| Feature tables | `data/processed/features_*.csv` |
| Visualizations | `data/interim/*.html` |
| Labels (ground truth) | `data/labels/*.csv` |

## Estimated Resource Usage

**Disk Space:**
- Pipeline code: ~5 MB
- Dependencies: ~500 MB
- Sample dataset (1 province, 1 season): ~500 MB
- Full Aegean, 3 seasons: ~5-10 GB

**Memory:**
- Local processing: 2-4 GB RAM
- GEE server-side: No local limit

**Time:**
- Single province, 1 month: ~5 minutes
- Single province, full season: ~20 minutes
- All Aegean provinces, 3 seasons: ~2 hours (first run; cached after)

---

**Now you're ready to monitor Turkey's olive groves from space! 🛰️🫒**
