# gunicorn_config.py
bind       = "0.0.0.0:5000"
workers    = 1           # must be 1 for SocketIO with eventlet
worker_class = "eventlet"
timeout    = 120
keepalive  = 5
accesslog  = "/var/log/securechat/access.log"
errorlog   = "/var/log/securechat/error.log"
loglevel   = "info"
