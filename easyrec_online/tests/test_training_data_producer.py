import sys
import types
import unittest
from unittest import mock

# Ensure project root on path
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestTrainingDataProducer(unittest.TestCase):
    def setUp(self):
        # Import after potential sys.modules manipulation in individual tests
        pass

    def test_fallback_to_mock_when_backends_unavailable(self):
        # Simulate absence / failure of both confluent_kafka and kafka
        if 'confluent_kafka' in sys.modules:
            del sys.modules['confluent_kafka']
        if 'kafka' in sys.modules:
            del sys.modules['kafka']
        # Create dummy modules that raise on Producer init
        failing_confluent = types.ModuleType('confluent_kafka')
        class _BadProducer:  # noqa
            def __init__(self, *a, **kw):
                raise RuntimeError('fail')
        failing_confluent.Producer = _BadProducer  # type: ignore
        failing_kafka = types.ModuleType('kafka')
        class _BadKafkaProducer:  # noqa
            def __init__(self, *a, **kw):
                raise RuntimeError('fail')
        failing_kafka.KafkaProducer = _BadKafkaProducer  # type: ignore
        sys.modules['confluent_kafka'] = failing_confluent
        sys.modules['kafka'] = failing_kafka

        from streaming.training_data_producer import TrainingDataProducer  # import after stubbing
        prod = TrainingDataProducer(servers='localhost:9092', topic='t')
        self.assertEqual(prod.backend, 'mock')
        ok_single = prod.send({'user_id': 1, 'label': 1})
        ok_batch = prod.send_batch([{'user_id': 1}, {'user_id': 2}])
        self.assertTrue(ok_single)
        self.assertEqual(ok_batch, 2)

    def test_send_batch_partial(self):
        # Force mock backend and patch send to fail one item
        from streaming.training_data_producer import TrainingDataProducer
        prod = TrainingDataProducer(servers='localhost:9092', topic='t')
        # Force to mock regardless of environment
        prod._impl = 'mock'
        calls = {'n': 0}
        real_send = prod.send
        def _send(sample):
            calls['n'] += 1
            if calls['n'] == 2:
                return False
            return real_send(sample)
        prod.send = _send  # type: ignore
        count = prod.send_batch([{'user_id': 1}, {'user_id': 2}, {'user_id': 3}])
        self.assertEqual(count, 2)

    def test_key_field_usage(self):
        # Provide custom key field
        from streaming.training_data_producer import TrainingDataProducer
        prod = TrainingDataProducer(servers='localhost:9092', topic='t', key_field='custom')
        prod._impl = 'mock'  # ensure no real send
        with mock.patch('logging.Logger.debug') as dbg:
            prod.send({'custom': 'abc', 'v': 1})
            # Ensure some debug call happened (mock backend path)
            self.assertTrue(dbg.called)

if __name__ == '__main__':
    unittest.main()
