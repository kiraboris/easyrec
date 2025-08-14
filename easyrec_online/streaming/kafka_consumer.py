"""
Kafka Consumer for Streaming Training Data
Integrates with Alibaba EasyRec's Online Deep Learning (ODL) framework
"""
import json
import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime
import time

try:
    from kafka import KafkaConsumer, TopicPartition
    from kafka.errors import KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    KafkaConsumer = None
    TopicPartition = None

logger = logging.getLogger(__name__)


class EasyRecKafkaConsumer:
    """
    Kafka consumer for EasyRec online training
    Compatible with EasyRec's ODL (Online Deep Learning) format
    """
    
    def __init__(self, 
                 servers: str,
                 topic: str,
                 group: str,
                 offset_time: Optional[str] = None,
                 offset_info: Optional[str] = None):
        """
        Initialize Kafka consumer for EasyRec ODL
        
        Args:
            servers: Kafka bootstrap servers (comma-separated)
            topic: Kafka topic to consume from
            group: Consumer group ID
            offset_time: Start time for reading data ('YYYYMMDD HH:MM:SS' or unix timestamp)
            offset_info: JSON string with partition offset info
        """
        if not KAFKA_AVAILABLE:
            raise ImportError("kafka-python is required for streaming functionality")
        
        self.servers = servers
        self.topic = topic
        self.group = group
        self.offset_time = offset_time
        self.offset_info = offset_info
        self.consumer = None
        self.running = False
        
    def connect(self):
        """Connect to Kafka"""
        try:
            self.consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.servers.split(','),
                group_id=self.group,
                value_deserializer=lambda x: x.decode('utf-8'),
                key_deserializer=lambda x: x.decode('utf-8') if x else None,
                enable_auto_commit=True,
                auto_commit_interval_ms=5000,
                consumer_timeout_ms=1000
            )
            
            # Set up offset positioning
            self._setup_offsets()
            
            logger.info(f"Connected to Kafka topic: {self.topic}")
            return True
            
        except KafkaError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            return False
    
    def _setup_offsets(self):
        """Set up offset positioning based on offset_time or offset_info"""
        if self.offset_info:
            # Use specific partition offsets
            try:
                offset_data = json.loads(self.offset_info)
                partitions = []
                
                for partition_str, offset in offset_data.items():
                    partition_id = int(partition_str)
                    tp = TopicPartition(self.topic, partition_id)
                    partitions.append(tp)
                
                self.consumer.assign(partitions)
                
                for partition_str, offset in offset_data.items():
                    partition_id = int(partition_str)
                    tp = TopicPartition(self.topic, partition_id)
                    self.consumer.seek(tp, offset)
                
                logger.info(f"Set specific offsets: {offset_data}")
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Invalid offset_info format: {e}")
                
        elif self.offset_time:
            # Use timestamp to find offset
            try:
                if self.offset_time.isdigit():
                    timestamp = int(self.offset_time) * 1000  # Convert to milliseconds
                else:
                    # Parse datetime string
                    dt = datetime.strptime(self.offset_time, '%Y%m%d %H:%M:%S')
                    timestamp = int(dt.timestamp() * 1000)
                
                # Get partitions for topic
                partitions = self.consumer.partitions_for_topic(self.topic)
                if partitions:
                    topic_partitions = [TopicPartition(self.topic, p) for p in partitions]
                    
                    # Get offsets for timestamp
                    offset_map = self.consumer.offsets_for_times({
                        tp: timestamp for tp in topic_partitions
                    })
                    
                    # Seek to the offsets
                    for tp, offset_metadata in offset_map.items():
                        if offset_metadata:
                            self.consumer.seek(tp, offset_metadata.offset)
                    
                    logger.info(f"Set offsets for timestamp: {self.offset_time}")
                
            except ValueError as e:
                logger.error(f"Invalid offset_time format: {e}")
    
    def consume_batch(self, batch_size: int = 100, timeout: int = 10) -> List[Dict]:
        """
        Consume a batch of messages
        
        Args:
            batch_size: Maximum messages per batch
            timeout: Timeout in seconds
            
        Returns:
            List of training samples in EasyRec format
        """
        if not self.consumer:
            if not self.connect():
                return []
        
        messages = []
        start_time = time.time()
        
        try:
            for message in self.consumer:
                # Parse EasyRec training sample
                sample = self._parse_message(message)
                if sample:
                    messages.append(sample)
                
                # Check batch size and timeout
                if len(messages) >= batch_size:
                    break
                    
                if time.time() - start_time > timeout:
                    break
                    
        except Exception as e:
            logger.error(f"Error consuming messages: {e}")
        
        logger.info(f"Consumed {len(messages)} messages")
        return messages
    
    def _parse_message(self, message) -> Optional[Dict]:
        """
        Parse Kafka message into EasyRec training sample format
        
        Message format:
        - Key: sample_id (request_id, user_id, item_id)  
        - Value: CSV format sample data
        """
        try:
            # Extract sample metadata from key
            sample_key = message.key or ""
            
            # Parse CSV sample data from value
            sample_data = message.value
            
            if not sample_data:
                return None
            
            # Split CSV fields
            fields = sample_data.strip().split(',')
            
            # Create sample dict (customize based on your data format)
            sample = {
                'key': sample_key,
                'data': sample_data,
                'fields': fields,
                'partition': message.partition,
                'offset': message.offset,
                'timestamp': message.timestamp,
                'raw_message': message
            }
            
            return sample
            
        except Exception as e:
            logger.error(f"Error parsing message: {e}")
            return None
    
    def stream_consume(self, callback: Callable[[Dict], None], 
                      batch_size: int = 100) -> None:
        """
        Start streaming consumption with callback
        
        Args:
            callback: Function to process each batch of samples
            batch_size: Messages per batch
        """
        self.running = True
        logger.info("Starting streaming consumption...")
        
        try:
            while self.running:
                batch = self.consume_batch(batch_size, timeout=5)
                if batch:
                    callback(batch)
                    
        except KeyboardInterrupt:
            logger.info("Stopping streaming consumption...")
        except Exception as e:
            logger.error(f"Error in streaming consumption: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop consumption and close consumer"""
        self.running = False
        if self.consumer:
            self.consumer.close()
            logger.info("Kafka consumer stopped")
    
    def get_current_offsets(self) -> Dict[int, int]:
        """Get current offsets for all partitions"""
        if not self.consumer:
            return {}
        
        offsets = {}
        try:
            partitions = self.consumer.assignment()
            for tp in partitions:
                offset = self.consumer.position(tp)
                offsets[tp.partition] = offset
                
        except Exception as e:
            logger.error(f"Error getting offsets: {e}")
        
        return offsets


# Mock implementation for testing when Kafka is not available
class MockKafkaConsumer:
    """Mock Kafka consumer for testing"""
    
    def __init__(self, *args, **kwargs):
        self.running = False
        logger.warning("Using mock Kafka consumer - Kafka not available")
    
    def connect(self):
        return True
    
    def consume_batch(self, batch_size=100, timeout=10):
        # Return mock data
        import random
        import time
        
        time.sleep(1)  # Simulate network delay
        
        mock_samples = []
        for i in range(min(batch_size, 10)):  # Limit mock data
            sample = {
                'key': f'user_{random.randint(1, 1000)}_item_{random.randint(1, 500)}',
                'data': f'{random.randint(0, 1)},{random.randint(1, 1000)},{random.randint(1, 500)},{random.random():.4f}',
                'fields': ['label', 'user_id', 'item_id', 'rating'],
                'partition': 0,
                'offset': i,
                'timestamp': int(time.time() * 1000)
            }
            mock_samples.append(sample)
        
        return mock_samples
    
    def stream_consume(self, callback, batch_size=100):
        self.running = True
        while self.running:
            batch = self.consume_batch(batch_size)
            if batch:
                callback(batch)
            time.sleep(2)
    
    def stop(self):
        self.running = False
    
    def get_current_offsets(self):
        return {0: 12345}


# Use mock if Kafka is not available
if not KAFKA_AVAILABLE:
    EasyRecKafkaConsumer = MockKafkaConsumer
