# OliveIntel Architecture

**Last Updated:** 2026-07-08  
**Status:** Milestone 0 Complete, Moving to Milestone 1

---

## Overview

OliveIntel is a **satellite-based olive orchard health monitoring system** for Türkiye, targeting small-to-midsize farmers and agricultural cooperatives. The system provides:

1. **Real-time health monitoring** - Current orchard health vs 5-year baseline
2. **Yield forecasting** - Province-level production predictions accounting for alternate bearing cycles
3. **Actionable insights** - Anomaly detection and intervention recommendations

**Core Principle:** Honest, accurate predictions over inflated marketing claims. If the model can't confidently predict, we say so.

---

## Technology Stack

### Data Layer
| Component | Technology | Purpose | Cost |
|-----------|-----------|---------|------|
| Satellite Data | Google Earth Engine + Sentinel-2 | 10m resolution multi-spectral imagery, free for research | **$0/mo** |
| Database | Neon PostgreSQL + PostGIS | Spatial queries, time-series storage | **$0/mo** (0.5GB free tier) |
| Object Storage | Cloudflare R2 | Export large rasters, backup datasets | **$0/mo** (10GB free) |
| Weather Data | ERA5-Land (via CDS API) | Temperature, precipitation covariates | **$0/mo** |

### Processing Pipeline
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Data Access | `earthengine-api` | Fetch Sentinel-2 collections |
| Preprocessing | `s2cloudless` | Cloud/shadow masking |
| Indices | NDVI, NDRE, EVI, GNDVI, MSAVI2 | Vegetation health metrics |
| Time Series | `scipy` (Savitzky-Golay), pandas | Gap-filling, smoothing |
| Phenology | Custom thresholding | Greenup, peak, senescence dates |
| ML Model | LightGBM | Yield prediction (province × season) |

### Application Layer
| Component | Technology | Purpose | Cost |
|-----------|-----------|---------|------|
| Frontend | Next.js 14 + React | Interactive health map, KPI dashboard | **$0/mo** (Vercel Hobby) |
| Map Visualization | Mapbox GL JS | Province polygons, heatmaps | **$0/mo** (50k loads/mo free) |
| API | Next.js API Routes | Serverless endpoints | Included in Vercel |
| Caching | Vercel Edge Cache | Static map tiles, province summaries | Included |

**Total Monthly Cost:** **$0** for MVP (scales to ~$20-50/mo at 10k users)

---

## Why Google Earth Engine (Not Apple Maps)

Apple Maps/MapKit was evaluated but **lacks all capabilities needed** for agricultural monitoring:

| Feature | Google Earth Engine | Apple MapKit |
|---------|---------------------|--------------|
| Satellite data access | ✅ 90+ PB, 50+ years | ❌ Display-only tiles |
| Multi-spectral bands | ✅ 13 bands (RGB, NIR, SWIR) | ❌ RGB only |
| Historical archive | ✅ Landsat (1972+), Sentinel-2 (2015+) | ❌ Current view only |
| Analysis capabilities | ✅ Python/JS API, cloud compute | ❌ None |
| Time-series extraction | ✅ Built-in reducers | ❌ N/A |
| Pricing for research | ✅ Free | ✅ Free (but irrelevant) |

