# Object Detection and Production Monitoring

A local computer-vision system that detects objects from an RTSP camera
stream **or an uploaded recorded video**, tracks them with YOLO ByteTrack,
counts each bag as its center crosses a production line, records every
crossing as a **production event**, and presents live status and analytics in
a Streamlit dashboard.

When the dashboard starts, the user chooses the **Video Source** in the
sidebar:

- **Connect an RTSP Camera** – live detection from the RTSP stream (pipeline
  runs in `app.py`; the dashboard monitors it).
- **Upload a Recorded Video** – the uploaded file is processed by the
  *exact same* detection / verification pipeline (YOLO → ByteTrack →
  counting line → production events), with all events tagged under the
  dedicated Camera ID `CAM_VIDEO`.

The project follows a clean separation of concerns, using a `src/` layout:

- **`src/core/`** – pure domain logic (no UI, no direct persistence).
- **`src/database/`** – the dedicated, clearly-visible persistence layer.
- **`src/service/`** – application orchestration that wires core + database + logging.
- **`src/api/`** – FastAPI REST endpoint layer exposing events, status, and reports over HTTP.
- **`config/`** – single source of truth for settings (overridable via `.env`), kept outside `src/`.
- **`src/utils/`** – cross-cutting helpers (logging setup).
- **`app.py` / `dashboard.py`** – thin entrypoints at the project root.

All application/source code lives under `src/`; configuration, model weights,
data, and logs stay outside it.

---

## Project layout

```text
bag_detection_system/
├── .env                  # local/environment config (git-ignored, see .env.example)
├
├── app.py                # detection pipeline + REST API entrypoint (root, RTSP cameras)
├── dashboard.py          # Streamlit dashboard entrypoint (root): source selection
│                         #   (RTSP Camera / Upload Recorded Video) + monitoring
│
├── config/               # CONFIGURATION (outside src)
│   ├── __init__.py       # loads .env, re-exports settings
│   ├── loader.py         # python-dotenv loader
│   └── settings.py       # paths, cameras, thresholds, shifts, logging config
│
├── src/                  # ALL APPLICATION/SOURCE CODE
│   ├── core/             # DOMAIN LOGIC (UI- and storage-agnostic)
│   │   ├── stream/
│   │   │   ├── capture.py    # open RTSP capture handle (also opens video files)
│   │   │   └── worker.py     # per-camera threaded processing loop
│   │   │                     #   run_camera_worker          -> live RTSP stream
│   │   │                     #   run_uploaded_video_worker  -> uploaded video
│   │   │                     #     (both share the SAME detection/verification
│   │   │                     #      pipeline: YOLODetector, TrackManager,
│   │   │                     #      production sink, visualization, status)
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
│   ├── api/              # REST API LAYER (FastAPI)
│   │   ├── __init__.py
│   │   ├── endpoint.py     # FastAPI app + routes (events, status, reports)
│   │   ├── schemas.py      # Pydantic request/response schemas (API contract)
│   │   └── dependencies.py # FastAPI dependency wiring (shared repositories)
│   └── utils/
│       └── logging_setup.py  # application.log, api.log, camera.log, detection.log
│
├── data/                 # generated CSV, status JSON, latest annotated frame,
│   │                     #   and uploaded videos (data/uploads/) (outside src)
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
 stream worker (src/core/stream)                 uploaded video (dashboard.py)
   run_camera_worker (RTSP)                        run_uploaded_video_worker
         |  reads frames                                  |  reads frames
         +----------------+-------------------------------+
                          v
 YOLODetector (src/core/detection) ──normalized detections──► TrackManager (src/core/counting)
                                                                  │
                                             counts line crossings, issues ProductionEvent
                                                                  ▼
                                         production_sink → EventRepository (src/database/)
                                                                  │ persists
                                                                  ▼
                              data/production_events.csv  ←── read by dashboard
```

Both the live RTSP stream and an uploaded recorded video go through the
**exact same** pipeline (`YOLODetector` → `TrackManager` line-crossing
verification → `production_sink` → `EventRepository`). The only differences:
uploaded videos are read from a local file instead of the RTSP socket, they run
in a dashboard background thread, they stop at end-of-file (no reconnection
loop), and their events/status are tagged with Camera ID `CAM_VIDEO`.

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

