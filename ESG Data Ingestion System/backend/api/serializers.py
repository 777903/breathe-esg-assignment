"""
API Serializers

Keep serializers focused:
  - Read serializers: return everything the frontend needs
  - Write serializers: validate incoming data, minimal fields
"""

from rest_framework import serializers
from apps.core.models import (
    Organization, DataSource, RawData,
    EmissionRecord, ValidationError, AuditLog,
)


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'slug']


class DataSourceSerializer(serializers.ModelSerializer):
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)

    class Meta:
        model = DataSource
        fields = ['id', 'name', 'source_type', 'source_type_display', 'description']


class ValidationErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValidationError
        fields = ['id', 'field_name', 'rule_code', 'message', 'severity']


class EmissionRecordListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the table view — avoids N+1 on validation errors."""
    source_name = serializers.CharField(source='data_source.name', read_only=True)
    source_type = serializers.CharField(source='data_source.source_type', read_only=True)
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    error_count = serializers.SerializerMethodField()
    warning_count = serializers.SerializerMethodField()

    class Meta:
        model = EmissionRecord
        fields = [
            'id', 'scope', 'scope_display', 'category',
            'quantity_value', 'quantity_unit',
            'original_value', 'original_unit',
            'co2e_kg', 'activity_date', 'period_end',
            'status', 'status_display',
            'source_name', 'source_type',
            'error_count', 'warning_count',
            'created_at',
        ]

    def get_error_count(self, obj) -> int:
        # Prefetched in the view
        return sum(1 for e in obj.validation_errors.all() if e.severity == 'error')

    def get_warning_count(self, obj) -> int:
        return sum(1 for e in obj.validation_errors.all() if e.severity == 'warning')


class EmissionRecordDetailSerializer(EmissionRecordListSerializer):
    """Full detail including validation errors and raw data payload."""
    validation_errors = ValidationErrorSerializer(many=True, read_only=True)
    raw_payload = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    class Meta(EmissionRecordListSerializer.Meta):
        fields = EmissionRecordListSerializer.Meta.fields + [
            'validation_errors', 'raw_payload',
            'approved_by_name', 'approved_at', 'updated_at',
        ]

    def get_raw_payload(self, obj) -> dict:
        try:
            return obj.raw_data.payload
        except Exception:
            return {}

    def get_approved_by_name(self, obj) -> str | None:
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.username
        return None


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ['id', 'action', 'changes', 'actor_name', 'timestamp']

    def get_actor_name(self, obj) -> str:
        if obj.actor:
            return obj.actor.get_full_name() or obj.actor.username
        return 'System'


class UploadSerializer(serializers.Serializer):
    """Validates file upload request."""
    file = serializers.FileField()
    data_source_id = serializers.UUIDField()
