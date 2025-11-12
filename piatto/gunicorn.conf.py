# gunicorn.conf.py
import multiprocessing
import os

# Configuración para manejar SSE y conexiones largas
bind = "0.0.0.0:{}".format(int(os.getenv("PORT", 10000)))
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"

# ✅ CONFIGURACIÓN CRÍTICA para SSE
timeout = 120  # 2 minutos para conexiones largas
keepalive = 5  # Mantener conexiones vivas
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Headers para SSE
def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def pre_fork(server, worker):
    pass

def pre_exec(server):
    server.log.info("Forked child, re-executing.")

def when_ready(server):
    server.log.info("Server is ready. Spawning workers")