**Apple's "Gaussian model"** refers to 3D Gaussian Splatting for Flyover (photorealistic city rendering), not satellite analysis. **Verdict:** Stick with GEE + Sentinel-2.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface (Next.js)                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │  Health Map     │  │  KPI Dashboard  │  │  Province   │ │
│  │  (Mapbox GL)    │  │  (current vs    │  │  Time Series│ │
│  │                 │  │   baseline)     │  │  (Recharts) │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              API Layer (Next.js API Routes)                 │
│  GET /api/provinces/{id}/health                             │
│  GET /api/provinces/{id}/timeseries?start=&end=             │
│  GET /api/provinces/{id}/forecast                           │
│  GET /api/map/tiles/{z}/{x}/{y}  (cached GeoJSON)          │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 Database (Neon PostgreSQL)                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ provinces: id, name, geometry (PostGIS), area_ha     │  │
│  │ timeseries: province_id, date, ndvi, ndre, evi, ...  │  │
│  │ phenology: province_id, year, greenup_date, peak_... │  │
│  │ forecasts: province_id, year, predicted_yield, ci_.. │  │
│  │ alerts: province_id, date, severity, anomaly_type    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ▲
┌─────────────────────────────────────────────────────────────┐
│          Batch Processing Pipeline (Python)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ 1. GEE Fetch │→ │ 2. Preprocess│→ │ 3. Extract   │     │
│  │ (Sentinel-2) │  │ (s2cloudless)│  │    Indices   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│          ▼                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ 4. Time      │→ │ 5. Phenology │→ │ 6. Store in  │     │
│  │    Series    │  │    Extraction│  │    PostgreSQL│     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│          ▼                                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 7. ML Model (LightGBM) - Yield Forecast             │  │
│  │    Features: phenology + weather + on/off-year flag │  │
│  │    Target: Province production (tonnes)              │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ▲
┌─────────────────────────────────────────────────────────────┐
│         External Data Sources (Read-Only)                   │
│  • Google Earth Engine (Sentinel-2, 2015-present)           │
│  • Copernicus Climate Data Store (ERA5-Land weather)        │
│  • TÜİK (Turkish Statistical Institute - ground truth)      │
│  • UZZK (CORINE olive land cover validation)               │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### 1. Satellite Data Ingestion (Weekly Batch Job)

```python
# For each province (İzmir, Aydın, Balıkesir, Manisa, Muğla, ...)
for province in provinces:
    # Fetch Sentinel-2 images for last 7 days
    collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
        .filterBounds(province.geometry) \
        .filterDate(today - 7, today) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    
    # Preprocess: cloud masking
    collection = preprocess_collection(collection, cloud_prob_thresh=40)
    
    # Compute indices
    collection = compute_indices(collection, ['NDVI', 'NDRE', 'EVI'])
    
    # Extract mean values over province
    df = extract_raw_time_series(collection, province.geometry, 
                                   band_name='NDVI', reducer='mean', scale=100)
    
    # Store in PostgreSQL
    db.insert('timeseries', df)
```

**Frequency:** Weekly (Sentinel-2 has 5-day revisit time)  
**Storage:** ~50 KB/province/week (compact time-series)  
**Retention:** 10 years (phenology comparisons)

### 2. Time Series Processing (Daily)

```python
# Gap-fill missing observations (clouds)
df_filled = gap_fill_linear(df_raw, max_gap_days=30)

# Smooth noise (preserve phenology signals)
df_smooth = smooth_savitzky_golay(df_filled, window_length=11)

# Detect phenology
phenology = detect_phenology_simple(df_smooth)
# → greenup_date, peak_date, senescence_date, season_length, integral

# Store phenology metrics
db.insert('phenology', phenology)
```

### 3. Yield Forecasting (Seasonal - April & August)

**Training Data:** 6-8 seasons of TÜİK province-level production data (2018-2025)

**Features (per province × season):**
| Category | Features |
|----------|----------|
| Phenology | Greenup DOY, peak DOY, senescence DOY, season length, peak NDVI, integral (AUC) |
| Weather | Growing season avg temp, total precip, GDD (base 10°C), frost days |
| Temporal | Year, month, on/off-year flag (alternate bearing) |
| Spatial | Province area (ha), latitude, elevation |

**Model:** LightGBM Regressor
- **Target:** Log-transformed yield (tonnes) - handles skew
- **Validation:** Temporal holdout (train 2018-2023, test 2024-2025)
- **Metrics:** RMSE, MAE, R² on test set
- **Uncertainty:** Quantile regression for 80% CI

**Alternate Bearing Handling:**
```python
# On/off-year flag derived from 2-year production ratio
df['on_year'] = (df['production'] > df['production'].shift(1)).astype(int)
```