This starts the detection pipeline **and** the REST API together
(API on `API_HOST:API_PORT`, interactive docs at `/docs`).

In a second terminal with the same environment activated, start the dashboard:

```powershell
streamlit run dashboard.py
```

Streamlit prints the local URL, typically `http://localhost:8501`.

Press `Ctrl+C` in the pipeline terminal to stop it; the pipeline marks active
cameras offline.

### Using an uploaded video (no RTSP camera required)

The dashboard can also process a recorded video **without** running
`app.py` — the dashboard spins up the same pipeline itself:

```powershell
streamlit run dashboard.py
```

1. In the sidebar under **Video Source**, choose **Upload a Recorded Video**.
2. Upload a video file (`mp4`, `avi`, `mov`, `mkv`, `wmv`). It is saved to
   `data/uploads/`.
3. Click **▶ Start Processing** — the video runs through the same
   detection → tracking → counting-line → production-event pipeline in a
   background thread (Stop Processing can interrupt it early).
4. The processed annotated frame and production events appear on the page and
   in the usual `Production Events` / `Reports & Analytics` pages.

> **Note:** selecting *Upload a Recorded Video* does **not** stop the RTSP
> camera. Both run independently with separate Camera IDs (`CAM-01` for RTSP,
> `CAM_VIDEO` for uploads). If both run at the same time on CPU, each YOLO
> instance shares the processor, so expect lower FPS in the live stream while
> a video is being processed.

---

## Dashboard pages

When the dashboard starts, the sidebar shows a **Video Source** selector:

- **Connect an RTSP Camera** – the original live monitor (unchanged).
- **Upload a Recorded Video** – upload UI + live processing feedback, using the
  same pipeline as RTSP (see *Using an uploaded video* above).

The pages below are shared by both sources:

- **Live Monitor** – configured/online camera counts, active bags, bags produced
  today, total production, per-camera status (FPS, counts, heartbeat), the latest
  processed frame, and recent production events. Optional auto-refresh.
  In *Upload* mode this page shows the upload UI, the latest annotated frame
  from the video, and recent events (including `CAM_VIDEO` events).
- **Production Events** – searchable/filterable event history (period, camera,
  direction, BagNo) with CSV download. Filter by `Camera ID` to separate RTSP
  (`CAM-01`) from uploaded-video (`CAM_VIDEO`) events.
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
  production count, FPS, heartbeat, message) plus a global `summary`. RTSP
  cameras appear under their configured `camera_id` (e.g. `CAM-01`);
  uploaded-video processing appears under `CAM_VIDEO`.
- `data/live_frame.jpg` – the latest annotated frame.
- `data/uploads/` – uploaded video files saved by the dashboard.

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
- Uploaded-video processing runs the same pipeline but reads from a local
  file: it stops at end-of-video (or when **Stop Processing** is clicked) and
  has no reconnection loop. All its events/status use Camera ID `CAM_VIDEO`.
- The RTSP camera and uploaded-video processing are independent: selecting
  *Upload a Recorded Video* in the dashboard does not stop the RTSP camera.
  However, running both simultaneously on CPU shares the processor between
  two YOLO instances, which can reduce live-stream FPS.

## Troubleshooting

| Symptom | Check |
|---|---|
| Model fails to load | Confirm `model/bag.pt` exists and matches the installed `ultralytics` version |
| Camera remains offline | Verify `RTSP_URL` / camera credentials / network reachability / codec support |
| Dashboard has no data | Start `python app.py` first; wait for `data/status.json` and events in `data/production_events.csv` |
| No bags counted | Check `CONFIDENCE_THRESHOLD`, `LINE_HEIGHT_RATIO`; counts require a line crossing |
| `config`/`core` import errors | Run `python app.py` / `streamlit run dashboard.py` from the project root; those entrypoints bootstrap both the root (for `config`) and `src/` (for `core`,`database`,`service`,`utils`) onto `sys.path` |