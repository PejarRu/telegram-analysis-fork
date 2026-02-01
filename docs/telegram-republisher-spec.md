# Telegram Translation + Republisher — SPEC

## Rol

Actúa como **ingeniero senior** especializado en:

- Telegram (MTProto + Bot API)
- n8n
- Sistemas de automatización con LLMs

Tu tarea no es solo implementar, sino **auditar, corregir y mejorar** un sistema en producción.

---

## Accesos disponibles

- MCP de n8n (configurado en `.vscode/mcp.json`)
- Código local de una API custom basada en **Telethon**
- Workflow existente en **n8n**
- VPS con la API Telethon desplegada

---

## Datos del entorno (fuente de verdad)

- Canal origen: `@knyazevinvest`
- Canal destino (chat_id): `-4673324381`
- Dominio API Telethon: `https://api-telegram.antonberzins.com`
- Auth header: `X-API-Key` (ya configurado en n8n)
- Endpoint principal:
  - `POST /trigger`
  - Body ejemplo:
    ```json
    {
      "entity": "@knyazevinvest",
      "limit": 2
    }
    ```
- Respuesta esperada:
  - Array de mensajes Telethon
  - Campos relevantes:
    - `id`
    - `date`
    - `message` (texto)
    - `media` (si existe)
    - `grouped_id` (si álbum)

- Código local API Telethon:
  - El usuario indicará la ruta para inspección directa

---

## Contexto general

Existe un workflow en n8n llamado:

🟢 **Telegram Translation + Republisher**

El sistema lleva **semanas en producción** y funciona parcialmente, pero presenta **problemas críticos de consistencia**.

---

## Objetivo del sistema

- Leer mensajes de un canal/grupo público usando **Telethon (MTProto)**
- Filtrar y traducir contenido informativo al español
- Republicar en un canal propio usando **Bot API**
- Eliminar publicidad, promociones y CTAs
- Mantener fidelidad total al texto original:
  - estructura
  - listas
  - emojis
  - tono
- Evitar duplicados
- Idealmente clonar también la **imagen del post original**

---

## Flujo actual (alto nivel)

1. Trigger (Schedule / Manual)
2. HTTP Request → API Telethon (`/trigger`)
3. Split Out → 1 item = 1 mensaje
4. Set / Mapeado:
   - `id`
   - `text`
   - `date`
   - `link = https://t.me/<grupo>/<id>`
   - `media` (si existe)
5. Remove Duplicates (por `id`)
6. AI Agent:
   - Decide qué hacer con el mensaje
7. Telegram Tool:
   - Envía texto al canal destino

---

## Validación CRÍTICA (anti-mismatch)

Para **cada mensaje** debe cumplirse:

- El `id` usado para:
  - el texto
  - el link
  - la deduplicación  
  **es exactamente el mismo**
- El link debe ser:
https://t.me/<username_origen>/<id>

yaml
Copiar código
- El texto enviado debe provenir del mismo objeto que generó el link

Si aparece cualquier inconsistencia:
- Auditar Split / Set / Variables
- Auditar entity usada en la API
- Auditar lógica de offsets, orden o cache en Telethon

El sistema debe poder explicar **por qué** cada mensaje enviado corresponde exactamente a ese link.

---

## Problemas detectados en producción

### ❌ 1. Mensajes incorrectos

- El texto publicado **no coincide** con el mensaje real del link
- El link apunta a un post diferente

👉 Esto es un **bug crítico** y tiene prioridad máxima.

---

### ❌ 2. Imágenes NO clonadas

- Telethon devuelve `MessageMediaPhoto`
- No existe URL pública oficial
- Enviar texto + link NO genera preview
- Manualmente sí

---

### ❌ 3. API Telethon posiblemente incompleta

La API creció sin diseño previo.

Posibles carencias:
- Manejo incorrecto de:
- `entity`
- `chat_id` vs `channel_id`
- No tratamiento de:
- álbumes (`grouped_id`)
- media compleja
- Orden incorrecto de mensajes

👉 Se permite modificar la API.

---

## Definición de “clonar imagen”

Mínimo viable:

- Si el mensaje tiene **1 foto**:
- Enviar esa foto al canal destino
- Usar la traducción como caption

Opcional:
- Si es álbum (`grouped_id`):
- Enviar solo la primera imagen
- O todas si es trivial

---

## Misión (orden de prioridad)

### 1️⃣ Auditoría total

- Workflow n8n
- API Telethon
- Construcción de links
- IDs reales de Telegram
- Inputs al AI Agent

---

### 2️⃣ Duplicar workflow

Trabajar SOLO sobre la copia.

Nombre sugerido:
🧪 **Telegram Translation + Republisher (Image + Audit)**

---

### 3️⃣ Lógica funcional final

Para cada mensaje:

#### A. Publicidad pura
👉 NO hacer nada

#### B. Mixto
👉 Traducir solo la parte informativa  
👉 Eliminar completamente la parte promocional

#### C. Informativo
👉 Traducir fielmente, sin resumir

---

### 4️⃣ Publicación

Enviar al canal destino:

- Texto traducido
- Link al original
- Imagen original (si existe y es viable)

---

### 5️⃣ Clonado de imágenes (CRÍTICO)

Investigar con el stack actual:

- Descargar imagen vía Telethon
- Servirla desde la API como binary
- Consumirla desde n8n (`Download: true`)
- Enviarla vía `Telegram Send Photo`

❗ Si NO es viable:
- DETENERSE
- Explicar exactamente:
- Qué lo impide
- Por qué
- Qué alternativas existen:
  - ForwardMessage
  - CopyMessage
  - User account
  - Bot + user híbrido
  - Storage intermedio
  - Aceptar solo texto + link

⚠️ No inventar soluciones irreales.

---

## Edge cases obligatorios

- Mensajes vacíos
- Mensajes editados
- Álbumes (`grouped_id`)
- Videos / documentos
- Captions largas (límite Telegram)
- Rate limits
- Fallos de descarga de media
- Fallos al enviar imagen
- Dedupe tras reinicio de n8n
- Mensajes reenviados (`forwarded`)

---

## Reglas

- Usar MCP de n8n
- No scraping HTML de `t.me`
- No asumir viabilidad sin verificar en Telethon
- Documentar decisiones técnicas
- Priorizar robustez a workarounds frágiles

---

## Resultado esperado

### ✅ Estado A – Solución completa
- Mensajes correctos
- Texto fiel
- Imagen clonada
- Workflow estable

### ❌ Estado B – Bloqueo justificado
- Explicación clara del bloqueo
- Qué parte del stack lo impide
- Alternativas técnicas reales

---

## Nota final

Este sistema es **a largo plazo**.

Prefiero:
- Una limitación bien explicada  
antes que  
- Una solución frágil o falsa.

