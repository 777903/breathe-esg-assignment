"""
Travel Adapter — parses corporate travel data (flights, hotels, ground transport).

Real-world travel data from corporate booking tools (Concur, SAP Travel, Egencia)
has these challenges:
  - Distances are often not provided — only origin/destination airport codes
  - The same route can appear as SYD-SIN or SIN-SYD without indication of direction
  - Hotel nights may use country codes, city names, or airport codes for location
  - Ground transport may list km, miles, or just say "taxi" with no distance
  - Flight class (economy vs business) significantly affects emission factors
  - Multi-leg trips are sometimes one row, sometimes multiple rows

This adapter:
  1. Resolves IATA airport codes → approximate great-circle distances
  2. Normalises transport_mode to a controlled vocabulary
  3. Extracts flight class
  4. Handles hotel night counting
"""

import csv
import io
from datetime import datetime
from .base import BaseAdapter


# Approximate great-circle distances (km) for common corporate routes.
# In production this would call a geo distance API or maintain a full IATA DB.
# This lookup covers a representative subset to make the demo realistic.
AIRPORT_DISTANCES_KM: dict[frozenset, float] = {
    frozenset({'LHR', 'JFK'}): 5540,
    frozenset({'LHR', 'LAX'}): 8757,
    frozenset({'LHR', 'DXB'}): 5490,
    frozenset({'LHR', 'SIN'}): 10841,
    frozenset({'LHR', 'HKG'}): 9648,
    frozenset({'LHR', 'SYD'}): 16993,
    frozenset({'LHR', 'CDG'}): 341,
    frozenset({'LHR', 'FRA'}): 631,
    frozenset({'LHR', 'AMS'}): 371,
    frozenset({'JFK', 'LAX'}): 3983,
    frozenset({'JFK', 'ORD'}): 1196,
    frozenset({'JFK', 'SFO'}): 4139,
    frozenset({'JFK', 'DXB'}): 11006,
    frozenset({'JFK', 'SIN'}): 15348,
    frozenset({'JFK', 'HKG'}): 13026,
    frozenset({'LAX', 'SFO'}): 543,
    frozenset({'LAX', 'SIN'}): 14100,
    frozenset({'LAX', 'SYD'}): 12059,
    frozenset({'DXB', 'BOM'}): 1931,
    frozenset({'DXB', 'DEL'}): 2192,
    frozenset({'DXB', 'SIN'}): 5842,
    frozenset({'SIN', 'SYD'}): 6310,
    frozenset({'SIN', 'HKG'}): 2568,
    frozenset({'SIN', 'BOM'}): 4182,
    frozenset({'CDG', 'FRA'}): 479,
    frozenset({'CDG', 'AMS'}): 431,
    frozenset({'BOM', 'DEL'}): 1147,
    frozenset({'BOM', 'BLR'}): 980,
    frozenset({'DEL', 'BLR'}): 1754,
}

TRANSPORT_MODE_MAP = {
    # Flight
    'flight': 'air', 'air': 'air', 'plane': 'air', 'airplane': 'air',
    'aircraft': 'air', 'fly': 'air', 'domestic flight': 'air',
    'international flight': 'air', 'long-haul': 'air', 'short-haul': 'air',
    # Rail
    'rail': 'rail', 'train': 'rail', 'railway': 'rail', 'metro': 'rail',
    'tram': 'rail', 'eurostar': 'rail',
    # Road
    'car': 'road', 'taxi': 'road', 'rideshare': 'road', 'uber': 'road',
    'lyft': 'road', 'rental car': 'road', 'hire car': 'road',
    'bus': 'road', 'coach': 'road', 'shuttle': 'road',
    # Hotel
    'hotel': 'hotel', 'accommodation': 'hotel', 'lodging': 'hotel',
    'motel': 'hotel', 'hostel': 'hotel', 'bnb': 'hotel',
}

FLIGHT_CLASS_MAP = {
    'y': 'economy', 'eco': 'economy', 'economy': 'economy',
    'economy class': 'economy', 'coach': 'economy',
    'w': 'premium_economy', 'premium': 'premium_economy',
    'premium economy': 'premium_economy', 'premium_economy': 'premium_economy',
    'c': 'business', 'business': 'business', 'business class': 'business',
    'first': 'first', 'f': 'first', 'first class': 'first',
}

