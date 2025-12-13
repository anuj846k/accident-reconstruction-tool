"""
Frame Extraction Service.

Extracts specific frames from videos and converts them to base64 for VLM analysis.
"""

import logging
import base64
import tempfile
from typing import Dict, Any, Optional
from pathlib import Path
import cv2
import requests
from io import BytesIO

logger = logging.getLogger(__name__)


class FrameExtractor:
    """Extracts frames from video URLs."""
    
    async def extract_key_frames_for_collision(
        self,
        video_url: str,
        key_frames: Dict[str, int],
        collision_info: Any
    ) -> Dict[str, Dict[str, Any]]:
        """
        Extract key frames for a collision event.
        
        Args:
            video_url: URL to the video (Cloudinary or other)
            key_frames: Dict with "approach", "contact", "peak", "separation" frame numbers
            collision_info: Collision event information
            
        Returns:
            Dictionary with frame data including base64 images
        """
        frames_data = {}
        
        try:
            # Download video to temporary file
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_file:
                video_path = tmp_file.name
                
                # Download video
                response = requests.get(video_url, stream=True)
                response.raise_for_status()
                
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                
                tmp_file.flush()
            
            # Open video with OpenCV
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                raise ValueError(f"Failed to open video: {video_url}")
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Extract each key frame
            for moment, frame_number in key_frames.items():
                if frame_number is None or frame_number < 0:
                    continue
                
                # Clamp frame number to valid range
                frame_number = min(frame_number, total_frames - 1)
                
                # Seek to frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
                ret, frame = cap.read()
                
                if not ret:
                    logger.warning(f"Failed to read frame {frame_number} for {moment}")
                    continue
                
                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Encode to JPEG and then base64
                from PIL import Image
                pil_image = Image.fromarray(frame_rgb)
                
                buffer = BytesIO()
                pil_image.save(buffer, format='JPEG', quality=85)
                image_bytes = buffer.getvalue()
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                
                frames_data[moment] = {
                    "frame_number": frame_number,
                    "image_base64": image_base64,
                    "timestamp_ms": int((frame_number / fps) * 1000) if fps > 0 else 0
                }
                
                logger.info(f"Extracted {moment} frame {frame_number}")
            
            cap.release()
            
            # Clean up temporary file
            Path(video_path).unlink(missing_ok=True)
            
        except Exception as e:
            logger.error(f"Error extracting frames: {e}", exc_info=True)
            raise
        
        return frames_data
    
    def extract_frame_at_timestamp(
        self,
        video_path: str,
        timestamp_ms: int
    ) -> Optional[str]:
        """
        Extract a single frame at a specific timestamp.
        
        Args:
            video_path: Path to video file
            timestamp_ms: Timestamp in milliseconds
            
        Returns:
            Base64 encoded image or None
        """
        try:
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                return None
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_number = int((timestamp_ms / 1000.0) * fps)
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = cap.read()
            
            if not ret:
                cap.release()
                return None
            
            # Convert to RGB and encode
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            from PIL import Image
            pil_image = Image.fromarray(frame_rgb)
            
            buffer = BytesIO()
            pil_image.save(buffer, format='JPEG', quality=85)
            image_bytes = buffer.getvalue()
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            cap.release()
            return image_base64
            
        except Exception as e:
            logger.error(f"Error extracting frame at {timestamp_ms}ms: {e}")
            return None

