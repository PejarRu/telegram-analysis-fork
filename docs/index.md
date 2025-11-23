# Telegram Analysis API

Bienvenido a la referencia rápida del servicio que expone mensajes de Telegram mediante Flask + Telethon.

## Características clave

- Cliente único de Telethon compartido por todos los endpoints.
- Enriquecimiento de mensajes con enlaces firmados para archivos multimedia.
- Reenvío opcional a webhooks (incluido listener en tiempo real).
- Despliegue simple via Docker + Dokploy/Traefik.

## Requisitos previos

1. Crea un archivo `.env` a partir de `.env.example` y rellénalo con tus credenciales de Telegram y `API_KEY`.
2. Genera la sesión de Telethon una vez:
   ```bash
   python -m app.auth
   ```
3. Monta el archivo de sesión (p. ej. `@usuario.session`) en `data/` tanto en local como en producción.

## Ejecutar en local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

La API escucha en `http://127.0.0.1:5000/`.

### Ejemplos

```bash
curl -X POST http://127.0.0.1:5000/trigger \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: ${API_KEY}" \
  -d '{"entity": "@telegram", "limit": 2}'

curl "http://127.0.0.1:5000/message?entity=@telegram&message_id=123" \
  -H "X-API-Key: ${API_KEY}"
```

## Endpoints principales

| Método | Ruta | Descripción |
| --- | --- | --- |
| `POST` | `/trigger` | Recupera `limit` mensajes recientes y opcionalmente los envía a un webhook. |
| `GET` | `/message` | Devuelve un mensaje concreto por ID manteniendo el formato de `/trigger`. |
| `GET` | `/media/<token>` | Sirve archivos mediante enlaces firmados (`signed_url`). |
| `GET` | `/last-response` | Expone el último payload persistido (requiere API key). |
| `GET` | `/` | Página HTML con documentación y versión del servicio. |

Todos los endpoints salvo `/media/<token>` requieren `X-API-Key: <API_KEY>` o `Authorization: Bearer <API_KEY>`.

## Variables de entorno destacadas

- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`, `TELEGRAM_USERNAME` — credenciales básicas.
- `TELEGRAM_SESSION_FILE`, `TELEGRAM_SESSION_DIR` — dónde se almacena la sesión (.session) autorizada.
- `API_KEY` — clave compartida obligatoria para proteger los endpoints.
- `N8N_WEBHOOK_URL` — destino por defecto cuando un payload debe reenviarse.
- `TELEGRAM_MEDIA_DIR`, `MEDIA_BASE_URL` — controlan dónde se descargan y exponen los archivos.
- `MEDIA_SIGNING_SECRET`, `MEDIA_URL_TTL_SECONDS` — parámetros de los enlaces firmados para `/media/<token>`.
- `TELEGRAM_LISTENER_ENTITY`, `LISTENER_WEBHOOK_URL` — activan el listener en tiempo real.

Consulta `app/config.py` para ver el listado completo y los valores por defecto.

## Despliegue en producción (resumen)

1. Copia el archivo de sesión autorizado al servidor y móntalo en `/app/data` dentro del contenedor.
2. Configura las variables de entorno en Dokploy (o el orquestador que uses).
3. Despliega usando el Dockerfile incluido. Gunicorn expone el puerto interno `8000`.
4. Tras el despliegue, valida con:
   ```bash
   curl -X POST https://tu-dominio/trigger \
     -H 'Content-Type: application/json' \
     -H 'X-API-Key: <tu-clave>' \
     -d '{"entity": "@telegram", "limit": 1}'
   ```

## Listener en tiempo real

Define las variables:

```bash
TELEGRAM_LISTENER_ENTITY=@tu_canal
LISTENER_WEBHOOK_URL=https://n8n.dominio.com/webhook/telegram-live
```

El servicio lanzará un hilo que escucha `NewMessage`, descarga medios y envía cada payload al webhook configurado; el último mensaje queda persistido en `data/last_response.json`.

## Inspeccionar el último payload

```bash
curl https://tu-dominio/last-response \
  -H 'X-API-Key: <tu-clave>'
```

Recibirás el JSON almacenado o `{"message": "No response yet"}` si aún no existe.

## Documentación estática

Este sitio se genera con [MkDocs Material](https://squidfunk.github.io/mkdocs-material/). Para modificarlo:

```bash
pip install -r requirements-docs.txt
mkdocs serve
```

Abre `http://127.0.0.1:8000/` (el que usa MkDocs) para previsualizar. Cuando estés listo publica con `mkdocs build` o `mkdocs gh-deploy`.
