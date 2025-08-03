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
        'message': 'EasyRec Online API is running',
        'model_status': model.get_model_info(),
        'features': {
            'online_learning': True,
            'streaming_support': True,
            'incremental_updates': True
        }
    })


@app.route('/model/info', methods=['GET'])
def model_info():
    """Get model information"""
    try:
        info = model.get_model_info()
        return jsonify({
            'success': True,
            'data': info
        })
    except Exception as e:
        logger.error(f"Error getting model info: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


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


def main():
    """Main function to run the Flask app"""
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting EasyRec API server on port {port}")
    logger.info(f"Debug mode: {debug}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)


if __name__ == '__main__':
    main()
