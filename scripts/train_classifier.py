"""
Train Random Forest classifier for olive tree identification (Milestone 2).

This is a skeleton/template for future implementation.
Requires ground truth data collection first.

Steps:
1. Collect training samples (50-100 olive parcels + non-olive samples)
2. Extract multi-temporal features from Sentinel-2
3. Train Random Forest classifier
4. Validate with hold-out test set
5. Apply to all provinces
6. Update database with improved classifications
"""

import ee
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import pickle
from pathlib import Path
import json


def collect_ground_truth():
    """
    Collect ground truth training samples.

    TODO: Implement manual digitization workflow
    - Load province boundaries in Google Earth
    - Trace known olive parcels (50-100 per province)
    - Trace non-olive samples (vineyards, forests, urban, bare soil)
    - Export as KML/GeoJSON
    - Store in data/ground_truth/training_samples.geojson

    Format:
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"class": "Olive", "province": "İzmir"},
                "geometry": {"type": "Polygon", "coordinates": [...]}
            },
            ...
        ]
    }

    Returns:
        ee.FeatureCollection of training samples
    """

    training_path = Path('data/ground_truth/training_samples.geojson')

    if not training_path.exists():
        print("❌ Ground truth file not found")
        print(f"   Expected: {training_path}")
        print("\nTo create training samples:")
        print("1. Open Google Earth Pro")
        print("2. Load province boundaries from data/geo/")
        print("3. Use polygon tool to trace:")
        print("   - Olive groves (50-100 samples per province)")
        print("   - Vineyards (50 samples)")
        print("   - Forests (50 samples)")
        print("   - Urban areas (30 samples)")
        print("   - Bare soil/agriculture (30 samples)")
        print("4. Save as KML, convert to GeoJSON")
        print("5. Place in data/ground_truth/training_samples.geojson")
        return None

    with open(training_path, 'r') as f:
        geojson = json.load(f)

    # Convert to Earth Engine FeatureCollection
    features = []
    for feature in geojson['features']:
        ee_feature = ee.Feature(
            ee.Geometry(feature['geometry']),
            feature['properties']
        )
        features.append(ee_feature)

    return ee.FeatureCollection(features)


def extract_features(training_samples, year=2024):
    """
    Extract multi-temporal spectral features at training locations.

    Args:
        training_samples: ee.FeatureCollection with 'class' property
        year: Year to extract features from

    Returns:
        pandas DataFrame with features and labels
    """

    print("\nExtracting features from Sentinel-2...")

    # Define 3 key dates for phenology
    dates = [
        (f'{year}-04-15', 'april'),   # Greenup
        (f'{year}-06-15', 'june'),    # Peak
        (f'{year}-09-15', 'september') # Pre-harvest
    ]

    all_features = []

    for date_str, season in dates:
        print(f"  Processing {season} ({date_str})...")

        # Get Sentinel-2 imagery for this date (±15 day window)
        collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                      .filterDate(
                          ee.Date(date_str).advance(-15, 'day'),
                          ee.Date(date_str).advance(15, 'day')
                      )
                      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)))

        # Compute median composite
        composite = collection.median()

        # Compute indices
        ndvi = composite.normalizedDifference(['B8', 'B4']).rename(f'NDVI_{season}')
        ndre = composite.normalizedDifference(['B8', 'B5']).rename(f'NDRE_{season}')
        evi = composite.expression(
            '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))',
            {
                'NIR': composite.select('B8'),
                'RED': composite.select('B4'),
                'BLUE': composite.select('B2')
            }
        ).rename(f'EVI_{season}')

        # GCVI (Green Chlorophyll Vegetation Index) - best for olive discrimination
        gcvi = composite.expression(
            '(NIR / GREEN) - 1',
            {
                'NIR': composite.select('B8'),
                'GREEN': composite.select('B3')
            }
        ).rename(f'GCVI_{season}')

        # Red-edge bands (critical for classification)
        b5 = composite.select('B5').rename(f'B5_{season}')
        b6 = composite.select('B6').rename(f'B6_{season}')
        b7 = composite.select('B7').rename(f'B7_{season}')

        features_image = ee.Image.cat([ndvi, ndre, evi, gcvi, b5, b6, b7])

        all_features.append(features_image)

    # Combine all dates
    feature_stack = ee.Image.cat(all_features)

    # Sample at training locations
    print("\n  Sampling at training locations...")

    samples = feature_stack.sampleRegions(
        collection=training_samples,
        scale=10,  # 10m resolution
        projection='EPSG:4326',
        geometries=True
    )

    # Convert to pandas DataFrame
    sample_data = samples.getInfo()

    rows = []
    for feature in sample_data['features']:
        props = feature['properties']
        rows.append(props)

    df = pd.DataFrame(rows)

    print(f"  ✅ Extracted features for {len(df)} samples")

    return df


