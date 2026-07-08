# OliveIntel Türkiye

**Satellite-based olive tree health monitoring, production estimation, and price context for Turkey's olive sector.**

## Overview

OliveIntel uses free Sentinel-2 satellite imagery to monitor olive tree health, estimate regional production, and provide price context for Turkey's olive/olive-oil industry. The platform balances ambitious technical goals with scientific honesty about the limits of remote sensing and commodity price forecasting.

### Core Capabilities

- ✅ **Strong:** Tree health/vigour monitoring at 10m resolution (~95-96% accuracy)
- ✅ **Feasible:** Province-level production estimation (constrained by label granularity)
- ✅ **Context-only:** Price scenarios (NOT point forecasts) — acknowledging global market dominance

### Geographic Focus

- **Aegean Region** (MVP) — 80% of production goes to oil
- **Marmara** — 90% table olives
- **Southeast Anatolia** — 86% oil

## Project Status

**Current Milestone:** M0 - Data Spine Foundation  
**Started:** 2026-07-08  
**Target:** Build reproducible data pipeline for Aegean oil region

## Tech Stack

- **Frontend:** Vercel (Next.js + TypeScript + MapLibre GL JS)
- **Backend:** Vercel Serverless Functions (FastAPI) + Render (TiTiler)
- **Database:** Neon PostgreSQL with PostGIS (0.5GB free tier)
- **Storage:** Cloudflare R2 (Cloud-Optimized GeoTIFFs)
- **Cron:** GitHub Actions (weekly Sentinel-2 ingestion)
- **Data Sources:** Google Earth Engine, ERA5-Land, TÜİK/UZZK/IOC

## Setup

### Prerequisites

- Python 3.11+
- Google Earth Engine service account (for Sentinel-2 access)
- Neon PostgreSQL account (free tier)
- AWS/Cloudflare account (for COG storage)

### Installation

```bash
# Clone repository
cd ~/Projects/oliveintel

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Copy environment template
cp .env.example .env
# Edit .env with your credentials
```

### Google Earth Engine Setup

