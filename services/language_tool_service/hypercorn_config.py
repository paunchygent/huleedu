from __future__ import annotations

import os

_default_host = "0.0.0.0"
_default_port = 8085  # Default port for Language Tool Service

host = os.getenv("LANGUAGE_TOOL_SERVICE_HOST", _default_host)
port = int(os.getenv("LANGUAGE_TOOL_SERVICE_PORT", _default_port))
bind = f"{host}:{port}"
workers = int(os.getenv("WEB_CONCURRENCY", 1))
worker_class = "asyncio"

loglevel = os.getenv("LANGUAGE_TOOL_SERVICE_LOG_LEVEL", "info").lower()
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", 30))  # Shorter for faster shutdown in dev
keepalive_timeout = int(os.getenv("KEEP_ALIVE_TIMEOUT", 5))