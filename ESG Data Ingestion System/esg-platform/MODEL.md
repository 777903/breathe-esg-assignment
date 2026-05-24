# MODEL.md — Database Schema & Design Decisions

## Overview

The ESG platform uses 6 core models organized in a layered data architecture. The central design principle is **immutability of raw data**: once a row is ingested it is never overwritten — only supplemented with normalized views and state transitions.

---

## Entity Relationship Diagram

```
Organization
    │
    ├──< DataSource (source_type: sap | utility | travel)
    │        │
    │        └──< RawData (verbatim JSON payload per row)
    │                 │
    │                 └── EmissionRecord (normalized, one-to-one with RawData)
    │                          │
    │                          ├──< ValidationError (0..N per record)
    │                          └──< AuditLog (0..N per record)
```

---

## Models

### Organization

Multi-tenancy root. Every row in every other table is scoped to an Organization.

| Field      | Type      | Notes                             |
|------------|-----------|-----------------------------------|
| id         | UUIDv4    | Primary key                       |
| name       | CharField | Display name                      |
| slug       | SlugField | URL-safe, unique identifier       |
| created_at | DateTime  | Auto set on creation              |

**Multi-tenancy approach**: In this prototype, tenancy is enforced at the query level (each view filters by `organization`). In production, this would be a custom `OrgScopedManager` that automatically injects the tenant from the JWT claim, making isolation impossible to forget.

---

### DataSource

Represents a configured upstream data provider. The `source_type` field determines which Adapter is used.

| Field       | Type      | Notes                              |
|-------------|-----------|------------------------------------|
| id          | UUIDv4    | Primary key                        |
| organization| FK        | Tenant scoping                     |
| name        | CharField | Human-readable name                |
| source_type | Choice    | `sap` \| `utility` \| `travel`    |
| description | TextField | Optional notes                     |

---

### RawData

**The most important design decision**: store the original input verbatim before any transformation.

| Field       | Type       | Notes                               |
|-------------|------------|-------------------------------------|
| id          | UUIDv4     | Primary key                         |
| data_source | FK         | Which source this came from         |
| payload     | JSONField  | Verbatim row dict from CSV parser   |
| row_number  | PositiveInt| Row index in original file          |
| file_name   | CharField  | Original uploaded filename          |
| ingested_at | DateTime   | Auto timestamp                      |

**Why store raw?**
1. Re-process records if normalization rules change without re-uploading
2. Forensic audit: auditors can see exactly what was submitted
3. Debugging: compare raw vs. normalized to trace transformation errors

---

### EmissionRecord

The analyst-facing, normalized emission event.

| Field          | Type      | Notes                                  |
|----------------|-----------|----------------------------------------|
| id             | UUIDv4    | Primary key                            |
| raw_data       | OneToOne  | Link to verbatim source                |
| organization   | FK        | Tenant                                 |
| data_source    | FK        | Source system                          |
| scope          | Choice    | `scope1` \| `scope2` \| `scope3`      |
| category       | CharField | e.g. `diesel_combustion`, `air_travel` |
| quantity_value | Float     | In canonical unit                      |
| quantity_unit  | CharField | Canonical unit (kWh, km, liters)       |
| original_value | Float     | As it appeared in source               |
| original_unit  | CharField | As it appeared in source               |
| co2e_kg        | Float?    | kg CO₂ equivalent (nullable)           |
| activity_date  | Date      | When the activity occurred             |
| period_end     | Date?     | End of billing period (utility only)   |
| status         | Choice    | `pending → valid/error/suspicious → approved` |
| approved_by    | FK User   | Null until approved                    |
| approved_at    | DateTime? | Null until approved                    |

**Scope classification follows GHG Protocol:**
- Scope 1: Direct emissions from fuel combustion (SAP fuel data)
- Scope 2: Indirect from purchased electricity (Utility billing)
- Scope 3: All other indirect — travel, supply chain (Travel + SAP procurement)

**Unit normalization**: All quantities are stored in a canonical unit per category. The original value and unit are preserved for display and audit purposes. Example: a reading of "1,234 Gal" becomes `quantity_value=4673.1, quantity_unit=liters, original_value=1234, original_unit=gallons`.

---

### ValidationError

One or more rule violations attached to a single EmissionRecord.

| Field           | Type     | Notes                                   |
|-----------------|----------|-----------------------------------------|
| id              | UUIDv4   | Primary key                             |
| emission_record | FK       | Which record this applies to            |
| field_name      | CharField| Which field triggered the rule          |
| rule_code       | CharField| Machine-readable code (e.g. `NEGATIVE_VALUE`) |
| message         | TextField| Human-readable analyst message          |
| severity        | Choice   | `error` (blocks approval) \| `warning`  |

**Severity → Status mapping:**
- Any `error` → record status = `error`
- Only `warning`s → record status = `suspicious`
- No violations → record status = `valid`

Errors are stored separately from EmissionRecord so they can be cleared and recalculated without mutating the record itself.

---

### AuditLog

Insert-only immutable audit trail.

| Field           | Type     | Notes                                       |
|-----------------|----------|---------------------------------------------|
| id              | UUIDv4   | Primary key                                 |
| emission_record | FK       | Which record changed                        |
| actor           | FK User? | Who triggered it (null = system)            |
| action          | CharField| e.g. `ingested`, `normalized`, `approved`   |
| changes         | JSONField| `{field: {from: old, to: new}}`             |
| source_ip       | IP?      | Client IP for human-initiated events        |
| timestamp       | DateTime | Auto set, never mutable                     |

**Rule**: Only INSERT operations are ever performed on AuditLog. No UPDATE, no DELETE. This makes it tamper-evident.

---

## Normalization Pipeline

```
Upload (file) 
    → Adapter.parse()     [source-schema dict]
    → RawData.save()      [persists verbatim]
    → NormalizationService.normalize()  [canonical fields]
    → ValidationService.validate()      [status + errors]
    → EmissionRecord.save()
    → ValidationError.bulk_create()
    → AuditLog.create(action='ingested')
```
