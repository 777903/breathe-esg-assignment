# TRADEOFFS.md — What Was Not Built and Why

## 1. Celery / Async Processing

**What it would do**: Move file ingestion into a background task queue (Celery + Redis), so the HTTP request returns immediately with a job ID, and the client polls for completion.

**Why it was not built**:
- For prototype demonstration, synchronous processing is simpler to run and explain. Files of 10,000 rows process in under 2 seconds.
- Celery requires an additional infrastructure component (Redis or RabbitMQ) and a worker process, which complicates local setup.
- The architecture already supports this: `IngestionService.ingest()` is a plain Python method. Wrapping it in a Celery task is a single decorator addition.

**What you'd add**:
```python
# tasks.py
@celery_app.task
def ingest_file_task(data_source_id, file_path, actor_id):
    data_source = DataSource.objects.get(id=data_source_id)
    with open(file_path, 'rb') as f:
        IngestionService().ingest(data_source, f, actor_id)
```

---

## 2. Dynamic Emission Factor Database

**What it would do**: Store emission factors in a database table with year, geography, and category dimensions, allowing factors to be updated without code deployment.

**Why it was not built**:
- Designing a correct emission factor schema requires domain expertise. Different standards (DEFRA, EPA, GHG Protocol, ISO 14064) use different factor boundaries and category definitions.
- The built-in DEFRA 2023 values are accurate enough to demonstrate the system behavior.
- The code structure already supports this: `NormalizationService` is the only place factors are used, so swapping hardcoded dicts for a DB lookup is a localized change.

**What you'd add**:
```
EmissionFactor model:
  - category (CharField)
  - scope (CharField)
  - factor_value (Float)
  - factor_unit (CharField)
  - reporting_year (IntegerField)
  - region (CharField)  # 'UK', 'US', 'Global'
  - source (CharField)  # 'DEFRA', 'EPA', 'IEA'
  - effective_from (Date)
  - effective_to (Date, nullable)
```

---

## 3. Full Authentication & Multi-Tenancy Isolation

**What it would do**: JWT authentication with per-request tenant resolution; all database queries automatically filtered by `organization_id` from the token; role-based access (admin vs. analyst vs. viewer).

**Why it was not built**:
- Auth is a cross-cutting concern that would add ~300 lines of middleware, serializer, and test code without illuminating the ESG-specific architecture.
- The models are designed for multi-tenancy (every model has an `organization` FK) — the enforcement layer just isn't wired up.
- Adding `django-tenant-schemas` or a custom manager is a localized change.

**What you'd add**:
```python
class OrgScopedManager(models.Manager):
    def get_queryset(self):
        org_id = get_current_org()  # from thread-local or middleware
        return super().get_queryset().filter(organization_id=org_id)

class EmissionRecord(models.Model):
    objects = OrgScopedManager()
    ...
```
Then wire `get_current_org()` to read from the JWT sub claim.

---

## Summary

| Feature                   | Effort to Add | Architectural Blocker? |
|---------------------------|---------------|------------------------|
| Async ingestion (Celery)  | Low           | No — isolated in tasks.py |
| Emission factor DB table  | Medium        | No — localized to NormalizationService |
| Full auth + tenant isolation | Medium     | No — models already multi-tenant |
