"""
OliveIntel Streamlit Health Map - PostgreSQL Version

Connects to Neon PostgreSQL instead of reading JSON files.
"""

import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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


@st.cache_resource
def get_db_connection():
    """Get database connection (cached)."""
    DATABASE_URL = os.getenv('DATABASE_URL')

    if not DATABASE_URL:
        st.error("❌ DATABASE_URL not found in environment variables")
        st.stop()

    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        st.error(f"❌ Database connection failed: {e}")
        st.stop()


@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_provinces():
    """Load province list from database."""
    conn = get_db_connection()

    query = """
        SELECT id, name, name_tr, area_ha,
               olive_area_ha, olive_tree_count,
               quality_score, quality_grade, quality_badge
        FROM provinces
        ORDER BY name
    """

    df = pd.read_sql(query, conn)
    return df


@st.cache_data(ttl=3600)
def load_province_timeseries(province_id, index_name='ndvi'):
    """Load time series for a province."""
    conn = get_db_connection()

    query = f"""
        SELECT date, {index_name}
        FROM timeseries
        WHERE province_id = %s
          AND {index_name} IS NOT NULL
        ORDER BY date
    """

    df = pd.read_sql(query, conn, params=(province_id,))
    df['date'] = pd.to_datetime(df['date'])

    return df


@st.cache_data(ttl=3600)
def load_province_phenology(province_id, index_name='NDVI'):
    """Load phenology metrics for a province."""
    conn = get_db_connection()

    query = """
        SELECT year, index_name, greenup_date, peak_date, peak_value,
               senescence_date, season_length_days, integral_auc
        FROM phenology
        WHERE province_id = %s AND index_name = %s
        ORDER BY year DESC
    """

    df = pd.read_sql(query, conn, params=(province_id, index_name))
    return df


@st.cache_data(ttl=3600)
def get_current_health(province_id):
    """Get current health status from view."""
    conn = get_db_connection()

    query = """
        SELECT *
        FROM v_current_health
        WHERE province_id = %s
    """

    df = pd.read_sql(query, conn, params=(province_id,))

    if len(df) > 0:
        return df.iloc[0].to_dict()
    return None


def compute_baseline_manual(df, current_date, window_days=7):
    """Fallback: compute baseline if view doesn't have it."""
    current_doy = current_date.timetuple().tm_yday
    baseline_start = current_date - timedelta(days=5*365)

    baseline_data = []

    for _, row in df.iterrows():
        row_date = pd.to_datetime(row['date'])

        if row_date >= baseline_start and row_date < current_date:
            row_doy = row_date.timetuple().tm_yday

            if abs(row_doy - current_doy) <= window_days:
                baseline_data.append(row['ndvi'])

    if len(baseline_data) < 5:
        return None, None

    return np.mean(baseline_data), np.std(baseline_data)


