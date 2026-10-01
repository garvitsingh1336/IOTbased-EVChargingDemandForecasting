# Architecture

```mermaid
flowchart LR
  B[Official Boulder snapshot] --> P[Validate / deduplicate / UTC hourly arrivals]
  P --> T[Chronological XGBoost and baseline evaluation]
  T --> M[Versioned model and reports]
  P --> H[(PostgreSQL historical observations)]
  B --> R[Historical arrival replay]
  R --> A[FastAPI REST ingestion]
  A --> E[(Separate replay events)]
  M --> F[24-hour forecast service]
  H --> F
  F --> S[(Immutable forecast runs)]
  H --> G[Grafana read-only dashboard]
  E --> G
  S --> G
```

Python runs on Windows; Docker hosts PostgreSQL and Grafana. Grafana is the primary frontend. Training stays offline. Replay never modifies historical aggregates. Timestamps are stored in UTC and displayed in America/Denver. Dataset hashes, model versions, training cutoffs and separate forecast IDs preserve provenance.