**Prediction Window:** 2-3 months before harvest (July-August)

### 4. Anomaly Detection (Daily)

Compare current NDVI to **5-year baseline** (same DOY):

```python
baseline = db.query("""
    SELECT AVG(ndvi) as ndvi_mean, STDDEV(ndvi) as ndvi_std
    FROM timeseries
    WHERE province_id = ? AND 
          EXTRACT(DOY FROM date) BETWEEN ? AND ? AND
          date >= NOW() - INTERVAL '5 years'
""")

z_score = (current_ndvi - baseline.ndvi_mean) / baseline.ndvi_std

if z_score < -2:  # 2 std deviations below normal
    alert = {
        'severity': 'high' if z_score < -3 else 'medium',
        'type': 'vegetation_stress',
        'message': f'NDVI {abs(z_score):.1f}σ below 5-year average'
    }
    db.insert('alerts', alert)
```

---

## ML Model Details

### LightGBM Configuration

```python
model = lgb.LGBMRegressor(
    objective='regression',
    n_estimators=200,
    max_depth=6,
    learning_rate=0.05,
    num_leaves=31,
    feature_fraction=0.8,
    bagging_fraction=0.8,
    bagging_freq=5,
    random_state=42
)
```

### Feature Importance (Expected Top 5)
1. **peak_ndvi** - Maximum greenness → biomass proxy
2. **season_length_days** - Longer season → more photosynthesis
3. **on_year_flag** - Alternate bearing dominates interannual variance
4. **integral_auc** - Total photosynthetic activity over season
5. **precip_growing_season** - Water availability

### Honest Uncertainty Communication

```python
# Quantile regression (10th, 50th, 90th percentiles)
model_q10 = lgb.LGBMRegressor(objective='quantile', alpha=0.1)
model_q90 = lgb.LGBMRegressor(objective='quantile', alpha=0.9)

prediction = {
    'yield_tonnes': median_pred,
    'ci_lower': q10_pred,  # 10th percentile
    'ci_upper': q90_pred,  # 90th percentile
    'confidence': 'high' if (q90 - q10) < 0.2 * median else 'medium'
}
```

**UI Display:**
- High confidence: Show point estimate + narrow band
- Medium confidence: Show wide band + "Uncertain - check back in 2 weeks"
- Low confidence: Don't show forecast, explain why (e.g., "Insufficient historical data")

---

## Sentinel-2 Band Usage

| Band | Wavelength | Resolution | OliveIntel Use |
|------|------------|------------|----------------|
| B2 (Blue) | 490 nm | 10m | RGB visualization |
| B3 (Green) | 560 nm | 10m | RGB visualization, GNDVI |
| B4 (Red) | 665 nm | 10m | RGB visualization, NDVI, EVI |
| B5 (Red Edge 1) | 705 nm | 20m | NDRE (early stress detection) |
| B8 (NIR) | 842 nm | 10m | NDVI, EVI, MSAVI2 (vegetation vigor) |
| B8A (Narrow NIR) | 865 nm | 20m | NDRE |
| B11 (SWIR 1) | 1610 nm | 20m | EVI, soil/moisture discrimination |

**Key Indices:**
- **NDVI** = (NIR - Red) / (NIR + Red) → General vegetation health
- **NDRE** = (NIR - RedEdge) / (NIR + RedEdge) → Early stress detection (sensitive to chlorophyll)
- **EVI** = 2.5 × (NIR - Red) / (NIR + 6×Red - 7.5×Blue + 1) → Reduces soil/atmosphere noise
- **GNDVI** = (NIR - Green) / (NIR + Green) → Chlorophyll content
- **MSAVI2** = (2×NIR + 1 - √((2×NIR + 1)² - 8×(NIR - Red))) / 2 → Soil-adjusted, good for sparse canopies

---

## Spatial Resolution Strategy

