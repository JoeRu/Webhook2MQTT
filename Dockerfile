FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --system --no-create-home --uid 10001 app

COPY ./app /app

# Docker lets unprivileged users bind ports < 1024 inside the container
# (net.ipv4.ip_unprivileged_port_start=0), so port 80 is kept for compatibility.
USER app
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:80/healthz', timeout=4).status == 200 else 1)"

CMD ["gunicorn", "--bind", "0.0.0.0:80", "--workers", "2", "--access-logfile", "-", "--graceful-timeout", "10", "main:create_app()"]
