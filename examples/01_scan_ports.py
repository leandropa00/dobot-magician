#!/usr/bin/env python3
"""Ejemplo 1: Escaneo y diagnóstico de puertos serie en Ubuntu."""

from dobot_controller.connection import list_serial_ports, find_dobot_port, check_dialout_permission

def main():
    print("=== Diagnóstico de Puertos para Dobot Magician ===")
    
    # 1. Comprobar permisos
    perm = check_dialout_permission()
    print(f"Usuario: {perm['user']}")
    print(f"Grupo dialout: {'✔ Asignado' if perm['in_dialout'] else '✖ FALTA ASIGNAR'}")
    if not perm["in_dialout"]:
        print(f"  -> Ejecuta: {perm['fix_command']}")
    print("-" * 50)

    # 2. Listar puertos disponibles
    ports = list_serial_ports()
    print(f"Puertos serie activos encontrados: {len(ports)}")
    for p in ports:
        print(f"  - Dispositivo: {p['device']}")
        print(f"    Descripción: {p['description']}")
        print(f"    VID:PID: {p['vid']}:{p['pid']}")
        print(f"    ¿Es Dobot?: {'SÍ' if p['is_dobot'] else 'No'}")
        print()

    # 3. Puerto recomendado
    dobot_port = find_dobot_port()
    if dobot_port:
        print(f"✔ Dobot Magician detectado automáticamente en: {dobot_port}")
    else:
        print("✖ No se detectó ningún puerto Dobot Magician activo.")

if __name__ == "__main__":
    main()
