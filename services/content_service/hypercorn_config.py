import os

_default_host = "0.0.0.0"
_default_port = 8000  # Default internal port for this service

bind = f"{os.getenv('HOST', _default_host)}:{int(os.getenv('PORT', _default_port))}"
workers = int(os.getenv("WEB_CONCURRENCY", 1))
worker_class = "asyncio"

loglevel = os.getenv("LOG_LEVEL", "info").lower()
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", 30))  # Shorter for faster shutdown in dev
keepalive_timeout = int(os.getenv("KEEP_ALIVE_TIMEOUT", 5))

# Reloading should be handled by Quart's dev server or other tools if needed
# For Hypercorn, 'reload' is often managed externally or by a wrapper.
# debug = os.getenv("QUART_DEBUG", "False").lower() == "true"
# reload = debug