| Scale | Resolution | Use Case |
|-------|------------|----------|
| Regional (Aegean) | 100m | Initial exploration, memory-efficient |
| Province | 20m | Time-series extraction, database storage |
| Orchard-level (future) | 10m | Individual farm monitoring |

**Rationale:** GEE memory limits + storage costs → 20m is sweet spot for province-level analysis. 10m only for localized queries.

---

## Database Schema

### `provinces`
```sql
CREATE TABLE provinces (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    name_tr VARCHAR(100),  -- Turkish name
    geometry GEOMETRY(MultiPolygon, 4326),  -- PostGIS
    area_ha NUMERIC,
    elevation_m INT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_provinces_geom ON provinces USING GIST(geometry);
```

### `timeseries`
```sql
CREATE TABLE timeseries (
    id SERIAL PRIMARY KEY,
    province_id INT REFERENCES provinces(id),
    date DATE NOT NULL,
    ndvi NUMERIC(5,3),
    ndre NUMERIC(5,3),
    evi NUMERIC(5,3),
    gndvi NUMERIC(5,3),
    msavi2 NUMERIC(5,3),
    cloud_free_pixels INT,  -- Quality flag
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(province_id, date)
);
CREATE INDEX idx_timeseries_province_date ON timeseries(province_id, date DESC);
```

### `phenology`
```sql
CREATE TABLE phenology (
    id SERIAL PRIMARY KEY,
    province_id INT REFERENCES provinces(id),
    year INT NOT NULL,
    greenup_date DATE,
    peak_date DATE,
    senescence_date DATE,
    season_length_days INT,
    peak_ndvi NUMERIC(5,3),
    integral_auc NUMERIC(8,2),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(province_id, year)
);
```

### `forecasts`
```sql
CREATE TABLE forecasts (
    id SERIAL PRIMARY KEY,
    province_id INT REFERENCES provinces(id),
    year INT NOT NULL,
    predicted_yield_tonnes NUMERIC(10,2),
    ci_lower NUMERIC(10,2),
    ci_upper NUMERIC(10,2),
    confidence VARCHAR(20),  -- 'high', 'medium', 'low'
    on_year_flag BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(province_id, year)
);
```

### `alerts`
```sql
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    province_id INT REFERENCES provinces(id),
    date DATE NOT NULL,
    severity VARCHAR(20),  -- 'low', 'medium', 'high'
    anomaly_type VARCHAR(50),  -- 'vegetation_stress', 'drought', 'frost'
    message TEXT,
    z_score NUMERIC(5,2),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_alerts_province_date ON alerts(province_id, date DESC);
```

---

## Frontend Architecture (Next.js)

### Page Structure
```
/                           → Landing page (hero, features, demo link)
/map                        → Interactive health map (Mapbox GL JS)
/provinces/[id]             → Province detail (time series, forecast, alerts)
/about                      → Methodology, data sources, limitations
/api/provinces/[id]/health  → Current health metrics
/api/provinces/[id]/forecast → Yield prediction
```

### Map Component (Milestone 1)

```tsx
// components/HealthMap.tsx
import MapboxGL from 'mapbox-gl';

export default function HealthMap() {
  const [provinces, setProvinces] = useState<Province[]>([]);
  
  useEffect(() => {
    // Fetch province health data
    fetch('/api/provinces/health')
      .then(res => res.json())
      .then(data => setProvinces(data));
  }, []);
  
  return (
    <Map
      initialViewState={{ longitude: 27.75, latitude: 38.5, zoom: 7 }}
      mapStyle="mapbox://styles/mapbox/satellite-streets-v12"
    >
      <Source id="provinces" type="geojson" data={provincesGeoJSON}>
        <Layer
          id="provinces-fill"
          type="fill"
          paint={{
            'fill-color': [
              'interpolate', ['linear'], ['get', 'health_score'],
              0, '#d73027',    // Critical
              50, '#fee08b',   // Poor
              75, '#d9ef8b',   // Fair
              90, '#1a9850'    // Excellent
            ],
            'fill-opacity': 0.7
          }}
        />
      </Source>
    </Map>
  );
}
```

