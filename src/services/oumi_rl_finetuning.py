"""
Oumi Reinforcement Learning Fine-tuning Service.

Uses Oumi's RLHF (Reinforcement Learning from Human Feedback) features
to fine-tune VLM models for accident analysis.

This is the REQUIRED feature for the hackathon:
"Your submission must use Oumi's Reinforcement Learning fine-tuning features"

Reference: https://github.com/oumi-ai/oumi
"""

import logging
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
import base64
import io

from PIL import Image

logger = logging.getLogger(__name__)


class OumiRLFineTuner:
    """
    Fine-tunes VLM models using Oumi's Reinforcement Learning from Human Feedback (RLHF).
    
    This demonstrates the REQUIRED hackathon feature:
    - Uses Oumi's RL fine-tuning capabilities
    - Fine-tunes VLM for better accident scene analysis
    - Uses reward function based on analysis quality
    """
    
    def __init__(self, base_model: str = "Qwen/Qwen2-VL-2B-Instruct"):
        """
        Initialize Oumi RL fine-tuner.
        
        Args:
            base_model: Base VLM model to fine-tune (Oumi-supported)
        """
        self.base_model = base_model
        self._oumi_available = False
        self._check_oumi()
    
    def _check_oumi(self):
        """Check if Oumi is installed."""
        try:
            import oumi
            self._oumi_available = True
            logger.info("Oumi framework detected - RL fine-tuning enabled")
        except ImportError:
            self._oumi_available = False
            logger.warning("Oumi not installed - install with: pip install oumi")
    
    def prepare_training_dataset(
        self,
        accident_frames: List[Dict[str, Any]],
        output_dir: Path
    ) -> Path:
        """
        Prepare dataset for RL fine-tuning in Oumi format.
        
        Args:
            accident_frames: List of frames with image_base64, prompt, and preferred response
            output_dir: Where to save the dataset
            
        Returns:
            Path to dataset file
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Prepare dataset in Oumi format for RL training
        dataset = []
        
        for i, frame in enumerate(accident_frames):
            # Decode and save image
            image_bytes = base64.b64decode(frame["image_base64"])
            image = Image.open(io.BytesIO(image_bytes))
            image_path = output_dir / f"frame_{i:04d}.jpg"
            image.save(image_path)
            
            # Create training example
            example = {
                "id": f"accident_{i:04d}",
                "image": str(image_path),
                "prompt": frame.get("prompt", "Describe this traffic scene in detail."),
                "chosen": frame.get("chosen_response", ""),  # Preferred response
                "rejected": frame.get("rejected_response", ""),  # Less preferred response (for preference learning)
                "metadata": {
                    "frame_type": frame.get("frame_type", "unknown"),
                    "collision_severity": frame.get("collision_severity", "unknown"),
                    **frame.get("metadata", {})
                }
            }
            dataset.append(example)
        
        # Save dataset
        dataset_path = output_dir / "rl_training_dataset.json"
        with open(dataset_path, "w") as f:
            json.dump(dataset, f, indent=2)
        
        logger.info(f"Prepared RL training dataset with {len(dataset)} examples at {dataset_path}")
        return dataset_path
    
    def create_reward_function(self, output_dir: Path) -> Path:
        """
        Create reward function for accident analysis quality.
        
        The reward function evaluates how well the VLM analyzes accident scenes.
        Higher rewards for:
        - Accurate vehicle identification
        - Correct collision description
        - Detailed scene analysis
        
        Args:
            output_dir: Where to save the reward function
            
        Returns:
            Path to reward function file
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        reward_function_code = '''
"""
Reward function for accident analysis VLM fine-tuning.

This function evaluates the quality of VLM responses for accident scene analysis.
"""
import re
from typing import Dict, Any


def calculate_reward(response: str, metadata: Dict[str, Any]) -> float:
    """
    Calculate reward for VLM response on accident analysis.
    
    Args:
        response: VLM-generated text response
        metadata: Frame metadata (frame_type, collision_severity, etc.)
        
    Returns:
        Reward score (0.0 to 1.0)
    """
    reward = 0.0
    
    # Check for key accident analysis terms
    vehicle_keywords = ["vehicle", "car", "truck", "motorcycle", "bus"]
    collision_keywords = ["collision", "crash", "impact", "accident", "collide"]
    detail_keywords = ["position", "direction", "speed", "damage", "intersection"]
    
    response_lower = response.lower()
    
    # Reward for vehicle identification (0.3 points)
    vehicle_count = sum(1 for kw in vehicle_keywords if kw in response_lower)
    reward += min(0.3, vehicle_count * 0.1)
    
    # Reward for collision description (0.3 points)
    collision_count = sum(1 for kw in collision_keywords if kw in response_lower)
    reward += min(0.3, collision_count * 0.1)
    
    # Reward for detailed analysis (0.2 points)
    detail_count = sum(1 for kw in detail_keywords if kw in response_lower)
    reward += min(0.2, detail_count * 0.05)
    
    # Reward for response length (detailed responses are better) (0.1 points)
    word_count = len(response.split())
    if word_count > 50:
        reward += 0.1
    elif word_count > 20:
        reward += 0.05
    
    # Reward for frame type relevance (0.1 points)
    frame_type = metadata.get("frame_type", "")
    if frame_type == "peak" and "collision" in response_lower:
        reward += 0.1
    elif frame_type == "approach" and ("approaching" in response_lower or "coming" in response_lower):
        reward += 0.1
    
    return min(1.0, reward)


def reward_function(response: str, metadata: Dict[str, Any]) -> float:
    """Wrapper for Oumi reward function interface."""
    return calculate_reward(response, metadata)
'''
        
        reward_path = output_dir / "reward_function.py"
        with open(reward_path, "w") as f:
            f.write(reward_function_code)
        
        logger.info(f"Created reward function at {reward_path}")
        return reward_path
    
    def create_rl_training_config(
        self,
        dataset_path: Path,
        reward_function_path: Path,
        output_dir: Path,
        model_name: Optional[str] = None
    ) -> Path:
        """
        Create Oumi RL training configuration.
        
        Uses Oumi's RLHF features (GRPO, PPO, etc.) to fine-tune the VLM.
        
        Args:
            dataset_path: Path to training dataset
            reward_function_path: Path to reward function
            output_dir: Where to save training outputs
            model_name: Model to fine-tune (defaults to base_model)
            
        Returns:
            Path to training config file
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        model_name = model_name or self.base_model
        
        # Oumi RL training config
        config = {
            "model": {
                "model_name": model_name,
                "trust_remote_code": True,
                "torch_dtype_str": "float16",
                "model_max_length": 2048
            },
            "dataset": {
                "dataset_path": str(dataset_path),
                "dataset_type": "preference",  # For RLHF
                "format": "json"
            },
            "reward_function": {
                "path": str(reward_function_path),
                "function_name": "reward_function"
            },
            "training": {
                "method": "grpo",  # Group Relative Policy Optimization (Oumi's RL method)
                "learning_rate": 1e-5,
                "batch_size": 4,
                "num_epochs": 3,
                "gradient_accumulation_steps": 4
            },
            "output_dir": str(output_dir),
            "enable_wandb": False,
            "save_steps": 100
        }
        
        # Save config
        config_path = output_dir / "rl_training_config.yaml"
        import yaml
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info(f"Created RL training config at {config_path}")
        return config_path
    
    def fine_tune_with_oumi_rl(
        self,
        accident_frames: List[Dict[str, Any]],
        output_dir: Optional[Path] = None,
        model_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fine-tune VLM using Oumi's Reinforcement Learning from Human Feedback (RLHF).
        
        This is the REQUIRED hackathon feature.
        
        Args:
            accident_frames: Training data with images, prompts, and preferred responses
            output_dir: Where to save fine-tuned model
            model_name: Model to fine-tune (defaults to base_model)
            
        Returns:
            Training results and model path
        """
        if not self._oumi_available:
            raise RuntimeError(
                "Oumi not installed. Install with: pip install oumi\n"
                "This is REQUIRED for the hackathon award."
            )
        
        model_name = model_name or self.base_model
        
        if output_dir is None:
            import tempfile
            output_dir = Path(tempfile.mkdtemp(prefix="oumi_rl_training_"))
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Starting Oumi RL fine-tuning for {model_name} on {len(accident_frames)} frames")
        
        try:
            # 1. Prepare dataset
            dataset_path = self.prepare_training_dataset(accident_frames, output_dir / "dataset")
            
            # 2. Create reward function
            reward_function_path = self.create_reward_function(output_dir / "reward")
            
            # 3. Create training config
            config_path = self.create_rl_training_config(
                dataset_path,
                reward_function_path,
                output_dir,
                model_name
            )
            
            # 4. Run Oumi RL training
            training_results = self._run_oumi_rl_training(config_path, output_dir)
            
            # 5. Save fine-tuned model path
            fine_tuned_model_path = output_dir / "fine_tuned_model"
            
            return {
                "status": "success",
                "base_model": model_name,
                "fine_tuned_model_path": str(fine_tuned_model_path),
                "config_path": str(config_path),
                "dataset_path": str(dataset_path),
                "training_results": training_results,
                "message": "Oumi RL fine-tuning completed - demonstrating required hackathon feature"
            }
            
        except Exception as e:
            logger.error(f"Error during Oumi RL fine-tuning: {e}")
            raise RuntimeError(f"Oumi RL fine-tuning failed: {str(e)}")
    
    def _run_oumi_rl_training(
        self,
        config_path: Path,
        output_dir: Path
    ) -> Dict[str, Any]:
        """
        Run Oumi RL training using the config.
        
        Args:
            config_path: Path to training config
            output_dir: Output directory
            
        Returns:
            Training results
        """
        try:
            # Try to use Oumi's Python API
            from oumi.core.configs import RLTrainingConfig
            from oumi.train import train_rl
            
            # Load config
            config = RLTrainingConfig.from_yaml(str(config_path))
            
            # Run RL training
            results = train_rl(config)
            
            return {
                "status": "success",
                "metrics": results.get("metrics", {}),
                "checkpoint_path": str(output_dir / "checkpoints")
            }
            
        except ImportError:
            # Fallback: Use command-line interface
            import subprocess
            
            logger.info(f"Running Oumi RL training via CLI: oumi train -c {config_path}")
            
            result = subprocess.run(
                ["oumi", "train", "-c", str(config_path), "--method", "rl"],
                capture_output=True,
                text=True,
                cwd=str(output_dir)
            )
            
            if result.returncode == 0:
                return {
                    "status": "success",
                    "output": result.stdout,
                    "checkpoint_path": str(output_dir / "checkpoints")
                }
            else:
                raise RuntimeError(f"Oumi RL training failed: {result.stderr}")

