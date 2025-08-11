"""
Model evaluation script
"""
import os
import sys
import argparse
import logging
import pandas as pd
import numpy as np
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.recommendation_model import get_model

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_test_data(test_data_path: str) -> pd.DataFrame:
    """Load test data from CSV file"""
    if not os.path.exists(test_data_path):
        raise FileNotFoundError(f"Test data file not found: {test_data_path}")
    
    logger.info(f"Loading test data from {test_data_path}")
    data = pd.read_csv(test_data_path)
    logger.info(f"Loaded {len(data)} test samples")
    return data


def calculate_metrics(predictions: np.ndarray, labels: np.ndarray) -> Dict[str, float]:
    """Calculate evaluation metrics"""
    from sklearn.metrics import roc_auc_score, accuracy_score, precision_score, recall_score, f1_score
    
    # Convert predictions to binary predictions (threshold = 0.5)
    binary_predictions = (predictions >= 0.5).astype(int)
    
    metrics = {
        'auc': roc_auc_score(labels, predictions),
        'accuracy': accuracy_score(labels, binary_predictions),
        'precision': precision_score(labels, binary_predictions),
        'recall': recall_score(labels, binary_predictions),
        'f1_score': f1_score(labels, binary_predictions)
    }
    
    return metrics


def evaluate_model_performance(model, test_data: pd.DataFrame, 
                             batch_size: int = 1000) -> Dict[str, Any]:
    """
    Evaluate model performance on test data
    
    Args:
        model: Recommendation model instance
        test_data: Test dataset
        batch_size: Batch size for evaluation
        
    Returns:
        Dictionary containing evaluation results
    """
    logger.info("Starting model evaluation...")
    
    predictions = []
    labels = test_data['label'].values
    
    # Process data in batches
    num_batches = (len(test_data) + batch_size - 1) // batch_size
    
    for i in range(num_batches):
        start_idx = i * batch_size
        end_idx = min((i + 1) * batch_size, len(test_data))
        
        batch_data = test_data.iloc[start_idx:end_idx]
        user_ids = batch_data['user_id'].tolist()
        item_ids = batch_data['item_id'].tolist()
        
        # Get predictions for batch
        batch_predictions = model.predict_scores(user_ids, item_ids)
        predictions.extend(batch_predictions)
        
        if (i + 1) % 10 == 0 or i == num_batches - 1:
            logger.info(f"Processed batch {i + 1}/{num_batches}")
    
    predictions = np.array(predictions)
    
    # Calculate metrics
    metrics = calculate_metrics(predictions, labels)
    
    # Additional statistics
    results = {
        'metrics': metrics,
        'statistics': {
            'num_samples': len(test_data),
            'num_users': test_data['user_id'].nunique(),
            'num_items': test_data['item_id'].nunique(),
            'label_distribution': test_data['label'].value_counts().to_dict(),
            'prediction_stats': {
                'mean': float(predictions.mean()),
                'std': float(predictions.std()),
                'min': float(predictions.min()),
                'max': float(predictions.max())
            }
        }
    }
    
    return results


def print_evaluation_results(results: Dict[str, Any]):
    """Print evaluation results in a formatted way"""
    print("\n" + "=" * 60)
    print("MODEL EVALUATION RESULTS")
    print("=" * 60)
    
    metrics = results['metrics']
    print(f"AUC Score:        {metrics['auc']:.4f}")
    print(f"Accuracy:         {metrics['accuracy']:.4f}")
    print(f"Precision:        {metrics['precision']:.4f}")
    print(f"Recall:           {metrics['recall']:.4f}")
    print(f"F1 Score:         {metrics['f1_score']:.4f}")
    
    print("\n" + "-" * 40)
    print("DATASET STATISTICS")
    print("-" * 40)
    
    stats = results['statistics']
    print(f"Number of samples: {stats['num_samples']}")
    print(f"Number of users:   {stats['num_users']}")
    print(f"Number of items:   {stats['num_items']}")
    
    print(f"\nLabel distribution:")
    for label, count in stats['label_distribution'].items():
        percentage = (count / stats['num_samples']) * 100
        print(f"  Label {label}: {count} ({percentage:.1f}%)")
    
    print(f"\nPrediction statistics:")
    pred_stats = stats['prediction_stats']
    print(f"  Mean:  {pred_stats['mean']:.4f}")
    print(f"  Std:   {pred_stats['std']:.4f}")
    print(f"  Min:   {pred_stats['min']:.4f}")
    print(f"  Max:   {pred_stats['max']:.4f}")


def main():
    """Main evaluation function"""
    parser = argparse.ArgumentParser(description='Evaluate EasyRec recommendation model')
    parser.add_argument('--test_data', 
                       default='data/movies_test_data.csv',
                       help='Path to test data file')
    parser.add_argument('--model_dir',
                       default='models/checkpoints/deepfm_movies',
                       help='Directory containing the trained model')
    parser.add_argument('--config',
                       default='config/deepfm_config.prototxt',
                       help='Path to model configuration file')
    parser.add_argument('--batch_size', type=int, default=1000,
                       help='Batch size for evaluation')
    parser.add_argument('--output',
                       help='Path to save evaluation results (JSON format)')
    
    args = parser.parse_args()
    
    try:
        # Load model
        logger.info("Loading model...")
        model = get_model()
        
        # Load test data
        test_data = load_test_data(args.test_data)
        
        # Evaluate model
        results = evaluate_model_performance(model, test_data, args.batch_size)
        
        # Print results
        print_evaluation_results(results)
        
        # Save results if output path is specified
        if args.output:
            import json
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            logger.info(f"Results saved to {args.output}")
        
        logger.info("Evaluation completed successfully!")
        return 0
        
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
