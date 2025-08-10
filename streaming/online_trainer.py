"""
Online Trainer for EasyRec Models
Integrates with Alibaba EasyRec's Online Deep Learning (ODL) framework
"""
import os
# removed unused json import
import logging
import subprocess
import tempfile
from typing import Dict, List, Optional, Any
from datetime import datetime
import time
import threading
import re
import sys
from collections import deque
import select  # used for non-blocking I/O in log consumption
import atexit

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
        self._lock = threading.RLock()
        self._temp_config_path: Optional[str] = None
        self._log_threads: List[threading.Thread] = []
        self._stop_logs_event = threading.Event()
        self.stdout_log_path = os.path.join(self.model_dir, 'online_train_stdout.log')
        self.stderr_log_path = os.path.join(self.model_dir, 'online_train_stderr.log')
        self._log_tail_cache = {
            'stdout': deque(maxlen=500),
            'stderr': deque(maxlen=500)
        }
        self._max_log_size = 5 * 1024 * 1024  # 5MB per file before rotation
        # Watchdog / lifecycle
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_stop_event = threading.Event()
        self._heartbeat_ts: float = time.time()
        self._restart_count: int = 0
        self.max_restarts: int = 3
        self.restart_backoff_sec: int = 10
        self._last_start_params: Dict[str, Any] = {}
        self._tail_lock = threading.Lock()
        # Log rotation retention
        self._log_retention = 5  # keep last 5 rotated files
        # Watchdog interval configurable
        self.watchdog_interval_sec = 5
        # Heartbeat & hung detection thresholds
        self.heartbeat_timeout_sec = 30  # if no progress/logs within this, considered stale
        self.hung_restart_sec = 90       # if stale for this long, trigger restart
        self._last_progress_ts: float = time.time()
        self._last_checkpoint_mtime: float = 0.0
        # Ensure model directory exists
        os.makedirs(model_dir, exist_ok=True)
        # Register atexit cleanup
        atexit.register(self._atexit_cleanup)

    def start_incremental_training(self, 
                                 kafka_config: Dict[str, Any],
                                 update_config: Optional[Dict[str, Any]] = None,
                                 max_restarts: int = 3,
                                 restart_backoff_sec: int = 10,
                                 env_overrides: Optional[Dict[str, str]] = None,
                                 watchdog_interval_sec: int = 5) -> bool:
        """
        Start incremental training with streaming data
        
        Args:
            kafka_config: Kafka configuration for streaming input
            update_config: Incremental update configuration
            max_restarts: Maximum number of restart attempts if the training process exits
            restart_backoff_sec: Backoff time in seconds before restarting the training process
            env_overrides: Environment variable overrides for the training process
            
        Returns:
            True if training started successfully
        """
        with self._lock:
            if self.is_training:
                logger.warning("Training already in progress")
                return False
            try:
                self.watchdog_interval_sec = max(1, watchdog_interval_sec)
                self._restart_count = 0
                safe_kafka = dict(kafka_config) if kafka_config else {}
                safe_update = None if update_config is None else dict(update_config)
                # Basic validation (improved)
                missing = [k for k in ('servers','topic') if k not in safe_kafka or not safe_kafka.get(k)]
                if missing:
                    logger.error(f"Missing required kafka_config fields: {missing}")
                    return False
                # Validate servers format host:port[,host:port]
                servers = safe_kafka.get('servers','')
                bad_parts = []
                for part in servers.split(','):
                    part = part.strip()
                    if not part:
                        continue
                    if ':' not in part:
                        bad_parts.append(part)
                        continue
                    h, p = part.rsplit(':',1)
                    if not h or not p.isdigit():
                        bad_parts.append(part)
                if bad_parts:
                    logger.error(f"Invalid Kafka bootstrap servers entries: {bad_parts}")
                    return False
                if self._temp_config_path and os.path.exists(self._temp_config_path):
                    try: os.remove(self._temp_config_path)
                    except OSError: pass
                online_config_path = self._generate_online_config(safe_kafka, safe_update)
                self._temp_config_path = online_config_path
                cmd = [
                    sys.executable, '-m', 'easy_rec.python.train_eval',
                    '--pipeline_config_path', online_config_path,
                    '--model_dir', self.model_dir,
                    '--continue_train'
                ]
                if self.base_checkpoint:
                    cmd.extend(['--fine_tune_checkpoint', self.base_checkpoint])
                logger.info(f"Starting incremental training: {' '.join(cmd)}")
                full_env = os.environ.copy()
                if env_overrides:
                    full_env.update({k: str(v) for k, v in env_overrides.items()})
                self.training_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    env=full_env
                )
                self.is_training = True
                self._stop_logs_event.clear()
                # Reset progress metrics
                self._heartbeat_ts = time.time()
                self._last_progress_ts = self._heartbeat_ts
                self._last_checkpoint_mtime = 0.0
                self._start_log_threads()
                # Early failure detection window
                time.sleep(0.5)
                rc_early = self.training_process.poll()
                if rc_early is not None:
                    # Collect initial stderr
                    try:
                        initial_err = self.training_process.stderr.read() if self.training_process.stderr else ''
                        if initial_err:
                            for line in initial_err.splitlines():
                                with self._tail_lock:
                                    self._log_tail_cache['stderr'].append(line)
                    except Exception:
                        pass
                    logger.error(f"Training process exited immediately with code {rc_early}")
                    self._stop_log_threads(join_timeout=1.0)
                    self.training_process = None
                    self.is_training = False
                    return False
                self.max_restarts = max_restarts
                self.restart_backoff_sec = restart_backoff_sec
                self._last_start_params = {
                    'kafka_config': safe_kafka,
                    'update_config': safe_update,
                    'env_overrides': dict(env_overrides) if env_overrides else None,
                }
                self._start_watchdog()
                logger.info("Incremental training started successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to start incremental training: {e}")
                if self.training_process and self.training_process.poll() is None:
                    try: self.training_process.kill()
                    except Exception: pass
                self.training_process = None
                self.is_training = False
                return False
    
    def _generate_online_config(self, 
                              kafka_config: Dict[str, Any],
                              update_config: Optional[Dict[str, Any]] = None) -> str:
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
                'incr_save_config': (
                    {
                        'dense_save_steps': 100,
                        'sparse_save_steps': 100,
                        'fs': {}
                    } if update_config is None else update_config
                ),
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
        Safer than naive string replace: inserts incr section only once, preserves rest.
        """
        modified_config = base_config
        def _esc(val: str) -> str:
            return str(val).replace("'", "\\'").replace('\n', ' ')
        # Build Kafka section
        kafka_config = modifications.get('kafka_train_input', {})
        kafka_section = (
            "kafka_train_input {\n"
            f"  server: '{_esc(kafka_config.get('server', 'localhost:9092'))}'\n"
            f"  topic: '{_esc(kafka_config.get('topic', 'easyrec_training'))}'\n"
            f"  group: '{_esc(kafka_config.get('group', 'easyrec_online'))}'\n"
            f"  offset_time: '{_esc(kafka_config.get('offset_time', '20240101 00:00:00'))}'\n"
            "}\n\n"
        )
        
        # Incremental update section
        train_config_mods = modifications.get('train_config', {})
        incr_config = train_config_mods.get('incr_save_config', {})
        incr_section = (
            f"  incr_save_config {{\n"
            f"    dense_save_steps: {incr_config.get('dense_save_steps', 100)}\n"
            f"    sparse_save_steps: {incr_config.get('sparse_save_steps', 100)}\n"
            f"    fs {{}}\n"
            f"  }}\n"
            f"  enable_oss_stop_signal: {str(train_config_mods.get('enable_oss_stop_signal', True)).lower()}\n"
        )
        
        # Insert Kafka section at beginning if not present
        pattern_kafka = re.compile(r'^[ \t]*kafka_train_input\s*{', re.MULTILINE)
        if not pattern_kafka.search(modified_config):
            modified_config = kafka_section + modified_config
        
        # Regex to find train_config block opening
        pattern = re.compile(r'(^\s*train_config\s*{)', re.MULTILINE)
        if pattern.search(modified_config) and 'incr_save_config' not in modified_config:
            modified_config = pattern.sub(r"\1\n" + incr_section, modified_config, count=1)
        elif 'incr_save_config' in modified_config:
            logger.debug("Incremental section already present; skipping insert")
        else:
            # Append a new train_config if none exists (edge case)
            modified_config += f"\ntrain_config {{\n{incr_section}}}\n"
        
        return modified_config
    
    def _rotate_if_needed(self, path: str):
        try:
            if os.path.exists(path) and os.path.getsize(path) > self._max_log_size:
                ts = datetime.utcnow().strftime('%Y%m%d%H%M%S')
                new_name = f"{path}.{ts}"
                os.rename(path, new_name)
                # Apply retention
                base = os.path.basename(path)
                dir_ = os.path.dirname(path)
                rotated = [f for f in os.listdir(dir_) if f.startswith(base + '.')]
                if len(rotated) > self._log_retention:
                    # Sort by time extracted from suffix
                    def _suffix_time(fn):
                        try: return int(fn.rsplit('.',1)[-1])
                        except Exception: return 0
                    for old in sorted(rotated, key=_suffix_time)[:-self._log_retention]:
                        try: os.remove(os.path.join(dir_, old))
                        except OSError: pass
        except Exception as e:
            logger.warning(f"Log rotation failed for {path}: {e}")
    
    def _log_consumer(self, stream, path: str, cache_key: str):
        """Non-blocking-ish consumer using select to allow timely shutdown."""
        try:
            fileno = None
            try:
                fileno = stream.fileno()
            except Exception:
                pass
            while not self._stop_logs_event.is_set():
                if fileno is not None:
                    r, _, _ = select.select([stream], [], [], 1.0)
                    if not r:
                        continue
                line = stream.readline()
                if not line:
                    # If process ended, break; else small sleep
                    if not self.training_process or self.training_process.poll() is not None:
                        break
                    time.sleep(0.2)
                    continue
                self._heartbeat_ts = time.time()
                self._rotate_if_needed(path)
                try:
                    with open(path, 'a', encoding='utf-8') as f:
                        f.write(line)
                except Exception:
                    pass
                with self._tail_lock:
                    self._log_tail_cache[cache_key].append(line.rstrip('\n'))
        except Exception as e:
            logger.warning(f"Log consumer error for {cache_key}: {e}")

    def _start_log_threads(self):
        if not self.training_process:
            return
        stdout_thread = threading.Thread(target=self._log_consumer, args=(self.training_process.stdout, self.stdout_log_path, 'stdout'), daemon=True)
        stderr_thread = threading.Thread(target=self._log_consumer, args=(self.training_process.stderr, self.stderr_log_path, 'stderr'), daemon=True)
        self._log_threads = [stdout_thread, stderr_thread]
        for t in self._log_threads:
            t.start()
    
    def _stop_log_threads(self, join_timeout: float = 3.0):
        self._stop_logs_event.set()
        for t in self._log_threads:
            try: t.join(timeout=join_timeout)
            except Exception: pass
        self._log_threads = []
        # Close underlying pipes to unblock readers
        try:
            if self.training_process and self.training_process.stdout:
                self.training_process.stdout.close()
        except Exception:
            pass
        try:
            if self.training_process and self.training_process.stderr:
                self.training_process.stderr.close()
        except Exception:
            pass
    
    # Progress / heartbeat helpers
    def _update_progress_from_checkpoints(self):
        try:
            latest_mtime = self._last_checkpoint_mtime
            for entry in os.listdir(self.model_dir):
                full = os.path.join(self.model_dir, entry)
                if entry.endswith('.meta') or entry.endswith('.index') or (entry.startswith('savedmodel') and os.path.isdir(full)):
                    try:
                        m = os.path.getmtime(full)
                        if m > latest_mtime:
                            latest_mtime = m
                    except OSError:
                        pass
            if latest_mtime > self._last_checkpoint_mtime:
                self._last_checkpoint_mtime = latest_mtime
                self._last_progress_ts = time.time()
                return True
        except Exception:
            pass
        return False

    def update_restart_policy(self, max_restarts: Optional[int] = None, backoff_sec: Optional[int] = None):
        with self._lock:
            if max_restarts is not None:
                self.max_restarts = max(0, max_restarts)
            if backoff_sec is not None:
                self.restart_backoff_sec = max(0, backoff_sec)
            return {'max_restarts': self.max_restarts, 'restart_backoff_sec': self.restart_backoff_sec}

    def manual_restart(self) -> bool:
        """Manual restart disabled intentionally."""
        logger.info("manual_restart called but feature is disabled")
        return False

    def _start_watchdog(self):
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            return
        self._watchdog_stop_event.clear()
        def _run():
            while not self._watchdog_stop_event.is_set():
                # granularity
                for _ in range(self.watchdog_interval_sec):
                    if self._watchdog_stop_event.is_set():
                        return
                    time.sleep(1)
                restart_needed = False
                restart_reason_rc = None
                with self._lock:
                    if not self.is_training or not self.training_process:
                        continue
                    rc = self.training_process.poll()
                    if rc is None:
                        # Check for hung (no new logs & no checkpoints)
                        since_hb = time.time() - self._heartbeat_ts
                        if since_hb > self.heartbeat_timeout_sec:
                            progressed = self._update_progress_from_checkpoints()
                            if progressed:
                                self._heartbeat_ts = time.time()
                            elif since_hb > self.hung_restart_sec:
                                if self._restart_count < self.max_restarts:
                                    self._restart_count += 1
                                    restart_needed = True
                                    restart_reason_rc = f'hung>{since_hb:.0f}s'
                                    logger.warning(f"Training appears hung for {since_hb:.0f}s. Restart {self._restart_count}/{self.max_restarts}")
                                else:
                                    logger.error("Training hung and restart limit reached; stopping")
                                    self.is_training = False
                                    self._stop_logs_event.set()
                        continue
                    # Process exited
                    if self._restart_count < self.max_restarts and not self._stop_logs_event.is_set():
                        self._restart_count += 1
                        restart_needed = True
                        restart_reason_rc = rc
                        logger.warning(f"Training process exited with code {rc}. Scheduling restart {self._restart_count}/{self.max_restarts} after backoff")
                    else:
                        logger.error(f"Training process exited with code {rc}; no more restarts")
                        self.is_training = False
                        self._stop_logs_event.set()
                        break
                if restart_needed:
                    for _ in range(self.restart_backoff_sec):
                        if self._watchdog_stop_event.is_set():
                            return
                        time.sleep(1)
                    with self._lock:
                        if (not self.is_training) or self._watchdog_stop_event.is_set():
                            break
                        try:
                            params = self._last_start_params
                            if self._temp_config_path and os.path.exists(self._temp_config_path):
                                try: os.remove(self._temp_config_path)
                                except OSError: pass
                            kafka_cfg = params.get('kafka_config') or {}
                            update_cfg = params.get('update_config')
                            online_config_path = self._generate_online_config(kafka_cfg, update_cfg)
                            self._temp_config_path = online_config_path
                            cmd = [
                                sys.executable, '-m', 'easy_rec.python.train_eval',
                                '--pipeline_config_path', online_config_path,
                                '--model_dir', self.model_dir,
                                '--continue_train'
                            ]
                            if self.base_checkpoint:
                                cmd.extend(['--fine_tune_checkpoint', self.base_checkpoint])
                            full_env = os.environ.copy()
                            if params.get('env_overrides'):
                                full_env.update({k: str(v) for k, v in params['env_overrides'].items()})
                            self._stop_log_threads(join_timeout=1.0)
                            self._stop_logs_event.clear()
                            self.training_process = subprocess.Popen(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                                bufsize=1,
                                env=full_env
                            )
                            self._start_log_threads()
                            self._heartbeat_ts = time.time()
                            self._last_progress_ts = self._heartbeat_ts
                            logger.info(f"Training process restarted successfully (reason={restart_reason_rc})")
                        except Exception as e:
                            logger.error(f"Failed to restart training after reason={restart_reason_rc}: {e}")
                            self.is_training = False
                            self._stop_logs_event.set()
                            break
        self._watchdog_thread = threading.Thread(target=_run, name='easyrec_watchdog', daemon=True)
        self._watchdog_thread.start()

    def get_health(self) -> Dict[str, Any]:
        """Return heartbeat age, restart stats and process status."""
        with self._lock:
            age = time.time() - self._heartbeat_ts
            rc = self.training_process.poll() if self.training_process else None
            return {
                'is_training': self.is_training,
                'heartbeat_age_sec': age,
                'restarts': self._restart_count,
                'max_restarts': self.max_restarts,
                'process_return_code': rc,
            }
    
    def stop_training(self, timeout: int = 60) -> bool:
        """
        Stop incremental training gracefully.
        """
        with self._lock:
            if not self.training_process or not self.is_training:
                return False
            try:
                # Create stop signal file (EasyRec ODL feature)
                stop_signal_path = os.path.join(self.model_dir, 'OSS_STOP_SIGNAL')
                with open(stop_signal_path, 'w') as f:
                    f.write('stop')
                
                # Poll for graceful shutdown
                start_time = time.time()
                while time.time() - start_time < timeout:
                    rc = self.training_process.poll()
                    if rc is not None:
                        break
                    time.sleep(2)
                
                if self.training_process.poll() is None:
                    logger.warning("Training did not exit gracefully; terminating")
                    self.training_process.terminate()
                    try:
                        self.training_process.wait(10)
                    except subprocess.TimeoutExpired:
                        logger.error("Terminate timeout; killing process")
                        self.training_process.kill()
                
                self._stop_logs_event.set()
                self._watchdog_stop_event.set()
                # Allow log threads to drain
                self._stop_log_threads(join_timeout=5)
                
                # Clean up stop signal
                if os.path.exists(stop_signal_path):
                    os.remove(stop_signal_path)
                
                # Remove temporary config file
                if self._temp_config_path and os.path.exists(self._temp_config_path):
                    try:
                        os.remove(self._temp_config_path)
                    except OSError:
                        pass
                self._temp_config_path = None
                
                self.is_training = False
                # capture watchdog thread for join
                watchdog_thread = self._watchdog_thread
                self._watchdog_thread = None
                # set training_process to None after stop
                self.training_process = None
                logger.info("Incremental training stopped")
            except Exception as e:
                logger.error(f"Error stopping training: {e}")
                if self.training_process:
                    try:
                        self.training_process.kill()
                    except Exception:
                        pass
                self.is_training = False
                watchdog_thread = self._watchdog_thread
                self._watchdog_thread = None
            finally:
                # join watchdog outside lock scope
                pass
        # join outside lock to avoid deadlocks
        if 'watchdog_thread' in locals() and watchdog_thread:
            try:
                watchdog_thread.join(timeout=5)
            except Exception:
                pass
        return not self.is_training
    
    def get_training_status(self) -> Dict[str, Any]:
        """
        Get current training status including log tail
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
        
        # Add log tails
        status['log_tail'] = self.tail_logs(20)
        status['restarts'] = self._restart_count
        status['max_restarts'] = self.max_restarts
        status['watchdog_interval_sec'] = self.watchdog_interval_sec
        status['heartbeat_age_sec'] = time.time() - self._heartbeat_ts
        status['last_progress_age_sec'] = time.time() - self._last_progress_ts
        return status
    
    def tail_logs(self, lines: int = 50, stream: str = 'both') -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        with self._tail_lock:
            if stream in ('stdout', 'both'):
                result['stdout'] = list(self._log_tail_cache['stdout'])[-lines:]
            if stream in ('stderr', 'both'):
                result['stderr'] = list(self._log_tail_cache['stderr'])[-lines:]
        return result
    
    def _list_checkpoints(self) -> List[str]:
        checkpoints = []
        try:
            # TF1 style .meta based checkpoints
            meta_files = [f for f in os.listdir(self.model_dir) if f.endswith('.meta')]
            for file in meta_files:
                checkpoints.append(os.path.join(self.model_dir, file[:-5]))
            # TF2 style checkpoint index (.index) files
            index_files = [f for f in os.listdir(self.model_dir) if f.endswith('.index')]
            for file in index_files:
                base = file[:-6]
                path_base = os.path.join(self.model_dir, base)
                if path_base not in checkpoints:
                    checkpoints.append(path_base)
            # SavedModel exported directories (savedmodel-* pattern)
            for entry in os.listdir(self.model_dir):
                if entry.startswith('savedmodel') and os.path.isdir(os.path.join(self.model_dir, entry)):
                    checkpoints.append(os.path.join(self.model_dir, entry))
            # Sort by modification time of underlying files/dirs
            def _mtime(p: str) -> float:
                target = p + '.meta' if os.path.exists(p + '.meta') else (p + '.index' if os.path.exists(p + '.index') else p)
                try:
                    return os.path.getmtime(target)
                except OSError:
                    return 0.0
            checkpoints = sorted(set(checkpoints), key=_mtime)
        except Exception as e:
            logger.error(f"Error listing checkpoints: {e}")
        return checkpoints
    
    def trigger_model_export(self, export_dir: str) -> bool:
        """
        Export the latest model for serving
        """
        try:
            os.makedirs(export_dir, exist_ok=True)
            cmd = [
                sys.executable, '-m', 'easy_rec.python.export',
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
        Add training samples for incremental learning (mock)
        """
        try:
            logger.info(f"Adding {len(samples)} training samples (mock)")
            for i, sample in enumerate(samples[:5]):
                logger.debug(f"Sample {i}: {sample}")
            return True
        except Exception as e:
            logger.error(f"Error adding training samples: {e}")
            return False
    
    def get_incremental_updates(self) -> Dict[str, Any]:
        """
        Get information about incremental model updates
        """
        try:
            incr_save_dir = os.path.join(self.model_dir, 'incr_save')
            if not os.path.exists(incr_save_dir):
                return {'available': False, 'message': 'No incremental updates found'}
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

    def _atexit_cleanup(self):
        try:
            if self.training_process and self.training_process.poll() is None:
                logger.info("Atexit: stopping training process")
                try:
                    self.training_process.terminate()
                    self.training_process.wait(timeout=5)
                except Exception:
                    try: self.training_process.kill()
                    except Exception: pass
        except Exception:
            pass
