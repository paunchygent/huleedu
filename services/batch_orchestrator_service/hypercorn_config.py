from config import settings

bind = f"{settings.HOST}:{settings.PORT}"
workers = settings.WEB_CONCURRENCY
worker_class = "asyncio"

loglevel = settings.LOG_LEVEL.lower()
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

graceful_timeout = settings.GRACEFUL_TIMEOUT
keepalive_timeout = settings.KEEP_ALIVE_TIMEOUT
