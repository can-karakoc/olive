# Milestone 1: Health Map MVP

**Goal:** Interactive map showing current olive orchard health vs 5-year baseline  
**Status:** In Progress  
**Started:** 2026-07-08

---

## Progress Checklist

### ✅ Completed

- [x] Province boundaries downloaded from GADM (via Google Earth Engine)
  - İzmir, Aydın, Balıkesir, Manisa, Muğla
  - Saved as individual and combined GeoJSON files
  - Area estimates computed

- [x] Database schema designed (PostgreSQL + PostGIS)
  - Tables: provinces, timeseries, phenology, forecasts, alerts
  - Views: v_current_health, v_seasonal_phenology
  - Helper function: compute_health_score()
  - Saved to `database/schema.sql`

- [x] Time series processing script created
  - Extract NDVI, NDRE, EVI for each province
  - 2019-2024 date range (5 years baseline + current)
  - Gap-filling and Savitzky-Golay smoothing
  - Phenology extraction per year
  - Script: `scripts/process_provinces.py`

- [x] Streamlit app skeleton built
  - Province selector
  - KPI cards (current NDVI, baseline, % change, health status)
  - Time series plot with baseline band
  - Phenology table by year
  - Simple location map
  - File: `app/streamlit_app.py`

### 🔄 In Progress

- [ ] Province time series extraction
  - Status: Running in background
  - Expected completion: ~10-15 minutes
  - Output: `data/interim/provinces/*_timeseries.json`

### ⏳ To Do

- [ ] Test Streamlit app locally
  - Install dependencies: `pip install -r app/requirements.txt`
  - Run: `streamlit run app/streamlit_app.py`
  - Verify all 5 provinces display correctly

- [ ] Set up Neon PostgreSQL database
  - Create free tier account at https://neon.tech
  - Create database: `oliveintel`
  - Run schema: `database/schema.sql`
  - Create `.env` with connection string

- [ ] Load data into database
  - Script: `scripts/load_provinces_to_db.py` (to be created)
  - Load province boundaries from GeoJSON
  - Load time series from JSON files
  - Compute and store phenology metrics

- [ ] Connect Streamlit to database
  - Replace file-based data loading with SQL queries
  - Use `st.connection` for PostgreSQL
  - Cache database queries

- [ ] Add all-provinces map view
  - Choropleth map colored by health status
  - Click province to see details
  - Use plotly or folium

- [ ] Deploy to Streamlit Cloud
  - Create account at https://streamlit.io/cloud
  - Connect GitHub repository
  - Set secrets (database connection)
  - Deploy app

- [ ] Testing & polish
  - Test with all 5 provinces
  - Add loading states
  - Error handling
  - Mobile responsiveness
  - Add metadata (last updated, data quality indicators)

---

## Architecture (Milestone 1)

```
┌─────────────────────────────────────┐
│   Streamlit App (Local/Cloud)      │
│  - Province selector                │
│  - KPI dashboard                    │
│  - Time series plots                │
│  - Health map                       │
└─────────────────────────────────────┘
              ▼
┌─────────────────────────────────────┐
│   Neon PostgreSQL + PostGIS         │
│  - provinces (geometries)           │
│  - timeseries (daily NDVI/NDRE/EVI) │
│  - phenology (seasonal metrics)     │
│  - v_current_health (view)          │
└─────────────────────────────────────┘
              ▲
┌─────────────────────────────────────┐
│   Batch Processing (Python)         │
│  1. GEE fetch (Sentinel-2)          │
│  2. Cloud masking                   │
│  3. Indices computation             │
│  4. Time series extraction          │
│  5. Gap-fill + smooth               │
│  6. Phenology detection             │
│  7. Load to PostgreSQL              │
└─────────────────────────────────────┘
```

---

## Data Files

### Province Boundaries
- `data/geo/aegean_provinces.geojson` - All 5 provinces combined
- `data/geo/{province}_boundary.geojson` - Individual province files
- `data/geo/aegean_provinces_metadata.csv` - Metadata (area, bounds)

### Time Series (Generated)
- `data/interim/provinces/izmir_timeseries.json`
- `data/interim/provinces/aydin_timeseries.json`
- `data/interim/provinces/balikesir_timeseries.json`
- `data/interim/provinces/manisa_timeseries.json`
- `data/interim/provinces/mugla_timeseries.json`

Each JSON file contains:
```json
{
  "province_id": 1,
  "province_name": "İzmir",
  "area_ha": 3467038,
  "date_range": {"start": "2019-04-01", "end": "2024-10-31"},
  "indices": {
    "NDVI": {
      "time_series": [{"date": "2019-04-05", "value": 0.45, "value_smoothed": 0.47}, ...],
      "phenology_by_year": {
        "2019": {"greenup_date": "2019-04-15", "peak_date": "2019-06-20", ...},
        ...
      },
      "stats": {"n_observations": 450, "value_mean": 0.52, ...}
    },
    "NDRE": {...},
    "EVI": {...}
  }
}
```

---

## Scripts

### Province Boundaries
```bash
# Download province boundaries from GADM (via GEE)
python scripts/create_province_boundaries_gee.py
```

### Time Series Processing
```bash
# Extract time series for all provinces (10-15 min)
python scripts/process_provinces.py
```

### Database Setup
```bash
# Apply schema to Neon PostgreSQL
psql $DATABASE_URL -f database/schema.sql

# Load province data
python scripts/load_provinces_to_db.py  # (to be created)
```

### Streamlit App
```bash
# Install dependencies
pip install -r app/requirements.txt

# Run locally
cd app
streamlit run streamlit_app.py
```

---

## Acceptance Criteria

- [x] Province boundaries available for 5 Aegean provinces
- [ ] Time series extracted (2019-2024, NDVI/NDRE/EVI)
- [ ] Streamlit app runs locally
- [ ] Map shows all 5 provinces
- [ ] KPI cards display current vs baseline
- [ ] Time series plots work for all provinces
- [ ] Health status computed correctly (z-score)
- [ ] App deployed to Streamlit Cloud (optional for M1, required for M3)

---

## Next: Milestone 2

Once Milestone 1 is complete, Milestone 2 will add:
1. TÜİK ground truth labels (2018-2025 provincial production)
2. ERA5-Land weather data (temp, precip, GDD)
3. LightGBM yield forecasting model
4. Forecast view in Streamlit app

---

## Notes

### Why 100m resolution?
- Province-level analysis → don't need 10m detail
- Reduces GEE memory errors
- Faster processing
- For orchard-level (future), we'll use 10m

### Why 5-year baseline?
- Captures inter-annual variability (including alternate bearing cycles)
- Long enough to be robust, short enough to reflect recent climate
- Standard in satellite-based monitoring

### Data update frequency?
- **Milestone 1:** One-time batch (manual processing)
- **Milestone 2:** Weekly cron job on Vercel
- **Milestone 3:** Daily updates with alerts

---

**Last Updated:** 2026-07-08  
**Next Review:** When province processing completes
