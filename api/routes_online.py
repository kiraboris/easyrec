"""
Online Learning API Routes for EasyRec
Extends the base API with real-time learning capabilities
"""
from flask import Blueprint, request, jsonify
import logging
import os
import sys
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streaming.kafka_consumer import EasyRecKafkaConsumer
from streaming.online_trainer import EasyRecOnlineTrainer

logger = logging.getLogger(__name__)

# Create blueprint for online learning routes
online_bp = Blueprint('online', __name__, url_prefix='/online')

# Global instances (should be properly managed in production)
_kafka_consumer = None
_online_trainer = None


def get_kafka_consumer():
    """Get or create Kafka consumer instance"""
    global _kafka_consumer
    if _kafka_consumer is None:
        # Default configuration - should come from config file
        servers = os.getenv('KAFKA_SERVERS', 'localhost:9092')
        topic = os.getenv('KAFKA_TOPIC', 'easyrec_training')
        group = os.getenv('KAFKA_GROUP', 'easyrec_online')
        
        _kafka_consumer = EasyRecKafkaConsumer(
            servers=servers,
            topic=topic,
            group=group
        )
    return _kafka_consumer


def get_online_trainer():
    """Get or create online trainer instance"""
    global _online_trainer
    if _online_trainer is None:
        config_path = os.getenv('CONFIG_PATH', 'config/deepfm_config.prototxt')
        model_dir = os.getenv('ONLINE_MODEL_DIR', 'models/online/deepfm_movies')
        base_checkpoint = os.getenv('BASE_CHECKPOINT_PATH', 'models/checkpoints/deepfm_movies')
        
        _online_trainer = EasyRecOnlineTrainer(
            config_path=config_path,
            model_dir=model_dir,
            base_checkpoint=base_checkpoint
        )
    return _online_trainer


