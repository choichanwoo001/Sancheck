"""
human_detector.py

ROS-independent wrapper around:
  - YOLOv8  (person detection)
  - BotSort  (ByteTrack motion association + OSNet appearance Re-ID)

BotSort = ByteTrack association algorithm + ReID appearance model.
It satisfies the requirement of "ByteTrack tracking + OSNet Re-ID" in a
single, well-maintained library (boxmot).

Target lock-on logic
--------------------
1. auto_select_target()  — call once to lock onto the nearest/largest person
2. get_target_track()    — returns the locked track each frame
3. If the track is lost, a ReID search is triggered automatically by BotSort
   when the person re-enters the frame.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy imports — graceful error on missing packages
# ---------------------------------------------------------------------------
try:
    from ultralytics import YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False
    logger.error("ultralytics not installed.  Run: pip install ultralytics")

try:
    # boxmot v10+ exposes trackers directly; v17 changed the package structure.
    # Try the direct submodule path first, then fall back to the top-level import.
    try:
        from boxmot.trackers.botsort.botsort import BotSort
    except ImportError:
        from boxmot import BotSort  # older boxmot versions
    _BOXMOT_AVAILABLE = True
except ImportError:
    _BOXMOT_AVAILABLE = False
    logger.error("boxmot not installed.  Run: pip install boxmot")


class Track:
    """Thin wrapper around a boxmot track row for easier access."""
    __slots__ = ('x1', 'y1', 'x2', 'y2', 'id', 'conf', 'cls')

    def __init__(self, row: np.ndarray):
        self.x1, self.y1, self.x2, self.y2 = row[0], row[1], row[2], row[3]
        self.id   = int(row[4])
        self.conf = float(row[5])
        self.cls  = int(row[6])

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def area(self) -> float:
        return (self.x2 - self.x1) * (self.y2 - self.y1)

    def crop(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        x1 = max(0, int(self.x1))
        y1 = max(0, int(self.y1))
        x2 = min(w, int(self.x2))
        y2 = min(h, int(self.y2))
        return frame[y1:y2, x1:x2]


class HumanDetector:
    """
    Detects and tracks people using YOLOv8 + BotSort (ByteTrack + OSNet).

    Parameters
    ----------
    yolo_weights : str
        Path or model name for YOLOv8, e.g. 'yolov8n.pt'.
    reid_weights : str
        Path to OSNet Re-ID weights, e.g. 'osnet_x0_25_msmt17.pt'.
        BotSort will auto-download this on first run.
    device : str
        'cuda', 'cuda:0', or 'cpu'.
    conf_threshold : float
        YOLO detection confidence threshold.
    half : bool
        Use FP16 inference (requires CUDA).
    """

    def __init__(
        self,
        yolo_weights: str = 'yolov8n.pt',
        reid_weights: str = 'osnet_x0_25_msmt17.pt',
        device: str = 'cuda',
        conf_threshold: float = 0.5,
        half: bool = True,
    ) -> None:
        if not _YOLO_AVAILABLE:
            raise RuntimeError("ultralytics package is required.")
        if not _BOXMOT_AVAILABLE:
            raise RuntimeError("boxmot package is required.")

        self.conf_threshold = conf_threshold

        # boxmot은 device 인덱스('0', '1', ...)를 요구하며 'cuda' 문자열은 거부함
        if device in ('cuda', 'gpu'):
            device = '0'

        # ── YOLOv8 ─────────────────────────────────────────────────────────
        self.yolo = YOLO(yolo_weights)

        # ── BotSort tracker (ByteTrack assoc + OSNet Re-ID) ─────────────────
        self.tracker = BotSort(
            reid_weights=Path(reid_weights),
            device=device,
            half=half,
        )

        # ── Target lock-on state ────────────────────────────────────────────
        self.target_id: Optional[int] = None
        self._no_target_frames: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, frame_bgr: np.ndarray) -> list[Track]:
        """
        Run detection + tracking on one frame.

        Returns list of Track objects for ALL detected people.
        """
        results = self.yolo(
            frame_bgr,
            classes=[0],          # 0 = person
            conf=self.conf_threshold,
            verbose=False,
        )

        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            # Feed empty array so tracker can age-out lost tracks
            self.tracker.update(np.empty((0, 6)), frame_bgr)
            return []

        # Build N×6 array: [x1, y1, x2, y2, conf, cls]
        xyxy = boxes.xyxy.cpu().numpy()
        conf = boxes.conf.cpu().numpy().reshape(-1, 1)
        cls  = boxes.cls.cpu().numpy().reshape(-1, 1)
        dets = np.hstack([xyxy, conf, cls])

        raw_tracks = self.tracker.update(dets, frame_bgr)  # M×8+
        if raw_tracks is None or len(raw_tracks) == 0:
            return []

        return [Track(row) for row in raw_tracks]

    def auto_select_target(
        self,
        tracks: list[Track],
        frame_width: int,
        strategy: str = 'nearest_center',
    ) -> Optional[int]:
        """
        Lock onto a target person.

        Strategies
        ----------
        'nearest_center' : person whose bbox center is closest to frame center
        'largest'        : person with the largest bounding-box area
        """
        if not tracks:
            return None

        frame_cx = frame_width / 2.0

        if strategy == 'largest':
            best = max(tracks, key=lambda t: t.area)
        else:  # nearest_center
            best = min(tracks, key=lambda t: abs(t.cx - frame_cx))

        self.target_id = best.id
        self._no_target_frames = 0
        logger.info(f"[HumanDetector] Target locked: track_id={self.target_id}")
        return self.target_id

    def get_target_track(self, tracks: list[Track]) -> Optional[Track]:
        """Return the locked-on target track, or None if not visible."""
        if self.target_id is None:
            return None
        for t in tracks:
            if t.id == self.target_id:
                self._no_target_frames = 0
                return t
        self._no_target_frames += 1
        return None

    def release_target(self) -> None:
        self.target_id = None
        self._no_target_frames = 0

    @property
    def is_target_locked(self) -> bool:
        return self.target_id is not None

    @property
    def frames_without_target(self) -> int:
        return self._no_target_frames

    # ------------------------------------------------------------------
    # Visualization helper
    # ------------------------------------------------------------------

    def draw_tracks(
        self,
        frame_bgr: np.ndarray,
        tracks: list[Track],
        target_track: Optional[Track] = None,
    ) -> np.ndarray:
        """Draw bounding boxes + IDs.  Target person highlighted in green."""
        vis = frame_bgr.copy()
        for t in tracks:
            is_target = (target_track is not None and t.id == target_track.id)
            color = (0, 255, 0) if is_target else (0, 165, 255)
            thickness = 3 if is_target else 2
            cv2.rectangle(vis,
                          (int(t.x1), int(t.y1)),
                          (int(t.x2), int(t.y2)),
                          color, thickness)
            label = f"ID:{t.id} {t.conf:.2f}"
            if is_target:
                label = f"[TARGET] {label}"
            cv2.putText(vis, label,
                        (int(t.x1), int(t.y1) - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        return vis
