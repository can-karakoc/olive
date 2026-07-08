"""Apply database schema to Neon PostgreSQL."""

import psycopg2
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("❌ DATABASE_URL not found in .env file")
    exit(1)

# Read schema file
schema_path = Path('database/schema.sql')

if not schema_path.exists():
    print(f"❌ Schema file not found: {schema_path}")
    exit(1)

with open(schema_path, 'r') as f:
    schema_sql = f.read()

print("Applying OliveIntel database schema...")
print("=" * 60)

try:
    # Connect
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True  # Required for CREATE EXTENSION
    cursor = conn.cursor()

    print("✅ Connected")

    # Execute schema
    print("\nApplying schema (this may take a moment)...")
    cursor.execute(schema_sql)

    print("✅ Schema applied successfully!")

    # Verify tables created
    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = cursor.fetchall()

    print(f"\nCreated tables ({len(tables)}):")
    for (table,) in tables:
        # Get row count
        cursor.execute(f"SELECT COUNT(*) FROM {table};")
        count = cursor.fetchone()[0]
        print(f"  • {table:20} ({count} rows)")

    # Verify views
    cursor.execute("""
        SELECT table_name
        FROM information_schema.views
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    views = cursor.fetchall()

    if views:
        print(f"\nCreated views ({len(views)}):")
        for (view,) in views:
            print(f"  • {view}")

    # Check PostGIS
    cursor.execute("SELECT PostGIS_Version();")
    postgis_version = cursor.fetchone()[0]
    print(f"\n✅ PostGIS installed: {postgis_version}")

    cursor.close()
    conn.close()

    print("\n" + "=" * 60)
    print("✅ Database ready!")
    print("\nNext steps:")
    print("  1. Wait for province processing to complete")
    print("  2. Load data: python scripts/load_provinces_to_db.py")
    print("  3. Run Streamlit app: streamlit run app/streamlit_app.py")

except Exception as e:
    print(f"\n❌ Schema application failed: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
