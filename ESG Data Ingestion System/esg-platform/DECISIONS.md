# DECISIONS.md — Architecture Choices & Assumptions

## 1. Adapter Pattern for Source Ingestion

**Decision**: Each data source has its own Adapter class (`SAPAdapter`, `UtilityAdapter`, `TravelAdapter`) that implements a common `BaseAdapter.parse()` interface.

**Why**:
- SAP, utility, and travel data have completely different schemas, formats, and quirks. Trying to handle them in a single parser would create an unmaintainable mess of conditionals.
- Adding a new source (e.g., fleet telematics) requires only a new Adapter file with no changes to existing code (Open/Closed Principle).
- Adapters are pure functions (no DB access), making them extremely easy to unit test with a CSV string.

**Alternative considered**: A single generic CSV parser with column-mapping config files (YAML/JSON). Rejected because real-world SAP data requires imperative logic (European number parsing, SAP date formats) that cannot be expressed declaratively.

---

## 2. Service Layer for Business Logic

**Decision**: `IngestionService`, `NormalizationService`, `ValidationService` — all business logic lives here, not in views.

**Why**:
- Views that contain business logic cannot be reused from management commands, Celery tasks, or tests without going through HTTP. Services are plain Python classes.
- Separation makes it possible to test normalization rules without spinning up the Django test client.
- Each service has a single, clear responsibility.

**Trade-off**: A tiny bit more boilerplate. Views become boring delegation calls — but boring views are a feature, not a bug.

---

## 3. Raw Data Preservation

**Decision**: Store the original row as a JSON blob in `RawData.payload` before any transformation.

**Why**:
- ESG reporting is heavily audited. Regulators may ask: "What exactly did your SAP system report on January 10th?" You must be able to answer with the original numbers.
- Normalization rules change over time (e.g., a new emission factor is released). Raw data allows re-processing without asking data owners to re-send files.
- Debugging: when an analyst questions a CO₂e figure, you can trace it back to the exact CSV row.

**Cost**: Roughly 2× storage for each record. Acceptable given that ESG datasets are typically in the thousands of rows per month, not billions.

---

## 4. Validation as a Separate Pass (Not Inline)

**Decision**: `ValidationService` runs as a distinct step after normalization, not inline within the adapters.

**Why**:
- Adapters know about format quirks (European numbers, IATA codes). They should not also know business rules.
- Validation rules need to run on *normalized* data (canonical units, resolved dates). Running them on raw data would require every rule to handle multiple unit formats.
- The rule registry (`@rule` decorator) is easy to extend without touching existing rules.

---

## 5. SQLite for Development

**Decision**: SQLite as the development database.

**Why**: Zero configuration for a prototype. JSONField is supported in Django 3.1+ with SQLite. 

**Production note**: Switch to PostgreSQL. JSONField queries are much faster with PostgreSQL's native JSONB type and GIN indexes.

---

## 6. React + Vite (No Redux)

**Decision**: React functional components, hooks, no Redux or heavy state management.

**Why**:
- The application has two pages: Upload and Dashboard. Global state is minimal.
- `useRecords` custom hook covers the most complex state (records list + pagination + filters). Hooks are sufficient.
- Redux would add 3–5 files of boilerplate for no benefit at this scale.
- Vite provides extremely fast HMR and simple config.

---

## 7. GHG Protocol Scope Classification

**Decision**: Classify emissions into Scope 1 / 2 / 3 in NormalizationService, not in the adapter or UI.

**Why**: Scope classification requires knowing both the source type *and* the activity category (e.g., purchased electricity is always Scope 2 regardless of which utility). This is business logic, not parsing logic.

**Assumption**: SAP procurement data contains only direct fuel consumption (Scope 1). In a full implementation, procured goods would be Scope 3.

---

## 8. Emission Factors

**Assumption**: Built-in emission factors use DEFRA 2023 GHG Conversion Factors (UK). These are representative values for a prototype.

**Production gap**: Emission factors vary by year, country/grid, and fuel grade. A production system would need:
- An `EmissionFactor` database table with versioning
- Geographic lookup (UK grid ≠ German grid ≠ Indian grid)
- Factor versioning tied to the reporting year

---

## 9. Airport Distance Lookup

**Decision**: Use a hardcoded lookup table of common corporate routes for IATA code → distance.

**Why**: Building or licensing a full IATA database is out of scope for a prototype. The 30 routes in the table cover 80%+ of typical corporate travel.

**Production approach**: Call the [Great Circle Mapper API](http://www.gcmap.com/) or maintain a database from [OpenFlights](https://openflights.org/data.html).

---

## 10. No Authentication in Prototype

**Assumption**: Authentication is omitted. The `actor` field in `AuditLog` accepts `None` when no user is authenticated.

**Production gap**: Add Django REST Framework TokenAuthentication or JWT, and a multi-tenant middleware that reads `org_id` from the token and injects it into all queries.
