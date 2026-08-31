# Bag Detection and Production Monitoring

A local computer-vision system that detects cement bags from RTSP camera
streams, tracks them with YOLO ByteTrack, counts each bag as its center
crosses a production line, records every crossing as a **production event**, and
presents live status and analytics in a Streamlit dashboard.

The project follows a clean separation of concerns, using a `src/` layout:

- **`src/core/`** – pure domain logic (no UI, no direct persistence).
- **`src/database/`** – the dedicated, clearly-visible persistence layer.
- **`src/service/`** – application orchestration that wires core + database + logging.
- **`config/`** – single source of truth for settings (overridable via `.env`), kept outside `src/`.
- **`src/utils/`** – cross-cutting helpers (logging setup).
- **`app.py` / `dashboard.py` / `main.py`** – thin entrypoints at the project root.

All application/source code lives under `src/`; configuration, model weights,
data, and logs stay outside it.

---

## Project layout

```text
bag_detection_system/
├── .env                  # local/environment config (git-ignored, see .env.example)
├── .env.example          # documented template for .env
├── app.py                # detection pipeline entrypoint (root)
├── dashboard.py          # Streamlit dashboard entrypoint (root)
├── main.py               # launcher (delegates to app.main)
│
├── config/               # CONFIGURATION (outside src)
│   ├── __init__.py       # loads .env, re-exports settings
│   ├── loader.py         # python-dotenv loader
│   └── settings.py       # paths, cameras, thresholds, shifts, logging config
│
├── src/                  # ALL APPLICATION/SOURCE CODE
│   ├── core/             # DOMAIN LOGIC (UI- and storage-agnostic)
│   │   ├── stream/
│   │   │   ├── capture.py    # open RTSP capture handle
│   │   │   └── worker.py     # per-camera threaded processing loop
│   │   ├── detection/
│   │   │   └── yolo_detector.py  # YOLO + ByteTrack wrapper -> normalized detections
│   │   ├── counting/
│   │   │   └── track_manager.py  # line-crossing counting + bag numbering
│   │   ├── production/
│   │   │   ├── shifts.py     # current-shift resolution
│   │   │   └── events.py     # ProductionEvent dataclass + CSV columns
│   │   └── visualization.py  # overlay drawing + live-frame saving
│   ├── database/         # PERSISTENCE LAYER (swap backends here)
│   │   ├── connection.py     # DatabaseConnection: selects/owns the backend
│   │   ├── repository.py     # EventRepository / StatusRepository interfaces
│   │   └── csv_repository.py # default CSV + JSON implementation
│   ├── service/          # ORCHESTRATION
│   │   ├── detection_service.py  # starts/stops camera workers
│   │   └── status_service.py     # merges per-camera status + global summary
│   └── utils/
│       └── logging_setup.py  # application.log, camera.log, detection.log
│
├── data/                 # generated CSV, status JSON, latest annotated frame (outside src)
├── model/
│   └── bag.pt            # required custom YOLO weights (add locally, outside src)
├── logs/                 # runtime logs (application, camera, detection) (outside src)
├── video_data/           # optional local video assets
├── requirements.txt      # pip dependencies
└── pyproject.toml        # project metadata and uv dependencies
```

---

## How the layers connect

```text
 stream worker (src/core/stream)
        │  reads frames
        ▼
 YOLODetector (src/core/detection) ──normalized detections──► TrackManager (src/core/counting)
                                                                  │
                                             counts line crossings, issues ProductionEvent
                                                                  ▼
                                         production_sink → EventRepository (src/database/)
                                                                  │ persists
                                                                  ▼
                              data/production_events.csv  ←── read by dashboard
```

- **Core** modules never call `database` or Streamlit directly. `TrackManager`
  emits a `ProductionEvent` through an injected *sink*; the worker wires that
  sink to the event repository + logging.
- **Service** (`DetectionService`, `StatusService`) owns wiring and workflow.
- **Dashboard** reads events/status only through the repository interfaces.

---

## Requirements

- Python 3.12 or newer
- A custom bag-detection model at `model/bag.pt`
- At least one reachable RTSP camera stream configured in `config/settings.py`
  (or via `RTSP_URL` in `.env`)

The current configuration runs on CPU (`DEVICE = "cpu"`). To use an NVIDIA GPU,
set `DEVICE = cuda` in `.env`.

---

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Or, if you use `uv`:

```powershell
uv sync
```

Then, optionally, prepare your local environment:

```powershell
Copy-Item .env.example .env
# edit .env with your RTSP URL / overrides
```

---

## Environment configuration (`.env`)

Create a `.env` file at the project root (a documented template is provided in
[`.env.example`](.env.example)). It is loaded at startup by `config/loader.py`
and is **not** committed to version control.

Key variables (all optional – sane defaults exist in `config/settings.py`):

