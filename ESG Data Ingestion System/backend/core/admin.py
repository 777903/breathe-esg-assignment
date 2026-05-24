from django.contrib import admin
from .models import Organization, DataSource, RawData, EmissionRecord, ValidationError, AuditLog


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'source_type', 'organization', 'created_at']
    list_filter = ['source_type', 'organization']


@admin.register(RawData)
class RawDataAdmin(admin.ModelAdmin):
    list_display = ['id', 'data_source', 'row_number', 'file_name', 'ingested_at']
    list_filter = ['data_source__source_type']
    readonly_fields = ['id', 'ingested_at', 'payload']


@admin.register(EmissionRecord)
class EmissionRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'scope', 'category', 'status', 'quantity_value', 'quantity_unit', 'activity_date']
    list_filter = ['scope', 'status', 'data_source__source_type']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ValidationError)
class ValidationErrorAdmin(admin.ModelAdmin):
    list_display = ['rule_code', 'severity', 'field_name', 'emission_record', 'created_at']
    list_filter = ['severity', 'rule_code']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'emission_record', 'actor', 'timestamp']
    list_filter = ['action']
    readonly_fields = ['id', 'timestamp']
