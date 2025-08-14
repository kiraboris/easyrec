"""
EasyRec Recommendation Model Wrapper
"""
import os
import json
import numpy as np
import tensorflow as tf
from typing import List, Dict, Any, Optional


class RecommendationModel:
    """
    Wrapper class for EasyRec recommendation models
    """
    
    def __init__(self, model_dir: str, config_path: str):
        """
        Initialize the recommendation model
        
        Args:
            model_dir: Directory containing the trained model
            config_path: Path to the model configuration file
        """
        self.model_dir = self._sanitize_dir(model_dir, 'models')
        self.config_path = self._sanitize_file(config_path, 'config')
        self.session = None
        self.model = None
        self.input_signature = {}
        self.output_signature = {}
        self.load_error: Optional[str] = None
    
    # --- Path sanitization helpers ---
    @staticmethod
    def _sanitize_dir(path: str, base_required: str) -> str:
        """Sanitize a directory path: must be relative, no traversal, under optional base.
        Allows existing relative custom test dirs (no enforcement beyond traversal & absolutes).
        """
        if not path:
            raise ValueError("model_dir cannot be empty")
        if os.path.isabs(path):
            raise ValueError("Absolute paths are not allowed for model_dir")
        norm = os.path.normpath(path)
        parts = norm.split(os.sep)
        if any(p == '..' for p in parts):
            raise ValueError("Path traversal not allowed in model_dir")
        if os.sep in norm:
            # Enforce first component match exactly (avoid prefix tricks like models_tmp)
            if parts[0] != base_required:
                raise ValueError(f"model_dir must reside under '{base_required}' (first component mismatch)")
        return norm

    @staticmethod
    def _sanitize_file(path: str, base_required: str) -> str:
        if not path:
            raise ValueError("config_path cannot be empty")
        if os.path.isabs(path):
            raise ValueError("Absolute paths are not allowed for config_path")
        norm = os.path.normpath(path)
        parts = norm.split(os.sep)
        if any(p == '..' for p in parts):
            raise ValueError("Path traversal not allowed in config_path")
        if os.sep in norm and parts[0] != base_required:
            raise ValueError(f"config_path must reside under '{base_required}' (first component mismatch)")
        return norm
        
    def load_model(self):
        """Load the trained EasyRec model.
        Sets self.model or records self.load_error (no random fallback).
        Returns True if loaded, False otherwise.
        """
        self.load_error = None
        try:
            # Look for saved model in export directory
            export_dir = os.path.join(self.model_dir, 'export')
            if os.path.exists(export_dir):
                # Find the latest exported model (directories only, ignore symlinks)
                model_versions = [d for d in os.listdir(export_dir)
                                  if os.path.isdir(os.path.join(export_dir, d)) and not os.path.islink(os.path.join(export_dir, d))]
                if model_versions:
                    # Prefer numeric / lexicographically highest version
                    try:
                        model_versions.sort(key=lambda x: int(x) if str(x).isdigit() else x)
                    except Exception:
                        model_versions.sort()
                    latest_version = model_versions[-1]
                    model_path = os.path.join(export_dir, latest_version)
                    try:
                        self.model = tf.saved_model.load(model_path)
                        print(f"Model loaded from {model_path}")
                        return True
                    except Exception as e:  # capture load error
                        self.load_error = f"Failed to load SavedModel at {model_path}: {e}"
                        self.model = None
            # Fallback: try to detect checkpoint presence (do not simulate)
            checkpoint_path = tf.train.latest_checkpoint(self.model_dir)
            if checkpoint_path:
                # Mark as not loaded but available
                self.load_error = (self.load_error or '') + f" SavedModel not loaded; checkpoint detected at {checkpoint_path} but direct checkpoint loading not implemented."
        except Exception as e:
            self.load_error = f"Unexpected error during model load: {e}"
            self.model = None
        return False
        
    def predict_scores(self, user_ids: List[int], item_ids: List[int]) -> List[float]:
        """Predict scores for user-item pairs.
        Raises RuntimeError if model not loaded or output invalid.
        """
        if not self.model:
            raise RuntimeError(self.load_error or "Model not loaded")
        try:
            input_data = {
                'user_id': tf.constant(user_ids, dtype=tf.int32),
                'item_id': tf.constant(item_ids, dtype=tf.int32)
            }
            predictions = self.model(input_data)
            if isinstance(predictions, dict):
                scores = predictions.get('scores') or predictions.get('output')
            else:
                scores = predictions
            if scores is None:
                raise RuntimeError("Model output did not contain scores")
            if hasattr(scores, 'numpy'):
                scores = scores.numpy()
            # Ensure iterable
            try:
                scores_list = list(scores)
            except Exception as e:
                raise RuntimeError(f"Scores object not iterable: {e}") from e
            return [float(s) for s in scores_list]
        except Exception as e:
            raise RuntimeError(f"Prediction error: {e}") from e
    
    def recommend_items(self, user_id: int, candidate_items: List[int], 
                       top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Recommend top-k items for a user
        
        Args:
            user_id: User ID
            candidate_items: List of candidate item IDs
            top_k: Number of recommendations to return
            
        Returns:
            List of recommended items with scores
        """
        if not candidate_items:
            return []
        user_ids = [user_id] * len(candidate_items)
        scores = self.predict_scores(user_ids, candidate_items)
        item_scores = list(zip(candidate_items, scores))
        item_scores.sort(key=lambda x: x[1], reverse=True)
        top_items = item_scores[:top_k]
        recommendations: List[Dict[str, Any]] = []
        for item_id, score in top_items:
            recommendations.append({
                'item_id': int(item_id),
                'score': float(score),
                'rank': len(recommendations) + 1
            })
        return recommendations
    
    def get_user_embedding(self, user_id: int) -> Optional[List[float]]:
        """
        Get user embedding vector
        
        Args:
            user_id: User ID
            
        Returns:
            User embedding vector or None if not available
        """
        # Deterministic placeholder: zeros if model unavailable
        if not self.model:
            return [0.0] * 32
        # If model provides embedding interface, implement here; placeholder zeros
        return [0.0] * 32
    
    def get_item_embedding(self, item_id: int) -> Optional[List[float]]:
        """
        Get item embedding vector
        
        Args:
            item_id: Item ID
            
        Returns:
            Item embedding vector or None if not available
        """
        if not self.model:
            return [0.0] * 32
        return [0.0] * 32
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get model information
        
        Returns:
            Dictionary containing model information
        """
        return {
            'model_dir': self.model_dir,
            'config_path': self.config_path,
            'model_loaded': self.model is not None,
            'model_type': 'DeepFM',
            'embedding_dim': 32,
            'status': 'ready' if self.model else 'not_loaded',
            'load_error': self.load_error
        }


# Global model instance
_model_instance = None


def get_model() -> RecommendationModel:
    """Get the global model instance"""
    global _model_instance
    if _model_instance is None:
        model_dir = os.getenv('MODEL_DIR', 'models/checkpoints/deepfm_movies')
        config_path = os.getenv('CONFIG_PATH', 'config/deepfm_config.prototxt')
        _model_instance = RecommendationModel(model_dir, config_path)
        _model_instance.load_model()
    return _model_instance
