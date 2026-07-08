"""Test Neon PostgreSQL connection."""

import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("❌ DATABASE_URL not found in .env file")
    exit(1)

print("Testing Neon PostgreSQL connection...")
print("=" * 60)

try:
    # Connect
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    print("✅ Connected successfully!")

    # Test query
    cursor.execute("SELECT version();")
    version = cursor.fetchone()[0]
    print(f"\nPostgreSQL version:")
    print(f"  {version}")

    # Check if PostGIS is available
    cursor.execute("""
        SELECT COUNT(*)
        FROM pg_available_extensions
        WHERE name = 'postgis';
    """)
    postgis_available = cursor.fetchone()[0]

    if postgis_available:
        print(f"\n✅ PostGIS extension is available")

        # Check if installed
        cursor.execute("""
            SELECT COUNT(*)
            FROM pg_extension
            WHERE extname = 'postgis';
        """)
        postgis_installed = cursor.fetchone()[0]

        if postgis_installed:
            cursor.execute("SELECT PostGIS_Version();")
            postgis_version = cursor.fetchone()[0]
            print(f"   PostGIS version: {postgis_version}")
        else:
            print(f"   ⚠️  PostGIS not installed yet (will install with schema)")
    else:
        print(f"\n⚠️  PostGIS not available on this instance")

    # Check existing tables
    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = cursor.fetchall()

    if tables:
        print(f"\nExisting tables ({len(tables)}):")
        for (table,) in tables:
            print(f"  • {table}")
    else:
        print(f"\nNo tables found (database is empty)")

    cursor.close()
    conn.close()

    print("\n" + "=" * 60)
    print("✅ Database connection test successful!")
    print("\nNext step: Apply schema with:")
    print("  python scripts/apply_schema.py")

except Exception as e:
    print(f"\n❌ Connection failed: {e}")
    print("\nCheck:")
    print("  1. DATABASE_URL in .env is correct")
    print("  2. Neon project is active (not paused)")
    print("  3. IP is allowed (Neon free tier allows all IPs)")
    exit(1)
