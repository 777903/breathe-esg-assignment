"""
NormalizationService
====================

Transforms adapter output (source-schema dicts) into structured EmissionRecord
field sets, applying:
  - Unit conversion to canonical units
  - Scope classification (GHG Protocol Scope 1 / 2 / 3)
  - CO2e estimation using built-in emission factors

Design principles:
  - Pure functions where possible (easy to unit test)
  - No database access in this layer — caller (IngestionService) handles persistence
  - Returns a dict suitable for passing to EmissionRecord(**data)

Emission factors used (kg CO2e per unit):
  - These are simplified DEFRA/EPA representative values.
  - In production, load from a configurable EmissionFactor database table.
"""

from datetime import date
from typing import Any


# ---------------------------------------------------------------------------
# Emission factor tables (kgCO2e per unit)
# Source: DEFRA 2023 GHG Conversion Factors (simplified subset)
# ---------------------------------------------------------------------------

FUEL_FACTORS: dict[str, dict] = {
    # category → {factor_kg_co2e_per_liter, scope}
    'diesel': {'factor': 2.6808, 'unit': 'liters', 'scope': 'scope1'},
    'petrol': {'factor': 2.3122, 'unit': 'liters', 'scope': 'scope1'},
    'gasoline': {'factor': 2.3122, 'unit': 'liters', 'scope': 'scope1'},
    'natural_gas': {'factor': 2.0402, 'unit': 'kg', 'scope': 'scope1'},
    'lpg': {'factor': 1.5551, 'unit': 'liters', 'scope': 'scope1'},
    'fuel_consumption': {'factor': 2.6808, 'unit': 'liters', 'scope': 'scope1'},  # default to diesel
    'fuel_oil': {'factor': 2.9597, 'unit': 'liters', 'scope': 'scope1'},
}

# Grid electricity emission factor (UK average 2023): 0.23314 kgCO2e/kWh
ELECTRICITY_FACTOR_KG_PER_KWH = 0.23314

FLIGHT_FACTORS: dict[str, float] = {
    # flight class → kgCO2e per passenger-km (includes radiative forcing)
    'economy': 0.1557,
    'premium_economy': 0.2369,
    'business': 0.4293,
    'first': 0.5765,
}

TRANSPORT_FACTORS: dict[str, float] = {
    # mode → kgCO2e per passenger-km
    'road': 0.1714,    # average car
    'rail': 0.0410,    # UK average rail
    'hotel': 31.0,     # kgCO2e per room-night (UK average hotel)
}

# Unit conversion table → canonical unit per source unit
UNIT_CONVERSIONS: dict[str, dict] = {
    # Volume → liters
    'liters': {'factor': 1.0, 'canonical': 'liters'},
    'litres': {'factor': 1.0, 'canonical': 'liters'},
    'l': {'factor': 1.0, 'canonical': 'liters'},
    'gallons': {'factor': 3.78541, 'canonical': 'liters'},
    'gal': {'factor': 3.78541, 'canonical': 'liters'},
    'm3': {'factor': 1000.0, 'canonical': 'liters'},
    'cbm': {'factor': 1000.0, 'canonical': 'liters'},
    # Energy → kWh
    'kwh': {'factor': 1.0, 'canonical': 'kWh'},
    'mwh': {'factor': 1000.0, 'canonical': 'kWh'},
    'gwh': {'factor': 1_000_000.0, 'canonical': 'kWh'},
    # Mass → kg
    'kg': {'factor': 1.0, 'canonical': 'kg'},
    'tonnes': {'factor': 1000.0, 'canonical': 'kg'},
    'ton': {'factor': 1000.0, 'canonical': 'kg'},
    'lbs': {'factor': 0.453592, 'canonical': 'kg'},
    # Distance → km
    'km': {'factor': 1.0, 'canonical': 'km'},
    'miles': {'factor': 1.60934, 'canonical': 'km'},
    # Already canonical
    'unknown': {'factor': 1.0, 'canonical': 'unknown'},
    'computed_from_iata': {'factor': 1.0, 'canonical': 'km'},
}


