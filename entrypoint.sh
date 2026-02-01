#!/bin/sh
set -eu

SESSION_DIR="${TELEGRAM_SESSION_DIR:-/app/data}"
SESSION_FILE="${TELEGRAM_SESSION_FILE:-${TELEGRAM_USERNAME:-session}}"

case "${SESSION_FILE}" in
    /*) SESSION_PATH="${SESSION_FILE}" ;;
    *) SESSION_PATH="${SESSION_DIR}/${SESSION_FILE}" ;;
esac

mkdir -p "${SESSION_DIR}"

if [ -n "${TELEGRAM_SESSION_B64:-}" ]; then
    if [ ! -s "${SESSION_PATH}" ]; then
        echo "Restoring Telegram session from TELEGRAM_SESSION_B64..."
        echo "${TELEGRAM_SESSION_B64}" | base64 -d > "${SESSION_PATH}"
        chmod 600 "${SESSION_PATH}"
    else
        echo "Existing session found at ${SESSION_PATH}; skipping restore."
    fi
fi

exec "$@"