def main():
    st.markdown('<div class="main-header">🫒 OliveIntel</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Olive Orchard Health Monitor - Aegean Region</div>', unsafe_allow_html=True)

    # Load provinces
    try:
        provinces_df = load_provinces()
    except Exception as e:
        st.error(f"❌ Failed to load provinces: {e}")
        st.info("Make sure to run: python scripts/load_data_to_db.py")
        return

    if len(provinces_df) == 0:
        st.warning("⚠️ No provinces found in database")
        st.info("Run: python scripts/load_data_to_db.py")
        return

    st.success(f"✅ Loaded data for {len(provinces_df)} provinces")

    # Sidebar
    st.sidebar.header("Select Province")

    province_names = provinces_df['name'].tolist()
    selected_province_name = st.sidebar.selectbox("Province", province_names)

    selected_province = provinces_df[provinces_df['name'] == selected_province_name].iloc[0]
    province_id = int(selected_province['id'])  # Convert numpy.int64 to Python int

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

    **Database:** Neon PostgreSQL
    """)

    # Main content
    st.header(f"{selected_province_name} Province")

    # Load time series
    try:
        df = load_province_timeseries(province_id, 'ndvi')
    except Exception as e:
        st.error(f"❌ Failed to load time series: {e}")
        return

    if len(df) == 0:
        st.warning(f"⚠️ No time series data for {selected_province_name}")
        return

    # Get current health
    health = get_current_health(province_id)

    if health:
        current_ndvi = health['current_ndvi']
        current_date = pd.to_datetime(health['current_date'])  # Convert to pandas Timestamp
        baseline_ndvi = health['baseline_ndvi']
        baseline_stddev = health['baseline_stddev']
        z_score = health['z_score']
        health_status = health['health_status']
    else:
        # Fallback
        current_ndvi = df.iloc[-1]['ndvi']
        current_date = pd.to_datetime(df.iloc[-1]['date'])  # Ensure Timestamp
        baseline_ndvi, baseline_stddev = compute_baseline_manual(df, current_date)

        if baseline_ndvi:
            z_score = (current_ndvi - baseline_ndvi) / baseline_stddev if baseline_stddev else 0

            if z_score < -3:
                health_status = 'critical'
            elif z_score < -2:
                health_status = 'warning'
            elif z_score < -1:
                health_status = 'fair'
            else:
                health_status = 'good'
        else:
            baseline_ndvi = df['ndvi'].mean()
            baseline_stddev = df['ndvi'].std()
            z_score = 0
            health_status = 'unknown'

    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Current NDVI</div>
            <div class="kpi-value">{current_ndvi:.3f}</div>
            <div class="kpi-label">{current_date.strftime('%Y-%m-%d') if hasattr(current_date, 'strftime') else current_date}</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">5-Year Baseline</div>
            <div class="kpi-value">{baseline_ndvi:.3f}</div>
            <div class="kpi-label">±{baseline_stddev:.3f}</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        pct_change = ((current_ndvi - baseline_ndvi) / baseline_ndvi) * 100 if baseline_ndvi else 0
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
        status_emoji = {
            "good": "🟢",
            "fair": "🟡",
            "warning": "🟠",
            "critical": "🔴",
            "unknown": "⚪"
        }.get(health_status, "⚪")

        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-label">Health Status</div>
            <div class="kpi-value {status_class}">{status_emoji} {health_status.upper()}</div>
        </div>
        """, unsafe_allow_html=True)

    # Province Metrics
    if selected_province['quality_score']:
        st.markdown("### 📊 Province Metrics")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Quality Score",
                f"{selected_province['quality_score']}/100",
                delta=f"{selected_province['quality_badge']}"
            )

        with col2:
            if selected_province['olive_area_ha']:
                st.metric(
                    "Olive Grove Area",
                    f"{selected_province['olive_area_ha']:,.0f} ha"
                )

        with col3:
            if selected_province['olive_tree_count']:
                st.metric(
                    "Est. Tree Count",
                    f"~{selected_province['olive_tree_count']:,}"
                )

    # Time series plot
    st.markdown("### 📈 NDVI Time Series")

    fig = go.Figure()

    # Plot NDVI
    fig.add_trace(go.Scatter(
        x=df['date'],
        y=df['ndvi'],
        mode='lines+markers',
        name='NDVI',
        line=dict(color='darkgreen', width=2),
        marker=dict(size=3)
    ))

    # Baseline line
    recent_dates = df[df['date'] >= current_date - timedelta(days=365)]['date']
    if len(recent_dates) > 0:
        fig.add_trace(go.Scatter(
            x=recent_dates,
            y=[baseline_ndvi] * len(recent_dates),
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
    st.markdown("### 🌱 Phenology Metrics")

    try:
        phenology_df = load_province_phenology(province_id, 'NDVI')

        if len(phenology_df) > 0:
            # Format for display
            display_df = phenology_df[['year', 'greenup_date', 'peak_date', 'peak_value', 'senescence_date', 'season_length_days', 'integral_auc']].copy()
            display_df.columns = ['Year', 'Greenup', 'Peak Date', 'Peak NDVI', 'Senescence', 'Season Length (days)', 'Integral (AUC)']
            display_df['Peak NDVI'] = display_df['Peak NDVI'].apply(lambda x: f"{x:.3f}" if pd.notna(x) else 'N/A')
            display_df['Integral (AUC)'] = display_df['Integral (AUC)'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else 'N/A')

            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info("No phenology data available")
    except Exception as e:
        st.warning(f"Could not load phenology: {e}")


if __name__ == '__main__':
    main()
