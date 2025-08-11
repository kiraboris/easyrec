"""
Unit tests for the EasyRec API
"""
import unittest
import json
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.app import app


class TestEasyRecAPI(unittest.TestCase):
    """Test cases for EasyRec API endpoints"""
    
    def setUp(self):
        """Set up test client"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('model_status', data)
    
    def test_model_info(self):
        """Test model info endpoint"""
        response = self.client.get('/model/info')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('data', data)
    
    def test_predict_scores_valid_input(self):
        """Test predict scores endpoint with valid input"""
        payload = {
            'user_ids': [1, 2, 3],
            'item_ids': [101, 102, 103]
        }
        
        response = self.client.post('/predict',
                                   data=json.dumps(payload),
                                   content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertEqual(len(data['data']['predictions']), 3)
    
    def test_predict_scores_invalid_input(self):
        """Test predict scores endpoint with invalid input"""
        # Test missing user_ids
        payload = {'item_ids': [101, 102, 103]}
        
        response = self.client.post('/predict',
                                   data=json.dumps(payload),
                                   content_type='application/json')
        
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('error', data)
    
    def test_predict_scores_mismatched_lengths(self):
        """Test predict scores endpoint with mismatched input lengths"""
        payload = {
            'user_ids': [1, 2],
            'item_ids': [101, 102, 103]  # Different length
        }
        
        response = self.client.post('/predict',
                                   data=json.dumps(payload),
                                   content_type='application/json')
        
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertFalse(data['success'])
    
    def test_recommend_items_valid_input(self):
        """Test recommend items endpoint with valid input"""
        payload = {
            'user_id': 123,
            'candidate_items': [1, 2, 3, 4, 5],
            'top_k': 3
        }
        
        response = self.client.post('/recommend',
                                   data=json.dumps(payload),
                                   content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertEqual(data['data']['user_id'], 123)
        self.assertLessEqual(len(data['data']['recommendations']), 3)
    
    def test_recommend_items_invalid_input(self):
        """Test recommend items endpoint with invalid input"""
        # Test missing user_id
        payload = {
            'candidate_items': [1, 2, 3, 4, 5],
            'top_k': 3
        }
        
        response = self.client.post('/recommend',
                                   data=json.dumps(payload),
                                   content_type='application/json')
        
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('error', data)
    
    def test_recommend_items_empty_candidates(self):
        """Test recommend items endpoint with empty candidate list"""
        payload = {
            'user_id': 123,
            'candidate_items': [],
            'top_k': 3
        }
        
        response = self.client.post('/recommend',
                                   data=json.dumps(payload),
                                   content_type='application/json')
        
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertFalse(data['success'])
    
    def test_get_user_embedding(self):
        """Test get user embedding endpoint"""
        user_id = 123
        response = self.client.get(f'/embeddings/user/{user_id}')
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['user_id'], user_id)
        self.assertIn('embedding', data['data'])
        self.assertIn('dimension', data['data'])
    
    def test_get_item_embedding(self):
        """Test get item embedding endpoint"""
        item_id = 456
        response = self.client.get(f'/embeddings/item/{item_id}')
        
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['item_id'], item_id)
        self.assertIn('embedding', data['data'])
        self.assertIn('dimension', data['data'])
    
    def test_not_found_endpoint(self):
        """Test 404 error handling"""
        response = self.client.get('/nonexistent')
        self.assertEqual(response.status_code, 404)
        
        data = json.loads(response.data)
        self.assertFalse(data['success'])
        self.assertIn('error', data)


class TestRecommendationModel(unittest.TestCase):
    """Test cases for RecommendationModel class"""
    
    def setUp(self):
        """Set up test model"""
        from models.recommendation_model import RecommendationModel
        self.model = RecommendationModel('test_model_dir', 'test_config.prototxt')
    
    def test_predict_scores(self):
        """Test predict_scores method"""
        user_ids = [1, 2, 3]
        item_ids = [101, 102, 103]
        
        scores = self.model.predict_scores(user_ids, item_ids)
        
        self.assertEqual(len(scores), 3)
        self.assertTrue(all(0 <= score <= 1 for score in scores))
    
    def test_recommend_items(self):
        """Test recommend_items method"""
        user_id = 123
        candidate_items = [1, 2, 3, 4, 5]
        top_k = 3
        
        recommendations = self.model.recommend_items(user_id, candidate_items, top_k)
        
        self.assertLessEqual(len(recommendations), top_k)
        
        if recommendations:
            # Check that items are sorted by score (descending)
            scores = [rec['score'] for rec in recommendations]
            self.assertEqual(scores, sorted(scores, reverse=True))
            
            # Check structure of recommendations
            for i, rec in enumerate(recommendations):
                self.assertIn('item_id', rec)
                self.assertIn('score', rec)
                self.assertIn('rank', rec)
                self.assertEqual(rec['rank'], i + 1)
    
    def test_get_embeddings(self):
        """Test embedding methods"""
        user_embedding = self.model.get_user_embedding(123)
        item_embedding = self.model.get_item_embedding(456)
        
        self.assertIsNotNone(user_embedding)
        self.assertIsNotNone(item_embedding)
        self.assertEqual(len(user_embedding), 32)  # Default embedding dimension
        self.assertEqual(len(item_embedding), 32)
    
    def test_model_info(self):
        """Test get_model_info method"""
        info = self.model.get_model_info()
        
        self.assertIn('model_dir', info)
        self.assertIn('config_path', info)
        self.assertIn('model_loaded', info)
        self.assertIn('status', info)


def run_tests():
    """Run all tests"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestEasyRecAPI))
    suite.addTests(loader.loadTestsFromTestCase(TestRecommendationModel))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
