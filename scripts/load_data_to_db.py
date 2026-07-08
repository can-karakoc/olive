"""
Load province data into Neon PostgreSQL database.

Loads:
1. Province boundaries (from GeoJSON)
2. Time series data (from JSON files)
3. Phenology metrics (from JSON files)
4. Density metrics (from JSON files)
5. Quality scores (from JSON files)
"""

import psycopg2
import json
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')


def connect_db():
    """Connect to PostgreSQL database."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not found in .env file")

    return psycopg2.connect(DATABASE_URL)


def load_provinces(cursor):
    """
    Load province boundaries into provinces table.

    Returns:
        Dict mapping province names to IDs
    """

    print("\n1. Loading province boundaries...")

    # Load combined GeoJSON
    geojson_path = Path('data/geo/aegean_provinces.geojson')

    if not geojson_path.exists():
        print(f"  ⚠️  GeoJSON not found: {geojson_path}")
        return {}

    with open(geojson_path, 'r', encoding='utf-8') as f:
        geojson = json.load(f)

    province_ids = {}

    for feature in geojson['features']:
        props = feature['properties']
        geom = feature['geometry']

        name = props['name_en']
        area_ha = props.get('area_ha', 0)

        # Convert geometry to WKT for PostGIS
        geom_wkt = geometry_to_wkt(geom)

        # Check if province exists
        cursor.execute(
            "SELECT id FROM provinces WHERE name = %s",
            (name,)
        )

        result = cursor.fetchone()

        if result:
            province_id = result[0]
            print(f"  • {name}: Already exists (ID={province_id})")
        else:
            # Insert new province
            cursor.execute("""
                INSERT INTO provinces (name, name_tr, gadm_name, geometry, area_ha)
                VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326), %s)
                RETURNING id
            """, (
                name,
                name,  # For now, same as English
                props.get('gadm_name', name),
                geom_wkt,
                area_ha
            ))

            province_id = cursor.fetchone()[0]
            print(f"  • {name}: Inserted (ID={province_id})")

        province_ids[name] = province_id

    print(f"\n  ✅ Loaded {len(province_ids)} provinces")

    return province_ids


def load_time_series(cursor, province_ids):
    """Load time series data into timeseries table."""

    print("\n2. Loading time series data...")

    data_dir = Path('data/interim/provinces')

    if not data_dir.exists():
        print(f"  ⚠️  Directory not found: {data_dir}")
        return

    json_files = list(data_dir.glob('*_timeseries.json'))

    total_rows = 0

    for json_path in sorted(json_files):
        with open(json_path, 'r', encoding='utf-8') as f:
            province_data = json.load(f)

        province_name = province_data['province_name']

        if province_name not in province_ids:
            print(f"  ⚠️  Province not found in database: {province_name}")
            continue

        province_id = province_ids[province_name]

        # Load time series for each index
        for index_name, index_data in province_data.get('indices', {}).items():
            time_series = index_data.get('time_series', [])

            if not time_series:
                continue

            print(f"  • {province_name} - {index_name}: {len(time_series)} observations")

            for record in time_series:
                date = record['date']
                value = record.get('value_smoothed', record.get('value'))

                if value is None:
                    continue

                # Check if record exists
                cursor.execute("""
                    SELECT id FROM timeseries
                    WHERE province_id = %s AND date = %s
                """, (province_id, date))

                existing = cursor.fetchone()

                if existing:
                    # Update existing record
                    update_query = f"""
                        UPDATE timeseries
                        SET {index_name.lower()} = %s
                        WHERE province_id = %s AND date = %s
                    """
                    cursor.execute(update_query, (value, province_id, date))
                else:
                    # Insert new record
                    insert_query = f"""
                        INSERT INTO timeseries (province_id, date, {index_name.lower()})
                        VALUES (%s, %s, %s)
                    """
                    cursor.execute(insert_query, (province_id, date, value))

                total_rows += 1

    print(f"\n  ✅ Loaded {total_rows} time series records")


def load_phenology(cursor, province_ids):
    """Load phenology metrics into phenology table."""

    print("\n3. Loading phenology metrics...")

    data_dir = Path('data/interim/provinces')
    json_files = list(data_dir.glob('*_timeseries.json'))

    total_rows = 0

    for json_path in sorted(json_files):
        with open(json_path, 'r', encoding='utf-8') as f:
            province_data = json.load(f)

        province_name = province_data['province_name']

        if province_name not in province_ids:
            continue

        province_id = province_ids[province_name]

        # Load phenology for each index
        for index_name, index_data in province_data.get('indices', {}).items():
            phenology_by_year = index_data.get('phenology_by_year', {})

            for year, metrics in phenology_by_year.items():
                year = int(year)

                # Extract metrics
                greenup_date = metrics.get('greenup_date')
                peak_date = metrics.get('peak_date')
                peak_value = metrics.get('peak_value')
                senescence_date = metrics.get('senescence_date')
                season_length = metrics.get('season_length_days')
                integral_auc = metrics.get('integral_auc')

                if not peak_date:
                    continue

                # Compute DOY
                peak_doy = datetime.strptime(peak_date, '%Y-%m-%d').timetuple().tm_yday

                # Check if exists
                cursor.execute("""
                    SELECT id FROM phenology
                    WHERE province_id = %s AND year = %s AND index_name = %s
                """, (province_id, year, index_name))

                if cursor.fetchone():
                    # Update
                    cursor.execute("""
                        UPDATE phenology
                        SET greenup_date = %s, peak_date = %s, peak_doy = %s,
                            peak_value = %s, senescence_date = %s,
                            season_length_days = %s, integral_auc = %s
                        WHERE province_id = %s AND year = %s AND index_name = %s
                    """, (
                        greenup_date, peak_date, peak_doy, peak_value,
                        senescence_date, season_length, integral_auc,
                        province_id, year, index_name
                    ))
                else:
                    # Insert
                    cursor.execute("""
                        INSERT INTO phenology (
                            province_id, year, index_name,
                            greenup_date, peak_date, peak_doy, peak_value,
                            senescence_date, season_length_days, integral_auc
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        province_id, year, index_name,
                        greenup_date, peak_date, peak_doy, peak_value,
                        senescence_date, season_length, integral_auc
                    ))

                total_rows += 1

    print(f"  ✅ Loaded {total_rows} phenology records")


