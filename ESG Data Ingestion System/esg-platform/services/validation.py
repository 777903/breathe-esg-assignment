"""
ValidationService
=================

Applies a set of configurable rules to an EmissionRecord and returns a list
of ValidationError descriptors.

Design:
  - Rules are plain Python functions registered via @rule decorator
  - Each rule receives the normalized field dict and returns 0..N ValidationError dicts
  - ValidationService.validate() aggregates all results and computes final status
  - No database access — pure in/out

Rule severity:
  - 'error'   → record status becomes 'error'  (blocks approval)
  - 'warning' → record status becomes 'suspicious' (analyst must acknowledge)

If no rules trigger → status = 'valid'
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any
import datetime


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RuleViolation:
    field_name: str
    rule_code: str
    message: str
    severity: str  # 'error' | 'warning'


ValidationResult = list[RuleViolation]

# Registry: list of (rule_function, applies_to) tuples
_RULES: list[tuple[Callable, str | None]] = []


def rule(applies_to: str | None = None):
    """
    Decorator to register a validation rule.

    Args:
        applies_to: source_type filter ('sap', 'utility', 'travel') or None (all)
    """
    def decorator(fn: Callable) -> Callable:
        _RULES.append((fn, applies_to))
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------

@rule()
def check_missing_quantity(fields: dict, source_type: str) -> ValidationResult:
    """All records must have a non-null quantity."""
    if fields.get('quantity_value') is None:
        return [RuleViolation(
            field_name='quantity_value',
            rule_code='MISSING_QUANTITY',
            message='Quantity is missing or could not be parsed from source data.',
            severity='error',
        )]
    return []


@rule()
def check_negative_quantity(fields: dict, source_type: str) -> ValidationResult:
    """Quantities must be non-negative (credits/reversals should use a separate field)."""
    qty = fields.get('quantity_value')
    if qty is not None and qty < 0:
        return [RuleViolation(
            field_name='quantity_value',
            rule_code='NEGATIVE_VALUE',
            message=f'Quantity is negative ({qty}). Negative consumption is unusual; '
                    f'verify this is not a data entry error.',
            severity='error',
        )]
    return []


@rule()
def check_missing_date(fields: dict, source_type: str) -> ValidationResult:
    """Activity date must be present and parseable."""
    if not fields.get('activity_date'):
        return [RuleViolation(
            field_name='activity_date',
            rule_code='MISSING_DATE',
            message='Activity date is missing or unparseable.',
            severity='error',
        )]
    return []


@rule()
def check_future_date(fields: dict, source_type: str) -> ValidationResult:
    """Activity date should not be in the future (with 7-day grace for billing lag)."""
    d = fields.get('activity_date')
    if d is not None:
        today = datetime.date.today()
        if d > today + datetime.timedelta(days=7):
            return [RuleViolation(
                field_name='activity_date',
                rule_code='FUTURE_DATE',
                message=f'Activity date {d} is in the future. Verify billing period.',
                severity='warning',
            )]
    return []


@rule()
def check_very_old_date(fields: dict, source_type: str) -> ValidationResult:
    """Flag records older than 3 years — may indicate wrong year in date field."""
    d = fields.get('activity_date')
    if d is not None:
        cutoff = datetime.date.today().replace(year=datetime.date.today().year - 3)
        if d < cutoff:
            return [RuleViolation(
                field_name='activity_date',
                rule_code='VERY_OLD_DATE',
                message=f'Activity date {d} is more than 3 years ago. Confirm this is correct.',
                severity='warning',
            )]
    return []


@rule()
def check_suspiciously_large_quantity(fields: dict, source_type: str) -> ValidationResult:
    """Flag quantities that are extreme outliers (>10x typical range per source)."""
    qty = fields.get('quantity_value')
    unit = fields.get('quantity_unit', '')
    if qty is None:
        return []

    thresholds = {
        'liters': 500_000,    # 500 kL — possible for a large fleet, but worth flagging
        'kWh': 1_000_000,     # 1 GWh — very large building
        'km': 50_000,         # Circumference of Earth ~40k km
        'kg': 100_000,        # 100 tonnes
    }
    limit = thresholds.get(unit)
    if limit and qty > limit:
        return [RuleViolation(
            field_name='quantity_value',
            rule_code='EXTREME_VALUE',
            message=f'Quantity {qty} {unit} exceeds expected maximum of {limit}. '
                    f'This may be a unit error (e.g., MWh entered as kWh).',
            severity='warning',
        )]
    return []


@rule()
def check_missing_co2e(fields: dict, source_type: str) -> ValidationResult:
    """Warn if CO2e could not be computed (usually means unknown unit or category)."""
    if fields.get('co2e_kg') is None and fields.get('quantity_value') is not None:
        return [RuleViolation(
            field_name='co2e_kg',
            rule_code='MISSING_CO2E',
            message='CO2e could not be computed. Check that the activity category '
                    'and unit are recognised.',
            severity='warning',
        )]
    return []


@rule(applies_to='utility')
def check_estimated_read(fields: dict, source_type: str) -> ValidationResult:
    """Flag utility reads that are marked as estimated by the provider."""
    if fields.get('is_estimated'):
        return [RuleViolation(
            field_name='quantity_value',
            rule_code='ESTIMATED_READ',
            message='Electricity reading is marked as estimated by the utility provider. '
                    'Actual read may differ.',
            severity='warning',
        )]
    return []


@rule(applies_to='travel')
def check_unknown_airport(fields: dict, source_type: str) -> ValidationResult:
    """Flag travel records where distance could not be computed from airport codes."""
    mode = fields.get('transport_mode', '')
    dist = fields.get('quantity_value')
    if mode == 'air_travel' and (dist is None or dist == 0):
        origin = fields.get('origin', '')
        dest = fields.get('destination', '')
        return [RuleViolation(
            field_name='quantity_value',
            rule_code='UNKNOWN_AIRPORT_PAIR',
            message=f'Distance could not be determined for route {origin} → {dest}. '
                    f'Airport codes may be invalid or route not in reference data.',
            severity='warning',
        )]
    return []


@rule(applies_to='travel')
def check_extreme_flight_distance(fields: dict, source_type: str) -> ValidationResult:
    """Maximum realistic single flight is ~17,000 km (SIN→JFK direct)."""
    mode = fields.get('transport_mode', '')
    dist = fields.get('quantity_value')
    if mode == 'air_travel' and dist is not None and dist > 18_000:
        return [RuleViolation(
            field_name='quantity_value',
            rule_code='EXTREME_FLIGHT_DISTANCE',
            message=f'Flight distance {dist} km exceeds the longest commercial route. '
                    f'Check if this is a round-trip being entered as one row.',
            severity='warning',
        )]
    return []


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class ValidationService:
    """
    Runs all registered rules against a normalised record and returns the
    computed status and list of violations.
    """

    def validate(
        self,
        fields: dict,
        source_type: str,
    ) -> tuple[str, list[dict]]:
        """
        Validate normalized record fields.

        Args:
            fields:      Normalised EmissionRecord field dict from NormalizationService
            source_type: 'sap' | 'utility' | 'travel'

        Returns:
            (status, violations)
            status:     'valid' | 'error' | 'suspicious'
            violations: List of dicts matching ValidationError model fields
        """
        all_violations: list[RuleViolation] = []

        for rule_fn, applies_to in _RULES:
            if applies_to is None or applies_to == source_type:
                result = rule_fn(fields, source_type)
                all_violations.extend(result)

        has_error = any(v.severity == 'error' for v in all_violations)
        has_warning = any(v.severity == 'warning' for v in all_violations)

        if has_error:
            status = 'error'
        elif has_warning:
            status = 'suspicious'
        else:
            status = 'valid'

        violation_dicts = [
            {
                'field_name': v.field_name,
                'rule_code': v.rule_code,
                'message': v.message,
                'severity': v.severity,
            }
            for v in all_violations
        ]

        return status, violation_dicts
