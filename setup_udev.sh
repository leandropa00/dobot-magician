#!/usr/bin/env bash
# Script para configurar reglas udev y permisos para Dobot Magician en Ubuntu

set -e

echo "=== Configuración de permisos udev para Dobot Magician ==="

if [ "$EUID" -ne 0 ]; then
    echo "Solicitando permisos de administrador (sudo)..."
    exec sudo bash "$0" "$@"
fi

RULES_FILE="$(dirname "$0")/udev/99-dobot.rules"
TARGET_RULES="/etc/udev/rules.d/99-dobot.rules"

if [ -f "$RULES_FILE" ]; then
    echo "Copiando reglas udev a $TARGET_RULES..."
    cp "$RULES_FILE" "$TARGET_RULES"
    chmod 644 "$TARGET_RULES"
else
    echo "Error: No se encontró el archivo $RULES_FILE"
    exit 1
fi

echo "Recargando reglas udev..."
udevadm control --reload-rules
udevadm trigger

CURRENT_USER="${SUDO_USER:-$USER}"
if [ -n "$CURRENT_USER" ]; then
    echo "Asegurando que el usuario '$CURRENT_USER' pertenezca al grupo dialout..."
    usermod -a -G dialout "$CURRENT_USER"
fi

echo "✔ Configuración udev completada con éxito."
echo "Si acabas de agregar tu usuario a dialout, es recomendable cerrar e iniciar sesión."
