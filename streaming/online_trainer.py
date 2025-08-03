"""
Online Trainer for EasyRec Models
Integrates with Alibaba EasyRec's Online Deep Learning (ODL) framework
"""
import os
import json
import logging
import subprocess
import tempfile
from typing import Dict, List, Optional, Any
from datetime import datetime
import time

logger = logging.getLogger(__name__)


class EasyRecOnlineTrainer:
    """
    Online trainer that integrates with Alibaba EasyRec's ODL system
    Supports incremental updates and real-time model training
    """
    
    def __init__(self, 
                 config_path: str,
                 model_dir: str,
                 base_checkpoint: Optional[str] = None):
        """
        Initialize online trainer
        
        Args:
            config_path: Path to EasyRec configuration file
            model_dir: Directory to save online model checkpoints
            base_checkpoint: Base checkpoint to start from (offline trained model)
        """
        self.config_path = config_path
        self.model_dir = model_dir
        self.base_checkpoint = base_checkpoint
        self.training_process = None
        self.is_training = False
        
        # Ensure model directory exists
        os.makedirs(model_dir, exist_ok=True)
    
    def start_incremental_training(self, 
                                 kafka_config: Dict[str, Any],
                                 update_config: Dict[str, Any] = None) -> bool:
        """
        Start incremental training with streaming data
        
        Args:
            kafka_config: Kafka configuration for streaming input
            update_config: Incremental update configuration
            
        Returns:
            True if training started successfully
        """
        try:
            # Generate online training config
            online_config_path = self._generate_online_config(kafka_config, update_config)
            
            # Start EasyRec online training
            cmd = [
                'python', '-m', 'easy_rec.python.train_eval',
                '--pipeline_config_path', online_config_path,
                '--model_dir', self.model_dir,
                '--continue_train'
            ]
            
            if self.base_checkpoint:
                cmd.extend(['--fine_tune_checkpoint', self.base_checkpoint])
            
            logger.info(f"Starting incremental training: {' '.join(cmd)}")
            
            # Start training process in background
            self.training_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.is_training = True
            logger.info("Incremental training started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start incremental training: {e}")
            return False
    
    def _generate_online_config(self, 
                              kafka_config: Dict[str, Any],
                              update_config: Dict[str, Any] = None) -> str:
        """
        Generate EasyRec configuration for online training
        
        Args:
            kafka_config: Kafka streaming configuration
            update_config: Incremental update configuration
            
        Returns:
            Path to generated config file
        """
        # Read base configuration
        with open(self.config_path, 'r') as f:
            base_config = f.read()
        
        # Create online configuration modifications
        online_modifications = {
            'kafka_train_input': {
                'server': kafka_config.get('servers', 'localhost:9092'),
                'topic': kafka_config.get('topic', 'easyrec_training'),
                'group': kafka_config.get('group', 'easyrec_online'),
                'offset_time': kafka_config.get('offset_time', datetime.now().strftime('%Y%m%d %H:%M:%S'))
            },
            'train_config': {
                'incr_save_config': update_config or {
                    'dense_save_steps': 100,
                    'sparse_save_steps': 100,
                    'fs': {}
                },
                'enable_oss_stop_signal': True,
                'save_checkpoints_steps': 500
            }
        }
        
        # Generate modified config
        online_config = self._modify_config(base_config, online_modifications)
        
        # Save to temporary file
        temp_config = tempfile.NamedTemporaryFile(
            mode='w', suffix='.config', delete=False
        )
        temp_config.write(online_config)
        temp_config.close()
        
        logger.info(f"Generated online config: {temp_config.name}")
        return temp_config.name
    
    def _modify_config(self, base_config: str, modifications: Dict) -> str:
        """
        Modify EasyRec configuration with online training parameters
        
        This is a simplified version - in production, you'd want to use
        proper protobuf parsing/modification
        """
        modified_config = base_config
        
        # Add Kafka input configuration
        kafka_config = modifications.get('kafka_train_input', {})
        kafka_section = f"""
kafka_train_input {{
  server: '{kafka_config.get('server', 'localhost:9092')}'
  topic: '{kafka_config.get('topic', 'easyrec_training')}'
  group: '{kafka_config.get('group', 'easyrec_online')}'
  offset_time: '{kafka_config.get('offset_time', '20240101 00:00:00')}'
}}
"""
        
        # Add incremental update configuration
        train_config_mods = modifications.get('train_config', {})
        incr_config = train_config_mods.get('incr_save_config', {})
        
        incr_section = f"""
  incr_save_config {{
    dense_save_steps: {incr_config.get('dense_save_steps', 100)}
    sparse_save_steps: {incr_config.get('sparse_save_steps', 100)}
    fs {{}}
  }}
  enable_oss_stop_signal: {str(train_config_mods.get('enable_oss_stop_signal', True)).lower()}
"""
        
        # Insert modifications into config
        # This is a simple text replacement - production should use proper parsing
        if 'train_config' in modified_config:
            # Insert incremental config into existing train_config
            modified_config = modified_config.replace(
                'train_config {',
                f'train_config {{\n{incr_section}'
            )
        
        # Add Kafka input section
        modified_config = kafka_section + '\n' + modified_config
        
        return modified_config
    
    def stop_training(self) -> bool:
        """
        Stop incremental training
        
        Returns:
            True if stopped successfully
        """
        try:
            if self.training_process and self.is_training:
                # Create stop signal file (EasyRec ODL feature)
                stop_signal_path = os.path.join(self.model_dir, 'OSS_STOP_SIGNAL')
                with open(stop_signal_path, 'w') as f:
                    f.write('stop')
                
                # Wait for process to finish
                self.training_process.wait(timeout=30)
                
                # Clean up stop signal
                if os.path.exists(stop_signal_path):
                    os.remove(stop_signal_path)
                    
                self.is_training = False
                logger.info("Incremental training stopped")
                return True
                
        except Exception as e:
            logger.error(f"Error stopping training: {e}")
            # Force terminate if needed
            if self.training_process:
                self.training_process.terminate()
                self.is_training = False
        
        return False
    
    def get_training_status(self) -> Dict[str, Any]:
        """
        Get current training status
        
        Returns:
            Dictionary with training status information
        """
        status = {
            'is_training': self.is_training,
            'model_dir': self.model_dir,
            'config_path': self.config_path,
            'base_checkpoint': self.base_checkpoint
        }
        
        if self.training_process:
            status['process_id'] = self.training_process.pid
            status['return_code'] = self.training_process.poll()
        
        # Check for latest checkpoint
        try:
            checkpoints = self._list_checkpoints()
            if checkpoints:
                status['latest_checkpoint'] = checkpoints[-1]
                status['num_checkpoints'] = len(checkpoints)
        except Exception as e:
            logger.error(f"Error getting checkpoint info: {e}")
        
        return status
    
    def _list_checkpoints(self) -> List[str]:
        """List available checkpoints in model directory"""
        checkpoints = []
        try:
            for file in os.listdir(self.model_dir):
                if file.endswith('.meta'):
                    checkpoint_name = file[:-5]  # Remove .meta extension
                    checkpoints.append(os.path.join(self.model_dir, checkpoint_name))
            
            checkpoints.sort(key=lambda x: os.path.getmtime(x + '.meta'))
            
        except Exception as e:
            logger.error(f"Error listing checkpoints: {e}")
        
        return checkpoints
    
    def trigger_model_export(self, export_dir: str) -> bool:
        """
        Export the latest model for serving
        
        Args:
            export_dir: Directory to export the model
            
        Returns:
            True if export successful
        """
        try:
            os.makedirs(export_dir, exist_ok=True)
            
            cmd = [
                'python', '-m', 'easy_rec.python.export',
                '--pipeline_config_path', self.config_path,
                '--export_dir', export_dir,
                '--checkpoint_path', self.model_dir
            ]
            
            logger.info(f"Exporting model: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Model exported successfully to {export_dir}")
                return True
            else:
                logger.error(f"Model export failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error exporting model: {e}")
            return False
    
    def add_training_data(self, samples: List[Dict[str, Any]]) -> bool:
        """
        Add training samples for incremental learning
        
        This is a simplified version - in production, samples would be
        sent to Kafka/DataHub for streaming consumption
        
        Args:
            samples: List of training samples
            
        Returns:
            True if samples added successfully
        """
        try:
            # In a real implementation, this would:
            # 1. Format samples according to EasyRec format
            # 2. Send to Kafka topic
            # 3. Let the streaming trainer consume them
            
            logger.info(f"Adding {len(samples)} training samples")
            
            # Mock implementation - log samples
            for i, sample in enumerate(samples[:5]):  # Log first 5 samples
                logger.debug(f"Sample {i}: {sample}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding training samples: {e}")
            return False
    
    def get_incremental_updates(self) -> Dict[str, Any]:
        """
        Get information about incremental model updates
        
        Returns:
            Dictionary with update information
        """
        try:
            incr_save_dir = os.path.join(self.model_dir, 'incr_save')
            
            if not os.path.exists(incr_save_dir):
                return {'available': False, 'message': 'No incremental updates found'}
            
            # List update files
            update_files = []
            for file in os.listdir(incr_save_dir):
                if file.endswith('.update'):
                    file_path = os.path.join(incr_save_dir, file)
                    update_files.append({
                        'file': file,
                        'path': file_path,
                        'size': os.path.getsize(file_path),
                        'modified': os.path.getmtime(file_path)
                    })
            
            return {
                'available': len(update_files) > 0,
                'update_files': update_files,
                'count': len(update_files)
            }
            
        except Exception as e:
            logger.error(f"Error getting incremental updates: {e}")
            return {'available': False, 'error': str(e)}