### KPI Dashboard

```tsx
// pages/provinces/[id].tsx
export default function ProvinceDetail({ province, timeseries, forecast }) {
  const currentHealth = timeseries[timeseries.length - 1].ndvi;
  const baseline5yr = computeBaseline(timeseries);
  const anomaly = ((currentHealth - baseline5yr) / baseline5yr) * 100;
  
  return (
    <div>
      <h1>{province.name} Olive Health</h1>
      
      <KPICard
        title="Current NDVI"
        value={currentHealth.toFixed(3)}
        change={anomaly}
        changeLabel={`vs 5-year avg (${baseline5yr.toFixed(3)})`}
        status={anomaly < -10 ? 'critical' : anomaly < 0 ? 'warning' : 'good'}
      />
      
      <KPICard
        title="2026 Yield Forecast"
        value={`${forecast.predicted_yield_tonnes.toLocaleString()} tonnes`}
        confidence={forecast.confidence}
        range={`${forecast.ci_lower.toLocaleString()} - ${forecast.ci_upper.toLocaleString()}`}
      />
      
      <TimeSeriesChart data={timeseries} />
    </div>
  );
}
```

---

## Next Steps (Milestone 1 → 2 → 3)

### Milestone 1: Health MVP (2 weeks)
**Goal:** Interactive map showing current health vs baseline

1. ✅ **Pipeline validated** (Milestone 0 complete)
2. **Run pipeline for 5 Aegean provinces:**
   - İzmir, Aydın, Balıkesir, Manisa, Muğla
   - Extract time series (2023-2024 growing seasons)
   - Compute 5-year baselines (2019-2023)
3. **Set up Neon PostgreSQL:**
   - Create schema (provinces, timeseries, alerts)
   - Load province boundaries from GADM
   - Ingest time series data
4. **Build Streamlit prototype:**
   - Map with province polygons colored by health
   - KPI cards (current NDVI, anomaly z-score, alert status)
   - Time series plot (current year vs 5-year envelope)
5. **Deploy to Streamlit Cloud** (free tier, password-protected)

**Deliverable:** Public demo URL showing live health map

---

### Milestone 2: Yield Model (3 weeks)
**Goal:** Province-level production forecasts with uncertainty

1. **Collect ground truth labels:**
   - TÜİK provincial olive production (2018-2025)
   - Verify on/off-year cycles
2. **Add weather covariates:**
   - Download ERA5-Land data (temp, precip, GDD)
   - Aggregate to province × growing season
3. **Feature engineering:**
   - Phenology metrics from time series
   - Weather aggregations
   - On/off-year flag (alternate bearing)
4. **Train LightGBM model:**
   - Temporal train/test split (2018-2023 train, 2024-2025 test)
   - Hyperparameter tuning (5-fold CV on train set)
   - Quantile regression for uncertainty
5. **Validation:**
   - RMSE, MAE, R² on test set
   - Feature importance analysis
   - Residual diagnostics (check for spatial/temporal patterns)
6. **Deploy model:**
   - Save to Cloudflare R2
   - Add `/api/forecast` endpoint
   - Update UI with forecast KPI cards

**Deliverable:** Forecast page with 2026 predictions + confidence intervals

---

### Milestone 3: Production Polish (2 weeks)
**Goal:** User-ready Next.js app on Vercel

1. **Migrate Streamlit → Next.js:**
   - Convert map to Mapbox GL JS
   - Rebuild dashboard with Tailwind CSS + shadcn/ui
   - Add responsive design (mobile-friendly)
2. **Optimize performance:**
   - Vercel Edge Caching for province summaries
   - Incremental Static Regeneration (ISR) for map tiles
   - Lazy-load time series data
3. **Add documentation:**
   - /about page: methodology, data sources, limitations
   - FAQ: alternate bearing, NDVI interpretation, confidence levels
