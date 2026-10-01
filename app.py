"""Streamlit historical forecasting demonstration. Run: python -m streamlit run app.py"""
import json
import time
import uuid

import pandas as pd
import plotly.express as px
import streamlit as st

from evforecast.config import ROOT
from evforecast.replay import LABEL, ReplayFeed, arrival_events

st.set_page_config(page_title="EV Charging Demand Forecasting", page_icon="âš¡", layout="wide")
st.title("EV Charging Forecasting | Legacy interface")
st.info("Grafana is the primary dashboard. This retained interface is optional.")
st.caption("College prototype â€¢ site-wide session arrivals â€¢ local software simulation")
required = ["reports/data_quality.json", "reports/evaluation.json", "data/hourly.csv",
            "data/sessions.csv", "artifacts/demo_forecast.csv", "reports/test_metrics.csv",
            "reports/test_predictions.csv", "reports/validation_metrics.csv", "reports/errors_by_hour.csv"]
missing = [p for p in required if not (ROOT / p).exists()]
if missing:
    st.error("Project outputs are missing. Run: python -m evforecast all")
    st.code("\n".join(missing))
    st.stop()

quality = json.loads((ROOT / "reports/data_quality.json").read_text())
evaluation = json.loads((ROOT / "reports/evaluation.json").read_text())
tz = evaluation["timezone"]
hourly = pd.read_csv(ROOT / "data/hourly.csv")
hourly["timestamp"] = pd.to_datetime(hourly.timestamp, utc=True)
hourly["local"] = hourly.timestamp.dt.tz_convert(tz)
sessions = pd.read_csv(ROOT / "data/sessions.csv", dtype={"siteID": str, "stationID": str, "sessionID": str})
demo = pd.read_csv(ROOT / "artifacts/demo_forecast.csv")
demo["timestamp"] = pd.to_datetime(demo.timestamp, utc=True)
origin = pd.Timestamp(evaluation["demo_origin"])
st.warning("Historical Boulder demonstration â€” not a validated forecast for today. Demand means session starts/hour, not electrical load.")
st.caption(f"Site: {evaluation['configuration']['site_name']} | Timezone: {tz} | Connections: {quality['first_connection_local']} to {quality['last_connection_local']}")
st.caption(f"Demo forecast origin: {origin.tz_convert(tz).isoformat()} | Last observed hour starts: "
           f"{pd.Timestamp(evaluation['demo_last_observation']).tz_convert(tz).isoformat()} "
           "(the hour ends at the origin).")

overview, patterns, prediction_tab, evaluation_tab, replay_tab = st.tabs(
    ["Data overview", "Historical patterns", "Next 24 hours", "Model evaluation", "Simulated IoT feed"])

with overview:
    a, b, c, d = st.columns(4)
    a.metric("Usable selected sessions", f"{quality['usable_arrivals']:,}")
    b.metric("Observed station names", quality["charging_points"])
    c.metric("Interior local days", quality["local_days"])
    d.metric("Assumed zero hours", quality["assumed_zero_hours"])
    st.write(f"Model series: {quality['included_arrivals']:,} arrivals across {quality['hourly_rows']:,} hours. "
             f"{quality['excluded_boundary_arrivals']} boundary-day arrivals excluded.")
    st.write("Source snapshot completeness does not establish feed uptime. A gap without events does not prove the feed was working; even populated hours can be undercounted.")
    for warning in quality["warnings"]:
        st.caption("â€¢ " + warning)
    st.dataframe(pd.DataFrame({
        "Check": ["Duplicate session IDs", "Missing doneChargingTime", "doneChargingTime outside session",
                  "Unusable arrivals", "Known missing hours"],
        "Count": [quality["duplicate_session_ids"], quality["invalid_or_missing_doneChargingTime"],
                  quality["done_charging_outside_session"], quality["unusable_arrival_records"],
                  quality["known_missing_hours"]]}), hide_index=True)
    with st.expander("Recovery and quality details"):
        st.json(quality)

