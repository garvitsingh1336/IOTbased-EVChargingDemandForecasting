# Project Purpose & Motivation

## 1. Academic & Industry Motivation
The global transition toward electrified transportation is essential for reducing greenhouse gas emissions and achieving carbon neutrality. However, widespread electric vehicle (EV) adoption poses severe infrastructure challenges. Unlike traditional internal combustion engine refueling, which takes minutes, EV charging sessions can last from 30 minutes to several hours. 

As a consequence, uncoordinated EV charging patterns create localized bottlenecks, transformer overload, voltage sag on distribution feeders, and long driver waiting times. Predicting charging station utilization has therefore emerged as a foundational requirement for sustainable urban energy management.

---

## 2. Core Problem Statement
Current commercial charging stations operate predominantly in a **reactive** paradigm:
1. Operators only observe congestion when all physical ports are already occupied.
2. Grid utilities must absorb sudden spikes in charging loads without prior warning.
3. Fleet and facility managers lack granular, hour-by-hour expectations of customer arrival surges.

Without forward-looking visibility, infrastructure planning relies on static averages or rule-of-thumb estimates that fail to capture weather anomalies, weekday-versus-weekend dynamics, and diurnal commuter cycles.

---

## 3. Why Session Arrival Demand Matters
A critical design distinction of this project is its focus on **charging session arrivals** ($\text{sessions/hour}$) rather than total electrical energy ($\text{kWh}$) or instantaneous electrical power ($\text{kW}$).

```
┌────────────────────────────────────────────────────────┐
│ Why Predict Session Arrivals Rather Than Electrical Load?│
└────────────────────────────────────────────────────────┘
                           │
       ┌───────────────────┴───────────────────┐
       ▼                                       ▼
[ Session Arrivals (This Project) ]   [ Total Energy Delivered (kWh) ]
• Direct proxy for charger congestion   • Confounded by battery state-of-charge
• Directly observable at plug-in        • Dependent on vehicle onboard charger specs
• Independent of vehicle battery size   • Does not identify peak traffic times
• Invariant to charging speed drops    • Cannot distinguish 1 car taking 50kWh
                                        from 5 cars taking 10kWh each
```

By predicting arrival instances, operators can directly solve queueing and physical bay occupancy problems. Electrical load modeling can subsequently be coupled to this arrival stream by multiplying arrival counts by average energy draw per vehicle.

---

## 4. Architectural Value Proposition

### 4.1 For Charging Station Operators (CPOs)
* **Dynamic Resource Allocation**: Anticipate morning and late-afternoon commuter surges to dynamically adjust tariff rates, incentivize off-peak charging, and optimize staffing.
* **Predictive Maintenance Windows**: Identify consistently low-demand periods (e.g., Tuesday 02:00–05:00) to schedule charger firmware updates or hardware servicing without disrupting drivers.

### 4.2 For Electric Utilities & Distribution System Operators (DSOs)
* **Feeder Headroom Management**: Incorporate 24-hour arrival forecasts into day-ahead unit commitment and battery energy storage system (BESS) dispatch algorithms.
* **Peak Shaving**: Prevent coincident peak demand between charging stations and residential air conditioning/heating cycles.

### 4.3 For Academic Research & Prototype Engineering
* **Benchmarking Against Simpler Baselines**: Rigorously proving whether non-linear machine learning models (XGBoost, Random Forest) deliver statistically meaningful improvements over seasonal heuristic baselines (`same_hour_last_week` and `hour_of_week_average`).
* **Reproducible Edge Telemetry**: Demonstrating how modern IoT communication paradigms (idempotent REST ingestion, structured schemas, replay pacing) translate into actionable time-series intelligence.

---

## 5. Technology Selection Rationale

| Dimension | Chosen Stack | Alternative Considered | Justification |
|---|---|---|---|
| **ML Engine** | **XGBoost (native UBJ)** | LSTM / Deep Learning (PyTorch) | Tabular time-series with calendar encodings and lag structures consistently yields superior or equivalent accuracy on tabular splits with $10\times$ lower compute, deterministic inference, and zero GPU requirement. |
| **API Layer** | **FastAPI (ASGI)** | Flask / Django | Built-in Pydantic data validation with strict type checking, native asynchronous lifespan handlers, and automated OpenAPI (Swagger) generation. |
| **Persistence** | **PostgreSQL 16** | MongoDB / InfluxDB | ACID guarantees, mature relational joins between actual demand and forecast runs, and native JSONB indexing for dataset quality metadata. |
| **Frontend** | **Grafana 12.2** | Custom React / Streamlit | Grafana is the worldwide industry standard for industrial IoT monitoring, featuring native SQL datasource plugins, declarative provisioning, and enterprise role-based security. |
