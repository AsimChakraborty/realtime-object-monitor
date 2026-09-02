from __future__ import annotations

import sys
from pathlib import Path

# Ensure both the project root (for `config`) and `src/` (for the application
# packages) are importable regardless of how this script is launched.
_PROJECT_ROOT = Path(__file__).resolve().parent
_SRC_DIR = _PROJECT_ROOT / "src"
for _path in (str(_PROJECT_ROOT), str(_SRC_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import time
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from config.settings import (
    AUTO_REFRESH_SECONDS,
    CAMERAS,
    LIVE_FRAME_PATH,
    MODEL_PATH,
)
from src.database.connection import DatabaseConnection

# Resolve the shared persistence layer (same store written by `app.py`).
_connection = DatabaseConnection.from_settings()
_event_repo = _connection.event_repository()
_status_repo = _connection.status_repository()

st.set_page_config(
    page_title="Cement Bag Production Monitor",
    layout="wide",
)


EVENT_COLUMNS = [
    "Timestamp",
    "Line ID",
    "Camera ID",
    "Detection ID",
    "Direction",
    "BagNo",
    "Shift",
    "Production Batch",
]


@st.cache_data(ttl=2)
def load_events() -> pd.DataFrame:
    """Load production events from the event repository."""
    df = _event_repo.read_events(as_dataframe=True)

    if df.empty:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    for col in EVENT_COLUMNS:
        if col not in df.columns:
            df[col] = None

    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df["BagNo"] = pd.to_numeric(df["BagNo"], errors="coerce")
    df["Detection ID"] = pd.to_numeric(df["Detection ID"], errors="coerce")

    return df.sort_values("Timestamp", ascending=False)


@st.cache_data(ttl=1)
def load_status() -> dict:
    return _status_repo.read_status()


def filter_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Filter events to the selected reporting period."""
    if df.empty:
        return df

    today = pd.Timestamp(date.today())

    if period == "Today":
        return df[df["Timestamp"].dt.date == today.date()]
    if period == "This Week":
        start = today - timedelta(days=today.weekday())
        return df[df["Timestamp"] >= start]
    if period == "This Month":
        start = today.replace(day=1)
        return df[df["Timestamp"] >= start]
    if period == "Last 7 Days":
        start = today - timedelta(days=7)
        return df[df["Timestamp"] >= start]
    if period == "Last 30 Days":
        start = today - timedelta(days=30)
        return df[df["Timestamp"] >= start]

    return df


def effective_camera_status(camera: dict) -> bool:
    """A camera is 'effectively online' if its heartbeat is recent."""
    heartbeat = camera.get("last_heartbeat", "")

    if not heartbeat:
        return False

    try:
        heartbeat_time = datetime.fromisoformat(heartbeat)
        return (datetime.now() - heartbeat_time).total_seconds() <= 10
    except Exception:
        return False


st.sidebar.title("Bag Production")
page = st.sidebar.radio(
    "Navigation",
    ["Live Monitor", "Production Events", "Reports & Analytics"],
)

auto_refresh = st.sidebar.checkbox(
    f"Auto Refresh ({AUTO_REFRESH_SECONDS}s)", value=True
)

st.sidebar.markdown("---")
st.sidebar.write(f"**Configured Cameras:** {len(CAMERAS)}")
st.sidebar.write(f"**Model:** {MODEL_PATH.name}")
st.sidebar.write("**Tracker:** ByteTrack")


events = load_events()
status = load_status()
# ============================================================
# LIVE MONITOR
# ============================================================
if page == "Live Monitor":
    st.title("Bag Production Monitor")

    cameras_status = status.get("cameras", {})

    online = 0
    active = 0

    for data in cameras_status.values():
        is_online = data.get("online", False) and effective_camera_status(data)
        if is_online:
            online += 1
        active += data.get("current_count", 0)

    today_events = filter_period(events, "Today")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cameras Online", f"{online} / {len(CAMERAS)}")
    col2.metric("Active Bags", active)
    col3.metric("Bags Produced Today", len(today_events))
    col4.metric("Total Production", len(events))

    st.markdown("---")
    st.subheader("📷 Camera Status")

    camera_items = list(cameras_status.items())

    if not camera_items:
        st.info("Start app.py to populate camera status.")
    else:
        cols = st.columns(min(3, len(camera_items)))

        for i, (camera_id, data) in enumerate(camera_items):
            with cols[i % len(cols)]:
                is_online = data.get("online", False) and effective_camera_status(data)
                icon = "🟢" if is_online else "🔴"

                with st.container(border=True):
                    st.markdown(f"### {icon} {camera_id}")
                    st.write(f"**Line:** {data.get('line_id', '-')}")
                    st.metric("Active Bags", data.get("current_count", 0))
                    st.metric("Production Count", data.get("production_count", 0))
                    st.write(f"**FPS:** {data.get('fps', 0):.1f}")
                    st.write(f"**Status:** {'ONLINE' if is_online else 'OFFLINE'}")
                    st.caption(data.get("message", ""))

    st.markdown("---")
    st.subheader("🎥 Latest Processed Frame")

    if LIVE_FRAME_PATH.exists():
        st.image(str(LIVE_FRAME_PATH), caption="Live processed frame")
    else:
        st.info("No live frame available yet.")

    st.markdown("---")
    st.subheader("🕒 Recent Production Events")

    if events.empty:
        st.info("No production events available.")
    else:
        st.dataframe(events.head(15), width="stretch", hide_index=True)

    if auto_refresh:
        time.sleep(AUTO_REFRESH_SECONDS)
        st.rerun()
# ============================================================
# PRODUCTION EVENTS
# ============================================================
elif page == "Production Events":
    st.title("🗂️ Production Events")

    if events.empty:
        st.info("No production events available.")
    else:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            period = st.selectbox(
                "Period",
                [
                    "All",
                    "Today",
                    "This Week",
                    "This Month",
                    "Last 7 Days",
                    "Last 30 Days",
                ],
            )

        with col2:
            cameras = sorted(events["Camera ID"].dropna().astype(str).unique())
            selected_cameras = st.multiselect("Camera", cameras, default=cameras)

        with col3:
            directions = sorted(events["Direction"].dropna().astype(str).unique())
            selected_directions = st.multiselect(
                "Direction", directions, default=directions
            )

        with col4:
            search_bag = st.text_input("Search BagNo")
            exact_match = st.checkbox("Exact match", value=True)

        filtered = events.copy()

        if period != "All":
            filtered = filter_period(filtered, period)

        if selected_cameras:
            filtered = filtered[
                filtered["Camera ID"].astype(str).isin(selected_cameras)
            ]

        if selected_directions:
            filtered = filtered[
                filtered["Direction"].astype(str).isin(selected_directions)
            ]

        if search_bag.strip():
            if exact_match:
                search_num = pd.to_numeric(search_bag, errors="coerce")
                if pd.notna(search_num):
                    filtered = filtered[filtered["BagNo"] == search_num]
                else:
                    filtered = filtered[
                        filtered["BagNo"].astype(str) == search_bag.strip()
                    ]
            else:
                filtered = filtered[
                    filtered["BagNo"].astype(str).str.contains(search_bag, na=False)
                ]

        st.metric("Matching Production Events", len(filtered))

        st.dataframe(filtered, width="stretch", hide_index=True, height=550)

        csv_data = filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download Events CSV",
            data=csv_data,
            file_name=f"production_events_{date.today()}.csv",
            mime="text/csv",
        )
# ============================================================
# REPORTS & ANALYTICS
# ============================================================
else:
    st.title("📊 Reports & Analytics")

    if events.empty:
        st.info("No production events available.")
    else:
        period = st.selectbox(
            "Report Period",
            [
                "Today",
                "This Week",
                "This Month",
                "Last 7 Days",
                "Last 30 Days",
                "All Time",
            ],
            index=2,
        )

        if period == "All Time":
            filtered = events.copy()
        else:
            filtered = filter_period(events, period)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Bags", len(filtered))
        col2.metric("Unique BagNo", filtered["BagNo"].nunique())
        col3.metric("DOWN", int((filtered["Direction"] == "DOWN").sum()))
        col4.metric("UP", int((filtered["Direction"] == "UP").sum()))

        st.markdown("---")

        if not filtered.empty:
            daily = (
                filtered.assign(Date=filtered["Timestamp"].dt.date)
                .groupby("Date")
                .size()
                .reset_index(name="Production")
            )

            fig = px.bar(
                daily,
                x="Date",
                y="Production",
                title="Daily Cement Bag Production",
            )
            st.plotly_chart(fig, width="stretch")

            shift_counts = filtered["Shift"].value_counts().reset_index()
            shift_counts.columns = ["Shift", "Production"]
            fig_shift = px.bar(
                shift_counts,
                x="Shift",
                y="Production",
                title="Production by Shift",
            )
            st.plotly_chart(fig_shift, width="stretch")

            camera_counts = filtered["Camera ID"].value_counts().reset_index()
            camera_counts.columns = ["Camera ID", "Production"]
            fig_camera = px.pie(
                camera_counts,
                names="Camera ID",
                values="Production",
                title="Production by Camera",
            )
            st.plotly_chart(fig_camera, width="stretch")