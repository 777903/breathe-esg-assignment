"""
API Views — thin layer between HTTP and service layer.

Each view:
  1. Validates input (serializer)
  2. Delegates to a service
  3. Returns a response

No business logic lives here.
"""

import logging
from django.db.models import Count, Q, Sum
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.models import DataSource, EmissionRecord, AuditLog, Organization
from api.serializers import (
    EmissionRecordListSerializer,
    EmissionRecordDetailSerializer,
    AuditLogSerializer,
    DataSourceSerializer,
    UploadSerializer,
)
from services.ingestion import IngestionService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_org(request) -> Organization:
    """
    In production this would extract the tenant from JWT / session.
    For this prototype we use a fixed org (created in setup).
    """
    return Organization.objects.first()


def _get_or_create_demo_org() -> Organization:
    org, _ = Organization.objects.get_or_create(
        slug='demo-corp',
        defaults={'name': 'Demo Corporation'},
    )
    return org


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------

@api_view(['POST'])
def upload_file(request):
    """
    POST /api/upload/

    Accepts multipart form data:
      - file:           CSV file
      - data_source_id: UUID of the target DataSource

    Returns ingestion summary.
    """
    serializer = UploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data_source_id = serializer.validated_data['data_source_id']
    uploaded_file = serializer.validated_data['file']

    try:
        data_source = DataSource.objects.select_related('organization').get(id=data_source_id)
    except DataSource.DoesNotExist:
        return Response(
            {'error': f'DataSource {data_source_id} not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    service = IngestionService()
    try:
        summary = service.ingest(
            data_source=data_source,
            file_obj=uploaded_file,
            file_name=uploaded_file.name,
            actor=request.user if request.user.is_authenticated else None,
        )
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.exception("Ingestion failed: %s", exc)
        return Response(
            {'error': 'Ingestion failed. Check server logs.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(summary, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Records listing
# ---------------------------------------------------------------------------

@api_view(['GET'])
def list_records(request):
    """
    GET /api/records/

    Query params:
      source     - filter by source_type (sap|utility|travel)
      status     - filter by status (valid|error|suspicious|approved|pending)
      scope      - filter by scope (scope1|scope2|scope3)
      page       - page number (default 1)
      page_size  - records per page (default 50, max 200)
    """
    qs = (
        EmissionRecord.objects
        .select_related('data_source', 'organization')
        .prefetch_related('validation_errors')
        .order_by('-activity_date', '-created_at')
    )

    # Filters
    source = request.query_params.get('source')
    if source:
        qs = qs.filter(data_source__source_type=source)

    record_status = request.query_params.get('status')
    if record_status:
        qs = qs.filter(status=record_status)

    scope = request.query_params.get('scope')
    if scope:
        qs = qs.filter(scope=scope)

    # Simple pagination
    page = max(1, int(request.query_params.get('page', 1)))
    page_size = min(200, max(1, int(request.query_params.get('page_size', 50))))
    start = (page - 1) * page_size
    end = start + page_size

    total = qs.count()
    records = qs[start:end]

    serializer = EmissionRecordListSerializer(records, many=True)
    return Response({
        'count': total,
        'page': page,
        'page_size': page_size,
        'results': serializer.data,
    })


@api_view(['GET'])
def list_issues(request):
    """
    GET /api/records/issues/

    Returns all records with status 'error' or 'suspicious', with their
    validation errors included.
    """
    qs = (
        EmissionRecord.objects
        .filter(status__in=['error', 'suspicious'])
        .select_related('data_source')
        .prefetch_related('validation_errors')
        .order_by('-created_at')
    )

    serializer = EmissionRecordDetailSerializer(qs, many=True)
    return Response({'count': qs.count(), 'results': serializer.data})


@api_view(['GET'])
def record_detail(request, record_id):
    """GET /api/records/<id>/"""
    try:
        record = (
            EmissionRecord.objects
            .select_related('data_source', 'approved_by', 'raw_data')
            .prefetch_related('validation_errors')
            .get(id=record_id)
        )
    except EmissionRecord.DoesNotExist:
        return Response({'error': 'Record not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = EmissionRecordDetailSerializer(record)
    return Response(serializer.data)


# ---------------------------------------------------------------------------
# Approve record
# ---------------------------------------------------------------------------

@api_view(['POST'])
def approve_record(request, record_id):
    """
    POST /api/records/<id>/approve/

    Transitions record to 'approved' status.
    Returns the updated record.
    """
    try:
        record = EmissionRecord.objects.select_related('data_source').get(id=record_id)
    except EmissionRecord.DoesNotExist:
        return Response({'error': 'Record not found.'}, status=status.HTTP_404_NOT_FOUND)

    service = IngestionService()
    try:
        updated = service.approve_record(
            record=record,
            actor=request.user if request.user.is_authenticated else None,
        )
    except ValueError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    serializer = EmissionRecordDetailSerializer(updated)
    return Response(serializer.data)


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

@api_view(['GET'])
def dashboard(request):
    """
    GET /api/dashboard/

    Returns aggregate statistics for the review dashboard:
      - Status breakdown
      - Source breakdown
      - Scope breakdown
      - Total CO2e by scope
      - Recent issues
    """
    base_qs = EmissionRecord.objects.all()

    # Status counts
    status_counts = {
        row['status']: row['count']
        for row in base_qs.values('status').annotate(count=Count('id'))
    }

    # Source counts
    source_counts = {
        row['data_source__source_type']: row['count']
        for row in base_qs.values('data_source__source_type').annotate(count=Count('id'))
    }

    # Scope CO2e totals
    scope_co2e = {
        row['scope']: round(row['total_co2e'] or 0, 2)
        for row in base_qs.values('scope').annotate(total_co2e=Sum('co2e_kg'))
    }

    # Total records
    total_records = base_qs.count()
    total_co2e = base_qs.aggregate(total=Sum('co2e_kg'))['total'] or 0

    # Recent issues (last 10 error/suspicious)
    recent_issues = (
        EmissionRecord.objects
        .filter(status__in=['error', 'suspicious'])
        .select_related('data_source')
        .prefetch_related('validation_errors')
        .order_by('-created_at')[:10]
    )
    recent_issues_data = EmissionRecordListSerializer(recent_issues, many=True).data

    # Data sources available
    data_sources = DataSource.objects.all()
    sources_data = DataSourceSerializer(data_sources, many=True).data

    return Response({
        'total_records': total_records,
        'total_co2e_kg': round(total_co2e, 2),
        'status_counts': status_counts,
        'source_counts': source_counts,
        'scope_co2e': scope_co2e,
        'recent_issues': recent_issues_data,
        'data_sources': sources_data,
    })


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@api_view(['GET'])
def audit_log(request, record_id):
    """GET /api/audit/<record_id>/"""
    try:
        EmissionRecord.objects.get(id=record_id)
    except EmissionRecord.DoesNotExist:
        return Response({'error': 'Record not found.'}, status=status.HTTP_404_NOT_FOUND)

    logs = AuditLog.objects.filter(emission_record_id=record_id).select_related('actor')
    serializer = AuditLogSerializer(logs, many=True)
    return Response({'record_id': str(record_id), 'audit_trail': serializer.data})


# ---------------------------------------------------------------------------
# Data sources listing (for upload form dropdown)
# ---------------------------------------------------------------------------

@api_view(['GET'])
def list_data_sources(request):
    """GET /api/datasources/"""
    sources = DataSource.objects.select_related('organization').all()
    serializer = DataSourceSerializer(sources, many=True)
    return Response(serializer.data)


# ---------------------------------------------------------------------------
# Seed demo data (development helper)
# ---------------------------------------------------------------------------

@api_view(['POST'])
def seed_demo(request):
    """
    POST /api/seed/
    Creates a demo Organization + DataSources if they don't exist.
    """
    org = _get_or_create_demo_org()

    sources_config = [
        {'name': 'SAP Fuel & Procurement', 'source_type': 'sap', 'description': 'SAP ECC fuel consumption and procurement data'},
        {'name': 'Main Office Utility', 'source_type': 'utility', 'description': 'Electricity billing from national grid'},
        {'name': 'Corporate Travel System', 'source_type': 'travel', 'description': 'Business travel from booking platform'},
    ]

    created = []
    for cfg in sources_config:
        ds, is_new = DataSource.objects.get_or_create(
            organization=org,
            source_type=cfg['source_type'],
            defaults={'name': cfg['name'], 'description': cfg['description']},
        )
        created.append({'id': str(ds.id), 'name': ds.name, 'created': is_new})

    return Response({'organization': org.name, 'data_sources': created})
