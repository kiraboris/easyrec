"""
Flask REST API for EasyRec Online - Real-time Recommendation System
Integrates Alibaba EasyRec with online learning capabilities
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import sys
import logging
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.recommendation_model import get_model

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize model
model = get_model()

# API version
API_VERSION = "1.1.0"

# Register online learning routes
try:
    from api.routes_online import online_bp
    app.register_blueprint(online_bp)
    logger.info("Online learning routes registered")
except ImportError as e:
    logger.warning(f"Online learning routes not available: {e}")


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'version': API_VERSION,
        'message': 'EasyRec Online API is running',
        'model_status': model.get_model_info(),
        'features': {
            'online_learning': True,
            'streaming_support': True,
            'incremental_updates': True
        }
    })


@app.route('/model/export', methods=['POST'])
def root_model_export():
    """Export current (possibly incrementally trained) model.
    Body: {"export_dir": "models/export/online", "include_incremental": true}
    """
    try:
        data = request.get_json() or {}
        export_dir = data.get('export_dir', 'models/export/online')
        # Reuse sanitizer from online routes if available
        try:
            from api.routes_online import _sanitize_export_dir, get_online_trainer
            ok, sanitized = _sanitize_export_dir(export_dir)
            if not ok:
                return jsonify({'success': False, 'error': sanitized}), 400
            trainer = get_online_trainer()
            include_incremental = data.get('include_incremental', True)
            success = trainer.trigger_model_export(sanitized)
            if not success:
                return jsonify({'success': False, 'error': 'Model export failed'}), 500
            incr = trainer.get_incremental_updates() if include_incremental else None
            return jsonify({'success': True, 'data': {'export_dir': sanitized, 'incremental_updates': incr}})
        except ImportError:
            # Fallback: just succeed with base model info
            return jsonify({'success': False, 'error': 'Online trainer not available'}), 400
    except Exception as e:
        logging.getLogger(__name__).error(f"Error exporting model: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/model/info', methods=['GET'])
def root_model_info():
    """Aggregate model info including online trainer status if present."""
    try:
        base_info = model.get_model_info()
        extra = {}
        try:
            from api.routes_online import get_online_trainer, ALLOWED_EXPORT_BASE
            trainer = get_online_trainer()
            status = trainer.get_training_status()
            latest_checkpoint = status.get('latest_checkpoint')
            num_checkpoints = status.get('num_checkpoints')
            incr = trainer.get_incremental_updates()
            exports = []
            base_export = os.path.normpath(ALLOWED_EXPORT_BASE)
            if os.path.isdir(base_export):
                for entry in os.listdir(base_export):
                    full = os.path.join(base_export, entry)
                    if os.path.isdir(full):
                        try: m = os.path.getmtime(full)
                        except OSError: m = 0.0
                        exports.append({'dir': entry, 'path': full, 'modified': m})
                exports.sort(key=lambda x: x['modified'])
            latest_export = exports[-1] if exports else None
            extra = {
                'online': True,
                'latest_checkpoint': latest_checkpoint,
                'num_checkpoints': num_checkpoints,
                'latest_export': latest_export,
                'exports': exports,
                'incremental_updates': incr
            }
        except ImportError:
            extra = {'online': False}
        return jsonify({'success': True, 'data': {'base_model': base_info, **extra}})
    except Exception as e:
        logging.getLogger(__name__).error(f"Error getting model info: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/predict', methods=['POST'])
def predict_scores():
    """
    Predict scores for user-item pairs
    
    Request body:
    {
        "user_ids": [1, 2, 3],
        "item_ids": [101, 102, 103]
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided'
            }), 400
        
        user_ids = data.get('user_ids', [])
        item_ids = data.get('item_ids', [])
        
        if not user_ids or not item_ids:
            return jsonify({
                'success': False,
                'error': 'user_ids and item_ids are required'
            }), 400
        
        if len(user_ids) != len(item_ids):
            return jsonify({
                'success': False,
                'error': 'user_ids and item_ids must have the same length'
            }), 400
        
        # Get predictions
        scores = model.predict_scores(user_ids, item_ids)
        
        # Format response
        predictions = []
        for i, (user_id, item_id, score) in enumerate(zip(user_ids, item_ids, scores)):
            predictions.append({
                'user_id': user_id,
                'item_id': item_id,
                'score': score
            })
        
        return jsonify({
            'success': True,
            'data': {
                'predictions': predictions,
                'count': len(predictions)
            }
        })
        
    except Exception as e:
        logger.error(f"Error in predict_scores: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/recommend', methods=['POST'])
def recommend_items():
    """
    Get item recommendations for a user
    
    Request body:
    {
        "user_id": 123,
        "candidate_items": [1, 2, 3, 4, 5],
        "top_k": 3
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided'
            }), 400
        
        user_id = data.get('user_id')
        candidate_items = data.get('candidate_items', [])
        top_k = data.get('top_k', 10)
        
        if user_id is None:
            return jsonify({
                'success': False,
                'error': 'user_id is required'
            }), 400
        
        if not candidate_items:
            return jsonify({
                'success': False,
                'error': 'candidate_items list is required'
            }), 400
        
        # Get recommendations
        recommendations = model.recommend_items(user_id, candidate_items, top_k)
        
        return jsonify({
            'success': True,
            'data': {
                'user_id': user_id,
                'recommendations': recommendations,
                'count': len(recommendations)
            }
        })
        
    except Exception as e:
        logger.error(f"Error in recommend_items: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/embeddings/user/<int:user_id>', methods=['GET'])
def get_user_embedding(user_id: int):
    """Get user embedding vector"""
    try:
        embedding = model.get_user_embedding(user_id)
        
        if embedding is None:
            return jsonify({
                'success': False,
                'error': f'User embedding not found for user_id: {user_id}'
            }), 404
        
        return jsonify({
            'success': True,
            'data': {
                'user_id': user_id,
                'embedding': embedding,
                'dimension': len(embedding)
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting user embedding: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/embeddings/item/<int:item_id>', methods=['GET'])
def get_item_embedding(item_id: int):
    """Get item embedding vector"""
    try:
        embedding = model.get_item_embedding(item_id)
        
        if embedding is None:
            return jsonify({
                'success': False,
                'error': f'Item embedding not found for item_id: {item_id}'
            }), 404
        
        return jsonify({
            'success': True,
            'data': {
                'item_id': item_id,
                'embedding': embedding,
                'dimension': len(embedding)
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting item embedding: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500


@app.after_request
def add_version_header(response):
    """Embed X-API-Version header in all responses"""
    response.headers['X-API-Version'] = API_VERSION
    return response


def main():
    """Main function to run the Flask app"""
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting EasyRec API server on port {port}")
    logger.info(f"Debug mode: {debug}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)


if __name__ == '__main__':
    main()