| Variable | Default | Purpose |
|---|---:|---|
| `RTSP_URL` | `rtsp://192.0.0.0:1945/` | Camera stream |
| `CAMERA_ID` | `CAM-01` | Camera identifier |
| `LINE_ID` | `LINE-01` | Production line identifier |
| `CONFIDENCE_THRESHOLD` | `0.50` | Minimum YOLO confidence |
| `IOU_THRESHOLD` | `0.50` | YOLO tracking IoU threshold |
| `TRACK_TIMEOUT` | `3.0` s | Timeout before an unseen track is closed |
| `FRAME_SKIP` | `1` | Process every Nth frame |
| `LINE_HEIGHT_RATIO` | `0.60` | Counting-line position as fraction of height |
| `DEVICE` | `cpu` | `cpu` or `cuda` |
| `RECONNECT_DELAY` | `5` s | Delay before retrying an unavailable stream |
| `MAX_FRAME_FAILURES` | `30` | Frame-read failures before reconnecting |
| `DEFAULT_PRODUCTION_BATCH` | `BATCH-20260831-001` | Active production batch |
| `BAG_START_NUMBER` | `1` | First bag number for the counter |
| `EVENT_REPOSITORY` | `csv` | Persistence backend (see below) |
| `LOG_LEVEL` | `INFO` | Log verbosity |

To add more cameras, edit the `CAMERAS` list in `config/settings.py` (each entry
needs a unique `camera_id`, a `line_id`, an `rtsp_url`, and `enabled: True`).
---

## Database / persistence layer

Persistence lives in its own dedicated `database/` package instead of being
hidden inside the application code.

- `database/repository.py` defines two interfaces:
  - `EventRepository` – store/read **production events**.
  - `StatusRepository` – store/read **runtime status** (heartbeat).
- `database/csv_repository.py` is the default implementation: events are stored
  as CSV and status as JSON. Writes are thread-safe and atomic (temp-file +
  rename) so multiple camera workers cannot corrupt the files.
- `database/connection.py` exposes `DatabaseConnection`, the single entry point
  that owns the backend and returns the concrete repositories.

### Switching to a real database later

To move from files to, say, SQLite/PostgreSQL:

1. Add a new class (e.g. `SqlRepository`) implementing `EventRepository` and
   `StatusRepository` under `database/`.
2. Register it in `DatabaseConnection._build_repository()` keyed by the new
   `EVENT_REPOSITORY` value (and optionally provide `DATABASE_URL`).
3. Nothing in `core/`, `service/`, or `dashboard.py` changes.

---

## Logging

Three log files are written under `logs/` (configured in `utils/logging_setup.py`):

| File | Captures |
|---|---|
| `application.log` | System lifecycle, service startup/shutdown, unexpected errors |
| `camera.log` | Stream open/close, reconnection, frame-failure, per-camera lifecycle |
| `detection.log` | Each production event (timestamps, line, detection ID, bag no, shift, batch) |

Logs are rotated (size-based) and their rotation limits can be tuned via
`LOG_MAX_BYTES` / `LOG_BACKUP_COUNT` in `.env`.

---

## Run the system

Start the detection pipeline first:

```powershell
python app.py
```

(`python main.py` is an alias that runs the same pipeline.)

In a second terminal with the same environment activated, start the dashboard:

```powershell
streamlit run dashboard.py
```

Streamlit prints the local URL, typically `http://localhost:8501`.

Press `Ctrl+C` in the pipeline terminal to stop it; the pipeline marks active
cameras offline.

---

## Dashboard pages

- **Live Monitor** – configured/online camera counts, active bags, bags produced
  today, total production, per-camera status (FPS, counts, heartbeat), the latest
  processed frame, and recent production events. Optional auto-refresh.
- **Production Events** – searchable/filterable event history (period, camera,
  direction, BagNo) with CSV download.
- **Reports & Analytics** – period-filtered totals, daily production bars,
  production by shift, and production by camera.

---

## Generated data

The pipeline creates these outputs on demand:

- `data/production_events.csv` – each counted bag crossing:

  | Column | Description |
  |---|---|
  | `Timestamp` | Time the crossing was recorded |
  | `Line ID` | Production line |
  | `Camera ID` | Source camera |
  | `Detection ID` | ByteTrack track ID |
  | `Direction` | `DOWN` or `UP` |
  | `BagNo` | Production sequence number |
  | `Shift` | Shift at the time of crossing |
  | `Production Batch` | Active batch |

- `data/status.json` – per-camera `cameras` object (online, active count,
  production count, FPS, heartbeat, message) plus a global `summary`.
- `data/live_frame.jpg` – the latest annotated frame.

---

## Operational notes

- The model must expose bags as class ID `0`, because the detector runs YOLO
  with `classes=[0]`.
- `BagNo` is an independent per-camera production sequence; `Detection ID` is the
  ByteTrack track ID (IDs may be reused after a tracker restart).
- Counting records a bag **once** when its tracked center crosses the configured
  horizontal line.
- Reconnection behaviour: if a stream cannot be opened or repeatedly fails to
  return frames, the camera is marked offline and the worker retries after
  `RECONNECT_DELAY`.

## Troubleshooting

| Symptom | Check |
|---|---|
| Model fails to load | Confirm `model/bag.pt` exists and matches the installed `ultralytics` version |
| Camera remains offline | Verify `RTSP_URL` / camera credentials / network reachability / codec support |
| Dashboard has no data | Start `python app.py` first; wait for `data/status.json` and events in `data/production_events.csv` |
| No bags counted | Check `CONFIDENCE_THRESHOLD`, `LINE_HEIGHT_RATIO`; counts require a line crossing |
| `config`/`core` import errors | Run `python app.py` / `streamlit run dashboard.py` from the project root; those entrypoints bootstrap both the root (for `config`) and `src/` (for `core`,`database`,`service`,`utils`) onto `sys.path` |