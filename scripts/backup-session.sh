#!/bin/sh
set -eu

DATA_VOLUME_NAME="${DATA_VOLUME_NAME:-telegram-data}"
BACKUP_DIR="${BACKUP_DIR:-/root/backups}"
TIMESTAMP="$(date +%Y%m%d-%H%M)"

mkdir -p "${BACKUP_DIR}"

docker run --rm \
  -v "${DATA_VOLUME_NAME}:/data" \
  -v "${BACKUP_DIR}:/backup" \
  alpine tar czf "/backup/telegram-session-${TIMESTAMP}.tar.gz" -C /data .

echo "Backup created at ${BACKUP_DIR}/telegram-session-${TIMESTAMP}.tar.gz"
