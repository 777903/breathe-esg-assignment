from django.urls import path
from . import views

urlpatterns = [
    # Upload
    path('upload/', views.upload_file, name='upload'),

    # Records
    path('records/', views.list_records, name='records-list'),
    path('records/issues/', views.list_issues, name='records-issues'),
    path('records/<uuid:record_id>/', views.record_detail, name='record-detail'),
    path('records/<uuid:record_id>/approve/', views.approve_record, name='record-approve'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Audit
    path('audit/<uuid:record_id>/', views.audit_log, name='audit-log'),

    # Data sources (for upload form)
    path('datasources/', views.list_data_sources, name='datasources'),

    # Dev helper
    path('seed/', views.seed_demo, name='seed-demo'),
]
