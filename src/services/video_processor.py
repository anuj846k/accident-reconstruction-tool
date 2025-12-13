"""
Video Processing Service using YOLO + ByteTrack.

This module handles:
1. Downloading video from Cloudinary
2. Running YOLO detection on each frame
3. Using ByteTrack for object tracking
4. Calculating real-world speeds using homography calibration
5. Saving detections to database
"""

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional, Callable, List
from dataclasses import dataclass, field

import cv2
import numpy as np
import requests

from src.services.distance_estimator import DistanceEstimator

logger = logging.getLogger(__name__)


@dataclass
class ProcessingConfig:
    """Configuration for video processing.
    
    Based on optimal settings from accident-analysis-hackathon project.
    """
    model_path: str = "yolov8s.pt"
    conf_threshold: float = 0.2  # Lower = detect more vehicles
    iou_threshold: float = 0.3  # Lower = less aggressive NMS
    # COCO classes: 2=car, 3=motorcycle, 5=bus, 7=truck
    vehicle_classes: list = None
    # ByteTrack parameters (proven optimal from original project)
    minimum_consecutive_frames: int = 2
    track_activation_threshold: float = 0.1  # Very low = easy to start tracking
    lost_track_buffer: int = 100  # Keep lost tracks longer
    minimum_matching_threshold: float = 0.95  # High = strict reconnection
    
    def __post_init__(self):
        if self.vehicle_classes is None:
            self.vehicle_classes = [2, 3, 5, 7]


@dataclass
class DetectionResult:
    """Result of processing a single frame."""
    frame_idx: int
    timestamp_ms: int
    track_id: Optional[int]
    class_name: str
    class_id: int
    confidence: float
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    center_x: float
    center_y: float
    # Calibration-based fields (populated when homography is available)
    speed_mph: Optional[float] = None
    world_x: Optional[float] = None  # GPS longitude
    world_y: Optional[float] = None  # GPS latitude


