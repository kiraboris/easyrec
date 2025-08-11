"""
Online Training Script for EasyRec Online
Manages real-time model training and updates
"""
import os
import sys
import argparse
import json
import logging
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streaming.online_trainer import EasyRecOnlineTrainer
from streaming.kafka_consumer import EasyRecKafkaConsumer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def start_online_training(config: Dict[str, Any]) -> bool:
    """
    Start online training with specified configuration
    
    Args:
        config: Online training configuration
        
    Returns:
        True if training started successfully
    """
    try:
        # Initialize trainer
        trainer = EasyRecOnlineTrainer(
            config_path=config['model']['config_path'],
            model_dir=config['model']['online_model_dir'],
            base_checkpoint=config['model'].get('base_checkpoint')
        )
        
        # Kafka configuration
        kafka_config = config['streaming']['kafka']
        
        # Update configuration
        update_config = config.get('training', {}).get('incremental_updates', {})
        
        # Start incremental training
        logger.info("Starting online training...")
        success = trainer.start_incremental_training(kafka_config, update_config)
        
        if success:
            logger.info("Online training started successfully")
            
            # Monitor training status
            while trainer.is_training:
                status = trainer.get_training_status()
                logger.info(f"Training status: {status}")
                
                # Sleep for monitoring interval
                import time
                time.sleep(30)  # Check every 30 seconds
                
        else:
            logger.error("Failed to start online training")
            
        return success
        
    except Exception as e:
        logger.error(f"Error in online training: {e}")
        return False


def test_streaming_connection(config: Dict[str, Any]) -> bool:
    """
    Test connection to streaming data source
    
    Args:
        config: Configuration dictionary
        
    Returns:
        True if connection successful
    """
    try:
        kafka_config = config['streaming']['kafka']
        
        consumer = EasyRecKafkaConsumer(
            servers=kafka_config['servers'],
            topic=kafka_config['topic'],
            group=kafka_config['group'] + '_test'
        )
        
        logger.info("Testing Kafka connection...")
        success = consumer.connect()
        
        if success:
            logger.info("Kafka connection successful")
            
            # Test consuming a small batch
            batch = consumer.consume_batch(batch_size=5, timeout=10)
            logger.info(f"Test batch consumed: {len(batch)} messages")
            
            for i, sample in enumerate(batch):
                logger.info(f"Sample {i}: {sample.get('key', 'N/A')}")
                
        consumer.stop()
        return success
        
    except Exception as e:
        logger.error(f"Error testing streaming connection: {e}")
        return False


def export_online_model(config: Dict[str, Any], export_dir: str) -> bool:
    """
    Export online model for serving
    
    Args:
        config: Configuration dictionary
        export_dir: Directory to export model
        
    Returns:
        True if export successful
    """
    try:
        trainer = EasyRecOnlineTrainer(
            config_path=config['model']['config_path'],
            model_dir=config['model']['online_model_dir']
        )
        
        logger.info(f"Exporting online model to {export_dir}")
        success = trainer.trigger_model_export(export_dir)
        
        if success:
            logger.info("Model export completed successfully")
            
            # Get incremental update info
            updates = trainer.get_incremental_updates()
            logger.info(f"Incremental updates: {updates}")
            
        return success
        
    except Exception as e:
        logger.error(f"Error exporting model: {e}")
        return False


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from file"""
    try:
        with open(config_path, 'r') as f:
            if config_path.endswith('.json'):
                return json.load(f)
            else:
                # Simple key=value format
                config = {}
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
                return config
                
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {}


def create_default_config() -> Dict[str, Any]:
    """Create default online training configuration"""
    return {
        'model': {
            'config_path': 'config/deepfm_config.prototxt',
            'online_model_dir': 'models/online/deepfm_movies',
            'base_checkpoint': 'models/checkpoints/deepfm_movies'
        },
        'streaming': {
            'kafka': {
                'servers': 'localhost:9092',
                'topic': 'easyrec_training',
                'group': 'easyrec_online',
                'offset_time': '20240101 00:00:00'
            }
        },
        'training': {
            'incremental_updates': {
                'dense_save_steps': 100,
                'sparse_save_steps': 100,
                'fs': {}
            }
        }
    }


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='EasyRec Online Training')
    parser.add_argument('--config', 
                       help='Configuration file path')
    parser.add_argument('--mode', 
                       choices=['train', 'test', 'export'],
                       default='train',
                       help='Operation mode')
    parser.add_argument('--export-dir', 
                       default='models/export/online',
                       help='Export directory for models')
    parser.add_argument('--create-config',
                       action='store_true',
                       help='Create default configuration file')
    
    args = parser.parse_args()
    
    # Create default config if requested
    if args.create_config:
        config = create_default_config()
        config_path = 'online_training_config.json'
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        logger.info(f"Default configuration created: {config_path}")
        return 0
    
    # Load configuration
    if args.config:
        config = load_config(args.config)
    else:
        config = create_default_config()
        logger.info("Using default configuration")
    
    if not config:
        logger.error("No valid configuration found")
        return 1
    
    # Execute based on mode
    success = False
    
    if args.mode == 'train':
        logger.info("Starting online training mode")
        success = start_online_training(config)
        
    elif args.mode == 'test':
        logger.info("Testing streaming connection")
        success = test_streaming_connection(config)
        
    elif args.mode == 'export':
        logger.info("Exporting online model")
        success = export_online_model(config, args.export_dir)
    
    if success:
        logger.info(f"Operation '{args.mode}' completed successfully")
        return 0
    else:
        logger.error(f"Operation '{args.mode}' failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
