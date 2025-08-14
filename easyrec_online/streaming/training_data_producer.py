"""Training data Kafka producer component.
Provides a unified interface to publish training events to the Kafka topic
consumed by EasyRec's internal online training pipeline.

Priority backend order:
1. confluent_kafka (librdkafka bindings) – best performance / features
2. kafka-python – pure Python fallback
If neither available, falls back to a no-op logger (mock) so the app remains usable.
"""
from __future__ import annotations
import json
import logging
import atexit
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class TrainingDataProducer:
    """Kafka producer for streaming training events.
    Attempts confluent_kafka first, then kafka-python.
    Thread-safety: individual send() calls are safe for low concurrency usage;
    for high throughput you may wrap calls with an external lock or queue.
    """

    def __init__(self,
                 servers: str,
                 topic: str,
                 key_field: Optional[str] = 'user_id',
                 prefer: Optional[str] = None,
                 compression: str = 'lz4',
                 linger_ms: int = 20):
        self.servers = servers
        self.topic = topic
        self.key_field = key_field
        self._impl: Optional[str] = None  # 'confluent' | 'kafka-python' | 'mock'
        self._producer = None
        self._compression = compression
        self._linger_ms = linger_ms
        self._init(prefer)
        atexit.register(self.close)

    # ---------------------- Initialization ----------------------
    def _init(self, prefer: Optional[str]):
        order = []
        if prefer in ('confluent', 'kafka-python'):
            order.append(prefer)
        if 'confluent' not in order:
            order.append('confluent')
        if 'kafka-python' not in order:
            order.append('kafka-python')
        for impl in order:
            try:
                if impl == 'confluent':
                    from confluent_kafka import Producer  # type: ignore
                    conf = {
                        'bootstrap.servers': self.servers,
                        'compression.type': self._compression,
                        'enable.idempotence': True,
                        'acks': 'all',
                        'queue.buffering.max.messages': 200000,
                        'linger.ms': self._linger_ms,
                    }
                    self._producer = Producer(conf)
                    self._impl = impl
                    logger.info("TrainingDataProducer initialized (confluent_kafka)")
                    return
                elif impl == 'kafka-python':
                    from kafka import KafkaProducer  # type: ignore
                    self._producer = KafkaProducer(
                        bootstrap_servers=[s.strip() for s in self.servers.split(',') if s.strip()],
                        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
                        key_serializer=lambda k: k.encode('utf-8') if k is not None else None,
                        retries=3,
                        linger_ms=self._linger_ms,
                        compression_type=self._compression if self._compression in ('gzip','snappy','lz4','zstd') else None
                    )
                    self._impl = impl
                    logger.info("TrainingDataProducer initialized (kafka-python)")
                    return
            except Exception as e:
                logger.debug(f"Failed to init backend '{impl}': {e}")
        # Fallback mock
        self._impl = 'mock'
        logger.warning("No Kafka producer backend available. Falling back to mock logger producer.")

    # ---------------------- Public API ----------------------
    def send(self, sample: Dict[str, Any]) -> bool:
        if self._impl == 'mock':
            logger.debug(f"(mock produce) {sample}")
            return True
        if not self._producer:
            logger.error("Producer not initialized")
            return False
        try:
            key = None
            if self.key_field and sample.get(self.key_field) is not None:
                key = str(sample[self.key_field])
            if self._impl == 'confluent':
                # Serialize manually (bytes required)
                payload = json.dumps(sample, ensure_ascii=False).encode('utf-8')
                self._producer.produce(
                    topic=self.topic,
                    key=key if key else None,
                    value=payload,
                    on_delivery=None  # could be augmented for metrics
                )
                # Poll quickly to serve delivery callbacks / free queue
                self._producer.poll(0)
            else:  # kafka-python
                fut = self._producer.send(
                    self.topic,
                    key=key,
                    value=sample
                )
                # Wait for first few deliveries only to surface early errors
                # (Callers can ignore latency by not awaiting all)
                fut.get(timeout=5)
            return True
        except Exception as e:
            logger.error(f"Send failed: {e}")
            return False

    def send_batch(self, samples: List[Dict[str, Any]]) -> int:
        sent = 0
        for s in samples:
            if self.send(s):
                sent += 1
        # Light flush
        try:
            if self._impl == 'confluent' and self._producer:
                self._producer.poll(0)
            elif self._impl == 'kafka-python' and self._producer:
                self._producer.flush(timeout=2)
        except Exception:
            pass
        if sent != len(samples):
            logger.warning(f"Partial batch publish {sent}/{len(samples)}")
        else:
            logger.info(f"Published {sent} samples to topic '{self.topic}'")
        return sent

    # ---------------------- Cleanup ----------------------
    def close(self):
        try:
            if self._producer:
                try:
                    if self._impl == 'confluent':
                        self._producer.flush(timeout=2)
                    elif self._impl == 'kafka-python':
                        self._producer.flush(timeout=2)
                except Exception:
                    pass
        finally:
            self._producer = None
            # keep _impl to know we were closed (optional)

    # ---------------------- Introspection ----------------------
    @property
    def backend(self) -> str:
        return self._impl or 'unknown'

__all__ = ["TrainingDataProducer"]
