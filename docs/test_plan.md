# System Test Plan

## 1. Overview & Objectives

The primary objective of the test plan is to ensure that the **IoT-Based EV Charging Demand Forecasting System** operates with complete mathematical integrity, API contract adherence, thread safety, and zero data leakage. 

Testing spans unit, integration, end-to-end smoke, and security audit levels.

---

## 2. Test Scope & Categorization

```
┌────────────────────────────────────────────────────────┐
│                   Testing Hierarchy                    │
├────────────────────────────────────────────────────────┤
│ Level 4: Live Grafana Query & Security Verification    │
├────────────────────────────────────────────────────────┤
│ Level 3: End-to-End PostgreSQL + REST Smoke Testing    │
├────────────────────────────────────────────────────────┤
│ Level 2: API Contract & Ingestion Integration Tests    │
├────────────────────────────────────────────────────────┤
│ Level 1: Unit Tests (Data, ML Invariants, Serialization)│
└────────────────────────────────────────────────────────┘
```

### 2.1 In-Scope
* Preprocessing correctness: Timestamp parsing, daylight saving transitions (DST fold/gap handling), deduplication, and coverage status.
* Machine learning invariants: Absence of lookahead leakage, non-negative predictions ($\hat{y} \ge 0$), and recursive lag calculations.
* API contracts: Status codes (200, 201, 404, 409, 422, 503), Pydantic input validation, timezone validation, and hourly boundary constraints.
* Replay idempotency: Duplicate detection, resume after pause, and generational reset isolation.
* Relational persistence: Dialect-aware upserts, transactional rollbacks, and foreign key cascades.
* Dashboard provisioning: Static JSON syntax, datasource mapping, and live SQL query execution against PostgreSQL.
* Security: RBAC verification ensuring `grafana_reader` role cannot write or drop tables.

---

## 3. Test Suites & Verification Modules

| Test Module | Level | Focus / Target | Test Count |
|---|---|---|:---:|
| `tests/test_data.py` | Unit | ACN data recovery, cleaning, hourly aggregation, and silent-gap masking. | 6 |
| `tests/test_boulder.py` | Unit | Boulder ArcGIS adapter, DST fold resolution, duplicate payload removal, and site filtering. | 9 |
| `tests/test_models.py` | Unit | Feature matrix construction, cyclical encodings, zero lookahead leakage, recursive 24h forecasting, and non-negativity. | 7 |
| `tests/test_artifacts.py` | Unit | Native XGBoost `.ubj` loading, cryptographic SHA-256 verification, and feature schema validation. | 4 |
| `tests/test_api.py` | Integration | FastAPI endpoints, readiness checks, hourly boundary validation, 409 conflict handling, replay idempotency, and immutable forecast persistence. | 14 |
| `tests/test_replay.py` | Integration | Simulated IoT feed client, arrival-only payload validation, pacing, and resume deduplication. | 5 |
| `tests/test_grafana_config.py`| Integration | Static JSON dashboard schema, variable definitions, and SQL target inspection. | 2 |
| `tests/test_dashboard.py` | Integration | Streamlit fallback interface controls and rendering tests. | 3 |
| `scripts/smoke_evforecast.py` | E2E Smoke | Live PostgreSQL container integration, bootstrap idempotency, REST ingestion, and forecast storage. | 1 |
| `scripts/verify_grafana.py` | E2E Audit | Execution of all 20 dashboard SQL queries against live PostgreSQL and verification of read-only permissions. | 1 |

---

## 4. Test Environment & Tooling

* **Test Framework**: `pytest==8.4.2`
* **Isolated Testing DB**: In-memory SQLite for rapid unit test execution without external Docker dependencies.
* **Production Testing DB**: PostgreSQL 16 Alpine container accessed via `127.0.0.1:5432`.
* **HTTP Test Client**: `httpx==0.28.1` (FastAPI `TestClient`).
* **Hardware Requirements**: Local x86_64 host with 4+ GB RAM and Docker Desktop active.

---

## 5. Pass / Fail Criteria & Quality Gates

| Quality Gate | Pass Criterion | Enforcement Mechanism |
|---|---|---|
| **Unit Test Pass Rate** | $100\%$ ($50 / 50$ tests pass) | Automated pytest execution |
| **Data Leakage Check** | Feature columns at time $t$ must strictly rely on indices $\le t-1$ | `tests/test_models.py::test_feature_leakage` |
| **Model Invariant** | $100\%$ of predicted values must be $\ge 0$ | `tests/test_models.py::test_nonnegative` |
| **Database RBAC** | `grafana_reader` must fail on `CREATE`, `DROP`, `INSERT` | `scripts/verify_grafana.py` |
| **Dashboard Queries** | $20 / 20$ SQL panels must return HTTP 200 and $>0$ rows | `scripts/verify_grafana.py` |

---

## 6. Execution Instructions

```powershell
# 1. Execute all 50 automated pytest suites
.\.venv\Scripts\python.exe -m pytest -q

# 2. Execute live PostgreSQL + REST API smoke test
.\.venv\Scripts\python.exe scripts/smoke_evforecast.py

# 3. Execute live Grafana SQL query and security verification
.\.venv\Scripts\python.exe scripts/verify_grafana.py
```
