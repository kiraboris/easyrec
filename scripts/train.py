"""
Training script for EasyRec models
"""
import os
import sys
import argparse
import subprocess
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_easyrec_installation():
    """Check if EasyRec is properly installed"""
    try:
        import easy_rec
        logger.info("EasyRec is installed")
        return True
    except ImportError:
        logger.error("EasyRec is not installed. Please install it first.")
        logger.info("Installation instructions:")
        logger.info("1. git clone https://github.com/alibaba/EasyRec.git")
        logger.info("2. cd EasyRec")
        logger.info("3. bash scripts/init.sh")
        logger.info("4. python setup.py install")
        return False


def train_model(config_path: str, model_dir: str = None):
    """
    Train EasyRec model using the specified configuration
    
    Args:
        config_path: Path to the configuration file
        model_dir: Directory to save the model (optional)
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    # Check if EasyRec is installed
    if not check_easyrec_installation():
        return False
    
    try:
        # Prepare training command
        cmd = [
            sys.executable, '-m', 'easy_rec.python.train_eval',
            '--pipeline_config_path', config_path
        ]
        
        if model_dir:
            # Update config to use specified model directory
            logger.info(f"Using model directory: {model_dir}")
        
        logger.info(f"Starting training with command: {' '.join(cmd)}")
        
        # Run training
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Training completed successfully!")
            logger.info("Training output:")
            logger.info(result.stdout)
            return True
        else:
            logger.error("Training failed!")
            logger.error("Error output:")
            logger.error(result.stderr)
            return False
            
    except Exception as e:
        logger.error(f"Error during training: {e}")
        return False


def evaluate_model(config_path: str):
    """
    Evaluate trained model
    
    Args:
        config_path: Path to the configuration file
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    try:
        cmd = [
            sys.executable, '-m', 'easy_rec.python.eval',
            '--pipeline_config_path', config_path
        ]
        
        logger.info(f"Starting evaluation with command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("Evaluation completed successfully!")
            logger.info("Evaluation output:")
            logger.info(result.stdout)
            return True
        else:
            logger.error("Evaluation failed!")
            logger.error("Error output:")
            logger.error(result.stderr)
            return False
            
    except Exception as e:
        logger.error(f"Error during evaluation: {e}")
        return False


def export_model(config_path: str, export_dir: str):
    """
    Export trained model for serving
    
    Args:
        config_path: Path to the configuration file
        export_dir: Directory to export the model
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    # Create export directory
    os.makedirs(export_dir, exist_ok=True)
    
    try:
        cmd = [
            sys.executable, '-m', 'easy_rec.python.export',
            '--pipeline_config_path', config_path,
            '--export_dir', export_dir
        ]
        
        logger.info(f"Starting model export with command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"Model exported successfully to {export_dir}!")
            logger.info("Export output:")
            logger.info(result.stdout)
            return True
        else:
            logger.error("Model export failed!")
            logger.error("Error output:")
            logger.error(result.stderr)
            return False
            
    except Exception as e:
        logger.error(f"Error during model export: {e}")
        return False


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Train EasyRec recommendation model')
    parser.add_argument('--config', required=True, 
                       help='Path to the configuration file')
    parser.add_argument('--mode', choices=['train', 'eval', 'export', 'all'],
                       default='train', help='Mode to run')
    parser.add_argument('--model_dir', 
                       help='Directory to save the model')
    parser.add_argument('--export_dir', 
                       help='Directory to export the model')
    
    args = parser.parse_args()
    
    config_path = args.config
    mode = args.mode
    
    logger.info(f"Running EasyRec in {mode} mode")
    logger.info(f"Configuration file: {config_path}")
    
    success = True
    
    if mode in ['train', 'all']:
        logger.info("=" * 50)
        logger.info("TRAINING")
        logger.info("=" * 50)
        success &= train_model(config_path, args.model_dir)
    
    if mode in ['eval', 'all'] and success:
        logger.info("=" * 50)
        logger.info("EVALUATION")
        logger.info("=" * 50)
        success &= evaluate_model(config_path)
    
    if mode in ['export', 'all'] and success:
        logger.info("=" * 50)
        logger.info("EXPORT")
        logger.info("=" * 50)
        export_dir = args.export_dir or 'models/export'
        success &= export_model(config_path, export_dir)
    
    if success:
        logger.info("All operations completed successfully!")
        return 0
    else:
        logger.error("Some operations failed!")
        return 1


if __name__ == '__main__':
    sys.exit(main())