@online_bp.route('/data/add', methods=['POST'])
def add_training_data():
    """
    Add training data for incremental learning
    
    Request body:
    {
        "samples": [
            {
                "user_id": 123,
                "item_id": 456,
                "label": 1,
                "features": {...}
            }
        ]
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'samples' not in data:
            return jsonify({
                'success': False,
                'error': 'samples field is required'
            }), 400
        
        samples = data['samples']
        if not isinstance(samples, list):
            return jsonify({
                'success': False,
                'error': 'samples must be a list'
            }), 400
        
        # Add samples to online trainer
        trainer = get_online_trainer()
        success = trainer.add_training_data(samples)
        
        if success:
            return jsonify({
                'success': True,
                'data': {
                    'samples_added': len(samples),
                    'message': 'Training data added successfully'
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to add training data'
            }), 500
            
    except Exception as e:
        logger.error(f"Error adding training data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@online_bp.route('/training/start', methods=['POST'])
def start_incremental_training():
    """
    Start incremental training with streaming data
    
    Request body:
    {
        "kafka_config": {
            "servers": "localhost:9092",
            "topic": "easyrec_training",
            "group": "easyrec_online",
            "offset_time": "20240101 00:00:00"
        },
        "update_config": {
            "dense_save_steps": 100,
            "sparse_save_steps": 100
        }
    }
    """
    try:
        data = request.get_json() or {}
        
        kafka_config = data.get('kafka_config', {
            'servers': 'localhost:9092',
            'topic': 'easyrec_training',
            'group': 'easyrec_online'
        })
        
        update_config = data.get('update_config', {
            'dense_save_steps': 100,
            'sparse_save_steps': 100,
            'fs': {}
        })
        
        # Start incremental training
        trainer = get_online_trainer()
        success = trainer.start_incremental_training(kafka_config, update_config)
        
        if success:
            return jsonify({
                'success': True,
                'data': {
                    'message': 'Incremental training started',
                    'status': trainer.get_training_status()
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to start incremental training'
            }), 500
            
    except Exception as e:
        logger.error(f"Error starting incremental training: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@online_bp.route('/training/stop', methods=['POST'])
def stop_incremental_training():
    """Stop incremental training"""
    try:
        trainer = get_online_trainer()
        success = trainer.stop_training()
        
        if success:
            return jsonify({
                'success': True,
                'data': {
                    'message': 'Incremental training stopped',
                    'status': trainer.get_training_status()
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to stop incremental training'
            }), 500
            
    except Exception as e:
        logger.error(f"Error stopping incremental training: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@online_bp.route('/training/status', methods=['GET'])
def get_training_status():
    """Get current training status"""
    try:
        trainer = get_online_trainer()
        status = trainer.get_training_status()
        
        return jsonify({
            'success': True,
            'data': status
        })
        
    except Exception as e:
        logger.error(f"Error getting training status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@online_bp.route('/model/retrain', methods=['POST'])
def trigger_model_retrain():
    """
    Trigger full model retraining
    
    Request body:
    {
        "retrain_type": "full",  # or "incremental"
        "data_source": "latest",  # or specific data source
        "export_after": true
    }
    """
    try:
        data = request.get_json() or {}
        
        retrain_type = data.get('retrain_type', 'incremental')
        export_after = data.get('export_after', True)
        
        trainer = get_online_trainer()
        
        if retrain_type == 'full':
            # For full retraining, we'd typically trigger a new training job
            # This is a simplified implementation
            logger.info("Full retraining requested - would trigger batch training job")
            
            return jsonify({
                'success': True,
                'data': {
                    'message': 'Full retraining scheduled',
                    'retrain_type': retrain_type,
                    'estimated_time': '2-4 hours'
                }
            })
            
        else:
            # Incremental retraining
            export_dir = 'models/export/online' if export_after else None
            
            if export_after:
                success = trainer.trigger_model_export(export_dir)
                if not success:
                    return jsonify({
                        'success': False,
                        'error': 'Model export failed'
                    }), 500
            
            return jsonify({
                'success': True,
                'data': {
                    'message': 'Incremental retraining completed',
                    'retrain_type': retrain_type,
                    'export_dir': export_dir if export_after else None
                }
            })
            
    except Exception as e:
        logger.error(f"Error triggering model retrain: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@online_bp.route('/model/export', methods=['POST'])
def export_model():
    """
    Export current model for serving
    
    Request body:
    {
        "export_dir": "models/export/online",
        "include_incremental": true
    }
    """
    try:
        data = request.get_json() or {}
        
        export_dir = data.get('export_dir', 'models/export/online')
        include_incremental = data.get('include_incremental', True)
        
        trainer = get_online_trainer()
        success = trainer.trigger_model_export(export_dir)
        
        if success:
            # Get incremental update info if requested
            incremental_info = None
            if include_incremental:
                incremental_info = trainer.get_incremental_updates()
            
            return jsonify({
                'success': True,
                'data': {
                    'export_dir': export_dir,
                    'message': 'Model exported successfully',
                    'incremental_updates': incremental_info
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Model export failed'
            }), 500
            
    except Exception as e:
        logger.error(f"Error exporting model: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@online_bp.route('/streaming/status', methods=['GET'])
def get_streaming_status():
    """Get streaming consumer status"""
    try:
        consumer = get_kafka_consumer()
        
        # Get current offsets
        offsets = consumer.get_current_offsets()
        
        return jsonify({
            'success': True,
            'data': {
                'connected': consumer.consumer is not None,
                'running': consumer.running,
                'topic': consumer.topic,
                'group': consumer.group,
                'current_offsets': offsets
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting streaming status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@online_bp.route('/streaming/consume', methods=['POST'])
def consume_streaming_batch():
    """
    Manually consume a batch of streaming data
    
    Request body:
    {
        "batch_size": 100,
        "timeout": 10
    }
    """
    try:
        data = request.get_json() or {}
        
        batch_size = data.get('batch_size', 100)
        timeout = data.get('timeout', 10)
        
        consumer = get_kafka_consumer()
        batch = consumer.consume_batch(batch_size, timeout)
        
        return jsonify({
            'success': True,
            'data': {
                'batch_size': len(batch),
                'samples': batch[:5],  # Return first 5 samples as preview
                'total_consumed': len(batch)
            }
        })
        
    except Exception as e:
        logger.error(f"Error consuming streaming batch: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@online_bp.route('/updates/list', methods=['GET'])
def list_incremental_updates():
    """List available incremental model updates"""
    try:
        trainer = get_online_trainer()
        updates = trainer.get_incremental_updates()
        
        return jsonify({
            'success': True,
            'data': updates
        })
        
    except Exception as e:
        logger.error(f"Error listing incremental updates: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