1. Create a service account at [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Earth Engine API
3. Download service account JSON key
4. Add to `.env`:
   ```
   GEE_SERVICE_ACCOUNT_EMAIL=your-sa@project.iam.gserviceaccount.com
   GEE_PRIVATE_KEY_PATH=./gee-service-account.json
   ```

5. Authenticate:
   ```bash
   earthengine authenticate
   ```

### Database Setup (Neon)

1. Create account at [neon.tech](https://neon.tech)
2. Create project: "oliveintel"
3. Enable PostGIS extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   CREATE EXTENSION IF NOT EXISTS postgis_topology;
   SELECT PostGIS_Version();
   ```
4. Add connection string to `.env`:
   ```
   NEON_DATABASE_URL=postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/oliveintel?sslmode=require
   ```

## Repository Structure

```
oliveintel/
├── README.md                      # This file
├── pyproject.toml                 # Python dependencies
├── .env.example                   # Environment template
├── data/
│   ├── raw/                       # Downloaded imagery (gitignored)
│   ├── interim/                   # Index time series, gap-filled
│   ├── processed/                 # Feature tables ready for ML
│   ├── labels/                    # TÜİK/UZZK/IOC ground truth
│   └── geo/                       # Province boundaries, AOI, olive masks
├── pipeline/
│   ├── access.py                  # GEE/STAC imagery access
│   ├── preprocess.py              # Cloud/shadow masking
│   ├── indices.py                 # Spectral indices (NDVI, NDRE, etc.)
│   ├── timeseries.py              # Gap-fill + smoothing
│   ├── phenology.py               # Green-up, peak, AUC
│   ├── weather.py                 # ERA5-Land covariates
│   ├── features.py                # Province×season feature table
│   └── mask.py                    # Olive orchard mask
├── models/
│   ├── train_yield.py             # LightGBM yield model
│   ├── price_context.py           # Supply-signal + scenarios
│   ├── evaluate.py                # Metrics, validation
│   └── artifacts/                 # Saved models (versioned)
├── api/
│   ├── main.py                    # FastAPI app
│   └── routes/                    # Endpoints
├── webapp/                        # Next.js frontend (or Streamlit MVP)
├── notebooks/                     # Exploration
└── tests/                         # Unit tests
```

## Running the Pipeline

### Milestone 0: Data Spine

```bash
# 1. Fetch Sentinel-2 L2A for Aegean region (6-8 seasons)
python -m pipeline.access --region=aegean --start=2018-01-01 --end=2024-12-31

# 2. Apply cloud masking and create composites
python -m pipeline.preprocess

# 3. Compute spectral indices
python -m pipeline.indices

# 4. Create olive orchard mask (NDVI threshold v1)
python -m pipeline.mask

# 5. Generate gap-filled time series
python -m pipeline.timeseries

# 6. Assemble province×season feature table
python -m pipeline.features
```

### Verification

```bash
# Open demo notebook
jupyter notebook notebooks/01_milestone0_demo.ipynb

# Should show:
# - NDVI map of Aegean region
# - Province time series plot across seasons
# - Olive mask overlay on basemap
```

## Milestone 0 Acceptance Criteria

- [ ] `python -m pipeline.features` runs end-to-end, outputs `data/processed/features_province_season.csv`
- [ ] Olive mask visually aligns with known Aegean olive areas
- [ ] Cloud masking demonstrably removes cloudy pixels (before/after shown)
- [ ] New developer can reproduce from this README
- [ ] No secrets committed; large rasters gitignored

## Critical Domain Knowledge

### Alternate Bearing Cycle (MOST IMPORTANT)

**Olives have a biennial on/off-year cycle.**  
Example: Turkey 2024/25 = 505,000 tonnes → 2025/26 = 290,000 tonnes (43% drop)

**This is NORMAL biology, not crop failure.**  
Any model without an on/off-year feature flag will produce garbage predictions.

### What Sentinel-2 Can/Cannot Do

✅ **CAN detect:** Stress, vigour anomalies, canopy density, phenology  
❌ **CANNOT distinguish:** Drought vs. disease vs. off-year vs. soil issues

**UI must say:** "Anomaly detected" (NOT "disease detected")

### Price Forecasting Reality

- Turkey = 5-10% of global olive oil production
- Spain/EU dominates global pricing
- **NEVER ship point forecast** — only scenario bands with stated assumptions

## Data Sources

### Satellite Imagery
- **Sentinel-2 L2A** (Google Earth Engine) — 10m resolution, 5-day revisit
- Free tier: 5TB/month

### Weather Data
- **ERA5-Land** (Copernicus Climate Data Store) — Rainfall, temperature, GDD

### Ground Truth Labels
- **TÜİK** (Turkish Statistical Institute) — Provincial production statistics
- **UZZK** (National Olive & Olive Oil Council) — Harvest estimates
- **IOC** (International Olive Council) — Global price series

## Development Roadmap

- [x] **M0:** Data spine (GEE pipeline, cloud masking, indices, olive mask, labels)
- [ ] **M1:** Health/coverage MVP (Streamlit — interactive map + KPIs)
- [ ] **M2:** Yield model (LightGBM + on/off-year flag + SHAP + confidence intervals)
- [ ] **M3:** Nowcasting + production system (FastAPI + PostGIS + TiTiler + cron)
- [ ] **M4:** Web app (Next.js + MapLibre — full dashboard)
- [ ] **M5:** Price context module (supply-signal + scenario bands)

## Cost Estimate

**MVP (M0-M2):** $0/month (free tiers)  
**Production (M3+):** $20-50/month (Neon Scale, Render Starter, Cloudflare R2)

## Contributing

This is currently a solo research project. Contributions welcome after M2 completion.

## License

TBD (likely MIT or Apache 2.0 for pipeline code; proprietary for commercial features)

## Contact

Can Karakoc — cankarakoc@berkeley.edu

---

**Last Updated:** 2026-07-08  
**Milestone:** M0 in progress
