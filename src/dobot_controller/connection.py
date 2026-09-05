"""Módulo de detección y diagnóstico de puertos de conexión para Dobot Magician."""

import os
import grp
from typing import List, Dict, Optional
from serial.tools import list_ports

# VIDs conocidos para adaptadores USB-Serie del Dobot Magician
KNOWN_DOBOT_VIDS = {
    0x10C4: "Silicon Labs CP210x (Dobot Estándar)",
    0x1A86: "WCH CH340 (Adaptador Serie Alternativo)",
}


def list_serial_ports(include_empty_ttys: bool = False) -> List[Dict[str, any]]:
    """
    Retorna una lista de puertos serie disponibles.
    Por defecto oculta puertos ttyS legados no conectados.
    """
    available = []
    for port in list_ports.comports():
        # Filtrar puertos virtuales vacíos comunes en placas base Linux (/dev/ttyS0 - 31)
        if not include_empty_ttys and port.device.startswith("/dev/ttyS") and port.vid is None:
            continue

        is_dobot_candidate = port.vid in KNOWN_DOBOT_VIDS
        available.append({
            "device": port.device,
            "description": port.description,
            "vid": hex(port.vid) if port.vid is not None else None,
            "pid": hex(port.pid) if port.pid is not None else None,
            "hwid": port.hwid,
            "is_dobot": is_dobot_candidate,
            "chip_info": KNOWN_DOBOT_VIDS.get(port.vid, "Desconocido")
        })
    return available


def find_dobot_port() -> Optional[str]:
    """Busca automáticamente el primer puerto que coincida con el hardware de Dobot Magician."""
    for port in list_ports.comports():
        if port.vid in KNOWN_DOBOT_VIDS:
            return port.device

    # Si no coincide el VID pero hay un /dev/ttyUSB0 o /dev/ttyACM0 disponible, retornarlo como fallback
    for fallback in ["/dev/dobot_magician", "/dev/ttyUSB0", "/dev/ttyACM0"]:
        if os.path.exists(fallback):
            return fallback

    return None


def check_dialout_permission() -> Dict[str, any]:
    """Verifica si el usuario actual pertenece al grupo dialout para acceder a puertos serie en Ubuntu."""
    user = os.getenv("USER", "")
    try:
        dialout_group = grp.getgrnam("dialout")
        # En Linux, un usuario puede estar en gr_mem o tener dialout como grupo suplementario efectivo
        in_group = user in dialout_group.gr_mem
        if not in_group:
            import subprocess
            res = subprocess.run(["groups", user], capture_output=True, text=True)
            if "dialout" in res.stdout:
                in_group = True
    except Exception:
        in_group = True

    return {
        "user": user,
        "in_dialout": in_group,
        "fix_command": f"sudo usermod -a -G dialout {user}"
    }
