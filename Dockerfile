# Dockerfile
FROM python:3.11-slim

# Evitar bytecode y forzar flush de logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Crea usuario no root
RUN useradd -ms /bin/bash appuser

WORKDIR /app

# Copia requirements e instala
COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

# Copia código
COPY . /app

# Crea directorios persistentes
RUN mkdir -p /app/data /app/logs \
    && chown -R appuser:appuser /app

# Entrypoint para restaurar sesión si se provee por variable
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Healthcheck performed in pure Python to avoid extra OS packages
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request as r, sys; \
    resp = r.urlopen('http://127.0.0.1:8000/health', timeout=3); \
    sys.exit(0 if resp.getcode() == 200 else 1)"

# Ejecuta
USER appuser
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "app.main:app"]