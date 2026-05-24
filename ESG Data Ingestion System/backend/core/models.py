"""
Core models for the ESG Data Ingestion Platform.

Design notes:
  - Organization enables multi-tenancy: every piece of data is scoped to an org.
  - RawData stores the *original* input verbatim so we can always re-process.
  - EmissionRecord is the normalized, analyst-facing view of an emission event.
  - ValidationError captures rule violations without mutating the record.
  - AuditLog provides an immutable trail of every state transition.
"""

import uuid
from django.db import models
from django.contrib.auth.models import User


# ---------------------------------------------------------------------------
# Multi-tenancy root
# ---------------------------------------------------------------------------

class Organization(models.Model):
    """
    Top-level tenant. Every record, source, and log entry belongs to one org.
    In a real deployment you would enforce org isolation at the ORM query level
    (e.g. a custom Manager that automatically filters by the request's tenant).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, help_text="URL-safe identifier, e.g. 'acme-corp'")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


# ---------------------------------------------------------------------------
# Data source registry
# ---------------------------------------------------------------------------

class DataSource(models.Model):
    """
    Represents a configured upstream data provider.

    SOURCE_TYPE maps to the adapter that knows how to parse it:
      - sap      → SAPAdapter
      - utility  → UtilityAdapter
      - travel   → TravelAdapter
    """

    class SourceType(models.TextChoices):
        SAP = 'sap', 'SAP (Fuel & Procurement)'
        UTILITY = 'utility', 'Utility (Electricity)'
        TRAVEL = 'travel', 'Corporate Travel'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='data_sources'
    )
    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_source_type_display()})"

    class Meta:
        ordering = ['name']


# ---------------------------------------------------------------------------
# Raw ingestion record
# ---------------------------------------------------------------------------

class RawData(models.Model):
    """
    Stores the *original* row exactly as received, before any transformation.

    Why store raw data?
      - Allows re-processing with updated normalization rules.
      - Provides forensic traceability for auditors.
      - Decouples ingestion from transformation (they can happen at different times).

    `payload` is an untyped JSON blob — deliberately so, because different
    source types have wildly different schemas.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    data_source = models.ForeignKey(
        DataSource, on_delete=models.PROTECT, related_name='raw_records'
    )
    payload = models.JSONField(
        help_text="Original row data as parsed from the source file, before normalization."
    )
    row_number = models.PositiveIntegerField(
        help_text="1-based row index within the uploaded file, for traceability."
    )
    file_name = models.CharField(max_length=512, help_text="Original uploaded filename.")
    ingested_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Raw#{self.row_number} from {self.data_source.name}"

    class Meta:
        ordering = ['ingested_at', 'row_number']
        verbose_name = 'Raw Data Record'


# ---------------------------------------------------------------------------
# Normalized emission record
# ---------------------------------------------------------------------------

class EmissionRecord(models.Model):
    """
    The analyst-facing, normalized emission event.

    Scope classification follows GHG Protocol:
      - Scope 1: Direct combustion (SAP fuel)
      - Scope 2: Purchased electricity (Utility)
      - Scope 3: Indirect — travel, supply chain (Travel, SAP procurement)

    Status lifecycle:
      pending → valid|error|suspicious → approved

    quantity_value is always stored in the *canonical* unit (kgCO2e for emissions,
    kWh for electricity, km for distance). The original unit is preserved in
    `original_unit` for display.
    """

    class Scope(models.TextChoices):
        SCOPE_1 = 'scope1', 'Scope 1 — Direct'
        SCOPE_2 = 'scope2', 'Scope 2 — Electricity'
        SCOPE_3 = 'scope3', 'Scope 3 — Indirect'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending Review'
        VALID = 'valid', 'Valid'
        ERROR = 'error', 'Error'
        SUSPICIOUS = 'suspicious', 'Suspicious'
        APPROVED = 'approved', 'Approved'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_data = models.OneToOneField(
        RawData, on_delete=models.PROTECT, related_name='emission_record'
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='emission_records'
    )
    data_source = models.ForeignKey(
        DataSource, on_delete=models.PROTECT, related_name='emission_records'
    )

    # Classification
    scope = models.CharField(max_length=10, choices=Scope.choices)
    category = models.CharField(
        max_length=100,
        help_text="Activity category, e.g. 'diesel_combustion', 'grid_electricity', 'air_travel'."
    )

    # Emission quantity
    quantity_value = models.FloatField(help_text="Normalized quantity in canonical unit.")
    quantity_unit = models.CharField(
        max_length=50,
        help_text="Canonical unit, e.g. 'kgCO2e', 'kWh', 'km'."
    )
    original_value = models.FloatField(help_text="Value as it appeared in the source file.")
    original_unit = models.CharField(max_length=50, help_text="Unit as it appeared in source.")

    # CO2 equivalent (computed by NormalizationService)
    co2e_kg = models.FloatField(
        null=True, blank=True,
        help_text="Estimated kg CO2 equivalent. Null if emission factor not available."
    )

    # Time period
    activity_date = models.DateField(help_text="Date the activity occurred or billing period start.")
    period_end = models.DateField(
        null=True, blank=True,
        help_text="End of billing period (relevant for utility data)."
    )

    # Status workflow
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='approved_records'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_scope_display()} | {self.category} | {self.quantity_value} {self.quantity_unit}"

    class Meta:
        ordering = ['-activity_date']
        verbose_name = 'Emission Record'


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class ValidationError(models.Model):
    """
    One or more validation rule violations attached to a single EmissionRecord.

    Deliberately separate from EmissionRecord so the record itself is not
    polluted with error detail — errors can be cleared without touching the record.

    severity:
      - warning → marks record as 'suspicious'
      - error   → marks record as 'error', blocks approval
    """

    class Severity(models.TextChoices):
        WARNING = 'warning', 'Warning'
        ERROR = 'error', 'Error'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    emission_record = models.ForeignKey(
        EmissionRecord, on_delete=models.CASCADE, related_name='validation_errors'
    )
    field_name = models.CharField(
        max_length=100,
        help_text="Which field triggered this error, e.g. 'quantity_value'."
    )
    rule_code = models.CharField(
        max_length=100,
        help_text="Machine-readable rule identifier, e.g. 'NEGATIVE_VALUE'."
    )
    message = models.TextField(help_text="Human-readable description for the analyst.")
    severity = models.CharField(max_length=10, choices=Severity.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.severity}] {self.rule_code} on {self.emission_record_id}"

    class Meta:
        ordering = ['severity', 'rule_code']


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class AuditLog(models.Model):
    """
    Immutable log of every state change on an EmissionRecord.

    Insert-only — never UPDATE or DELETE rows in this table.
    Each entry captures who changed what and when.

    `changes` stores a dict like:
      {"status": {"from": "pending", "to": "approved"}}
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    emission_record = models.ForeignKey(
        EmissionRecord, on_delete=models.CASCADE, related_name='audit_logs'
    )
    actor = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        help_text="User who triggered the change; null for system-initiated events."
    )
    action = models.CharField(
        max_length=100,
        help_text="Action taken, e.g. 'ingested', 'normalized', 'validated', 'approved'."
    )
    changes = models.JSONField(
        default=dict,
        help_text="Dict of field-level changes: {field: {from: old, to: new}}."
    )
    source_ip = models.GenericIPAddressField(
        null=True, blank=True,
        help_text="IP address of requester for human-initiated events."
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.action}] record={self.emission_record_id} at {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log Entry'
