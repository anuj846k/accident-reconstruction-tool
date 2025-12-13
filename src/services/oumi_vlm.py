"""
Oumi VLM Integration Service.

Uses Oumi's inference API to analyze video frames with VLM models.
Oumi supports: Qwen2-VL, Qwen3, and other open-source VLMs.

Reference: https://oumi.ai/docs/en/latest/user_guides/infer/infer.html
"""

import logging
from typing import List, Dict, Any, Optional
import base64
import os

from src.core.config import settings

logger = logging.getLogger(__name__)


class OumiVLMAnalyzer:
    """
    Analyzes images using Oumi's inference API with VLM models.
    
    Uses Oumi's unified inference interface for running VLM models.
    Supports Qwen2-VL and other Oumi-supported VLMs.
    
    Reference: https://oumi.ai/docs/en/latest/user_guides/infer/infer.html
    """
    
    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize Oumi VLM analyzer.
        
        Args:
            model_name: Optional model name. Uses Oumi-supported VLM:
                - Qwen/Qwen2-VL-2B-Instruct (smaller, ~2GB)
                - Qwen/Qwen2-VL-7B-Instruct (larger, better quality)
        """
        self.model_name = model_name or "Qwen/Qwen2-VL-2B-Instruct"
        self._engine = None
        self._inference_config = None
        self._initialized = False
    
    def _initialize(self):
        """Lazy initialization of Oumi inference engine."""
        if self._initialized:
            return
        
        try:
            # Import Oumi inference components
            from oumi.inference import VLLMInferenceEngine, NativeTextInferenceEngine
            from oumi.core.configs import InferenceConfig, ModelParams, GenerationParams, InferenceEngineType
            from oumi.core.types.conversation import Conversation, Message, Role, ContentItem, Type
            
            # Store imports for use in other methods
            self._VLLMInferenceEngine = VLLMInferenceEngine
            self._NativeTextInferenceEngine = NativeTextInferenceEngine
            self._InferenceConfig = InferenceConfig
            self._ModelParams = ModelParams
            self._GenerationParams = GenerationParams
            self._InferenceEngineType = InferenceEngineType
            self._Conversation = Conversation
            self._Message = Message
            self._Role = Role
            self._ContentItem = ContentItem
            self._Type = Type
            
            # Get cache directory (prioritize settings from .env, then env vars, then default)
            cache_dir = None
            
            # 1. Check settings.hf_cache_dir (reads from .env file via pydantic)
            if settings.hf_cache_dir:
                parent_dir = os.path.dirname(settings.hf_cache_dir)
                if os.path.exists(parent_dir):
                    cache_dir = settings.hf_cache_dir
                    logger.info(f"✅ Using cache directory from .env settings: {cache_dir}")
                else:
                    logger.warning(f"⚠️  SSD not mounted at {parent_dir}, will try other options")
            
            # 2. Check environment variables
            if not cache_dir:
                if os.getenv("HF_HOME"):
                    cache_dir = os.getenv("HF_HOME")
                    logger.info(f"✅ Using cache directory from HF_HOME env var: {cache_dir}")
                elif os.getenv("TRANSFORMERS_CACHE"):
                    cache_dir = os.getenv("TRANSFORMERS_CACHE")
                    logger.info(f"✅ Using cache directory from TRANSFORMERS_CACHE env var: {cache_dir}")
            
            # 3. Default fallback
            if not cache_dir:
                cache_dir = os.path.expanduser("~/.cache/huggingface")
                logger.warning(f"⚠️  Using default cache directory (internal drive): {cache_dir}")
            
            os.makedirs(cache_dir, exist_ok=True)
            
            # Set cache directory in environment for Oumi to use
            os.environ["HF_HOME"] = cache_dir
            os.environ["TRANSFORMERS_CACHE"] = cache_dir
            
            logger.info(f"Initializing Oumi inference engine with model: {self.model_name}")
            logger.info(f"Cache directory: {cache_dir}")
            
            # Verify model exists in cache (HuggingFace cache structure)
            # Models are stored in: cache_dir/models--org--model-name/snapshots/<commit-hash>/
            model_cache_path = os.path.join(cache_dir, f"models--{self.model_name.replace('/', '--')}")
            model_exists = os.path.exists(model_cache_path)
            
            # Check if model files actually exist in snapshots
            # WORKAROUND: Use direct snapshot path to bypass Oumi bug where model_kwargs
            # are not passed to from_pretrained(). See OUMI_CACHE_BUG_REPORT.md
            snapshot_path_to_use = None
            model_files_exist = False
            
            if model_exists:
                snapshots_dir = os.path.join(model_cache_path, "snapshots")
                if os.path.exists(snapshots_dir):
                    # Check if any snapshot directory has model files
                    for snapshot in os.listdir(snapshots_dir):
                        snapshot_path = os.path.join(snapshots_dir, snapshot)
                        if os.path.isdir(snapshot_path):
                            # Check for model files
                            if any(f.endswith('.safetensors') or f.endswith('.bin') for f in os.listdir(snapshot_path)):
                                model_files_exist = True
                                snapshot_path_to_use = snapshot_path
                                logger.info(f"✅ Model files found in cache: {snapshot_path}")
                                break
            
            # WORKAROUND: Use direct snapshot path when cache exists
            # This forces Oumi to load from local filesystem instead of trying to download
            if model_exists and model_files_exist and snapshot_path_to_use:
                logger.info(f"✅ Model fully cached at: {model_cache_path}")
                logger.info(f"🔧 WORKAROUND: Using direct snapshot path to bypass Oumi cache bug")
                logger.info(f"   Using snapshot path: {snapshot_path_to_use}")
                # Use the snapshot path directly as model_name
                # This bypasses HuggingFace Hub entirely and loads from local filesystem
                model_name_to_use = snapshot_path_to_use
            else:
                logger.warning(f"⚠️  Model not fully cached, will download if needed to: {cache_dir}")
                # Use original model name (will download if needed)
                model_name_to_use = self.model_name
            
            # Create model parameters
            # Note: Even though we set cache_dir in model_kwargs, Oumi doesn't pass it to from_pretrained()
            # That's why we use the direct snapshot path workaround above
            # NOTE: Cannot use BitsAndBytesConfig in model_kwargs because Oumi's ModelParams
            # tries to hash/serialize it, causing "unhashable type" error.
            # Using float16 instead to reduce memory from ~8GB to ~4GB (50% reduction)
            model_kwargs = {
                "cache_dir": cache_dir,  # Set anyway (might be used for other operations)
                "device_map": "auto",  # Let Oumi handle device placement
            }
            
            model_params = ModelParams(
                model_name=model_name_to_use,  # Use snapshot path if cached, otherwise Hub name
                model_max_length=2048,
                torch_dtype_str="float16",  # Use float16 to reduce memory (from ~8GB to ~4GB)
                model_kwargs=model_kwargs,
                processor_kwargs={
                    "cache_dir": cache_dir,  # Also pass to processor (for tokenizer, etc.)
                }
            )
            
            # Try VLLM first (faster), fallback to NativeTextInferenceEngine
            try:
                self._engine = VLLMInferenceEngine(model_params)
                logger.info("Using VLLMInferenceEngine for faster inference")
            except Exception as e:
                logger.warning(f"VLLMInferenceEngine failed, falling back to NativeTextInferenceEngine: {e}")
                self._engine = NativeTextInferenceEngine(model_params)
                logger.info("Using NativeTextInferenceEngine")
            
            # Create inference config
            self._inference_config = InferenceConfig(
                model=model_params,
                generation=GenerationParams(
                    max_new_tokens=256,  # Reduced from 512 to save memory
                    temperature=0.7
                ),
                engine=InferenceEngineType.VLLM if isinstance(self._engine, VLLMInferenceEngine) else InferenceEngineType.NATIVE
            )
            
            self._initialized = True
            logger.info("Oumi inference engine initialized successfully")
            
        except ImportError as e:
            logger.error(f"Failed to import Oumi: {e}")
            raise RuntimeError(
                "Oumi is required. Install with: pip install oumi\n"
                "This is REQUIRED for the hackathon award."
            )
        except Exception as e:
            logger.error(f"Failed to initialize Oumi inference engine: {e}")
            raise
    
    def analyze_frame(
        self,
        image_base64: str,
        prompt: str = "Describe what you see in this traffic scene. Identify vehicles, their positions, and any collision or interaction."
    ) -> str:
        """
        Analyze a single frame using Oumi's inference API.
        
        Args:
            image_base64: Base64 encoded image
            prompt: Prompt for the VLM
            
        Returns:
            Description of the scene
        """
        self._initialize()
        
        try:
            # Decode base64 to binary bytes
            # Use IMAGE_BINARY type for base64 images (more efficient, no file I/O)
            # Reference: https://oumi.ai/docs/en/latest/user_guides/infer/infer.html#multi-modal-inference
            image_bytes = base64.b64decode(image_base64)
            
            # Create conversation using Oumi's API
            conversation = self._Conversation(
                messages=[
                    self._Message(
                        role=self._Role.USER,
                        content=[
                            self._ContentItem(
                                type=self._Type.IMAGE_BINARY,  # ✅ Use IMAGE_BINARY for base64 data
                                binary=image_bytes,  # ✅ Pass decoded bytes directly
                            ),
                            self._ContentItem(
                                content=prompt,
                                type=self._Type.TEXT,
                            ),
                        ],
                    )
                ]
            )
            
            # Run inference using Oumi's engine
            # Reference: https://oumi.ai/docs/en/latest/user_guides/infer/infer.html#quick-start
            output_conversations = self._engine.infer(
                input=[conversation],
                inference_config=self._inference_config
            )
            
            # Extract response from Oumi's output
            if output_conversations and len(output_conversations) > 0:
                result_conversation = output_conversations[0]
                if result_conversation.messages and len(result_conversation.messages) > 0:
                    last_message = result_conversation.messages[-1]
                    # Extract text content from the message
                    if isinstance(last_message.content, list):
                        # Content is a list of ContentItems
                        text_parts = [
                            item.content for item in last_message.content 
                            if item.type == self._Type.TEXT
                        ]
                        return " ".join(text_parts) if text_parts else "No text response"
                    elif isinstance(last_message.content, str):
                        return last_message.content
                    else:
                        return str(last_message.content)
            
            return "No response generated"
            
        except Exception as e:
            logger.error(f"Error analyzing frame with Oumi VLM: {e}", exc_info=True)
            return f"Error analyzing frame: {str(e)}"
    
    def analyze_collision_frames(
        self,
        frames: Dict[str, Dict[str, Any]],
        collision_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze key frames from a collision event.
        
        Args:
            frames: Dictionary with 'approach', 'contact', 'peak', 'separation' frame data
            collision_info: Information about the collision
            
        Returns:
            Analysis results for each frame
        """
        self._initialize()
        
        results = {}
        
        # Custom prompts for each frame type
        prompts = {
            "approach": "Describe the vehicles approaching each other. What are their positions, directions, and speeds?",
            "contact": "Describe the moment of collision. What vehicles are involved? What is the impact point?",
            "peak": "Describe the peak of the collision. What is the maximum overlap? What damage or interaction do you see?",
            "separation": "Describe the vehicles after collision. How are they moving? What is their final state?"
        }
        
        for moment, frame_data in frames.items():
            if "image_base64" not in frame_data:
                continue
            
            prompt = prompts.get(moment, "Describe what you see in this traffic scene.")
            
            # Add collision context to prompt
            enhanced_prompt = f"""{prompt}
            
            Collision Context:
            - Track IDs: {collision_info.get('track_id_1')} and {collision_info.get('track_id_2')}
            - Frame: {frame_data.get('frame_number')}
            - Maximum IoU: {collision_info.get('max_iou', 0):.3f}
            - Severity: {collision_info.get('severity', 'unknown')}
            """
            
            try:
                analysis = self.analyze_frame(frame_data["image_base64"], enhanced_prompt)
                results[moment] = {
                    "frame_number": frame_data.get("frame_number"),
                    "analysis": analysis,
                    "prompt": enhanced_prompt
                }
                logger.info(f"Analyzed {moment} frame {frame_data.get('frame_number')}")
            except Exception as e:
                logger.error(f"Error analyzing {moment} frame: {e}")
                results[moment] = {
                    "frame_number": frame_data.get("frame_number"),
                    "analysis": f"Error: {str(e)}",
                    "error": True
                }
        
        return results
    
    def generate_collision_summary(
        self,
        frame_analyses: Dict[str, Any],
        collision_info: Dict[str, Any]
    ) -> str:
        """
        Generate a comprehensive summary from frame analyses.
        
        Args:
            frame_analyses: Results from analyze_collision_frames
            collision_info: Information about the collision
            
        Returns:
            Comprehensive accident report
        """
        summary_parts = []
        
        summary_parts.append("# ACCIDENT ANALYSIS REPORT\n")
        summary_parts.append(f"## Collision Details\n")
        summary_parts.append(f"- **Vehicles**: Track {collision_info.get('track_id_1')} and Track {collision_info.get('track_id_2')}\n")
        summary_parts.append(f"- **Severity**: {collision_info.get('severity', 'unknown').upper()}\n")
        summary_parts.append(f"- **Peak IoU**: {collision_info.get('max_iou', 0):.3f}\n")
        summary_parts.append(f"- **Duration**: {collision_info.get('duration_frames', 0)} frames\n\n")
        
        # Add frame-by-frame analysis
        summary_parts.append("## Frame-by-Frame Analysis\n\n")
        
        for moment in ["approach", "contact", "peak", "separation"]:
            if moment in frame_analyses:
                analysis = frame_analyses[moment]
                frame_num = analysis.get("frame_number", "?")
                description = analysis.get("analysis", "No analysis available")
                
                summary_parts.append(f"### {moment.upper()} (Frame {frame_num})\n")
                summary_parts.append(f"{description}\n\n")
        
        # Generate overall conclusion
        summary_parts.append("## Conclusion\n")
        
        # Extract key insights from analyses
        if "peak" in frame_analyses:
            peak_analysis = frame_analyses["peak"].get("analysis", "")
            summary_parts.append(f"Based on visual analysis, {peak_analysis[:200]}...\n")
        
        return "\n".join(summary_parts)

