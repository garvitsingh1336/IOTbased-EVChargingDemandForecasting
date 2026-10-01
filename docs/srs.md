# Software Requirements Specification (SRS)
## Standard IEEE 830 Format

---

## 1. Introduction

### 1.1 Purpose
This document specifies the software requirements for the **IoT-Based EV Charging Demand Forecasting System**. It details functional capabilities, performance criteria, security boundaries, and data contracts implemented across the data processing pipeline, machine learning engine, REST API, relational database, and Grafana dashboard.

### 1.2 Document Conventions
* **FR**: Functional Requirement
* **NFR**: Non-Functional Requirement
* **UTC**: Coordinated Universal Time
* **REST**: Representational State Transfer
* **UBJ**: Universal Binary JSON (native XGBoost serialization format)

### 1.3 Intended Audience
* Academic evaluators, viva panels, software engineers, and system architects.

---

## 2. Overall Description

### 2.1 Product Perspective
The system operates as a self-contained, microservice-based edge demand intelligence prototype running locally inside Docker containers and Python runtime environments.

```
┌─────────────────┐       HTTP JSON       ┌────────────────────────┐
│  IoT Simulator  │ ────────────────────► │  FastAPI REST Backend  │
└─────────────────┘                       └────────────────────────┘
                                                       │
                                   SQLAlchemy          │  Inference
                                        │              ▼
                                        │      ┌───────────────┐
                                        │      │ XGBoost Model │
                                        ▼      └───────────────┘
                              ┌───────────────────┐
                              │  PostgreSQL 16 DB │
                              └───────────────────┘
                                        ▲
                               Read-Only│SQL
                              ┌───────────────────┐
                              │    Grafana 12.2   │
                              └───────────────────┘
```

### 2.2 User Classes & Personas
1. **System Administrator / Developer**: Deploys services, triggers database bootstrapping, configures ML hyperparameters, and runs test suites.
2. **Operations Analyst**: Views Grafana dashboards, monitors 24-hour demand predictions, evaluates forecast accuracy against actuals, and tracks replay ingestion.
3. **Simulated Edge Sensor**: Automated client generating HTTP POST requests containing charging session arrival payloads.

### 2.3 Operating Environment
* Operating System: Linux / Windows 10/11 (PowerShell / Bash)
* Container Engine: Docker Engine 24+ / Docker Desktop (WSL 2 on Windows)
* Runtime: Python 3.11 – 3.13 (64-bit)

---

## 3. Functional Requirements (FR)

### 3.1 Data Ingestion & Preprocessing
* **FR-DATA-01 (ArcGIS Raw Ingestion)**: The system shall parse official City of Boulder Open Data JSON exports containing up to 150,000 transaction records.
* **FR-DATA-02 (Audit & Deduplication)**: The pipeline shall detect and eliminate duplicate record IDs (`ObjectId2`) and remove exact duplicate payload transactions.
* **FR-DATA-03 (Timezone & DST Normalization)**: The system shall resolve local `America/Denver` wall-clock timestamps into unambiguous UTC instants, correctly resolving 1-hour fall-back folds and spring-forward gaps.
* **FR-DATA-04 (Hourly Demand Aggregation)**: The system shall aggregate discrete plug-in events into regular 1-hour UTC bins ($\text{arrivals/hour}$).
* **FR-DATA-05 (Coverage Verification)**: Any silent gap of $\ge 168$ continuous hours without events shall be flagged as `unknown_coverage` rather than assumed zero demand.

### 3.2 Machine Learning & Recursive Forecasting
* **FR-ML-01 (Feature Engineering)**: The model shall construct leakage-free feature vectors including cyclical hour-of-day sine/cosine transforms, day-of-week indicators, weekend flags, lag values ($t-1, t-24, t-168$), and shifted rolling means/standard deviations over 24h and 168h windows.
* **FR-ML-02 (Recursive Horizon)**: The engine shall project exactly 24 consecutive elapsed hours recursively; for $h > 1$, missing future lag values shall use model predictions from earlier steps, never held-out actuals.
* **FR-ML-03 (Non-Negative Invariant)**: Model predictions must be strictly non-negative ($\hat{y}_t \ge 0$).
* **FR-ML-04 (Baseline Benchmarks)**: The pipeline shall calculate baseline predictions for `same_hour_last_week` and `hour_of_week_average` across identical evaluation windows.
* **FR-ML-05 (Immutable Artifact Storage)**: The trained XGBoost model shall be saved in native `.ubj` binary format accompanied by SHA-256 checksums and feature schema descriptors.