def load_density_metrics(cursor, province_ids):
    """Load density metrics into provinces table."""

    print("\n4. Loading density metrics...")

    data_dir = Path('data/interim/provinces')
    json_files = list(data_dir.glob('*_timeseries.json'))

    updated = 0

    for json_path in sorted(json_files):
        with open(json_path, 'r', encoding='utf-8') as f:
            province_data = json.load(f)

        province_name = province_data['province_name']

        if province_name not in province_ids:
            continue

        density = province_data.get('density')

        if not density:
            print(f"  • {province_name}: No density data")
            continue

        province_id = province_ids[province_name]

        # Update provinces table
        cursor.execute("""
            UPDATE provinces
            SET olive_area_ha = %s,
                olive_tree_count = %s,
                tree_count_confidence = %s,
                olive_coverage_pct = %s,
                density_last_updated = CURRENT_DATE
            WHERE id = %s
        """, (
            density.get('grove_area_ha'),
            density.get('tree_count'),
            density.get('tree_count_confidence'),
            density.get('grove_coverage_pct'),
            province_id
        ))

        print(f"  • {province_name}: {density['primary_value']:,.0f} {density['primary_metric'].replace('_', ' ')}")

        updated += 1

    print(f"\n  ✅ Updated {updated} provinces with density metrics")


def load_quality_scores(cursor, province_ids):
    """Load quality scores into provinces table."""

    print("\n5. Loading quality scores...")

    data_dir = Path('data/interim/provinces')
    json_files = list(data_dir.glob('*_timeseries.json'))

    updated = 0

    for json_path in sorted(json_files):
        with open(json_path, 'r', encoding='utf-8') as f:
            province_data = json.load(f)

        province_name = province_data['province_name']

        if province_name not in province_ids:
            continue

        quality = province_data.get('quality')

        if not quality:
            print(f"  • {province_name}: No quality data")
            continue

        province_id = province_ids[province_name]

        # Update provinces table
        cursor.execute("""
            UPDATE provinces
            SET quality_score = %s,
                quality_grade = %s,
                quality_badge = %s,
                quality_last_updated = CURRENT_DATE
            WHERE id = %s
        """, (
            quality.get('total_score'),
            quality.get('grade'),
            quality.get('badge'),
            province_id
        ))

        print(f"  • {province_name}: {quality['total_score']}/100 ({quality['badge']})")

        updated += 1

    print(f"\n  ✅ Updated {updated} provinces with quality scores")


def geometry_to_wkt(geom):
    """Convert GeoJSON geometry to WKT format."""

    geom_type = geom['type']
    coords = geom['coordinates']

    if geom_type == 'Polygon':
        # Single polygon
        rings = []
        for ring in coords:
            points = ', '.join([f"{lon} {lat}" for lon, lat in ring])
            rings.append(f"({points})")

        return f"POLYGON({', '.join(rings)})"

    elif geom_type == 'MultiPolygon':
        # Multiple polygons
        polygons = []
        for poly in coords:
            rings = []
            for ring in poly:
                points = ', '.join([f"{lon} {lat}" for lon, lat in ring])
                rings.append(f"({points})")
            polygons.append(f"({', '.join(rings)})")

        return f"MULTIPOLYGON({', '.join(polygons)})"

    else:
        raise ValueError(f"Unsupported geometry type: {geom_type}")


def main():
    print("OliveIntel - Database Data Loader")
    print("=" * 60)

    try:
        # Connect to database
        print("Connecting to database...")
        conn = connect_db()
        conn.autocommit = False  # Use transactions
        cursor = conn.cursor()

        print("✅ Connected to Neon PostgreSQL")

        # Load data in order
        province_ids = load_provinces(cursor)
        conn.commit()

        load_time_series(cursor, province_ids)
        conn.commit()

        load_phenology(cursor, province_ids)
        conn.commit()

        load_density_metrics(cursor, province_ids)
        conn.commit()

        load_quality_scores(cursor, province_ids)
        conn.commit()

        cursor.close()
        conn.close()

        print("\n" + "=" * 60)
        print("✅ ALL DATA LOADED SUCCESSFULLY")
        print("=" * 60)

        print("\nNext steps:")
        print("1. Verify data: SELECT * FROM v_current_health;")
        print("2. Test Streamlit app: streamlit run app/streamlit_app.py")
        print("3. Start frontend development (Milestone 3)")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

        if 'conn' in locals():
            conn.rollback()
            conn.close()

        exit(1)


if __name__ == '__main__':
    main()
