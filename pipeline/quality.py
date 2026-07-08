"""
Olive quality scoring module.

Computes a 0-100 quality score for olive orchards based on:
- Peak NDVI (biomass/vigor)
- Season length (productivity period)
- Inter-annual stability (management quality)
- Phenology timing (optimal vs delayed)
"""

import numpy as np
import pandas as pd
from typing import Dict, List


def compute_quality_score(
    phenology_metrics: Dict,
    historical_phenology: List[Dict] = None
) -> Dict:
    """
    Compute quality score (0-100) from phenology metrics.

    **Scoring Components:**
    1. **Peak NDVI (40 points)**: Higher = more vigorous
       - 0.70+: 40 pts
       - 0.60-0.70: 30 pts
       - 0.50-0.60: 20 pts
       - <0.50: 10 pts

    2. **Season Length (30 points)**: Longer = more productive
       - 180+ days: 30 pts
       - 150-180: 25 pts
       - 120-150: 20 pts
       - <120: 10 pts

    3. **Stability (20 points)**: Low inter-annual variance = consistent management
       - Requires 3+ years of historical data
       - Coefficient of variation < 0.1: 20 pts
       - CV 0.1-0.15: 15 pts
       - CV > 0.15: 10 pts

    4. **Timing (10 points)**: Early greenup = good start
       - Greenup before Apr 15: 10 pts
       - Apr 15-30: 8 pts
       - After May 1: 5 pts

    Args:
        phenology_metrics: Current year phenology
        historical_phenology: List of past years (for stability)

    Returns:
        Dict with:
        - total_score: 0-100
        - components: Breakdown by category
        - grade: Letter grade (A+, A, B, C, D, F)
        - badge: Verbal description
    """

    score = 0
    components = {}

    # 1. Peak NDVI Score (40 pts)
    peak_ndvi = phenology_metrics.get('peak_value', 0)

    if peak_ndvi >= 0.70:
        ndvi_score = 40
        ndvi_grade = 'Excellent'
    elif peak_ndvi >= 0.60:
        ndvi_score = 30 + ((peak_ndvi - 0.60) / 0.10) * 10
        ndvi_grade = 'Very Good'
    elif peak_ndvi >= 0.50:
        ndvi_score = 20 + ((peak_ndvi - 0.50) / 0.10) * 10
        ndvi_grade = 'Good'
    elif peak_ndvi >= 0.40:
        ndvi_score = 10 + ((peak_ndvi - 0.40) / 0.10) * 10
        ndvi_grade = 'Fair'
    else:
        ndvi_score = max(0, peak_ndvi * 25)
        ndvi_grade = 'Poor'

    components['peak_ndvi'] = {
        'value': float(peak_ndvi),
        'score': float(ndvi_score),
        'grade': ndvi_grade
    }
    score += ndvi_score

    # 2. Season Length Score (30 pts)
    season_length = phenology_metrics.get('season_length_days', 0)

    if season_length >= 180:
        length_score = 30
        length_grade = 'Excellent'
    elif season_length >= 150:
        length_score = 25 + ((season_length - 150) / 30) * 5
        length_grade = 'Very Good'
    elif season_length >= 120:
        length_score = 20 + ((season_length - 120) / 30) * 5
        length_grade = 'Good'
    elif season_length >= 90:
        length_score = 10 + ((season_length - 90) / 30) * 10
        length_grade = 'Fair'
    else:
        length_score = max(0, (season_length / 90) * 10)
        length_grade = 'Poor'

    components['season_length'] = {
        'value': int(season_length),
        'score': float(length_score),
        'grade': length_grade
    }
    score += length_score

    # 3. Stability Score (20 pts)
    if historical_phenology and len(historical_phenology) >= 3:
        # Compute coefficient of variation of peak NDVI
        peak_values = [p.get('peak_value', 0) for p in historical_phenology]
        peak_values = [v for v in peak_values if v > 0]  # Filter zeros

        if len(peak_values) >= 3:
            mean_peak = np.mean(peak_values)
            std_peak = np.std(peak_values)
            cv = std_peak / mean_peak if mean_peak > 0 else 1

            if cv < 0.10:
                stability_score = 20
                stability_grade = 'Very Stable'
            elif cv < 0.15:
                stability_score = 15
                stability_grade = 'Stable'
            elif cv < 0.20:
                stability_score = 10
                stability_grade = 'Moderate'
            else:
                stability_score = 5
                stability_grade = 'Variable'

            components['stability'] = {
                'cv': float(cv),
                'score': float(stability_score),
                'grade': stability_grade,
                'years_analyzed': len(peak_values)
            }
            score += stability_score
        else:
            components['stability'] = {
                'score': 0,
                'grade': 'Insufficient Data',
                'years_analyzed': len(peak_values)
            }
    else:
        components['stability'] = {
            'score': 0,
            'grade': 'Insufficient Data',
            'years_analyzed': 0
        }

    # 4. Timing Score (10 pts)
    greenup_date = phenology_metrics.get('greenup_date')

    if greenup_date:
        # Convert to day of year
        if isinstance(greenup_date, str):
            greenup_date = pd.to_datetime(greenup_date)

        greenup_doy = greenup_date.timetuple().tm_yday

        # Ideal greenup: early April (DOY ~95-105)
        ideal_doy = 105  # April 15

        if greenup_doy <= ideal_doy:
            timing_score = 10
            timing_grade = 'Early'
        elif greenup_doy <= ideal_doy + 15:  # By Apr 30
            timing_score = 8
            timing_grade = 'On Time'
        elif greenup_doy <= ideal_doy + 30:  # By May 15
            timing_score = 5
            timing_grade = 'Slightly Late'
        else:
            timing_score = 2
            timing_grade = 'Late'

        components['timing'] = {
            'greenup_doy': int(greenup_doy),
            'greenup_date': greenup_date.strftime('%Y-%m-%d'),
            'score': float(timing_score),
            'grade': timing_grade
        }
        score += timing_score
    else:
        components['timing'] = {
            'score': 0,
            'grade': 'Unknown'
        }

    # Total score
    total_score = round(score)

    # Grade
    if total_score >= 95:
        grade = 'A+'
        badge = 'Exceptional'
    elif total_score >= 90:
        grade = 'A'
        badge = 'Excellent'
    elif total_score >= 85:
        grade = 'A-'
        badge = 'Excellent'
    elif total_score >= 80:
        grade = 'B+'
        badge = 'Very Good'
    elif total_score >= 75:
        grade = 'B'
        badge = 'Very Good'
    elif total_score >= 70:
        grade = 'B-'
        badge = 'Good'
    elif total_score >= 65:
        grade = 'C+'
        badge = 'Good'
    elif total_score >= 60:
        grade = 'C'
        badge = 'Fair'
    elif total_score >= 55:
        grade = 'C-'
        badge = 'Fair'
    elif total_score >= 50:
        grade = 'D'
        badge = 'Below Average'
    else:
        grade = 'F'
        badge = 'Poor'

    return {
        'total_score': int(total_score),
        'grade': grade,
        'badge': badge,
        'components': components,
        'methodology': (
            'Score based on: Peak NDVI (40%), Season Length (30%), '
            'Stability (20%), Timing (10%)'
        )
    }


