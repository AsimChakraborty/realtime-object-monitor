from __future__ import annotations

import time
from datetime import datetime
from logging import Logger
from dataclasses import dataclass, field

from config.settings import (
    DEFAULT_PRODUCTION_BATCH,
    BAG_START_NUMBER,
    FRAME_SKIP,
    LINE_HEIGHT_RATIO,
    LIVE_FRAME_PATH,
    MAX_FRAME_FAILURES,
    RECONNECT_DELAY,
    STATUS_UPDATE_INTERVAL,
)
from core.counting.track_manager import ProductionSink, TrackManager
from core.detection.yolo_detector import YOLODetector
from core.production.events import ProductionEvent
from core.stream.capture import open_capture
from core.visualization import draw_detection, draw_overlay, save_live_frame


@dataclass
class WorkerLoggers:
    """Loggers bound to the three dedicated log files."""
    app: Logger
    camera: Logger
    detection: Logger


@dataclass
class CameraContext:
    """Everything a single camera worker needs to run."""
    camera_info: dict
    detector: YOLODetector
    status_service: object  # service.status_service.StatusService
    event_repository: object  # database.repository.EventRepository
    loggers: WorkerLoggers

    # Resolved per-camera settings.
    camera_id: str = field(init=False)
    line_id: str = field(init=False)
    rtsp_url: str = field(init=False)
    reconnect_delay: int = field(init=False)
    production_batch: str = field(init=False)
    bag_start_number: int = field(init=False)

    def __post_init__(self) -> None:
        info = self.camera_info
        self.camera_id = info["camera_id"]
        self.line_id = info["line_id"]
        self.rtsp_url = info["rtsp_url"]
        self.reconnect_delay = info.get("reconnect_delay", RECONNECT_DELAY)
        self.production_batch = info.get(
            "production_batch", DEFAULT_PRODUCTION_BATCH
        )
        self.bag_start_number = info.get("bag_start_number", BAG_START_NUMBER)


def build_production_sink(ctx: CameraContext) -> ProductionSink:
    """Return a callable that persists a ProductionEvent and logs it."""

    def sink(event: ProductionEvent) -> None:
        ctx.event_repository.append_event(event)
        ctx.loggers.detection.info(
            "[%s] PRODUCTION EVENT | Timestamp=%s | Line=%s | DetectionID=%s | "
            "Direction=%s | BagNo=%s | Shift=%s | Batch=%s",
            ctx.camera_id,
            event.timestamp,
            event.line_id,
            event.detection_id,
            event.direction,
            event.bag_no,
            event.shift,
            event.production_batch,
        )

    return sink


