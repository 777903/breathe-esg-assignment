"""
SAP Adapter — parses fuel and procurement data exported from SAP.

Real-world SAP exports are notoriously messy:
  - Column headers are often internal SAP field codes (MATNR, MENGE, MEINS...)
  - Numbers use European comma notation: "1.234,56" (thousands dot, decimal comma)
  - Units are inconsistent: sometimes 'L', sometimes 'LTR', 'Ltr', 'Liters'
  - Date fields can be YYYYMMDD (SAP standard), DD.MM.YYYY, or plain ISO
  - Rows may be subtotals/headers interspersed (we skip them)

This adapter normalises all of the above so NormalizationService only has to
deal with well-typed, consistently-named fields.

Expected (realistic) SAP CSV structure
(column names vary — that's the whole point of the adapter):
  Posting_Date | Material_Doc | Plant_Code | Material_Desc
  | Quantity | UOM | Cost_Center | Activity_Type | CO2_Factor_Optional
"""

import csv
import io
from datetime import datetime
from .base import BaseAdapter


# Map the chaos of real SAP column names → our internal field names.
# Order matters: first match wins.
COLUMN_ALIASES = {
    'activity_date': [
        'posting_date', 'postingdate', 'pstng_date', 'budat',
        'date', 'doc_date', 'document_date', 'bldat',
    ],
    'description': [
        'material_desc', 'materialdesc', 'maktx', 'short_text',
        'description', 'item_text', 'txt50',
    ],
    'quantity': [
        'quantity', 'qty', 'menge', 'erfmg', 'volume',
        'consumption', 'amount_qty',
    ],
    'unit': [
        'uom', 'unit_of_measure', 'meins', 'erfme', 'base_unit',
        'unit', 'units',
    ],
    'cost_center': [
        'cost_center', 'costcenter', 'kostl', 'cc', 'cost_ctr',
    ],
    'plant': [
        'plant', 'plant_code', 'werks', 'facility',
    ],
    'activity_type': [
        'activity_type', 'acttype', 'lstar', 'fuel_type',
        'material_group', 'matgrp',
    ],
}

# SAP exports European-format numbers in some locales
def _parse_sap_number(raw: str) -> float | None:
    """Handle both '1,234.56' and '1.234,56' European formats."""
    if not raw:
        return None
    s = str(raw).strip()
    if s.lower() in ('n/a', '-', '', 'none'):
        return None
    # Detect European format: if last separator is comma
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            # European: 1.234,56 → 1234.56
            s = s.replace('.', '').replace(',', '.')
        else:
            # US: 1,234.56 → 1234.56
            s = s.replace(',', '')
    elif ',' in s and '.' not in s:
        # Could be decimal: 1234,56 → 1234.56 or thousands: 1,234 → 1234
        # Heuristic: if after comma there are exactly 2–3 digits, treat as decimal
        after_comma = s.split(',')[-1]
        if len(after_comma) in (1, 2):
            s = s.replace(',', '.')
        else:
            s = s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        return None


def _parse_sap_date(raw: str) -> str | None:
    """Parse SAP date formats → ISO 8601 string (YYYY-MM-DD)."""
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ('%Y%m%d', '%d.%m.%Y', '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None  # unparseable — ValidationService will flag it


def _normalize_sap_unit(raw: str) -> str:
    """Map the zoo of SAP unit codes to a standard label."""
    if not raw:
        return 'unknown'
    mapping = {
        'l': 'liters', 'ltr': 'liters', 'liter': 'liters', 'liters': 'liters',
        'lt': 'liters', 'litre': 'liters', 'litres': 'liters',
        'gal': 'gallons', 'gallon': 'gallons', 'gal(us)': 'gallons',
        'm3': 'm3', 'cbm': 'm3', 'cum': 'm3',
        'kg': 'kg', 'kgs': 'kg', 'kilogram': 'kg', 'kilograms': 'kg',
        'ton': 'tonnes', 'mt': 'tonnes', 'tonne': 'tonnes', 'tonnes': 'tonnes',
        'kwh': 'kWh', 'mwh': 'mWh',
    }
    return mapping.get(raw.strip().lower(), raw.strip().lower())


class SAPAdapter(BaseAdapter):
    """
    Parses SAP fuel and procurement CSV exports.

    The adapter's job is purely parsing + column resolution.
    It does NOT compute CO2 equivalents.
    """

    source_type = 'sap'

    def parse(self, file_obj, file_name: str = 'sap_export.csv') -> list[dict]:
        """
        Parse SAP CSV into a list of normalised row dicts.

        Returns list of dicts with keys:
          _raw, _meta, activity_date, description, quantity, unit,
          cost_center, plant, activity_type
        """
        # SAP exports sometimes use Windows-1252 encoding with BOM
        if isinstance(file_obj, (bytes, bytearray)):
            text = file_obj.decode('utf-8-sig', errors='replace')
        else:
            raw_bytes = file_obj.read()
            text = raw_bytes.decode('utf-8-sig', errors='replace')

        reader = csv.DictReader(io.StringIO(text))

        if not reader.fieldnames:
            return []

        # Build a mapping: lowercase fieldname → alias key
        col_map = self._resolve_columns(reader.fieldnames)

        results = []
        for row_num, raw_row in enumerate(reader, start=2):  # row 1 = header
            # Skip SAP subtotal / blank rows (they have no quantity)
            if not any(raw_row.values()):
                continue

            mapped = self._map_row(raw_row, col_map)
            mapped['_raw'] = dict(raw_row)
            mapped['_meta'] = {'row_number': row_num, 'file_name': file_name}
            results.append(mapped)

        return results

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _resolve_columns(self, fieldnames: list[str]) -> dict[str, str]:
        """
        Map each CSV column header → our internal alias.
        Returns: {csv_column_lower: internal_field}
        """
        col_map = {}
        lower_fields = {f.lower().replace(' ', '_').replace('-', '_'): f for f in fieldnames}

        for internal_key, aliases in COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in lower_fields:
                    col_map[lower_fields[alias]] = internal_key
                    break

        return col_map  # {original_csv_col: internal_field}

    def _map_row(self, raw_row: dict, col_map: dict) -> dict:
        """Apply column map and type-coerce fields."""
        mapped = {}

        # Reverse the col_map: internal_field → original_csv_col
        field_to_col = {v: k for k, v in col_map.items()}

        def get(field):
            col = field_to_col.get(field)
            return raw_row.get(col, '').strip() if col else ''

        mapped['activity_date'] = _parse_sap_date(get('activity_date'))
        mapped['description'] = self.safe_str(get('description'))
        mapped['quantity'] = _parse_sap_number(get('quantity'))
        mapped['unit'] = _normalize_sap_unit(get('unit'))
        mapped['cost_center'] = self.safe_str(get('cost_center'))
        mapped['plant'] = self.safe_str(get('plant'))
        mapped['activity_type'] = self.safe_str(get('activity_type')) or 'fuel_consumption'

        return mapped
