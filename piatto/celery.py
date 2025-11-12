# piatto/celery.py
import os
from celery import Celery

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'piatto.settings')

app = Celery('piatto')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Use database as broker (ZERO COST)
app.conf.broker_url = 'django-db://'
app.conf.result_backend = 'django-db://'

# Optional configuration
app.conf.task_always_eager = False
app.conf.task_acks_late = True
app.conf.worker_prefetch_multiplier = 1

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')