with patterns:
    st.subheader("Historical site arrivals")
    chart = hourly.copy()
    # Offset-bearing labels preserve the distinction between repeated DST hours.
    chart["Local timestamp"] = chart.local.map(lambda x: x.isoformat())
    st.plotly_chart(px.line(chart, x="Local timestamp", y="arrivals",
                           labels={"arrivals": "Arrivals (sessions/hour)"}), width="stretch")
    chart["weekday"] = chart.local.dt.dayofweek
    chart["hour"] = chart.local.dt.hour
    chart["date"] = chart.local.dt.strftime("%Y-%m-%d")
    means = chart.groupby("weekday", as_index=False).arrivals.mean()
    means["Day"] = means.weekday.map(dict(enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])))
    left, right = st.columns(2)
    left.plotly_chart(px.bar(means, x="Day", y="arrivals", labels={"arrivals": "Mean sessions/hour"}), width="stretch")
    clock_means = chart.groupby("hour", as_index=False).arrivals.mean()
    right.plotly_chart(px.line(clock_means, x="hour", y="arrivals", labels={"hour": f"Hour ({tz})", "arrivals": "Mean sessions/hour"}), width="stretch")
    heat = chart.pivot_table(index="date", columns="hour", values="arrivals", aggfunc="mean")
    st.plotly_chart(px.imshow(heat, aspect="auto", labels={"x": f"Local hour ({tz})", "y": "Local date", "color": "Sessions/hour"},
                             title="Day/hour heatmap (repeated DST hours averaged)"), width="stretch")

with prediction_tab:
    st.subheader("Next 24 hours from the historical cutoff")
    st.write(f"Primary ML method: **XGBoost**; validation winner: **{evaluation['selected_model']}**")
    displayed = demo.copy()
    displayed["Local timestamp"] = displayed.timestamp.dt.tz_convert(tz).map(lambda x: x.isoformat())
    a, b = st.columns(2)
    a.metric("Expected total arrivals / 24 h", f"{demo.prediction.sum():.1f}")
    busiest = displayed.loc[displayed.prediction.idxmax()]
    b.metric("Busiest expected hour", busiest["Local timestamp"], f"{busiest.prediction:.2f} sessions/hour")
    st.plotly_chart(px.line(displayed, x="Local timestamp", y="prediction", markers=True,
                           labels={"prediction": "Expected arrivals (sessions/hour)"}), width="stretch")
    st.caption("Fractional predictions are expected counts. Display formatting does not change evaluation. No calibrated uncertainty bands are shown.")
    st.dataframe(displayed[["Local timestamp", "prediction"]].rename(columns={"prediction": "Expected sessions/hour"}), hide_index=True)
    st.download_button("Download historical forecast CSV", demo.to_csv(index=False), "historical_forecast.csv", "text/csv")

with evaluation_tab:
    metrics = pd.read_csv(ROOT / "reports/test_metrics.csv")
    st.subheader("Chronological held-out test")
    st.write(f"{evaluation['test_origins']} complete 24-hour origins â€¢ {evaluation['test_local_dates']} local dates â€¢ "
             f"{evaluation['unique_test_hours']} unique target hours. All models use identical timestamps.")
    st.caption(f"Test interval (UTC): {evaluation['test_start']} to {evaluation['test_end_exclusive']} (exclusive).")
    st.dataframe(metrics, hide_index=True)
    st.plotly_chart(px.bar(metrics.melt(id_vars="model", value_vars=["MAE", "RMSE"]), x="model",
                           y="value", color="variable", barmode="group",
                           labels={"value": "Error (sessions/hour)"}), width="stretch")
    st.caption("Selection uses validation scores, never the test winner. RF and historical averages are frozen throughout the test; lag inputs can use observations from before each forecast origin.")
    with st.expander("Validation scores and modest tuning"):
        st.dataframe(pd.read_csv(ROOT / "reports/validation_metrics.csv"), hide_index=True)
        st.json(evaluation["tuning"])
    predictions = pd.read_csv(ROOT / "reports/test_predictions.csv")
    chosen_origin = st.selectbox("Historical forecast origin (UTC)", predictions.origin.unique())
    subset = predictions[predictions.origin == chosen_origin]
    actual = subset[["timestamp", "actual"]].drop_duplicates().rename(columns={"actual": "value"})
    actual["series"] = "actual"
    predicted = subset[["timestamp", "model", "prediction"]].rename(columns={"model": "series", "prediction": "value"})
    curves = pd.concat([actual, predicted])
    curves["local_time"] = pd.to_datetime(curves.timestamp, utc=True).dt.tz_convert(tz).map(lambda x: x.isoformat())
    st.plotly_chart(px.line(curves, x="local_time", y="value", color="series",
                           labels={"local_time": f"Time ({tz})", "value": "Sessions/hour"}), width="stretch")
    errors = pd.read_csv(ROOT / "reports/errors_by_hour.csv")
    st.plotly_chart(px.line(errors, x="local_hour", y="absolute_error", color="model",
                           labels={"local_hour": f"Hour ({tz})", "absolute_error": "MAE (sessions/hour)"}), width="stretch")