class VideoProcessor:
    """
    Video processor using YOLO for detection and ByteTrack for tracking.
    Supports homography calibration for real-world speed calculation.
    """
    
    def __init__(
        self, 
        config: Optional[ProcessingConfig] = None,
        homography_matrix: Optional[List[List[float]]] = None
    ):
        """
        Initialize the video processor.
        
        Args:
            config: Processing configuration
            homography_matrix: Optional 3x3 homography matrix for coordinate transformation.
                              When provided, enables speed calculation in mph and GPS coordinates.
        """
        self.config = config or ProcessingConfig()
        self._model = None
        self._tracker = None
        self._initialized = False
        
        # Initialize distance estimator if homography is provided
        self._distance_estimator: Optional[DistanceEstimator] = None
        if homography_matrix:
            try:
                self._distance_estimator = DistanceEstimator(homography_matrix)
                logger.info("Homography calibration enabled - will calculate real-world speeds")
            except Exception as e:
                logger.warning(f"Failed to initialize distance estimator: {e}")
                self._distance_estimator = None
    
    def _initialize(self, fps: float = 30.0):
        """Lazy initialization of YOLO and ByteTrack."""
        if self._initialized:
            return
            
        try:
            from ultralytics import YOLO
            import supervision as sv
            
            logger.info(f"Loading YOLO model: {self.config.model_path}")
            self._model = YOLO(self.config.model_path)
            
            logger.info("Initializing ByteTrack tracker")
            self._tracker = sv.ByteTrack(
                frame_rate=int(fps),
                track_activation_threshold=self.config.track_activation_threshold,
                lost_track_buffer=self.config.lost_track_buffer,
                minimum_matching_threshold=self.config.minimum_matching_threshold,
                minimum_consecutive_frames=self.config.minimum_consecutive_frames,
            )
            
            self._initialized = True
            logger.info("Video processor initialized successfully")
            
        except ImportError as e:
            logger.error(f"Failed to import required libraries: {e}")
            raise RuntimeError(
                "Missing required libraries. Install with: pip install ultralytics supervision"
            )
    
    def download_video(self, video_url: str) -> Path:
        """
        Download video from URL to temporary file.
        
        Args:
            video_url: URL of the video (Cloudinary)
            
        Returns:
            Path to downloaded video file
        """
        logger.info(f"Downloading video from: {video_url[:50]}...")
        
        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(
            suffix=".mp4",
            delete=False
        )
        temp_path = Path(temp_file.name)
        temp_file.close()
        
        # Download video
        response = requests.get(video_url, stream=True)
        response.raise_for_status()
        
        with open(temp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"Video downloaded to: {temp_path}")
        return temp_path
    
    def get_video_info(self, video_path: Path) -> dict[str, Any]:
        """
        Extract video information.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dictionary with video properties
        """
        cap = cv2.VideoCapture(str(video_path))
        
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {video_path}")
        
        info = {
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": float(cap.get(cv2.CAP_PROP_FPS)) or 30.0,
            "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "duration_sec": 0.0,
        }
        
        if info["fps"] > 0:
            info["duration_sec"] = info["total_frames"] / info["fps"]
        
        cap.release()
        
        logger.info(
            f"Video info: {info['width']}x{info['height']} @ {info['fps']:.1f}fps, "
            f"{info['total_frames']} frames, {info['duration_sec']:.2f}s"
        )
        
        return info
    
    def process_video(
        self,
        video_path: Path,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> list[DetectionResult]:
        """
        Process video and extract detections.
        
        Args:
            video_path: Path to video file
            progress_callback: Optional callback for progress updates (current, total, message)
            
        Returns:
            List of detection results
        """
        import supervision as sv
        
        # Get video info first
        video_info = self.get_video_info(video_path)
        fps = video_info["fps"]
        total_frames = video_info["total_frames"]
        
        # Initialize model and tracker
        self._initialize(fps)
        
        # Open video
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {video_path}")
        
        detections_list = []
        frame_idx = 0
        
        logger.info(f"Starting video processing: {total_frames} frames")
        
        # Get class names from YOLO model
        class_names = self._model.model.names
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Calculate timestamp
            timestamp_ms = int((frame_idx / fps) * 1000)
            
            # Run YOLO detection
            results = self._model(
                frame,
                conf=self.config.conf_threshold,
                iou=self.config.iou_threshold,
                classes=self.config.vehicle_classes,
                verbose=False
            )[0]
            
            # Convert to supervision format
            detections = sv.Detections.from_ultralytics(results)
            
            # Update tracker
            if len(detections) > 0:
                detections = self._tracker.update_with_detections(detections)
            
            # Extract detection data
            for i in range(len(detections)):
                bbox = detections.xyxy[i]
                x1, y1, x2, y2 = bbox
                
                # Get track ID
                track_id = None
                if detections.tracker_id is not None:
                    track_id = int(detections.tracker_id[i])
                
                # Get class info
                class_id = int(detections.class_id[i]) if detections.class_id is not None else 0
                class_name = class_names.get(class_id, str(class_id))
                
                # Get confidence
                confidence = float(detections.confidence[i]) if detections.confidence is not None else 0.0
                
                # Calculate center and dimensions
                bbox_w = x2 - x1
                bbox_h = y2 - y1
                center_x = x1 + bbox_w / 2
                center_y = y1 + bbox_h / 2
                
                detection = DetectionResult(
                    frame_idx=frame_idx,
                    timestamp_ms=timestamp_ms,
                    track_id=track_id,
                    class_name=class_name,
                    class_id=class_id,
                    confidence=confidence,
                    bbox_x=float(x1),
                    bbox_y=float(y1),
                    bbox_w=float(bbox_w),
                    bbox_h=float(bbox_h),
                    center_x=float(center_x),
                    center_y=float(center_y),
                )
                detections_list.append(detection)
            
            # Progress callback
            if progress_callback and frame_idx % 10 == 0:
                progress_callback(
                    frame_idx,
                    total_frames,
                    f"Processing frame {frame_idx}/{total_frames}"
                )
            
            frame_idx += 1
        
        cap.release()
        
        # Post-process: Merge fragmented tracks
        detections_list = self._merge_fragmented_tracks(detections_list)
        
        # Get unique track count
        unique_tracks = len(set(d.track_id for d in detections_list if d.track_id is not None))
        
        logger.info(
            f"Processing complete: {len(detections_list)} detections, "
            f"{unique_tracks} unique tracks (after merging), {frame_idx} frames processed"
        )
        
        return detections_list
    
    def _merge_fragmented_tracks(self, detections: list[DetectionResult]) -> list[DetectionResult]:
        """
        Merge tracks that are likely the same vehicle.
        
        Strategy:
        - If two tracks appear in similar locations and don't overlap in time,
          they might be the same vehicle that lost tracking.
        - Merge tracks that are close in space and consecutive in time.
        """
        if not detections:
            return detections
        
        # Group detections by track_id
        tracks = {}
        for det in detections:
            if det.track_id is not None:
                if det.track_id not in tracks:
                    tracks[det.track_id] = []
                tracks[det.track_id].append(det)
        
        # Sort each track by frame
        for track_id in tracks:
            tracks[track_id].sort(key=lambda d: d.frame_idx)
        
        # Find tracks to merge
        # Two tracks should be merged if:
        # 1. They don't overlap in time (one ends before the other starts)
        # 2. They are close in space at the transition point
        # 3. They have similar class
        
        track_ids = sorted(tracks.keys())
        merge_map = {}  # {old_track_id: new_track_id}
        next_new_id = max(track_ids) + 1 if track_ids else 1
        
        for i, track_id1 in enumerate(track_ids):
            if track_id1 in merge_map:
                continue  # Already merged
            
            track1 = tracks[track_id1]
            track1_frames = [d.frame_idx for d in track1]
            track1_end_frame = max(track1_frames)
            track1_end_center = (track1[-1].center_x, track1[-1].center_y)
            track1_class = track1[0].class_name
            
            # Look for tracks that start right after this one ends
            for track_id2 in track_ids[i+1:]:
                if track_id2 in merge_map:
                    continue
                
                track2 = tracks[track_id2]
                track2_frames = [d.frame_idx for d in track2]
                track2_start_frame = min(track2_frames)
                track2_start_center = (track2[0].center_x, track2[0].center_y)
                track2_class = track2[0].class_name
                
                # Check if tracks should be merged
                frame_gap = track2_start_frame - track1_end_frame
                if frame_gap < 0:
                    continue  # Overlapping in time, don't merge
                
                if frame_gap > 10:
                    continue  # Too large a gap
                
                # Check spatial proximity (within 100 pixels)
                distance = np.sqrt(
                    (track2_start_center[0] - track1_end_center[0])**2 +
                    (track2_start_center[1] - track1_end_center[1])**2
                )
                
                if distance > 100:
                    continue  # Too far apart
                
                # Check same class
                if track1_class != track2_class:
                    continue
                
                # Merge track2 into track1
                logger.info(
                    f"Merging track {track_id2} into {track_id1} "
                    f"(gap: {frame_gap} frames, distance: {distance:.1f}px)"
                )
                merge_map[track_id2] = track_id1
        
        # Apply merges
        for det in detections:
            if det.track_id is not None and det.track_id in merge_map:
                det.track_id = merge_map[det.track_id]
        
        return detections
    
    def _calculate_speeds_and_world_coords(
        self,
        detections: list[DetectionResult],
        video_width: int,
        video_height: int
    ) -> list[DetectionResult]:
        """
        Calculate real-world speeds and GPS coordinates for all detections.
        
        Requires homography calibration to be available.
        Uses a 5-frame lookback window for speed calculation to reduce noise.
        
        Args:
            detections: List of detection results
            video_width: Video width in pixels
            video_height: Video height in pixels
            
        Returns:
            Detections updated with speed_mph, world_x, world_y
        """
        if not self._distance_estimator:
            logger.info("No homography calibration - skipping speed calculation")
            return detections
        
        if not detections:
            return detections
        
        logger.info(f"Calculating speeds for {len(detections)} detections using homography")
        
        # Group detections by track_id
        tracks: dict[int, list[DetectionResult]] = {}
        for det in detections:
            if det.track_id is not None:
                if det.track_id not in tracks:
                    tracks[det.track_id] = []
                tracks[det.track_id].append(det)
        
        # Sort each track by frame
        for track_id in tracks:
            tracks[track_id].sort(key=lambda d: d.frame_idx)
        
        # Calculate speeds for each track
        speed_count = 0
        for track_id, track_dets in tracks.items():
            for i, det in enumerate(track_dets):
                # Normalize coordinates (0-1 range)
                x_norm = det.center_x / video_width
                y_norm = det.center_y / video_height
                
                # Transform to world coordinates (GPS)
                try:
                    geo = self._distance_estimator.image_to_geo(x_norm, y_norm)
                    det.world_x = geo.lng
                    det.world_y = geo.lat
                except Exception as e:
                    logger.debug(f"Failed to transform coords for track {track_id}: {e}")
                    continue
                
                # Calculate speed using 5-frame lookback window for smoothing
                lookback = 5
                if i >= lookback:
                    old_det = track_dets[i - lookback]
                    old_x_norm = old_det.center_x / video_width
                    old_y_norm = old_det.center_y / video_height
                    
                    # Time difference in seconds
                    time_diff = (det.timestamp_ms - old_det.timestamp_ms) / 1000.0
                    
                    if time_diff > 0:
                        try:
                            speed = self._distance_estimator.calculate_speed(
                                (old_x_norm, old_y_norm),
                                (x_norm, y_norm),
                                time_diff
                            )
                            # Clamp to reasonable range (0-150 mph)
                            det.speed_mph = min(max(speed, 0.0), 150.0)
                            speed_count += 1
                        except Exception as e:
                            logger.debug(f"Failed to calculate speed for track {track_id}: {e}")
        
        logger.info(f"Calculated speeds for {speed_count} detections across {len(tracks)} tracks")
        return detections
    
    def process_video_from_url(
        self,
        video_url: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> tuple[list[DetectionResult], dict[str, Any]]:
        """
        Download and process video from URL.
        
        If homography calibration was provided during initialization,
        this will also calculate real-world speeds and GPS coordinates.
        
        Args:
            video_url: URL of the video
            progress_callback: Optional callback for progress updates
            
        Returns:
            Tuple of (detections_list, video_info)
        """
        # Download video
        video_path = self.download_video(video_url)
        
        try:
            # Get video info
            video_info = self.get_video_info(video_path)
            
            # Process video (detection + tracking)
            detections = self.process_video(video_path, progress_callback)
            
            # Calculate speeds and world coordinates if homography is available
            if self._distance_estimator:
                detections = self._calculate_speeds_and_world_coords(
                    detections,
                    video_info["width"],
                    video_info["height"]
                )
            
            return detections, video_info
            
        finally:
            # Clean up temp file
            try:
                video_path.unlink()
                logger.info(f"Cleaned up temp file: {video_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp file: {e}")


def create_annotated_frame(
    frame: np.ndarray,
    detections: list[DetectionResult],
    frame_idx: int
) -> np.ndarray:
    """
    Create an annotated frame with bounding boxes and labels.
    
    Args:
        frame: Original frame
        detections: List of detections for this frame
        frame_idx: Current frame index
        
    Returns:
        Annotated frame
    """
    import supervision as sv
    
    # Filter detections for this frame
    frame_detections = [d for d in detections if d.frame_idx == frame_idx]
    
    if not frame_detections:
        return frame
    
    # Create supervision detections
    xyxy = np.array([[d.bbox_x, d.bbox_y, d.bbox_x + d.bbox_w, d.bbox_y + d.bbox_h] for d in frame_detections])
    confidence = np.array([d.confidence for d in frame_detections])
    class_id = np.array([d.class_id for d in frame_detections])
    tracker_id = np.array([d.track_id if d.track_id else -1 for d in frame_detections])
    
    sv_detections = sv.Detections(
        xyxy=xyxy,
        confidence=confidence,
        class_id=class_id,
        tracker_id=tracker_id
    )
    
    # Annotate
    box_annotator = sv.BoxAnnotator(thickness=2)
    label_annotator = sv.LabelAnnotator(text_scale=0.5, text_thickness=1)
    
    labels = [
        f"#{d.track_id} {d.class_name} {d.confidence:.2f}"
        for d in frame_detections
    ]
    
    annotated = box_annotator.annotate(frame.copy(), sv_detections)
    annotated = label_annotator.annotate(annotated, sv_detections, labels)
    
    return annotated

