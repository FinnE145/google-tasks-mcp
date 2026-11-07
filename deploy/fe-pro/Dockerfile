# Google Tasks MCP on fe-pro; see deploy/fe-pro/docker-compose.yml and fe-pro's SERVER.md.
# Code and Python's files stay root-owned; the container runs as tasksmcp (2009) and writes only /data.
FROM python:3.12.12-slim-bookworm
# Secrets come from the compose env_file, not a .env in the image. FastMCP keeps its OAuth proxy state (client
# registrations, signing keys) under XDG_DATA_HOME, so it survives restarts and the connector stays authorised.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src HOME=/tmp XDG_DATA_HOME=/data/xdg
WORKDIR /app
COPY deploy/fe-pro/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt
COPY src ./src
COPY scripts ./scripts
EXPOSE 45690
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:45690/health', timeout=4)"
# server.py's __main__ binds 127.0.0.1, which another container can't reach; the factory runs the same app.
CMD ["uvicorn", "--factory", "tasks_bridge.server:build_starlette_app", "--host", "0.0.0.0", "--port", "45690", \
     "--proxy-headers", "--forwarded-allow-ips", "172.31.71.20"]