with replay_tab:
    st.subheader(LABEL)
    st.write("Arrival events contain only an ID, timestamp, site, and charger. The model stays frozen before the test cutoff.")
    replay_end = origin + pd.Timedelta(hours=24)
    events = arrival_events(sessions, origin, replay_end)
    if "replay_id" not in st.session_state:
        st.session_state.replay_id = uuid.uuid4().hex
        st.session_state.replay_running = False
        st.session_state.replay_clock = origin
        st.session_state.replay_tick = time.monotonic()
    feed = ReplayFeed(ROOT / "runtime" / f"dashboard_{st.session_state.replay_id}.jsonl")
    speed = st.slider("Historical minutes per real second", 1, 120, 60)
    a, b, c = st.columns(3)
    if a.button("Start / resume", key="start"):
        st.session_state.replay_running = True
        st.session_state.replay_tick = time.monotonic()
    if b.button("Pause", key="pause"):
        st.session_state.replay_running = False
    if c.button("Reset replay", key="reset"):
        feed.reset()
        st.session_state.replay_running = False
        st.session_state.replay_clock = origin
        st.session_state.replay_tick = time.monotonic()

    @st.fragment(run_every=1.0)
    def replay_panel():
        now = time.monotonic()
        if st.session_state.replay_running:
            seconds = (now - st.session_state.replay_tick) * speed * 60
            st.session_state.replay_clock = min(
                replay_end, st.session_state.replay_clock + pd.Timedelta(seconds=seconds))
            if st.session_state.replay_clock >= replay_end:
                st.session_state.replay_running = False
        st.session_state.replay_tick = now
        current_feed = ReplayFeed(feed.path)
        for event in events:
            if pd.Timestamp(event["timestamp"]) <= st.session_state.replay_clock:
                current_feed.ingest(event)
        clock = st.session_state.replay_clock
        st.write(f"Replay clock: **{clock.tz_convert(tz).isoformat()}**")
        st.write(f"State: {'Running' if st.session_state.replay_running else 'Paused / ready / complete'} | "
                 f"Unique ingested events: {len(current_feed.seen)}")
        visible = [event for event in events if event["event_id"] in current_feed.seen]
        st.dataframe(pd.DataFrame(visible[-20:]), hide_index=True)
        if visible:
            counts = pd.Series(pd.to_datetime([e["timestamp"] for e in visible], utc=True)).dt.floor("h").value_counts()
            completed = demo.loc[demo.timestamp + pd.Timedelta(hours=1) <= clock, ["timestamp", "prediction"]].copy()
            completed["replayed_arrivals"] = completed.timestamp.map(counts).fillna(0)
            completed["local_time"] = completed.timestamp.dt.tz_convert(tz).map(lambda x: x.isoformat())
            st.plotly_chart(px.line(completed, x="local_time", y=["prediction", "replayed_arrivals"],
                                   labels={"value": "Sessions/hour", "local_time": f"Completed replay hour ({tz})"}),
                            width="stretch")
        st.caption("Replay logs live only in runtime/. No final energy/departure details are emitted. Empty completed replay hours still rely on assumed historical coverage.")
    replay_panel()
