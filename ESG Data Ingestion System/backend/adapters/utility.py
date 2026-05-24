"""
Utility Adapter — parses electricity billing data from utility providers.

Real-world utility CSV exports have unique quirks:
  - Billing periods don't align to calendar months (e.g., "12 Jan – 14 Feb")
  - kWh totals may appear in multiple columns (peak / off-peak / total)
  - Some files use kWh, others use MWh; some mix both
  - Account numbers, meter IDs, and site codes are often not standardised
  - Demand charges and consumption charges are sometimes combined
  - Missing reads are filled with estimates (marked 'E' or 'EST')

This adapter:
  1. Detects billing period start/end dates from messy range strings
  2. Resolves kWh vs MWh and normalises to kWh
  3. Flags estimated reads for the ValidationService
"""

import csv
import io
import re
from datetime import datetime
from .base import BaseAdapter


# Regex to extract date ranges like "01 Jan 2024 - 31 Jan 2024" or "2024-01-01 to 2024-01-31"
DATE_RANGE_PATTERNS = [
    # "01 Jan 2024 - 31 Jan 2024"
    r'(\d{1,2}\s+\w{3}\s+\d{4})\s*[-–to]+\s*(\d{1,2}\s+\w{3}\s+\d{4})',
    # "2024-01-01 to 2024-01-31" or "2024-01-01 - 2024-01-31"
    r'(\d{4}-\d{2}-\d{2})\s*[-–/to]+\s*(\d{4}-\d{2}-\d{2})',
    # "01/01/2024 - 31/01/2024"
    r'(\d{1,2}/\d{1,2}/\d{4})\s*[-–/to]+\s*(\d{1,2}/\d{1,2}/\d{4})',
]

DATE_FORMATS = [
    '%d %b %Y', '%d %B %Y', '%Y-%m-%d',
    '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y',
]


def _parse_date(s: str) -> str | None:
    s = s.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def _extract_billing_period(raw_period: str) -> tuple[str | None, str | None]:
    """
    Attempt to extract (period_start, period_end) from a billing period string.
    Returns (None, None) if unparseable.
    """
    if not raw_period:
        return None, None

    for pattern in DATE_RANGE_PATTERNS:
        m = re.search(pattern, raw_period, re.IGNORECASE)
        if m:
            start = _parse_date(m.group(1))
            end = _parse_date(m.group(2))
            return start, end

    # Try single date (period start only)
    single = _parse_date(raw_period)
    if single:
        return single, None

    return None, None


def _resolve_kwh(row: dict, lower_cols: dict[str, str]) -> tuple[float | None, str]:
    """
    Find the energy consumption value from various possible column names.
    Returns (value_in_kWh, source_unit).
    """
    # Priority: total > consumption > usage > peak+off_peak
    kwh_cols = [
        'total_kwh', 'total_consumption_kwh', 'kwh_total', 'consumption_kwh',
        'energy_kwh', 'units_kwh', 'kwh', 'electricity_kwh', 'net_kwh',
    ]
    mwh_cols = [
        'total_mwh', 'consumption_mwh', 'energy_mwh', 'mwh',
    ]

    for col_key in kwh_cols:
        original_col = lower_cols.get(col_key)
        if original_col and row.get(original_col, '').strip():
            val = BaseAdapter.safe_float(row[original_col])
            if val is not None:
                return val, 'kWh'

    for col_key in mwh_cols:
        original_col = lower_cols.get(col_key)
        if original_col and row.get(original_col, '').strip():
            val = BaseAdapter.safe_float(row[original_col])
            if val is not None:
                return val * 1000, 'MWh'  # convert to kWh

    # Last resort: sum peak + off-peak
    peak_col = lower_cols.get('peak_kwh') or lower_cols.get('peak')
    offpeak_col = lower_cols.get('offpeak_kwh') or lower_cols.get('off_peak_kwh')
    if peak_col and offpeak_col:
        peak = BaseAdapter.safe_float(row.get(peak_col, ''))
        offpeak = BaseAdapter.safe_float(row.get(offpeak_col, ''))
        if peak is not None and offpeak is not None:
            return peak + offpeak, 'kWh'

    return None, 'unknown'


COLUMN_ALIASES = {
    'billing_period': [
        'billing_period', 'period', 'bill_period', 'service_period',
        'billing_dates', 'invoice_period', 'read_period',
    ],
    'account_number': [
        'account_number', 'account_no', 'acc_no', 'account', 'meter_account',
        'customer_account',
    ],
    'site': [
        'site', 'site_name', 'location', 'premises', 'service_address',
        'building', 'facility',
    ],
    'meter_id': [
        'meter_id', 'meter_number', 'meter_no', 'mpan', 'nmi', 'meter',
    ],
    'is_estimated': [
        'estimated', 'is_estimated', 'read_type', 'estimate_flag', 'est',
    ],
    'tariff': [
        'tariff', 'tariff_code', 'rate_code', 'price_plan', 'contract_type',
    ],
}


class UtilityAdapter(BaseAdapter):
    """
    Parses electricity billing exports from utility providers.

    Handles:
      - Billing periods that span non-calendar months
      - kWh / MWh disambiguation
      - Estimated read flagging
    """

    source_type = 'utility'

    def parse(self, file_obj, file_name: str = 'utility_bill.csv') -> list[dict]:
        if isinstance(file_obj, (bytes, bytearray)):
            text = file_obj.decode('utf-8-sig', errors='replace')
        else:
            raw_bytes = file_obj.read()
            text = raw_bytes.decode('utf-8-sig', errors='replace')

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return []

        # Build lower-cased column lookup
        lower_cols = {
            f.lower().replace(' ', '_').replace('-', '_'): f
            for f in reader.fieldnames
        }
        alias_map = self._resolve_columns(lower_cols)

        results = []
        for row_num, raw_row in enumerate(reader, start=2):
            if not any(v.strip() for v in raw_row.values() if v):
                continue

            mapped = self._map_row(raw_row, alias_map, lower_cols)
            mapped['_raw'] = dict(raw_row)
            mapped['_meta'] = {'row_number': row_num, 'file_name': file_name}
            results.append(mapped)

        return results

    def _resolve_columns(self, lower_cols: dict) -> dict:
        """Map our alias keys → original CSV column names."""
        result = {}
        for internal_key, aliases in COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in lower_cols:
                    result[internal_key] = lower_cols[alias]
                    break
        return result

    def _map_row(self, raw_row: dict, alias_map: dict, lower_cols: dict) -> dict:
        def get(key):
            col = alias_map.get(key)
            return raw_row.get(col, '').strip() if col else ''

        period_start, period_end = _extract_billing_period(get('billing_period'))

        kwh_value, original_unit = _resolve_kwh(raw_row, lower_cols)

        # Detect estimated reads
        est_raw = get('is_estimated').lower()
        is_estimated = est_raw in ('e', 'est', 'estimated', 'yes', 'y', '1', 'true')

        return {
            'activity_date': period_start,
            'period_end': period_end,
            'site': self.safe_str(get('site')),
            'meter_id': self.safe_str(get('meter_id')),
            'account_number': self.safe_str(get('account_number')),
            'quantity': kwh_value,
            'unit': 'kWh',
            'original_unit': original_unit,
            'is_estimated': is_estimated,
            'tariff': self.safe_str(get('tariff')),
        }
