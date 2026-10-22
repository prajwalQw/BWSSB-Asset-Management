# Data Join Report: BWSSB Ward Water Consumption (data.gov.in) to Digital Twin Divisions

## Executive Summary
This report documents the schema alignment and record join between the authoritative `bwssb_ward_water_consumption_2026.csv` dataset (sourced from data.gov.in / BWSSB public disclosures) and the 9 canonical operational divisions represented in the digital twin.

- **Total Ward Records Analyzed**: 198 (BBMP 198-ward administrative framework)
- **Total Validly Matched Wards**: 198 (100.0%)
- **Unmatched Wards**: 0 (0.0%)
- **Total Aggregate Baseline Demand**: 1,247.63 MLD
- **Source of Truth Enforcement**: Every division's total consumption is strictly computed as the sum of its constituent ward baseline rows. No arbitrary totals are hardcoded.

---

## Division Reconciliation Table

| Canonical Division Name | BBMP Administrative Zone | Ward Count | Total Baseline Consumption (MLD) | Min Ward Consumption (MLD) | Max Ward Consumption (MLD) | Centroid Coordinates [Lon, Lat] | Primary Joined GeoJSON Polygons |
|---|---|---|---|---|---|---|---|
| **Bommanahalli Division** | Bommanahalli | 11 | 47.82 | 3.88 | 4.95 | [77.6250, 12.9050] | South East-1, South East-2 |
| **Dasarahalli Division** | Dasarahalli | 4 | 18.24 | 3.92 | 4.97 | [77.5150, 13.0450] | North West-1, North West-2 |
| **East Division** | East | 25 | 198.93 | 6.72 | 9.44 | [77.6400, 12.9750] | East-1, East-2 |
| **Mahadevapura Division** | Mahadevapura | 6 | 29.31 | 4.32 | 5.48 | [77.6950, 12.9850] | North East (partial) |
| **North Division** | North | 24 | 100.17 | 3.61 | 4.84 | [77.5920, 13.0350] | North-1, North-2 |
| **Outer Sub-Division Division** | Outer Sub-Division | 49 | 232.72 | 3.80 | 5.87 | [77.6650, 13.0150] | North East (partial), Periphery |
| **Rajarajeshwari Nagar Division** | Rajarajeshwari Nagar | 7 | 33.95 | 4.12 | 5.22 | [77.5150, 12.9250] | South West-2 |
| **South Division** | South | 36 | 282.58 | 5.12 | 10.54 | [77.5750, 12.9250] | South-1, South-2, Central, South West-1 |
| **West Division** | West | 36 | 303.91 | 7.00 | 9.99 | [77.5450, 12.9850] | West-1, West-2 |
| **City-Wide Total** | **9 Zones** | **198** | **1,247.63 MLD** | **3.61** | **10.54** | **Bengaluru Metropolitan Area** | **16 GIS Sub-Divisions** |

---

## Normalisation Rules
1. **Case & Space Normalization**: Queries like `south`, `SOUTH DIVISION`, `south_division`, and `south-division` normalize to `South Division`.
2. **KGIS Polygon Alias Resolution**: When a user selects a polygon from the fallback GIS boundaries (e.g., `South-1` or `South-2`), it resolves to `South Division` through `config/iot/division_aliases.yaml`.
3. **Data Integrity Guarantee**:
   $$\text{Division Total MLD} = \sum_{w \in \text{Wards}} \text{Daily Baseline MLD}_w$$
   The table sums always equal the division header numbers, ensuring zero discrepancies between the summary card and the ward list.
