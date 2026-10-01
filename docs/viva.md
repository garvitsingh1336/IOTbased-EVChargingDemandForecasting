# Viva questions and answers

**What makes this IoT-related?** Software replays timestamped charging arrivals through a REST ingestion endpoint with validation, retries and duplicate suppression, representing the data path of connected chargers. There are no physical sensors; it is historical replay.

**Why public data?** It provides real observed charging behaviour without hardware or commercial access. The source, license, download checks and quality limitations are documented.

**Why Boulder?** Its official public records extend to November 2023 and support a full year at one location, instead of the earlier short ACN sample. It is not current/live data.

**Why session arrivals?** Start timestamps directly establish counts per hour. Total energy per session cannot reveal hourly power or energy distribution.

**Why XGBoost?** It is the required ML method, handles nonlinear relationships in calendar/lag features and runs on a local CPU. Modest validation-only tuning and seasonal baselines test whether it adds value.

**How was leakage prevented?** Chronological splits, no future session details, shifted rolling inputs, and a forecast-origin cutoff. Recursive forecasts substitute predictions for unavailable future arrivals. Test observations do not tune models.

**How does it compare?** XGBoost won validation. Test MAE/RMSE were 0.5097/0.8764 sessions/hour; same-hour-last-week was 0.5832/1.2360, on 30 origins and 720 matching hours. These are measured results for the selected site, not universal accuracy.

**Why not MAPE?** Many hourly counts are zero, making percentage errors undefined or unstable. MAE and RMSE retain sessions/hour units.

**Why fractional counts?** They are expected counts. Evaluation uses unrounded values; formatting does not change scores.

**How are duplicate records handled?** First deduplicate export IDs, then exact payload repeats across all charging fields. Keep the first and audit removed IDs. Records differing in other fields remain, with review flags.

**How does DST work?** Store UTC instants and use America/Denver for calendar features/display. Repeated hours have distinct UTC instants. Use timezone labels to resolve folds; mask unresolvable days. Forecasts always span 24 elapsed hours.

**Are the two station names two charging ports?** Not necessarily. The dataset lacks individual connector IDs; no physical capacity claim is made.

**Can forecasts establish waiting time?** No. Queues also need service durations, physical port counts, availability and queueing assumptions.

**Why PostgreSQL and Grafana?** PostgreSQL stores immutable history and separate forecast/replay records. Grafana queries it with read-only permissions and provides the primary dashboard. FastAPI handles ingestion and predictions; the CLI controls replay.

**What is needed at an Indian college?** Anonymized local arrivals covering seasonal/academic patterns, charger/site identifiers, consent/access permission, feed uptime and latency monitoring, operational security, and fresh chronological evaluation. US results do not automatically transfer.