class NormalizationService:
    """
    Converts a parsed adapter row into EmissionRecord field values.

    Usage:
        service = NormalizationService()
        fields = service.normalize(source_type='sap', parsed_row=row_dict)
        # fields is a dict suitable for EmissionRecord(**fields)
    """

    def normalize(self, source_type: str, parsed_row: dict) -> dict[str, Any]:
        """
        Main entry point.

        Args:
            source_type: 'sap' | 'utility' | 'travel'
            parsed_row:  Dict from an adapter's parse() method

        Returns:
            Dict of EmissionRecord field values (no _raw/_meta keys)
        """
        handler = {
            'sap': self._normalize_sap,
            'utility': self._normalize_utility,
            'travel': self._normalize_travel,
        }.get(source_type)

        if handler is None:
            raise ValueError(f"Unknown source_type: {source_type!r}")

        return handler(parsed_row)

    # ------------------------------------------------------------------ #
    # Source-specific normalizers                                          #
    # ------------------------------------------------------------------ #

    def _normalize_sap(self, row: dict) -> dict:
        """Normalize SAP fuel / procurement row."""
        raw_value = row.get('quantity')
        raw_unit = (row.get('unit') or 'liters').lower()

        canonical_value, canonical_unit = self._convert_unit(raw_value, raw_unit)

        activity_type = (row.get('activity_type') or 'fuel_consumption').lower()
        fuel_key = self._match_fuel_category(activity_type)
        fuel_info = FUEL_FACTORS.get(fuel_key, FUEL_FACTORS['fuel_consumption'])

        scope = fuel_info['scope']
        co2e = self._compute_fuel_co2e(canonical_value, canonical_unit, fuel_key)

        return {
            'scope': scope,
            'category': fuel_key,
            'quantity_value': canonical_value,
            'quantity_unit': canonical_unit,
            'original_value': raw_value,
            'original_unit': raw_unit,
            'co2e_kg': co2e,
            'activity_date': _parse_date_field(row.get('activity_date')),
            'period_end': None,
        }

    def _normalize_utility(self, row: dict) -> dict:
        """Normalize electricity billing row."""
        kwh = row.get('quantity')  # already in kWh after adapter
        co2e = (kwh * ELECTRICITY_FACTOR_KG_PER_KWH) if kwh is not None else None

        return {
            'scope': 'scope2',
            'category': 'grid_electricity',
            'quantity_value': kwh,
            'quantity_unit': 'kWh',
            'original_value': row.get('quantity'),
            'original_unit': row.get('original_unit', 'kWh'),
            'co2e_kg': co2e,
            'activity_date': _parse_date_field(row.get('activity_date')),
            'period_end': _parse_date_field(row.get('period_end')),
        }

    def _normalize_travel(self, row: dict) -> dict:
        """Normalize corporate travel row."""
        mode = row.get('transport_mode', 'unknown')
        distance_km = row.get('distance_km')
        passengers = row.get('passengers', 1) or 1

        scope = 'scope3'
        co2e = None
        category = f"{mode}_travel"

        if mode == 'air':
            flight_class = row.get('flight_class', 'economy')
            factor = FLIGHT_FACTORS.get(flight_class, FLIGHT_FACTORS['economy'])
            if distance_km is not None:
                co2e = distance_km * factor * passengers
        elif mode in ('road', 'rail'):
            factor = TRANSPORT_FACTORS.get(mode, 0.1714)
            if distance_km is not None:
                co2e = distance_km * factor * passengers
        elif mode == 'hotel':
            nights = row.get('nights', 1) or 1
            co2e = nights * TRANSPORT_FACTORS['hotel']
            category = 'hotel_stay'

        return {
            'scope': scope,
            'category': category,
            'quantity_value': distance_km or row.get('nights') or 0,
            'quantity_unit': 'nights' if mode == 'hotel' else 'km',
            'original_value': row.get('quantity'),
            'original_unit': row.get('original_unit', 'km'),
            'co2e_kg': co2e,
            'activity_date': _parse_date_field(row.get('activity_date')),
            'period_end': None,
        }

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _convert_unit(self, value: float | None, unit: str) -> tuple[float | None, str]:
        """Convert value from source unit to canonical unit."""
        if value is None:
            return None, unit
        conv = UNIT_CONVERSIONS.get(unit.lower())
        if conv:
            return value * conv['factor'], conv['canonical']
        return value, unit  # unknown unit — pass through

    def _match_fuel_category(self, activity_type: str) -> str:
        """Fuzzy-match an activity_type string to a known fuel category."""
        at = activity_type.lower()
        for key in FUEL_FACTORS:
            if key in at:
                return key
        # Keyword heuristics
        if 'diesel' in at:
            return 'diesel'
        if 'petrol' in at or 'gasoline' in at or 'gas' in at:
            return 'petrol'
        if 'lpg' in at or 'propane' in at:
            return 'lpg'
        if 'natural' in at:
            return 'natural_gas'
        if 'oil' in at:
            return 'fuel_oil'
        return 'fuel_consumption'

    def _compute_fuel_co2e(self, value: float | None, unit: str, fuel_key: str) -> float | None:
        if value is None:
            return None
        fuel = FUEL_FACTORS.get(fuel_key, FUEL_FACTORS['fuel_consumption'])
        canonical_unit = fuel['unit']

        # Convert to factor's expected unit if needed
        if unit == 'liters' and canonical_unit == 'liters':
            return value * fuel['factor']
        elif unit == 'kg' and canonical_unit == 'kg':
            return value * fuel['factor']
        elif unit == 'liters' and canonical_unit == 'kg':
            # rough density: 0.75 kg/L for liquid fuel average
            return value * 0.75 * fuel['factor']
        else:
            return value * fuel['factor']


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _parse_date_field(value) -> date | None:
    """Convert a string date (YYYY-MM-DD) to Python date, or return None."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    from datetime import datetime as dt
    try:
        return dt.strptime(str(value), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None
