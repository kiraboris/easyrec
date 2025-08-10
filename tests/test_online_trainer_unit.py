import os
import sys
import unittest
import tempfile
import json
from unittest import mock

# Add project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from streaming.online_trainer import EasyRecOnlineTrainer

DUMMY_BASE_CONFIG = """
model_config { name: 'x' }
train_config { save_checkpoints_steps: 100 }
""".strip()

class TestEasyRecOnlineTrainerUnit(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_file = os.path.join(self.tmpdir.name, 'config.prototxt')
        with open(self.config_file, 'w') as f:
            f.write(DUMMY_BASE_CONFIG)
        self.model_dir = os.path.join(self.tmpdir.name, 'model')
        os.makedirs(self.model_dir, exist_ok=True)
        self.trainer = EasyRecOnlineTrainer(
            config_path=self.config_file,
            model_dir=self.model_dir,
            base_checkpoint=None
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_generate_online_config_basic(self):
        kafka_cfg = {'servers': 'k1:9092', 'topic': 't1', 'group': 'g1'}
        path = self.trainer._generate_online_config(kafka_cfg, update_config={'dense_save_steps':50,'sparse_save_steps':60,'fs':{}})
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            content = f.read()
        self.assertIn('kafka_train_input', content)
        self.assertIn("topic: 't1'", content)
        self.assertIn('incr_save_config', content)

    def test_modify_config_idempotent(self):
        kafka_cfg = {'servers': 'k1:9092', 'topic': 't1', 'group': 'g1'}
        path1 = self.trainer._generate_online_config(kafka_cfg)
        with open(path1) as f:
            once = f.read()
        # Run again using the already modified file as base
        path2 = self.trainer._generate_online_config(kafka_cfg)
        with open(path2) as f:
            twice = f.read()
        # Ensure we did not duplicate kafka_train_input blocks
        self.assertEqual(once.count('kafka_train_input'), twice.count('kafka_train_input'))

    def test_update_restart_policy(self):
        result = self.trainer.update_restart_policy(max_restarts=5, backoff_sec=20)
        self.assertEqual(result['max_restarts'], 5)
        self.assertEqual(result['restart_backoff_sec'], 20)

    def test_add_training_data_mock(self):
        ok = self.trainer.add_training_data([{'user_id':1,'item_id':2,'label':1}])
        self.assertTrue(ok)

    @mock.patch('subprocess.Popen')
    def test_start_incremental_training_validation(self, popen_mock):
        # Fail missing servers
        bad = {'topic': 't'}
        ok = self.trainer.start_incremental_training(bad)
        self.assertFalse(ok)
        # Good config
        popen_proc = mock.Mock()
        popen_proc.poll.return_value = None
        popen_mock.return_value = popen_proc
        good = {'servers': 'k1:9092', 'topic': 'tt', 'group': 'gg'}
        ok = self.trainer.start_incremental_training(good)
        self.assertTrue(ok)
        self.assertTrue(self.trainer.is_training)

    def test_tail_logs_empty(self):
        logs = self.trainer.tail_logs(10)
        self.assertIn('stdout', logs)
        self.assertIn('stderr', logs)

if __name__ == '__main__':
    unittest.main()
