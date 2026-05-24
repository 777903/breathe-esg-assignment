"""
IngestionService
================

Orchestrates the full pipeline for a single file upload:

  1. SELECT adapter based on DataSource.source_type
  2. Parse raw rows (adapter.parse)
  3. Save each row to RawData
  4. Normalize (NormalizationService.normalize)
  5. Validate (ValidationService.validate)
  6. Create EmissionRecord + ValidationError objects
  7. Write AuditLog entries

This is the only place that touches the database in the ingestion flow.
Adapters, NormalizationService, and ValidationService are all stateless.

Usage:
    service = IngestionService()
    result = service.ingest(data_source=ds, file_obj=file, file_name='sap_jan.csv')
    # result: {'created': 42, 'errors': 3, 'suspicious': 5, 'valid': 34}
"""

import logging
from typing import IO

from apps.core.models import DataSource, RawData, EmissionRecord, ValidationError as VE, AuditLog
from adapters.sap import SAPAdapter
from adapters.utility import UtilityAdapter
from adapters.travel import TravelAdapter
from services.normalization import NormalizationService
from services.validation import ValidationService

logger = logging.getLogger(__name__)

ADAPTER_REGISTRY = {
    'sap': SAPAdapter,
    'utility': UtilityAdapter,
    'travel': TravelAdapter,
}


class IngestionService:
    """
    Orchestrates the end-to-end ingestion pipeline.

    Keeps business logic OUT of views — views only call ingest() and handle
    the HTTP response based on the returned summary dict.
    """

    def __init__(self):
        self.normalizer = NormalizationService()
        self.validator = ValidationService()

    def ingest(
        self,
        data_source: DataSource,
        file_obj: IO[bytes],
        file_name: str,
        actor=None,
    ) -> dict:
        """
        Full ingestion pipeline for one uploaded file.

        Args:
            data_source: Configured DataSource ORM instance
            file_obj:    Uploaded file-like object
            file_name:   Original filename (for RawData audit trail)
            actor:       Django User who triggered the upload (may be None for API keys)

        Returns:
            Summary dict: {created, valid, error, suspicious, skipped}
        """
        source_type = data_source.source_type
        adapter_class = ADAPTER_REGISTRY.get(source_type)

        if adapter_class is None:
            raise ValueError(f"No adapter registered for source_type={source_type!r}")

        adapter = adapter_class()
        parsed_rows = adapter.parse(file_obj, file_name=file_name)

        summary = {'created': 0, 'valid': 0, 'error': 0, 'suspicious': 0, 'skipped': 0}

        for parsed_row in parsed_rows:
            try:
                self._process_row(parsed_row, data_source, actor, summary)
            except Exception as exc:
                logger.exception(
                    "Unexpected error processing row %s from %s: %s",
                    parsed_row.get('_meta', {}).get('row_number'),
                    file_name,
                    exc,
                )
                summary['skipped'] += 1

        logger.info(
            "Ingestion complete for %s: %s", file_name, summary
        )
        return summary

    def _process_row(self, parsed_row: dict, data_source: DataSource, actor, summary: dict):
        """Process a single parsed row through the full pipeline."""
        meta = parsed_row.get('_meta', {})
        raw_payload = parsed_row.get('_raw', parsed_row)

        # ── Step 1: Persist raw data ──────────────────────────────────────
        raw_record = RawData.objects.create(
            data_source=data_source,
            payload=raw_payload,
            row_number=meta.get('row_number', 0),
            file_name=meta.get('file_name', 'unknown'),
        )

        # ── Step 2: Normalize ─────────────────────────────────────────────
        try:
            normalized_fields = self.normalizer.normalize(
                source_type=data_source.source_type,
                parsed_row=parsed_row,
            )
        except Exception as exc:
            logger.warning("Normalization failed for row %s: %s", raw_record.id, exc)
            normalized_fields = {
                'scope': 'scope1',
                'category': 'unknown',
                'quantity_value': None,
                'quantity_unit': 'unknown',
                'original_value': None,
                'original_unit': 'unknown',
                'co2e_kg': None,
                'activity_date': None,
                'period_end': None,
            }

        # ── Step 3: Validate ──────────────────────────────────────────────
        status, violations = self.validator.validate(
            fields=normalized_fields,
            source_type=data_source.source_type,
        )

        # ── Step 4: Create EmissionRecord ─────────────────────────────────
        emission_record = EmissionRecord.objects.create(
            raw_data=raw_record,
            organization=data_source.organization,
            data_source=data_source,
            status=status,
            **normalized_fields,
        )

        # ── Step 5: Attach validation errors ──────────────────────────────
        for v in violations:
            VE.objects.create(emission_record=emission_record, **v)

        # ── Step 6: Write audit log ───────────────────────────────────────
        AuditLog.objects.create(
            emission_record=emission_record,
            actor=actor,
            action='ingested',
            changes={
                'status': {'from': None, 'to': status},
                'source_file': meta.get('file_name', 'unknown'),
                'row_number': meta.get('row_number', 0),
            },
        )

        summary['created'] += 1
        summary[status] = summary.get(status, 0) + 1

    def approve_record(self, record: EmissionRecord, actor) -> EmissionRecord:
        """
        Transition a record from valid/suspicious → approved.

        Raises ValueError if the record is in 'error' status (must be fixed first).
        """
        if record.status == EmissionRecord.Status.ERROR:
            raise ValueError(
                "Cannot approve a record with status 'error'. "
                "Resolve all error-level validation issues first."
            )

        from django.utils import timezone
        old_status = record.status
        record.status = EmissionRecord.Status.APPROVED
        record.approved_by = actor
        record.approved_at = timezone.now()
        record.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

        AuditLog.objects.create(
            emission_record=record,
            actor=actor,
            action='approved',
            changes={
                'status': {'from': old_status, 'to': EmissionRecord.Status.APPROVED},
            },
        )

        return record
