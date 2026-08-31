from __future__ import annotations

from pathlib import Path

from ultralytics import YOLO

from config.settings import (
    CONFIDENCE_THRESHOLD,
    DEVICE,
    IOU_THRESHOLD,
)

# The model must expose bags as class ID 0.
BAG_CLASS = 0


class YOLODetector:
    """
    Thin wrapper around the Ultralytics YOLO model for bag detection + tracking.

    ``track()`` returns a list of normalized detection dictionaries:

        {track_id, confidence, center_x, center_y, box}
    """

    def __init__(
        self,
        model_path: str | Path,
        confidence: float = CONFIDENCE_THRESHOLD,
        iou: float = IOU_THRESHOLD,
        device: str = DEVICE,
        tracker: str = "bytetrack.yaml",
    ):
        self.model_path = Path(model_path)
        self.confidence = confidence
        self.iou = iou
        self.device = device
        self.tracker = tracker
        self.model: YOLO | None = None

    def load(self) -> "YOLODetector":
        """Load the YOLO weights from disk. Raises on failure."""
        self.model = YOLO(str(self.model_path))
        return self

    def track(self, frame):
        """Run ByteTrack-backed detection on a frame and return detections."""
        if self.model is None:
            raise RuntimeError("YOLODetector.track() called before load().")

        results = self.model.track(
            frame,
            conf=self.confidence,
            iou=self.iou,
            tracker=self.tracker,
            persist=True,
            verbose=False,
            device=self.device,
            classes=[BAG_CLASS],
        )

        detections: list[dict] = []

        if results and results[0].boxes is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            confs = results[0].boxes.conf.cpu().numpy()
            ids = results[0].boxes.id

            if ids is not None:
                ids = ids.cpu().numpy().astype(int)

                for box, tid, conf in zip(boxes, ids, confs):
                    x1, y1, x2, y2 = box

                    detections.append(
                        {
                            "track_id": int(tid),
                            "confidence": float(conf),
                            "center_x": float((x1 + x2) / 2),
                            "center_y": float((y1 + y2) / 2),
                            "box": box,
                        }
                    )

        return detections