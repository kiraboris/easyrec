"""
Online Learning API Routes for EasyRec
Extends the base API with real-time learning capabilities
"""
from flask import Blueprint, request, jsonify
import logging
import os
import sys
from typing import Dict, Any, Tuple

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


# Helper validation utilities
ALLOWED_EXPORT_BASE = os.getenv('ALLOWED_EXPORT_BASE', 'models/export')
DISALLOWED_ENV_KEYS = {k.lower() for k in ("PYTHONPATH", "PATH", "LD_PRELOAD")}

def _validate_kafka_config(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    required = ['servers', 'topic']
    for r in required:
        if r not in cfg or not cfg.get(r):
            return False, f"Missing kafka_config field '{r}'"
    servers = cfg.get('servers', '')
    bad = []
    for part in servers.split(','):
        part = part.strip()
        if not part:
            continue
        if ':' not in part:
            bad.append(part)
            continue
        host, port = part.rsplit(':', 1)
        if not host or not port.isdigit():
            bad.append(part)
            continue
        p = int(port)
        if p < 1 or p > 65535:
            bad.append(part)
    if bad:
        return False, f"Invalid bootstrap servers entries: {bad}"
    return True, ''

def _sanitize_export_dir(path: str) -> Tuple[bool, str]:
    if not path:
        return False, "export_dir is empty"
    if os.path.isabs(path):
        return False, "export_dir must be relative"
    norm = os.path.normpath(path)
    base_norm = os.path.normpath(ALLOWED_EXPORT_BASE)
    if not norm.startswith(base_norm):
        return False, f"export_dir must reside under '{ALLOWED_EXPORT_BASE}'"
    if '..' in norm.split(os.sep):
        return False, "export_dir path traversal not allowed"
    return True, norm

def _filter_env_overrides(env: Dict[str, Any]) -> Dict[str, str]:
    safe = {}
    for k, v in env.items():
        if k.lower() in DISALLOWED_ENV_KEYS:
            continue
        safe[k] = str(v)
    return safe


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
    
    Request body example:
    {
        "kafka_config": {"servers": "localhost:9092", "topic": "easyrec_training", "group": "easyrec_online", "offset_time": "20240101 00:00:00"},
        "update_config": {"dense_save_steps": 100, "sparse_save_steps": 100, "fs": {}},
        "max_restarts": 5,
        "restart_backoff_sec": 15,
        "watchdog_interval_sec": 5,
        "env_overrides": {"CUDA_VISIBLE_DEVICES": "0"}
    }
    """
    try:
        data = request.get_json() or {}
        kafka_config = data.get('kafka_config') or {
            'servers': 'localhost:9092',
            'topic': 'easyrec_training',
            'group': 'easyrec_online'
        }
        ok, err = _validate_kafka_config(kafka_config)
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        update_config = data.get('update_config') or {
            'dense_save_steps': 100,
            'sparse_save_steps': 100,
            'fs': {}
        }
        # numeric params
        try:
            max_restarts = int(data.get('max_restarts', 3))
            restart_backoff_sec = int(data.get('restart_backoff_sec', 10))
            watchdog_interval_sec = int(data.get('watchdog_interval_sec', 5))
        except ValueError:
            return jsonify({'success': False, 'error': 'Numeric parameters must be integers'}), 400
        if max_restarts < 0 or restart_backoff_sec < 0 or watchdog_interval_sec < 1:
            return jsonify({'success': False, 'error': 'Invalid numeric range for restarts/backoff/interval'}), 400
        env_overrides = data.get('env_overrides') if isinstance(data.get('env_overrides'), dict) else None
        if env_overrides:
            env_overrides = _filter_env_overrides(env_overrides)
        trainer = get_online_trainer()
        if trainer.is_training:
            return jsonify({'success': False, 'error': 'Training already in progress'}), 409
        success = trainer.start_incremental_training(
            kafka_config=kafka_config,
            update_config=update_config,
            max_restarts=max_restarts,
            restart_backoff_sec=restart_backoff_sec,
            env_overrides=env_overrides,
            watchdog_interval_sec=watchdog_interval_sec
        )
        if success:
            return jsonify({'success': True, 'data': {'message': 'Incremental training started', 'status': trainer.get_training_status()}})
        else:
            # Fallback generic error (trainer internal failure)
            return jsonify({'success': False, 'error': 'Trainer failed to start (see logs for details)'}), 500
    except Exception as e:
        logger.error(f"Error starting incremental training: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
        # Merge concise health info (process rc etc.)
        health = trainer.get_health()
        status.update({k: v for k, v in health.items() if k not in status})
        return jsonify({'success': True, 'data': status})
    except Exception as e:
        logger.error(f"Error getting training status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@online_bp.route('/training/restart-policy', methods=['PATCH'])
def update_restart_policy():
    """Update restart policy (max_restarts, backoff_sec)."""
    try:
        data = request.get_json() or {}
        trainer = get_online_trainer()
        max_restarts = data.get('max_restarts')
        backoff_sec = data.get('restart_backoff_sec') or data.get('backoff_sec')
        if max_restarts is not None:
            try: max_restarts = int(max_restarts)
            except ValueError: return jsonify({'success': False, 'error': 'max_restarts must be int'}), 400
            if max_restarts < 0: return jsonify({'success': False, 'error': 'max_restarts must be >=0'}), 400
        if backoff_sec is not None:
            try: backoff_sec = int(backoff_sec)
            except ValueError: return jsonify({'success': False, 'error': 'backoff_sec must be int'}), 400
            if backoff_sec < 0: return jsonify({'success': False, 'error': 'backoff_sec must be >=0'}), 400
        result = trainer.update_restart_policy(max_restarts=max_restarts, backoff_sec=backoff_sec)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"Error updating restart policy: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@online_bp.route('/training/logs', methods=['GET'])
def tail_training_logs():
    """Tail training logs.
    Query params: lines (int), stream=stdout|stderr|both
    """
    try:
        try:
            lines = int(request.args.get('lines', 50))
        except ValueError:
            return jsonify({'success': False, 'error': 'lines must be int'}), 400
        if lines < 1: lines = 1
        if lines > 500: lines = 500
        stream = request.args.get('stream', 'both')
        if stream not in ('stdout', 'stderr', 'both'):
            return jsonify({'success': False, 'error': 'stream must be stdout|stderr|both'}), 400
        trainer = get_online_trainer()
        logs = trainer.tail_logs(lines=lines, stream=stream)
        return jsonify({'success': True, 'data': {'stream': stream, 'lines': lines, 'logs': logs}})
    except Exception as e:
        logger.error(f"Error tailing logs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
