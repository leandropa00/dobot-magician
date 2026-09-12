"""
Utilidades para detección, configuración y activación de GoPro vía USB en Linux.
Soporta:
1. GoPro Connect (Webcam over USB / CDC-NCM Ethernet / HTTP API).
2. Detección de dispositivos V4L2 (/dev/video*).
"""

import os
import glob
import subprocess
import socket
import logging
import requests
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def list_v4l2_devices() -> List[Dict[str, Any]]:
    """Lista los dispositivos de video V4L2 disponibles en el sistema."""
    devices = []
    video_paths = sorted(glob.glob("/dev/video*"))
    for path in video_paths:
        dev_info = {"path": path, "name": "Dispositivo V4L2", "accessible": os.access(path, os.R_OK)}
        # Intentar obtener el nombre del dispositivo vía sysfs
        try:
            device_num = path.replace("/dev/video", "")
            sysfs_name_path = f"/sys/class/video4linux/video{device_num}/name"
            if os.path.exists(sysfs_name_path):
                with open(sysfs_name_path, "r") as f:
                    dev_info["name"] = f.read().strip()
        except Exception:
            pass
        devices.append(dev_info)
    return devices


def find_gopro_usb_device() -> Optional[Dict[str, str]]:
    """
    Busca si la cámara GoPro está físicamente conectada y enumerada en el bus USB
    usando lsusb (Vendor ID 0x2672 = GoPro, Inc.).
    """
    try:
        result = subprocess.run(["lsusb"], capture_output=True, text=True, check=True)
        for line in result.stdout.strip().split("\n"):
            line_lower = line.lower()
            if "2672:" in line_lower or "gopro" in line_lower:
                return {"description": line.strip()}
    except Exception as e:
        logger.debug(f"Error ejecutando lsusb: {e}")
    return None


def find_gopro_network_interface() -> Optional[Dict[str, str]]:
    """
    Busca interfaces de red físicas creadas por GoPro vía USB (CDC-NCM / RNDIS).
    La GoPro normalmente asigna una subred en 172.2X.1XX.0/24 o 10.5.5.0/24.
    """
    ignored_prefixes = ("docker", "br-", "veth", "virbr", "lo", "wlp", "wlan")
    try:
        result = subprocess.run(["ip", "-o", "-4", "addr", "show"], capture_output=True, text=True, check=True)
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 4:
                iface_name = parts[1]
                cidr = parts[3]
                ip_addr = cidr.split("/")[0]

                # Ignorar interfaces virtuales de contenedores, bridges o wifi
                if any(iface_name.startswith(p) for p in ignored_prefixes):
                    continue

                # Subredes típicas de GoPro (172.2X.xxx o 10.5.5.x)
                if ip_addr.startswith("172.") and (".2" in ip_addr or ".1" in ip_addr):
                    octets = ip_addr.split(".")
                    gopro_ip = f"{octets[0]}.{octets[1]}.{octets[2]}.51"
                    return {"interface": iface_name, "host_ip": ip_addr, "gopro_ip": gopro_ip}
                elif ip_addr.startswith("10.5.5."):
                    return {"interface": iface_name, "host_ip": ip_addr, "gopro_ip": "10.5.5.9"}

        # Si no encontramos IP asignada, verificar si existe una interfaz USB de red creada pero sin IP aún
        link_result = subprocess.run(["ip", "-o", "link", "show"], capture_output=True, text=True, check=True)
        for line in link_result.stdout.strip().split("\n"):
            parts = line.split(":")
            if len(parts) >= 2:
                iface_name = parts[1].strip()
                if iface_name.startswith("usb") or iface_name.startswith("enx"):
                    return {
                        "interface": iface_name,
                        "host_ip": "Sin IP (DHCP pendiente)",
                        "gopro_ip": "Pendiente",
                        "needs_dhcp": True
                    }
    except Exception as e:
        logger.debug(f"Error detectando interfaz GoPro: {e}")
    return None


def activate_gopro_webcam(gopro_ip: str, resolution: str = "1080", fov: str = "0", timeout: float = 3.0) -> bool:
    """
    Envía la solicitud HTTP a la GoPro para activar el modo de streaming por USB.
    Soporta Hero 8/9/10/11 y Hero 12 Black (Open GoPro).
    
    Args:
        gopro_ip: Dirección IP de la GoPro (ej. 172.2X.1XX.51 o 10.5.5.9).
        resolution: '1080' o '720' o '12' (Hero 12).
        fov: Campo de visión ('0' = Wide, '4' = Linear, etc.).
    
    Returns:
        True si la GoPro respondió con éxito al comando de inicio de webcam.
    """
    if gopro_ip in ("Pendiente", "Sin IP (DHCP pendiente)"):
        return False

    # Probar endpoint estándar de Webcam
    urls_to_try = [
        f"http://{gopro_ip}:8080/gopro/webcam/start?res={resolution}&fov={fov}",
        # Open GoPro Hero 12 res=12 (1080p)
        f"http://{gopro_ip}:8080/gopro/webcam/start?res=12&fov={fov}",
        # Fallback a Open GoPro live preview stream
        f"http://{gopro_ip}:8080/gopro/camera/stream/start"
    ]

    for url in urls_to_try:
        try:
            logger.info(f"Probando activación en {url}...")
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                logger.info("GoPro stream activado exitosamente.")
                return True
        except requests.exceptions.RequestException:
            continue
    return False


def stop_gopro_webcam(gopro_ip: str, timeout: float = 3.0) -> bool:
    """Detiene el streaming de webcam en la GoPro."""
    if gopro_ip in ("Pendiente", "Sin IP (DHCP pendiente)"):
        return False
    for endpoint in ("/gopro/webcam/stop", "/gopro/camera/stream/stop"):
        try:
            resp = requests.get(f"http://{gopro_ip}:8080{endpoint}", timeout=timeout)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
    return False


def check_gopro_status(gopro_ip: str, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
    """Consulta el estado actual de la webcam en la GoPro."""
    if gopro_ip in ("Pendiente", "Sin IP (DHCP pendiente)"):
        return None
    for endpoint in ("/gopro/webcam/status", "/gopro/camera/state"):
        try:
            resp = requests.get(f"http://{gopro_ip}:8080{endpoint}", timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
    return None