### 3.3 REST API Endpoints
* **FR-API-01 (`GET /health`)**: Returns service status, database connectivity, model readiness, and active model version.
* **FR-API-02 (`GET /history`)**: Queries time-bounded historical hourly demand with ISO 8601 UTC parameters.
* **FR-API-03 (`POST /forecasts`)**: Accepts a timestamped hourly origin, verifies that it is at or after the training cutoff with at least 168h of historical context, and returns a 24-point forecast.
* **FR-API-04 (`GET /forecasts/{forecast_id}`)**: Retrieves a saved forecast run, including hourly predictions, joined actuals, predicted total, and peak hour.
* **FR-API-05 (`POST /replay-runs/{run_id}/events`)**: Ingests incoming IoT arrival events. Rejects payloads with missing fields or site mismatches (HTTP 422), rejects duplicate IDs with mismatched values (HTTP 409 Conflict), and accepts identical replays idempotently without double-counting.
* **FR-API-06 (`POST /replay-runs/{run_id}/reset`)**: Resets an active replay run by incrementing its generation identifier and purging previously ingested events.

### 3.4 Storage & Relational Database
* **FR-DB-01 (Schema Integrity)**: Relational schema must enforce foreign keys, composite primary keys, and timestamp indexes across 7 tables (`datasets`, `hourly_demand`, `replay_runs`, `arrival_events`, `forecast_runs`, `forecast_points`, `evaluation_results`).
* **FR-DB-02 (Idempotent Ingestion)**: Database dialect adapters must support idempotent batch insertion using `ON CONFLICT DO NOTHING`.
* **FR-DB-03 (Role-Based Access Control)**: PostgreSQL must provision an application user (`ev_app`) with full DDL/DML rights and a dedicated reader user (`grafana_reader`) with strict `SELECT`-only privileges.

### 3.5 Grafana Dashboard
* **FR-UI-01 (Automated Provisioning)**: The dashboard must automatically provision on container boot without manual UI configuration.
* **FR-UI-02 (Telemetry Panels)**: The dashboard shall display 27 panels covering KPI stat cards, forecast exploration, actual-versus-predicted comparisons, diurnal/weekly patterns, correlation heatmaps, baseline benchmark comparisons, and live replay ingestion tables.
* **FR-UI-03 (Interactive Templating)**: Dropdown selectors for `Dataset`, `Forecast Run`, and `Replay Run` must dynamically filter dashboard queries.

---

## 4. Non-Functional Requirements (NFR)

### 4.1 Performance & Latency
* **NFR-PERF-01**: The REST API shall return `/health` requests in $< 15\text{ ms}$ under standard local load.
* **NFR-PERF-02**: A complete 24-hour recursive forecast generation via `POST /forecasts` shall execute in $< 100\text{ ms}$.
* **NFR-PERF-03**: All 20 SQL queries backing Grafana panels must execute in $< 50\text{ ms}$ each on a dataset containing 8,700+ rows.

### 4.2 Security & Protection
* **NFR-SEC-01**: Sensitive credentials (`POSTGRES_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`) must be injected via `.env` and never committed to version control.
* **NFR-SEC-02**: Grafana must connect using the read-only database credentials (`grafana_reader`) preventing SQL injection from altering or deleting data.
* **NFR-SEC-03**: API schemas must enforce `extra="forbid"` to reject unvalidated payload injection.

### 4.3 Reliability & Fault Tolerance
* **NFR-REL-01**: If the database is unreachable, the API shall return HTTP 503 Service Unavailable with a structured error response instead of crashing.
* **NFR-REL-02**: Replay simulator client must automatically retry failed HTTP requests with exponential backoff.
* **NFR-REL-03**: PostgreSQL container must have an automated healthcheck testing connectivity every 5 seconds.