def compute_quality_for_province(
    phenology_by_year: Dict[int, Dict],
    current_year: int = 2024
) -> Dict:
    """
    Compute quality score for a province using multi-year phenology.

    Args:
        phenology_by_year: Dict of {year: phenology_metrics}
        current_year: Year to score

    Returns:
        Quality score dict
    """

    if current_year not in phenology_by_year:
        return {
            'total_score': 0,
            'grade': 'N/A',
            'badge': 'No Data',
            'components': {},
            'error': f'No phenology data for {current_year}'
        }

    current_phenology = phenology_by_year[current_year]

    # Get historical phenology (past 3-5 years)
    historical_years = [y for y in phenology_by_year.keys() if y < current_year]
    historical_years.sort()
    recent_historical = historical_years[-5:]  # Last 5 years

    historical_phenology = [phenology_by_year[y] for y in recent_historical]

    # Compute score
    quality = compute_quality_score(current_phenology, historical_phenology)

    # Add metadata
    quality['year'] = current_year
    quality['historical_years'] = recent_historical

    return quality


def main():
    """Example usage."""
    import json

    print("OliveIntel - Quality Score Computation")
    print("=" * 60)

    # Example phenology data
    phenology_2024 = {
        'greenup_date': '2024-04-10',
        'peak_date': '2024-06-20',
        'peak_value': 0.68,
        'senescence_date': '2024-10-15',
        'season_length_days': 188,
        'integral_auc': 95.2
    }

    historical = [
        {'peak_value': 0.65, 'season_length_days': 175},
        {'peak_value': 0.67, 'season_length_days': 180},
        {'peak_value': 0.66, 'season_length_days': 182},
        {'peak_value': 0.69, 'season_length_days': 185},
    ]

    quality = compute_quality_score(phenology_2024, historical)

    print("\nQuality Score Results:")
    print("=" * 60)
    print(json.dumps(quality, indent=2))

    print(f"\n🎯 Final Score: {quality['total_score']}/100 ({quality['grade']})")
    print(f"   Badge: {quality['badge']}")


if __name__ == '__main__':
    main()
