import os
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv('REDIS_URL')

# Broker settings
broker_url = REDIS_URL
broker_use_ssl = {
    'ssl_cert_reqs': None
}

# Backend settings
result_backend = REDIS_URL
redis_backend_use_ssl = {
    'ssl_cert_reqs': None
}

# Task settings
task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'UTC'
enable_utc = True

task_routes = {
    'app.celery_worker.process_pr': {'queue': 'celery'},
}

# Worker settings
worker_prefetch_multiplier = 1
worker_lost_wait = 20
task_acks_late = True
task_track_started = True

# Connection settings
broker_connection_retry_on_startup = True
broker_connection_max_retries = 0
broker_pool_limit = None  # Disable connection pooling 

task_time_limit = 300  # Set a time limit of 5 minutes for tasks 