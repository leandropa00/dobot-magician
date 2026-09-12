"""
Manejador de cámaras para la interfaz web.
Permite alternar entre GoPro USB (HERO12 / Open GoPro vía red USB),
cámaras V4L2 locales (/dev/video*), cámara simulada (Mock)
y provee un stream MJPEG de baja latencia para el navegador.
"""

import os
import time
import cv2
import base64
import logging
import threading
from typing import Optional, List, Dict, Any, Generator
import numpy as np

from dobot_controller.vision.camera import GoProCapture
from dobot_controller.vision.gopro_setup import (
    find_gopro_network_interface,
    find_gopro_usb_device,
    list_v4l2_devices
)

logger = logging.getLogger(__name__)


class WebCameraManager:
    """Manejador thread-safe de fuentes de video del servidor (GoPro, V4L2, Mock)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.active_source: str = "none"  # "gopro", "mock", "v4l2:<path>", "none"
        self.current_fov: str = "linear"  # "linear" (Lineal) o "wide" (Gran Angular)
        self.capture: Optional[GoProCapture] = None
        self._last_jpeg: Optional[bytes] = None
        self._last_frame_b64: Optional[str] = None
        self.is_running: bool = False

    def list_server_cameras(self) -> List[Dict[str, Any]]:
        """Devuelve las fuentes de cámara disponibles en el sistema operativo."""
        devices = []

        # 1. Comprobar GoPro vía USB / Red
        gopro_usb = find_gopro_usb_device()
        gopro_net = find_gopro_network_interface()

        if gopro_net or gopro_usb:
            desc = "GoPro HERO12 Black"
            if gopro_usb and "description" in gopro_usb:
                raw = gopro_usb["description"]
                if "GoPro" in raw:
                    desc = raw[raw.index("GoPro"):].strip()
                elif "ID 2672:" in raw:
                    parts = raw.split("ID 2672:")[1].strip().split(" ", 1)
                    desc = parts[1] if len(parts) > 1 else desc
            devices.append({
                "id": "gopro",
                "name": f"📷 {desc} (USB Connect)",
                "type": "gopro",
                "ip": gopro_net.get("gopro_ip") if gopro_net else None,
                "interface": gopro_net.get("interface") if gopro_net else None,
                "ready": gopro_net is not None and gopro_net.get("gopro_ip") != "Pendiente"
            })

        # 2. Comprobar dispositivos V4L2 locales
        v4l2_devs = list_v4l2_devices()
        for d in v4l2_devs:
            if d.get("accessible"):
                name = d.get("name", "Cámara V4L2")
                devices.append({
                    "id": f"v4l2:{d['path']}",
                    "name": f"📹 {name} ({d['path']})",
                    "type": "v4l2",
                    "path": d["path"]
                })

        # 3. Cámara simulada (siempre disponible para testing)
        devices.append({
            "id": "mock",
            "name": "🧪 Cámara Simulada (Mock Dobot)",
            "type": "mock"
        })

        return devices

    def set_source(self, source_id: str) -> Dict[str, Any]:
        """Cambia la fuente activa de captura del servidor."""
        with self._lock:
            if self.active_source == source_id and self.capture is not None:
                return {"status": "ok", "source": self.active_source}

            logger.info(f"Cambiando fuente de cámara a: {source_id}")
            self._close_internal()

            self.active_source = source_id

            if source_id == "gopro":
                try:
                    self.capture = GoProCapture(source=None, mock=False, auto_activate_gopro=True, fov=self.current_fov)
                    self.is_running = True
                except Exception as e:
                    logger.error(f"Error activando GoPro: {e}")
                    self.active_source = "none"
                    raise RuntimeError(f"No se pudo conectar a la GoPro: {e}")

            elif source_id == "mock":
                self.capture = GoProCapture(mock=True, fov=self.current_fov)
                self.is_running = True

            elif source_id.startswith("v4l2:"):
                dev_path = source_id.split("v4l2:", 1)[1]
                self.capture = GoProCapture(source=dev_path, mock=False, fov=self.current_fov)
                self.is_running = True

            elif source_id == "none" or source_id == "browser":
                self.active_source = "browser"
                self.is_running = False

            return {"status": "ok", "source": self.active_source}

    def _close_internal(self):
        """Cierra la captura activa."""
        if self.capture is not None:
            try:
                self.capture.release()
            except Exception as e:
                logger.debug(f"Error liberando captura: {e}")
            self.capture = None
        self.is_running = False
        self._last_jpeg = None
        self._last_frame_b64 = None

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Obtiene el último fotograma capturado."""
        if not self.capture:
            return None
        ret, frame = self.capture.read()
        return frame if ret else None

    def get_latest_jpeg(self) -> Optional[bytes]:
        """Obtiene el último fotograma comprimido en JPEG."""
        frame = self.get_latest_frame()
        if frame is None:
            return self._last_jpeg

        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ret:
            self._last_jpeg = buffer.tobytes()
            return self._last_jpeg
        return self._last_jpeg

    def get_latest_base64(self) -> Optional[str]:
        """Devuelve el último fotograma como data URI base64."""
        jpg = self.get_latest_jpeg()
        if not jpg:
            return None
        return "data:image/jpeg;base64," + base64.b64encode(jpg).decode("utf-8")

    def mjpeg_stream_generator(self) -> Generator[bytes, None, None]:
        """Generador HTTP multipart para streaming continuo en tiempo real en navegadores."""
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        end = b"\r\n"

        while self.is_running and self.capture is not None:
            jpeg = self.get_latest_jpeg()
            if jpeg:
                yield boundary + jpeg + end
            time.sleep(0.04)  # ~25 FPS

    def get_fov(self) -> str:
        """Obtiene el campo de visión actual ('linear' o 'wide')."""
        return self.current_fov

    def set_fov(self, fov: str) -> Dict[str, Any]:
        """
        Cambia el campo de visión (FOV) / lente entre 'linear' y 'wide'.
        """
        with self._lock:
            target_fov = "linear" if str(fov).lower() in ("linear", "lineal", "4") else "wide"
            self.current_fov = target_fov

            if self.capture is not None:
                try:
                    self.capture.set_fov(target_fov)
                except Exception as e:
                    logger.warning(f"Error aplicando FOV a captura: {e}")

            logger.info(f"FOV de cámara configurado en: {self.current_fov}")
            return {
                "status": "ok",
                "fov": self.current_fov,
                "label": "Lineal" if self.current_fov == "linear" else "Gran Angular"
            }

    def toggle_fov(self) -> Dict[str, Any]:
        """Alterna entre 'linear' y 'wide'."""
        next_fov = "wide" if self.current_fov == "linear" else "linear"
        return self.set_fov(next_fov)

    def release(self):
        with self._lock:
            self._close_internal()


# Instancia global de WebCameraManager
camera_manager = WebCameraManager()