def run_camera_worker(ctx: CameraContext) -> None:
    """
    Run the processing loop for one camera.

    This blocks forever: read a frame -> detect + track -> count line
    crossings -> draw overlay -> update status/live frame. On stream failure it
    reconnects after ``RECONNECT_DELAY`` seconds. Intended to run in a thread.
    """
    cam_log = ctx.loggers.camera
    app_log = ctx.loggers.app

    cam_log.info(
        "[%s] Starting | Line=%s | Batch=%s",
        ctx.camera_id,
        ctx.line_id,
        ctx.production_batch,
    )

    while True:
        cap = open_capture(ctx.rtsp_url)

        if cap is None or not cap.isOpened():
            cam_log.warning(
                "[%s] Camera offline. Retrying in %ss.",
                ctx.camera_id,
                ctx.reconnect_delay,
            )
            ctx.status_service.write_status(
                camera_id=ctx.camera_id,
                line_id=ctx.line_id,
                online=False,
                current_count=0,
                message="Offline - Reconnecting",
            )
            time.sleep(ctx.reconnect_delay)
            continue

        ret, first_frame = cap.read()

        if not ret or first_frame is None:
            cap.release()
            cam_log.warning("[%s] Empty first frame. Reconnecting.", ctx.camera_id)
            time.sleep(ctx.reconnect_delay)
            continue

        frame_height = first_frame.shape[0]
        line_y = int(frame_height * LINE_HEIGHT_RATIO)

        tracker = TrackManager(
            line_id=ctx.line_id,
            camera_id=ctx.camera_id,
            line_y=line_y,
            bag_start_number=ctx.bag_start_number,
            production_batch=ctx.production_batch,
            production_sink=build_production_sink(ctx),
        )

        frame_count = 0
        frame_failures = 0
        fps_counter = 0
        fps_start = time.time()
        current_fps = 0.0
        last_status = time.time()
        last_live_frame = time.time()
        last_detection = ""

        ctx.status_service.write_status(
            camera_id=ctx.camera_id,
            line_id=ctx.line_id,
            online=True,
            current_count=0,
            message="Connected - Starting detection",
        )

        try:
            while True:
                ret, frame = cap.read()

                if not ret or frame is None:
                    frame_failures += 1

                    if frame_failures >= MAX_FRAME_FAILURES:
                        cam_log.warning(
                            "[%s] Stream failure. Reconnecting...", ctx.camera_id
                        )
                        break

                    time.sleep(0.05)
                    continue

                frame_failures = 0
                frame_count += 1

                if FRAME_SKIP > 1 and frame_count % FRAME_SKIP != 0:
                    continue

                try:
                    detections = ctx.detector.track(frame)
                except Exception as exc:
                    cam_log.error("[%s] YOLO error: %s", ctx.camera_id, exc)
                    continue

                current_count = tracker.update(detections, time.time())

                for detection in detections:
                    draw_detection(
                        frame,
                        detection["box"],
                        detection["track_id"],
                        detection["confidence"],
                    )

                if detections:
                    last_detection = datetime.now().isoformat(timespec="seconds")

                draw_overlay(
                    frame,
                    line_y,
                    ctx.camera_id,
                    ctx.line_id,
                    tracker.production_count,
                )

                fps_counter += 1
                elapsed = time.time() - fps_start

                if elapsed >= 1.0:
                    current_fps = fps_counter / elapsed
                    fps_counter = 0
                    fps_start = time.time()

                now_time = time.time()

                if now_time - last_live_frame >= 1.0:
                    save_live_frame(frame, LIVE_FRAME_PATH)
                    last_live_frame = now_time

                if now_time - last_status >= STATUS_UPDATE_INTERVAL:
                    ctx.status_service.write_status(
                        camera_id=ctx.camera_id,
                        line_id=ctx.line_id,
                        online=True,
                        current_count=current_count,
                        fps=current_fps,
                        message="Running",
                        total_detections=tracker.total_detections,
                        production_count=tracker.production_count,
                        last_detection=last_detection,
                    )
                    last_status = now_time

        except Exception as exc:
            app_log.exception("[%s] Unexpected error: %s", ctx.camera_id, exc)

        finally:
            cap.release()

        ctx.status_service.write_status(
            camera_id=ctx.camera_id,
            line_id=ctx.line_id,
            online=False,
            current_count=0,
            message="Offline - Reconnecting",
            total_detections=tracker.total_detections,
            production_count=tracker.production_count,
            last_detection=last_detection,
        )

        cam_log.info(
            "[%s] Sleeping %ss before reconnect.", ctx.camera_id, ctx.reconnect_delay
        )
        time.sleep(ctx.reconnect_delay)


# ============================================================
# UPLOADED VIDEO PROCESSING (new - RTSP worker above is unchanged)
# ------------------------------------------------------------
# The function below processes an UPLOADED RECORDED VIDEO using
# EXACTLY the same detection and verification pipeline that
# run_camera_worker() uses for a live RTSP stream. Parts reused:
#
#   * open_capture()              -> same capture handle (works for
#                                    a local video path too)
#   * LINE_HEIGHT_RATIO           -> same counting-line position
#   * TrackManager(...)           -> same ByteTrack tracking +
#                                    line-crossing verification
#   * build_production_sink(ctx)  -> same production-event
#                                    persistence (event repository
#                                    + detection log)
#   * ctx.detector.track(frame)   -> same YOLO detection + tracking
#   * draw_detection / draw_overlay / save_live_frame
#                                 -> same annotated output
#   * status_service.write_status -> same status reporting
#
# Differences from the RTSP worker: frames come from the uploaded
# file instead of the RTSP socket, there is no reconnect loop, and
# processing stops when the video ends (or ``stop_event`` is set).
# ============================================================


