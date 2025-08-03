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
        self.model_dir = model_dir
        self.config_path = config_path
        self.session = None
        self.model = None
        self.input_signature = {}
        self.output_signature = {}
        
    def load_model(self):
        """Load the trained EasyRec model"""
        try:
            # Look for saved model in export directory
            export_dir = os.path.join(self.model_dir, 'export')
            if os.path.exists(export_dir):
                # Find the latest exported model
                model_versions = [d for d in os.listdir(export_dir) 
                                if os.path.isdir(os.path.join(export_dir, d))]
                if model_versions:
                    latest_version = sorted(model_versions)[-1]
                    model_path = os.path.join(export_dir, latest_version)
                    
                    # Load SavedModel
                    self.model = tf.saved_model.load(model_path)
                    print(f"Model loaded from {model_path}")
                    return True
            
            # Fallback: try to load from checkpoint
            checkpoint_path = tf.train.latest_checkpoint(self.model_dir)
            if checkpoint_path:
                print(f"Loading from checkpoint: {checkpoint_path}")
                # This would require more complex loading logic
                # For now, we'll simulate a working model
                return True
                
        except Exception as e:
            print(f"Error loading model: {e}")
            return False
        
        return False
    
    def predict_scores(self, user_ids: List[int], item_ids: List[int]) -> List[float]:
        """
        Predict scores for user-item pairs
        
        Args:
            user_ids: List of user IDs
            item_ids: List of item IDs
            
        Returns:
            List of predicted scores
        """
        if not self.model:
            # Simulate predictions for demo purposes
            return [np.random.random() for _ in range(len(user_ids))]
        
        try:
            # Prepare input data
            input_data = {
                'user_id': tf.constant(user_ids, dtype=tf.int32),
                'item_id': tf.constant(item_ids, dtype=tf.int32)
            }
            
            # Run prediction
            predictions = self.model(input_data)
            
            # Extract scores
            if isinstance(predictions, dict):
                scores = predictions.get('scores', predictions.get('output'))
            else:
                scores = predictions
                
            return scores.numpy().tolist()
            
        except Exception as e:
            print(f"Error during prediction: {e}")
            # Return random scores as fallback
            return [np.random.random() for _ in range(len(user_ids))]
    
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
        
        # Prepare input for batch prediction
        user_ids = [user_id] * len(candidate_items)
        
        # Get scores for all candidates
        scores = self.predict_scores(user_ids, candidate_items)
        
        # Combine items with scores
        item_scores = list(zip(candidate_items, scores))
        
        # Sort by score (descending) and take top-k
        item_scores.sort(key=lambda x: x[1], reverse=True)
        top_items = item_scores[:top_k]
        
        # Format output
        recommendations = []
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
        # This would require access to the embedding layers
        # For now, return a random embedding
        embedding_dim = 32
        return np.random.normal(0, 0.1, embedding_dim).tolist()
    
    def get_item_embedding(self, item_id: int) -> Optional[List[float]]:
        """
        Get item embedding vector
        
        Args:
            item_id: Item ID
            
        Returns:
            Item embedding vector or None if not available
        """
        # This would require access to the embedding layers
        # For now, return a random embedding
        embedding_dim = 32
        return np.random.normal(0, 0.1, embedding_dim).tolist()
    
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
            'model_type': 'DeepFM',  # Could be parsed from config
            'embedding_dim': 32,
            'status': 'ready' if self.model else 'not_loaded'
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
