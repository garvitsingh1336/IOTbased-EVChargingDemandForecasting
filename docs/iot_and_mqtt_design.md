# IoT & MQTT Telemetry Design Document

## 1. IoT Edge Architecture

In production electric vehicle supply equipment (EVSE) environments, charging stations operate as distributed edge nodes communicating over cellular (4G/5G LTE) or Ethernet backhauls. 

This document defines the IoT telemetry architecture, MQTT topic taxonomy, message schema, quality of service (QoS) contracts, and the gateway bridging layer interfacing physical chargers with the FastAPI prediction platform.

```
┌────────────────────────────────────────────────────────┐
│               Edge Layer: EV Charging Stations         │
├────────────────────┬───────────────────┬───────────────┤
│ Charger 01 (Port A)│ Charger 02(Port B)│ ...Charger N  │
└─────────┬──────────┴─────────┬─────────┴───────┬───────┘
          │ (MQTT over TLS)    │                 │
          ▼                    ▼                 ▼
┌────────────────────────────────────────────────────────┐
│          Enterprise MQTT Broker (Mosquitto / EMQX)      │
│          Topics: ev/site/+/charger/+/arrival           │
└──────────────────────────┬─────────────────────────────┘
                           │ Subscribe (QoS 1)
                           ▼
┌────────────────────────────────────────────────────────┐
│             IoT Telemetry Gateway Service              │
│       • Message Validation & Schema Enforcement        │
│       • Deduplication by event_id                      │
│       • REST Forwarding to FastAPI Backend             │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTP POST /replay-runs/{run_id}/events
                           ▼
┌────────────────────────────────────────────────────────┐
│             FastAPI Backend & PostgreSQL DB            │
└────────────────────────────────────────────────────────┘
```

---

## 2. MQTT Topic Taxonomy & Structure

To ensure clean hierarchical filtering, publish/subscribe routing follows a standard semantic namespace:

```
ev/site/{site_id}/charger/{charger_id}/{telemetry_type}
```

### Topic Hierarchy Definitions

| Topic Path | Direction | Purpose | QoS | Retain |
|---|---|---|---|---|
| `ev/site/{site_id}/charger/{charger_id}/arrival` | Edge $\to$ Cloud | Emitted immediately upon vehicle plug-in detection. | **QoS 1** | False |
| `ev/site/{site_id}/charger/{charger_id}/heartbeat` | Edge $\to$ Cloud | Periodic device health ping (every 60s). | **QoS 0** | False |
| `ev/site/{site_id}/charger/{charger_id}/status` | Edge $\to$ Cloud | LWT (Last Will and Testament) indicating online/offline state. | **QoS 1** | **True** |
| `ev/site/{site_id}/broadcast/control` | Cloud $\to$ Edge | Remote operational commands (rate limits, firmware commands). | **QoS 2** | False |

---

## 3. Telemetry Payload Contracts

### 3.1 Arrival Event Payload (`ev/site/{site_id}/charger/{charger_id}/arrival`)
This is the core payload that feeds arrival demand forecasting. To preserve strict arrival-time isolation and prevent data leakage, **only fields known at the exact moment of connection** are transmitted.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "message_id": "msg-8f12a3d0-9941",
  "event_id": "boulder-147654",
  "timestamp": "2023-10-31T06:14:00Z",
  "site_id": "boulder-carpenter-park",
  "charger_id": "boulder-station-01",
  "port_number": 1,
  "connector_type": "J1772",
  "vehicle_detected": true
}
```

> **Leakage Prevention**: Attributes such as `energy_kwh`, `duration_minutes`, `disconnect_time`, or `charging_fee` are strictly prohibited from the arrival payload because they are only known when the driver leaves hours later.

### 3.2 Last Will & Testament (LWT) Health Payload
Emitted by the MQTT Broker if the charger loses TCP connectivity unexpectedly:

```json
{
  "charger_id": "boulder-station-01",
  "site_id": "boulder-carpenter-park",
  "status": "OFFLINE",
  "reason": "CONNECTION_LOST",
  "timestamp": "2023-10-31T06:45:12Z"
}
```

---

## 4. Edge-to-Cloud Quality of Service (QoS) & Reliability

1. **QoS 1 (At Least Once Delivery)**:
   * Arrival events use MQTT QoS 1. The edge charger stores arrival events in local non-volatile flash storage until an `MQTT PUBACK` is received from the broker.
   * If a cellular outage occurs, events are backlogged locally and re-transmitted sequentially upon reconnection.
2. **Gateway Idempotency & Deduplication**:
   * Because QoS 1 guarantees *at least once* delivery, temporary network retries can deliver duplicate packets.
   * The ingestion gateway and database employ `ON CONFLICT (run_id, event_id) DO NOTHING` to guarantee that duplicate transmissions are acknowledged but never double-counted into demand totals.

---

## 5. Software Simulation & Historical Replay Subsystem

To facilitate rigorous, reproducible local evaluation without deploying physical hardware, the system includes a high-fidelity **Simulated IoT Replay Engine** (`evforecast/replay_http.py`).

### 5.1 Replay Pacing Algorithm
The simulator reads chronological arrivals from the historical dataset and streams them across the REST API using an adjustable clock acceleration factor ($\text{speed}$):

$$\Delta t_{\text{sleep}} = \frac{t_{\text{arrival}}[i+1] - t_{\text{arrival}}[i]}{\text{speed}}$$

* `--speed 1.0`: Exact real-time replay (1 historical second = 1 wall-clock second).
* `--speed 3600.0`: 1 historical hour passes every 1 real-world second.
* `--speed 100000000.0`: Burst replay mode for instantaneous automated smoke tests.

### 5.2 Reset Isolation & Generation Identifiers
Each replay run has a unique `run_id` (e.g. `demo`) and an integer `generation`:
* Triggering `POST /replay-runs/{run_id}/reset` increments `generation = generation + 1` and wipes previously ingested events for that run.
* Any stale in-flight events from an earlier generation are rejected with `HTTP 409 Conflict`.
* **Database Safety**: Resetting a replay run touches only transient `arrival_events`; it **never** alters historical training tables (`hourly_demand`) or Docker volumes.