def run_uploaded_video_worker(
    ctx: CameraContext,
    video_path: str,
    stop_event=None,
) -> None:
    """
    Process an uploaded recorded video with the same RTSP pipeline.

    Reads every frame from ``video_path`` and feeds it through the
    identical detection -> tracking -> counting-line verification ->
    production-event persistence flow used by ``run_camera_worker``.
    Intended to run in a background thread (e.g. started by the
    Streamlit dashboard when the user uploads a video).
    """
    cam_log = ctx.loggers.camera
    app_log = ctx.loggers.app

    cam_log.info(
        "[%s] Processing uploaded video: %s",
        ctx.camera_id,
        video_path,
    )

    ctx.status_service.write_status(
        camera_id=ctx.camera_id,
        line_id=ctx.line_id,
        online=True,
        current_count=0,
        message="Processing uploaded video",
    )

    # ---- Same capture helper used for the RTSP stream ----
    cap = open_capture(video_path)

    if cap is None or not cap.isOpened():
        cam_log.error(
            "[%s] Could not open uploaded video: %s",
            ctx.camera_id,
            video_path,
        )
        ctx.status_service.write_status(
            camera_id=ctx.camera_id,
            line_id=ctx.line_id,
            online=False,
            current_count=0,
            message="Failed to open uploaded video",
        )
        return

    ret, first_frame = cap.read()

    if not ret or first_frame is None:
        cap.release()
        cam_log.error(
            "[%s] Uploaded video has no readable frames: %s",
            ctx.camera_id,
            video_path,
        )
        ctx.status_service.write_status(
            camera_id=ctx.camera_id,
            line_id=ctx.line_id,
            online=False,
            current_count=0,
            message="Uploaded video has no readable frames",
        )
        return

    # ---- Same counting line position as RTSP worker ----
    frame_height = first_frame.shape[0]
    line_y = int(frame_height * LINE_HEIGHT_RATIO)

    # ---- Same tracker / verifier / production-event sink as RTSP ----
    tracker = TrackManager(
        line_id=ctx.line_id,
        camera_id=ctx.camera_id,
        line_y=line_y,
        bag_start_number=ctx.bag_start_number,
        production_batch=ctx.production_batch,
        production_sink=build_production_sink(ctx),
    )

    frame_count = 0
    fps_counter = 0
    fps_start = time.time()
    current_fps = 0.0
    last_status = time.time()
    last_live_frame = time.time()
    last_detection = ""

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                cam_log.info(
                    "[%s] Upload processing stopped by user.",
                    ctx.camera_id,
                )
                break

            ret, frame = cap.read()

            # End of uploaded video -> stop (no RTSP reconnect here).
            if not ret or frame is None:
                cam_log.info(
                    "[%s] Uploaded video finished.",
                    ctx.camera_id,
                )
                break

            frame_count += 1

            # ---- Same FRAME_SKIP behavior as RTSP worker ----
            if FRAME_SKIP > 1 and frame_count % FRAME_SKIP != 0:
                continue

            # ---- Same YOLO detection + ByteTrack as RTSP ----
            try:
                detections = ctx.detector.track(frame)
            except Exception as exc:
                cam_log.error("[%s] YOLO error: %s", ctx.camera_id, exc)
                continue

            # ---- Same tracking / counting-line verification as RTSP ----
            current_count = tracker.update(detections, time.time())

            # ---- Same drawing / overlay / live-frame output as RTSP ----
            for detection in detections:
                draw_detection(
                    frame,
                    detection["box"],
                    detection["track_id"],
                    detection["confidence"],
                )

            if detections:
                last_detection = datetime.now().isoformat(timespec="seconds")

            draw_overlay(
                frame,
                line_y,
                ctx.camera_id,
                ctx.line_id,
                tracker.production_count,
            )

            fps_counter += 1
            elapsed = time.time() - fps_start

            if elapsed >= 1.0:
                current_fps = fps_counter / elapsed
                fps_counter = 0
                fps_start = time.time()

            now_time = time.time()

            if now_time - last_live_frame >= 1.0:
                save_live_frame(frame, LIVE_FRAME_PATH)
                last_live_frame = now_time

            if now_time - last_status >= STATUS_UPDATE_INTERVAL:
                ctx.status_service.write_status(
                    camera_id=ctx.camera_id,
                    line_id=ctx.line_id,
                    online=True,
                    current_count=current_count,
                    fps=current_fps,
                    message="Processing uploaded video",
                    total_detections=tracker.total_detections,
                    production_count=tracker.production_count,
                    last_detection=last_detection,
                )
                last_status = now_time

    except Exception as exc:
        app_log.exception(
            "[%s] Unexpected error while processing video: %s",
            ctx.camera_id,
            exc,
        )

    finally:
        cap.release()

    ctx.status_service.write_status(
        camera_id=ctx.camera_id,
        line_id=ctx.line_id,
        online=False,
        current_count=0,
        message="Upload processing finished",
        total_detections=tracker.total_detections,
        production_count=tracker.production_count,
        last_detection=last_detection,
    )

    cam_log.info(
        "[%s] Upload processing done | Production=%d",
        ctx.camera_id,
        tracker.production_count,
    )