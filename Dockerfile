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
RUN mkdir -p /app/data /app/logs

# Healthcheck performed in pure Python to avoid extra OS packages
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request as r; r.urlopen('http://127.0.0.1:8000/', timeout=3)"

# Ejecuta
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app.main:app"]