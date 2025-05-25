import os

_default_host = "0.0.0.0"
_default_port = 5000

bind = f"{os.getenv('HOST', _default_host)}:{int(os.getenv('PORT', _default_port))}"
workers = int(os.getenv("WEB_CONCURRENCY", 1))
worker_class = "asyncio"

loglevel = os.getenv("LOG_LEVEL", "info").lower()
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", 30))
keepalive_timeout = int(os.getenv("KEEP_ALIVE_TIMEOUT", 5))