COLUMN_ALIASES = {
    'travel_date': [
        'travel_date', 'departure_date', 'date', 'booking_date',
        'trip_date', 'check_in_date', 'start_date',
    ],
    'transport_mode': [
        'transport_mode', 'mode', 'travel_mode', 'type', 'trip_type',
        'travel_type', 'category', 'service_type',
    ],
    'origin': [
        'origin', 'from', 'departure', 'from_airport', 'origin_airport',
        'departure_airport', 'from_city',
    ],
    'destination': [
        'destination', 'to', 'arrival', 'to_airport', 'destination_airport',
        'arrival_airport', 'to_city',
    ],
    'distance_km': [
        'distance_km', 'distance', 'km', 'miles', 'dist_km',
        'route_km', 'journey_km',
    ],
    'flight_class': [
        'class', 'flight_class', 'cabin_class', 'cabin', 'fare_class',
        'booking_class', 'travel_class',
    ],
    'passengers': [
        'passengers', 'pax', 'travellers', 'travelers', 'num_passengers',
        'headcount',
    ],
    'nights': [
        'nights', 'hotel_nights', 'room_nights', 'stay_duration',
        'duration_nights',
    ],
    'employee_id': [
        'employee_id', 'emp_id', 'staff_id', 'traveler_id', 'user_id',
    ],
    'cost_center': [
        'cost_center', 'costcenter', 'dept', 'department', 'cc',
    ],
}


def _parse_travel_date(raw: str) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d %b %Y', '%d-%m-%Y', '%Y%m%d'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def _lookup_distance(origin: str, destination: str) -> float | None:
    """Look up great-circle distance between airport pair."""
    if not origin or not destination:
        return None
    key = frozenset({origin.strip().upper(), destination.strip().upper()})
    return AIRPORT_DISTANCES_KM.get(key)


def _miles_to_km(miles: float) -> float:
    return miles * 1.60934


class TravelAdapter(BaseAdapter):
    """
    Parses corporate travel booking data.

    Resolves airport codes to distances and normalises transport modes.
    """

    source_type = 'travel'

    def parse(self, file_obj, file_name: str = 'travel_data.csv') -> list[dict]:
        if isinstance(file_obj, (bytes, bytearray)):
            text = file_obj.decode('utf-8-sig', errors='replace')
        else:
            raw_bytes = file_obj.read()
            text = raw_bytes.decode('utf-8-sig', errors='replace')

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return []

        lower_cols = {
            f.lower().replace(' ', '_').replace('-', '_'): f
            for f in reader.fieldnames
        }
        alias_map = self._resolve_columns(lower_cols)

        results = []
        for row_num, raw_row in enumerate(reader, start=2):
            if not any(v.strip() for v in raw_row.values() if v):
                continue

            mapped = self._map_row(raw_row, alias_map)
            mapped['_raw'] = dict(raw_row)
            mapped['_meta'] = {'row_number': row_num, 'file_name': file_name}
            results.append(mapped)

        return results

    def _resolve_columns(self, lower_cols: dict) -> dict:
        result = {}
        for internal_key, aliases in COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in lower_cols:
                    result[internal_key] = lower_cols[alias]
                    break
        return result

    def _map_row(self, raw_row: dict, alias_map: dict) -> dict:
        def get(key):
            col = alias_map.get(key)
            return raw_row.get(col, '').strip() if col else ''

        mode_raw = get('transport_mode').lower()
        mode = TRANSPORT_MODE_MAP.get(mode_raw, mode_raw or 'unknown')

        origin = self.safe_str(get('origin')).upper()
        destination = self.safe_str(get('destination')).upper()

        # Resolve distance
        distance_raw = self.safe_float(get('distance_km'))
        distance_km = None
        original_unit = 'km'

        if distance_raw is not None:
            # Check if it might be miles (heuristic: column named 'miles')
            col_name = alias_map.get('distance_km', '')
            if 'mile' in col_name.lower():
                distance_km = _miles_to_km(distance_raw)
                original_unit = 'miles'
            else:
                distance_km = distance_raw
        elif mode == 'air' and origin and destination:
            # Try airport code lookup
            distance_km = _lookup_distance(origin, destination)
            original_unit = 'computed_from_iata'

        # Flight class
        class_raw = get('flight_class').lower()
        flight_class = FLIGHT_CLASS_MAP.get(class_raw, 'economy' if mode == 'air' else None)

        passengers = self.safe_float(get('passengers')) or 1
        nights = self.safe_float(get('nights'))

        return {
            'activity_date': _parse_travel_date(get('travel_date')),
            'transport_mode': mode,
            'origin': origin,
            'destination': destination,
            'distance_km': distance_km,
            'original_unit': original_unit,
            'flight_class': flight_class,
            'passengers': int(passengers),
            'nights': int(nights) if nights else None,
            'employee_id': self.safe_str(get('employee_id')),
            'cost_center': self.safe_str(get('cost_center')),
            # quantity and unit resolved by NormalizationService
            'quantity': distance_km,
            'unit': 'km',
        }