def train_classifier(df):
    """
    Train Random Forest classifier.

    Args:
        df: DataFrame with features and 'class' column

    Returns:
        Trained classifier
    """

    print("\nTraining Random Forest classifier...")

    # Separate features and labels
    X = df.drop(['class', 'province'], axis=1, errors='ignore')
    y = df['class']

    # Train/test split (80/20)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print(f"  Training samples: {len(X_train)}")
    print(f"  Test samples: {len(X_test)}")

    # Train Random Forest
    clf = RandomForestClassifier(
        n_estimators=500,
        max_depth=20,
        min_samples_split=10,
        min_samples_leaf=4,
        max_features='sqrt',
        random_state=42,
        n_jobs=-1,
        verbose=1
    )

    clf.fit(X_train, y_train)

    # Validate
    print("\n  Validation Results:")

    y_pred = clf.predict(X_test)

    print("\n", classification_report(y_test, y_pred))

    print("\n  Confusion Matrix:")
    cm = confusion_matrix(y_test, y_pred)
    print(cm)

    # Feature importance
    feature_importance = pd.DataFrame({
        'feature': X.columns,
        'importance': clf.feature_importances_
    }).sort_values('importance', ascending=False)

    print("\n  Top 10 Most Important Features:")
    print(feature_importance.head(10).to_string(index=False))

    # Save model
    model_path = Path('models/olive_classifier_rf.pkl')
    model_path.parent.mkdir(exist_ok=True)

    with open(model_path, 'wb') as f:
        pickle.dump(clf, f)

    print(f"\n  ✅ Model saved to {model_path}")

    return clf


def apply_classifier(classifier, province_geometry, year=2024):
    """
    Apply trained classifier to a province.

    TODO: Implement classification application
    This requires:
    1. Load the trained classifier
    2. Extract features for entire province (same dates as training)
    3. Classify each pixel
    4. Return olive mask

    Args:
        classifier: Trained sklearn classifier
        province_geometry: ee.Geometry of province
        year: Year to classify

    Returns:
        ee.Image with classification (1=Olive, 0=Non-Olive)
    """

    print("\n⚠️  Classification application not yet implemented")
    print("   This requires converting sklearn model to Earth Engine")
    print("   OR exporting features, classifying locally, re-uploading mask")

    # Placeholder
    return None


def main():
    """
    Main workflow for training olive classifier.

    THIS IS A SKELETON FOR MILESTONE 2.
    Requires ground truth data collection first.
    """

    print("OliveIntel - Olive Classifier Training (Milestone 2)")
    print("=" * 60)
    print("\n⚠️  THIS IS A TEMPLATE SCRIPT")
    print("   Requires ground truth data collection before running")
    print("=" * 60)

    # Initialize GEE
    ee.Initialize()

    # Step 1: Collect ground truth
    print("\nStep 1: Load ground truth samples")
    training_samples = collect_ground_truth()

    if training_samples is None:
        print("\n❌ Cannot proceed without training data")
        print("\nNext steps:")
        print("1. Collect training samples in Google Earth")
        print("2. Save to data/ground_truth/training_samples.geojson")
        print("3. Re-run this script")
        return

    # Step 2: Extract features
    print("\nStep 2: Extract multi-temporal features")
    df = extract_features(training_samples, year=2024)

    # Save extracted features for inspection
    features_path = Path('data/interim/extracted_features.csv')
    df.to_csv(features_path, index=False)
    print(f"\n  ✅ Features saved to {features_path}")

    # Step 3: Train classifier
    print("\nStep 3: Train Random Forest")
    classifier = train_classifier(df)

    # Step 4: Apply to provinces (TODO)
    print("\nStep 4: Apply classifier to provinces")
    print("  ⚠️  Not yet implemented - requires Earth Engine integration")

    print("\n" + "=" * 60)
    print("✅ CLASSIFIER TRAINING COMPLETE")
    print("=" * 60)

    print("\nNext steps:")
    print("1. Review validation metrics (target: >80% accuracy)")
    print("2. If accuracy is low:")
    print("   - Collect more training samples")
    print("   - Balance classes (equal samples per class)")
    print("   - Add more features")
    print("3. Implement classification application to provinces")
    print("4. Update pipeline/mask.py to use classifier instead of threshold")


if __name__ == '__main__':
    main()
