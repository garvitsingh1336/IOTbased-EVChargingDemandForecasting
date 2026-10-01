# Five-minute demonstration

Before presenting, start Docker Desktop, run `docker compose up -d --wait`, `python -m evforecast bootstrap-db`, and `python -m uvicorn evforecast.api:app --host 127.0.0.1 --port 8000` using the project virtual environment.

1. **0:00–0:45:** Open http://localhost:3000/d/evforecast-demand. Explain sessions/hour, historical Boulder dates, and the two source station names.
2. **0:45–1:30:** Show dataset coverage, timestamp checks and removal of 1,163 repeated export rows. Explain that zeros assume reporting coverage.
3. **1:30–2:30:** Show the forecast origin, training cutoff, expected total, peak hour and blue actual/orange forecast comparison. All predictions are historical.
4. **2:30–3:30:** Compare the model table: XGBoost MAE 0.510, over 30 full forecast origins. Explain chronological validation and recursive lags.
5. **3:30–4:30:** In a second terminal run `.\.venv\Scripts\python.exe -m evforecast simulate --api-url http://127.0.0.1:8000 --run-id demo --speed 3600 --reset`. Scroll to **Historical data replay — simulated IoT feed** and refresh. Ctrl+C pauses; rerun without reset to resume without duplicate counts.
6. **4:30–5:00:** Explain REST ingestion, PostgreSQL storage and Grafana's read-only role. State the Indian-campus generalization and missing-coverage limitations.

Use the existing `.env` admin credentials. For a quicker replay use `--speed 100000000 --limit 10`. Do not call 2023 observations live data.