4. **User testing:**
   - Share with 3-5 farmers/agronomists
   - Collect feedback on usability + accuracy
5. **Launch:**
   - Deploy to Vercel (custom domain: oliveintel.app?)
   - Monitor analytics (Vercel, PostHog?)

**Deliverable:** Public web app at oliveintel.app

---

## Limitations & Honest Framing

### What OliveIntel CAN Do:
- ✅ Detect vegetation stress 2-4 weeks earlier than ground observation
- ✅ Provide province-level yield forecasts 2-3 months pre-harvest
- ✅ Show multi-year trends (is this orchard declining?)
- ✅ Identify anomalies vs historical baseline

### What OliveIntel CANNOT Do:
- ❌ Individual tree-level monitoring (need 1m resolution, e.g., drone/Planet)
- ❌ Disease identification (e.g., Xylella fastidiosa) - requires spectral signatures beyond Sentinel-2
- ❌ Real-time alerts (<5 days) - Sentinel-2 revisit is 5 days, clouds add lag
- ❌ Sub-province yield prediction - ground truth only at province scale
- ❌ Prescriptive recommendations (irrigation schedule, fertilizer rates) - requires soil/microclimate data

### Alternate Bearing Reality:
Olive production alternates between high-yield ("on") and low-yield ("off") years due to tree physiology. This is NORMAL and cannot be "fixed" by monitoring. OliveIntel accounts for this via the `on_year_flag` feature but does NOT promise to eliminate it.

---

## Cost Projections

### MVP (0-100 users)
- Hosting: $0 (Vercel Hobby, Neon Free, R2 Free)
- Data: $0 (GEE research use, ERA5 open data)
- **Total: $0/month**

### Growth (100-10k users)
- Vercel Pro: $20/mo (more bandwidth, custom domains)
- Neon Pro: $19/mo (1GB storage, connection pooling)
- Mapbox: $0 (within 50k loads/mo)
- **Total: ~$40/month**

### Scale (10k+ users)
- Vercel Enterprise: ~$300/mo
- Neon Scale: ~$100/mo (autoscaling)
- GEE Commercial: TBD (contact sales)
- **Total: ~$500-1000/month**

---

## Security & Privacy

- **No PII collected** - Province-level only, no farm boundaries
- **Public data only** - Sentinel-2 is CC-BY, ERA5 is open
- **Read-only GEE access** - Service account with minimal permissions
- **Rate limiting** - Vercel Edge Middleware (100 req/min/IP)
- **HTTPS enforced** - Vercel automatic SSL

---

## Open Questions

1. **Orchard mask accuracy:** How well does NDVI thresholding separate olives from other vegetation? Need CORINE validation.
2. **Model generalization:** Will a model trained on Aegean work for Marmara/Mediterranean? May need region-specific models.
3. **Alternate bearing predictability:** Can we predict on/off-year AHEAD of time, or only explain it post-hoc?
4. **Farmer adoption:** Will small farmers trust satellite-based forecasts? Need user research.

---

## References

- [Sentinel-2 User Handbook](https://sentinels.copernicus.eu/web/sentinel/user-guides/sentinel-2-msi)
- [s2cloudless Cloud Detection](https://github.com/sentinel-hub/sentinel2-cloud-detector)
- [Google Earth Engine Docs](https://developers.google.com/earth-engine)
- [NDVI for Crop Monitoring (NASA)](https://earthobservatory.nasa.gov/features/MeasuringVegetation/measuring_vegetation_2.php)
- [Alternate Bearing in Olives (Research Paper)](https://www.mdpi.com/2073-4395/10/8/1228)
- [LightGBM Documentation](https://lightgbm.readthedocs.io/)
- [Next.js App Router](https://nextjs.org/docs/app)
- [Neon PostgreSQL](https://neon.tech/docs)
- [Mapbox GL JS](https://docs.mapbox.com/mapbox-gl-js/)

---

**Next Action:** Start Milestone 1 - run pipeline for 5 provinces and set up PostgreSQL schema.
