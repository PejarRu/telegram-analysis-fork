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
RUN mkdir -p /app/data /app/logs && chown -R appuser:appuser /app
USER appuser

# (Opcional) healthcheck simple: proceso vivo
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD pgrep -f "python" || exit 1

# Ejecuta
CMD ["python", "-m", "app.main"]