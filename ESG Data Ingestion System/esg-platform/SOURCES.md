# SOURCES.md — Real-World Data Formats Researched

## SAP ECC Export Format

### How SAP Actually Exports Data

SAP ECC (ERP Central Component) generates CSV/Excel exports from transaction MB52 (warehouse stocks), ME2M (purchase orders), and CO11N (activity confirmation). These exports have well-known characteristics:

1. **Field code headers**: SAP's internal field names (BUDAT = Posting Date, MENGE = Quantity, MEINS = Unit of Measure, KOSTL = Cost Center) often leak into export files, especially when users export directly from transaction screens rather than using a configured report.

2. **European decimal notation**: SAP in German, French, and other European locales uses period as thousands separator and comma as decimal: `1.234,56` instead of `1,234.56`. This is a very common source of import errors.

3. **Mixed date formats**: Depending on user locale settings, SAP can output `20240115` (ISO basic), `15.01.2024` (German), or `2024-01-15` (ISO extended).

4. **Unit of measure codes**: SAP uses its own internal UoM codes: `LTR` (liter), `M3` (cubic meter), `KG`, `T` (metric ton), `KWH`. These often appear inconsistently across different report extracts.

### Our SAP Sample Data (`sap_fuel_export.csv`)

The sample includes deliberately messy real-world scenarios:

| Row | Scenario | How we handle it |
|-----|----------|------------------|
| 3 | Quantity in M3 (cubic meters) | Unit converter: M3 → 1000× liters |
| 9 | European format: `1.234,56` | `_parse_sap_number()` detects European vs US format |
| 10 | Extreme value: 99,999 liters | ValidationService `EXTREME_VALUE` warning |
| 11 | Missing quantity (N/A) | `safe_float()` returns None → `MISSING_QUANTITY` error |
| 15 | Negative quantity | `NEGATIVE_VALUE` error (likely a credit note) |
| 16 | Gallons (US supplier) | Converted: 310 Gal × 3.785 = 1173 liters |

---

## Utility Billing Format

### Real-World Electricity Bills

UK electricity suppliers (British Gas, EDF, Octopus, OVO) provide structured billing data via BI exports or API:

1. **Non-calendar billing periods**: Utility meters are read on fixed cycles that rarely align to calendar months. A typical export has periods like "12 Jan 2024 – 14 Feb 2024" (33 days). This is extremely common and causes significant problems for month-based reporting.

2. **Estimated reads**: When a meter reader cannot access a property, or a smart meter fails to report, the utility generates an *estimated* read marked with 'E' or 'EST'. These should be flagged for analyst review because actuals may differ by 5–20%.

3. **Multi-rate tariffs**: Business customers often have peak/off-peak rates. The billing file may show separate kWh values for each rate band. Normalization must sum these.

4. **MWh for large consumers**: Large commercial customers (data centres, factories) receive bills in MWh. Mixed kWh/MWh in the same file is possible if an organization has sites of varying sizes.

### Our Utility Sample Data (`utility_electricity.csv`)

| Row | Scenario | How we handle it |
|-----|----------|------------------|
| 1-2 | Periods spanning months (Jan 12 – Feb 14) | Regex date range parser |
| 3,8 | Estimated reads (Y / E flag) | `is_estimated` flag → `ESTIMATED_READ` warning |
| 5-6 | MWh instead of kWh | Auto-detected by column name → ×1000 |
| 9 | Missing total kWh (peak + off-peak only) | `_resolve_kwh()` sums peak + off-peak |
| 10 | Extreme value: 1,500,000 kWh | `EXTREME_VALUE` warning |
| 11 | Slash-separated period: `2024-01-05/2024-02-04` | Regex with `/` as delimiter |

---

## Corporate Travel Format

### Real-World Travel Booking Data

Corporate booking platforms (Concur SAP, Egencia, TravelPerk, American Express GBT) export travel data in formats like:

1. **IATA codes instead of distances**: Travel bookings record origin/destination as 3-letter IATA airport codes (LHR, JFK, SIN). Distances are rarely included in booking exports — they must be derived from the route.

2. **Flight classes matter significantly**: Business class emits approximately 2.7× more CO₂e per km than economy due to larger seat footprint and radiative forcing multipliers. Travel data must capture cabin class to apply correct factors.

3. **Mixed transport modes**: A single travel export may contain flights, rail, hotel stays, and car hire on the same sheet. Each mode requires a different emission methodology.

4. **Hotel night-based emissions**: Hotels are not distance-based — they emit per room-night. UK average: ~31 kg CO₂e per room-night.

5. **Distance units**: Some booking tools report driving distances in miles (US-based tools), others in km.

### Our Travel Sample Data (`corporate_travel.csv`)

| Row | Scenario | How we handle it |
|-----|----------|------------------|
| 1 | LHR→JFK Business class | 5540 km × 0.4293 factor = 2378 kg CO₂e |
| 4,7,13 | Hotel stays | nights × 31 kg CO₂e/night |
| 10 | Unknown airports (XXX→YYY) | `UNKNOWN_AIRPORT_PAIR` warning |
| 12 | Distance in miles | Detected by column name → ×1.609 |
| 21 | LHR→SYD First class | 16,993 km × 0.5765 = 9796 kg CO₂e |

---

## Emission Factor Sources

The system uses simplified emission factors from:

- **DEFRA 2023 GHG Conversion Factors for Company Reporting** (UK Department for Environment, Food & Rural Affairs)
  - Diesel: 2.68 kg CO₂e/liter
  - Petrol: 2.31 kg CO₂e/liter
  - UK grid electricity: 0.233 kg CO₂e/kWh
  - Flights: 0.156–0.577 kg CO₂e/passenger-km (by class)
  - Hotel stays: 31 kg CO₂e/room-night

- **ICAO Carbon Emissions Calculator methodology** — used for flight distance validation and radiative forcing multipliers on aviation.

All factors are simplified representative values suitable for prototyping. Production systems require jurisdiction-specific and year-specific factors.
