# Executed verification

Python: 3.13.9

- original_sha256_unchanged: True
- identical_model_test_timestamps: True
- test_hours_per_model: 336
- nonnegative_predictions: True
- pytest_exit_code: 0
- cli_replay_unique_events: 10
- cli_replay_restart_deduplicates: True
- streamlit_health: HTTP 200: ok
- streamlit_home: HTTP 200
- dashboard_url: http://127.0.0.1:8501
- dashboard_pid: 14852
- note: Streamlit AppTest verifies rendering and controls; live HTTP verifies server startup. No visual browser inspection performed.

## Test runner

```text
......................                                                   [100%]
22 passed in 9.13s
```

Full pipeline preprocessing/training/evaluation completed on the real local source.
Official six-month download was attempted but returned truncated JSON; see official_access.json.
Dependency installation into a fresh virtual environment and a visual browser check were not performed.
Tests use small constructed fixtures solely for correctness; no synthetic data trains the project models.