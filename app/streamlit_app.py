"""
OliveIntel Streamlit Health Map - Milestone 1

Interactive map showing olive orchard health for Aegean provinces.
Displays current NDVI vs 5-year baseline.
"""

import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

# Page config
st.set_page_config(
    page_title="OliveIntel - Olive Health Monitor",
    page_icon="🫒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #2c5f2d;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .kpi-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1.5rem;
        text-align: center;
    }
    .kpi-value {
        font-size: 2rem;
        font-weight: 700;
        margin: 0.5rem 0;
    }
    .kpi-label {
        font-size: 0.9rem;
        color: #666;
    }
    .status-good { color: #1a9850; }
    .status-fair { color: #fee08b; }
    .status-warning { color: #f46d43; }
    .status-critical { color: #d73027; }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_province_data():
    """Load all province time series data."""

    data_dir = Path('data/interim/provinces')

    if not data_dir.exists():
        return {}

    provinces = {}

    for json_file in data_dir.glob('*_timeseries.json'):
        with open(json_file, 'r', encoding='utf-8') as f:
            province_data = json.load(f)
            province_name = province_data['province_name']
            provinces[province_name] = province_data

    return provinces


@st.cache_data
def load_province_geometries():
    """Load province boundaries for map visualization."""

    geojson_path = Path('data/geo/aegean_provinces.geojson')

    if not geojson_path.exists():
        return None

    with open(geojson_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def compute_baseline(timeseries_df, current_date, window_days=7):
    """Compute 5-year baseline NDVI for current day-of-year."""

    # Get current day of year
    current_doy = current_date.timetuple().tm_yday

    # Filter to +/- window around this DOY for past 5 years
    baseline_start = current_date - timedelta(days=5*365)

    baseline_data = []

    for _, row in timeseries_df.iterrows():
        row_date = pd.to_datetime(row['date'])

        if row_date >= baseline_start and row_date < current_date:
            row_doy = row_date.timetuple().tm_yday

            # Check if within window
            if abs(row_doy - current_doy) <= window_days:
                baseline_data.append(row['value_smoothed'])

    if len(baseline_data) < 5:
        return None, None

    return np.mean(baseline_data), np.std(baseline_data)


def compute_health_status(current_value, baseline_mean, baseline_std):
    """Compute health status from z-score."""

    if baseline_std == 0 or baseline_std is None:
        return 'unknown', 0

    z_score = (current_value - baseline_mean) / baseline_std

    if z_score < -3:
        status = 'critical'
    elif z_score < -2:
        status = 'warning'
    elif z_score < -1:
        status = 'fair'
    else:
        status = 'good'

    return status, z_score


def main():
    st.markdown('<div class="main-header">🫒 OliveIntel</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Olive Orchard Health Monitor - Aegean Region</div>', unsafe_allow_html=True)

    # Load data
    provinces = load_province_data()
    geometries = load_province_geometries()

    if not provinces:
        st.error("⚠️ No province data found. Please run `scripts/process_provinces.py` first.")
        st.info("Processing may take 10-15 minutes to extract Sentinel-2 time series for all provinces.")
        return

    st.success(f"✅ Loaded data for {len(provinces)} provinces")

    # Sidebar - Province selector
    st.sidebar.header("Select Province")

    province_names = sorted(provinces.keys())
    selected_province = st.sidebar.selectbox("Province", province_names)

    st.sidebar.markdown("---")
    st.sidebar.header("About")
    st.sidebar.info("""
    **Data Source:** Sentinel-2 satellite imagery (10m resolution)

    **Indices:**
    - NDVI: Vegetation health
    - NDRE: Early stress detection
    - EVI: Soil-adjusted vegetation

    **Baseline:** 5-year average (2019-2023)

    **Update Frequency:** Weekly
    """)

    # Main content
    province_data = provinces[selected_province]

    # Check if NDVI data exists
    if 'NDVI' not in province_data.get('indices', {}):
        st.warning(f"⚠️ No NDVI data available for {selected_province}")
        return

    ndvi_data = province_data['indices']['NDVI']
    timeseries_records = ndvi_data['time_series']

    # Convert to DataFrame
    df = pd.DataFrame(timeseries_records)
    df['date'] = pd.to_datetime(df['date'])

    if len(df) == 0:
        st.warning(f"⚠️ No time series data for {selected_province}")
        return

    # Get current (most recent) value
    current_row = df.iloc[-1]
    current_date = current_row['date']
    current_ndvi = current_row['value_smoothed']

    # Compute baseline
    baseline_mean, baseline_std = compute_baseline(df, current_date, window_days=7)

    if baseline_mean is None:
        st.warning("⚠️ Insufficient baseline data (need 5 years)")
        baseline_mean = df['value_smoothed'].mean()
        baseline_std = df['value_smoothed'].std()

    health_status, z_score = compute_health_status(current_ndvi, baseline_mean, baseline_std)

    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Current NDVI</div>
            <div class="kpi-value">{current_ndvi:.3f}</div>
            <div class="kpi-label">{current_date.strftime('%Y-%m-%d')}</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">5-Year Baseline</div>
            <div class="kpi-value">{baseline_mean:.3f}</div>
            <div class="kpi-label">±{baseline_std:.3f}</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        pct_change = ((current_ndvi - baseline_mean) / baseline_mean) * 100
        change_symbol = "▲" if pct_change > 0 else "▼"
        change_color = "green" if pct_change > 0 else "red"

        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">vs Baseline</div>
            <div class="kpi-value" style="color: {change_color};">{change_symbol} {abs(pct_change):.1f}%</div>
            <div class="kpi-label">z-score: {z_score:.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        status_class = f"status-{health_status}"
        status_emoji = {"good": "🟢", "fair": "🟡", "warning": "🟠", "critical": "🔴"}.get(health_status, "⚪")

        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Health Status</div>
            <div class="kpi-value {status_class}">{status_emoji} {health_status.upper()}</div>
        </div>
        """, unsafe_allow_html=True)

    # Time series plot
    st.markdown("### 📈 NDVI Time Series")

    fig = go.Figure()

    # Plot raw data
    fig.add_trace(go.Scatter(
        x=df['date'],
        y=df['value'],
        mode='markers',
        name='Raw',
        marker=dict(color='lightgray', size=4),
        opacity=0.5
    ))

    # Plot smoothed data
    fig.add_trace(go.Scatter(
        x=df['date'],
        y=df['value_smoothed'],
        mode='lines',
        name='Smoothed',
        line=dict(color='darkgreen', width=2)
    ))

    # Add baseline band
    baseline_dates = df[df['date'] >= current_date - timedelta(days=365)]['date']
    if len(baseline_dates) > 0:
        fig.add_trace(go.Scatter(
            x=baseline_dates.tolist() + baseline_dates.tolist()[::-1],
            y=[baseline_mean + baseline_std] * len(baseline_dates) + [baseline_mean - baseline_std] * len(baseline_dates),
            fill='toself',
            fillcolor='rgba(255, 200, 100, 0.2)',
            line=dict(color='rgba(255,255,255,0)'),
            name='5-year range',
            showlegend=True
        ))

        # Baseline mean line
        fig.add_trace(go.Scatter(
            x=baseline_dates,
            y=[baseline_mean] * len(baseline_dates),
            mode='lines',
            name='Baseline',
            line=dict(color='orange', width=2, dash='dash')
        ))

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="NDVI",
        hovermode='x unified',
        height=400,
        margin=dict(l=0, r=0, t=10, b=0)
    )

    st.plotly_chart(fig, use_container_width=True)

    # Phenology table
    if 'phenology_by_year' in ndvi_data and ndvi_data['phenology_by_year']:
        st.markdown("### 🌱 Phenology Metrics")

        phenology_data = []

        for year, metrics in ndvi_data['phenology_by_year'].items():
            phenology_data.append({
                'Year': year,
                'Greenup': metrics.get('greenup_date', 'N/A'),
                'Peak Date': metrics.get('peak_date', 'N/A'),
                'Peak NDVI': f"{metrics.get('peak_value', 0):.3f}",
                'Senescence': metrics.get('senescence_date', 'N/A'),
                'Season Length (days)': metrics.get('season_length_days', 'N/A'),
                'Integral (AUC)': f"{metrics.get('integral_auc', 0):.1f}"
            })

        phenology_df = pd.DataFrame(phenology_data)
        phenology_df = phenology_df.sort_values('Year', ascending=False)

        st.dataframe(phenology_df, use_container_width=True, hide_index=True)

    # Map (if geometries available)
    if geometries:
        st.markdown("### 🗺️ Province Location")

        # Extract this province's geometry
        province_feature = None
        for feature in geometries['features']:
            if feature['properties']['name_en'] == selected_province:
                province_feature = feature
                break

        if province_feature:
            # Create simple map
            geom = province_feature['geometry']

            # Get centroid (rough estimate)
            if geom['type'] == 'MultiPolygon':
                coords = geom['coordinates'][0][0]
            else:
                coords = geom['coordinates'][0]

            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]

            center_lon = (min(lons) + max(lons)) / 2
            center_lat = (min(lats) + max(lats)) / 2

            # Create plotly map
            fig_map = go.Figure(go.Scattermapbox(
                lon=[center_lon],
                lat=[center_lat],
                mode='markers+text',
                marker=dict(size=20, color='green'),
                text=[selected_province],
                textposition="top center"
            ))

            fig_map.update_layout(
                mapbox=dict(
                    style="open-street-map",
                    center=dict(lon=center_lon, lat=center_lat),
                    zoom=8
                ),
                height=400,
                margin=dict(l=0, r=0, t=0, b=0)
            )

            st.plotly_chart(fig_map, use_container_width=True)


if __name__ == '__main__':
    main()
