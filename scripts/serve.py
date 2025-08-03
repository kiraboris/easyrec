"""
Model serving script using Gunicorn
"""
import os
import sys
import multiprocessing

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.app import app

def number_of_workers():
    """Calculate number of workers based on CPU cores"""
    return (multiprocessing.cpu_count() * 2) + 1

def main():
    """Main serving function"""
    # Configuration
    bind_address = f"0.0.0.0:{os.getenv('PORT', 5000)}"
    workers = int(os.getenv('WORKERS', number_of_workers()))
    timeout = int(os.getenv('TIMEOUT', 120))
    log_level = os.getenv('LOG_LEVEL', 'info')
    
    # Gunicorn configuration
    options = {
        'bind': bind_address,
        'workers': workers,
        'worker_class': 'sync',
        'timeout': timeout,
        'keepalive': 2,
        'max_requests': 1000,
        'max_requests_jitter': 100,
        'preload_app': True,
        'worker_connections': 1000,
        'loglevel': log_level,
        'access_logfile': '-',
        'error_logfile': '-',
    }
    
    print(f"Starting EasyRec API server with {workers} workers on {bind_address}")
    
    # Import and start Gunicorn
    try:
        from gunicorn.app.base import BaseApplication
        
        class StandaloneApplication(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()
            
            def load_config(self):
                for key, value in self.options.items():
                    self.cfg.set(key.lower(), value)
            
            def load(self):
                return self.application
        
        StandaloneApplication(app, options).run()
        
    except ImportError:
        print("Gunicorn not installed, falling back to Flask development server")
        app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)

if __name__ == '__main__':
    main()
