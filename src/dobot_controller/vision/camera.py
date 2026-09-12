"""
Módulo de captura de video para GoPro y cámaras USB.
Incluye lector en hilo desacoplado (para evitar latencia por buffer)
y generador de fotogramas simulados (MockCamera).
"""

import os
import time
import base64
import math
import logging
import threading
from typing import Optional, Tuple, Union, Dict, Any
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

from dobot_controller.vision.gopro_setup import (
    find_gopro_network_interface,
    activate_gopro_webcam,
    stop_gopro_webcam,
    set_gopro_webcam_fov,
    list_v4l2_devices
)

logger = logging.getLogger(__name__)


class MockCamera:
    """
    Cámara simulada para desarrollo y pruebas sin hardware conectado.
    Genera una vista cenital del área de trabajo del Dobot con el efector y un objetivo.
    """

    def __init__(self, width: int = 640, height: int = 480, fov: str = "linear"):
        if cv2 is None:
            raise ImportError(
                "OpenCV no está instalado ('opencv-python'). "
                "La simulación de cámara local del servidor requiere opencv-python. "
                "Para la cámara del cliente/navegador no es necesario."
            )
        self.width = width
        self.height = height
        self.fov = "linear" if str(fov).lower() in ("linear", "lineal", "4") else "wide"
        self.target_pos = (width // 2 + 80, height // 2 - 50)  # Pixel pos del objetivo
        self.effector_pos = [width // 2, height // 2]        # Pixel pos del efector
        self.suction_active = False
        self._lock = threading.Lock()
        logger.info(f"MockCamera inicializada ({width}x{height}, FOV: {self.fov})")

    def set_fov(self, fov: str):
        """Cambia el campo de visión del simulador ('linear' o 'wide')."""
        with self._lock:
            self.fov = "linear" if str(fov).lower() in ("linear", "lineal", "4") else "wide"
            logger.info(f"MockCamera FOV configurado en: {self.fov}")

    def update_effector_from_robot(self, x: float, y: float, z: float, suction: bool = False):
        """
        Mapea coordenadas del Dobot a píxeles de la cámara cenital simulada.
        Rango típico Dobot: X: 150 a 320 mm, Y: -180 a 180 mm.
        """
        with self._lock:
            # Mapeo: Dobot X (adelante) -> Y imagen (abajo), Dobot Y (izquierda) -> X imagen (izquierda)
            # Centro aproximado en robot: X=230, Y=0
            px = int(self.width / 2 - (y * (self.width / 400.0)))
            py = int(self.height / 2 + ((x - 230.0) * (self.height / 300.0)))
            self.effector_pos = [max(10, min(self.width - 10, px)), max(10, min(self.height - 10, py))]
            self.suction_active = suction

    def read(self) -> Tuple[bool, np.ndarray]:
        """Genera un fotograma sintético del espacio de trabajo."""
        with self._lock:
            # Fondo de mesa gris claro
            frame = np.full((self.height, self.width, 3), 240, dtype=np.uint8)

            # Cuadrícula de referencia milimétrica
            for gx in range(0, self.width, 40):
                cv2.line(frame, (gx, 0), (gx, self.height), (220, 220, 220), 1)
            for gy in range(0, self.height, 40):
                cv2.line(frame, (0, gy), (self.width, gy), (220, 220, 220), 1)

            # Ejes de coordenadas de la cámara
            cv2.arrowedLine(frame, (30, 30), (80, 30), (0, 0, 255), 2)  # +X cámara (rojo)
            cv2.putText(frame, "+u (cam X)", (85, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
            cv2.arrowedLine(frame, (30, 30), (30, 80), (0, 255, 0), 2)  # +Y cámara (verde)
            cv2.putText(frame, "+v (cam Y)", (35, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

            # Objetivo (Cubo / Objeto rojo)
            tx, ty = self.target_pos
            cv2.rectangle(frame, (tx - 18, ty - 18), (tx + 18, ty + 18), (40, 40, 220), -1)
            cv2.rectangle(frame, (tx - 18, ty - 18), (tx + 18, ty + 18), (0, 0, 160), 2)
            cv2.putText(frame, "TARGET", (tx - 24, ty - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 180), 1)

            # Objeto real frente a la cámara (ejemplo: Taza de café con asa y vapor)
            obj_x = int(self.width * 0.6)
            obj_y = int(self.height * 0.5)

            # Plato / base
            cv2.ellipse(frame, (obj_x, obj_y + 45), (45, 12), 0, 0, 360, (200, 200, 200), -1)
            cv2.ellipse(frame, (obj_x, obj_y + 45), (45, 12), 0, 0, 360, (140, 140, 140), 2)

            # Cuerpo de la taza (cilindro)
            mug_pts = np.array([
                [obj_x - 30, obj_y - 20],
                [obj_x + 30, obj_y - 20],
                [obj_x + 24, obj_y + 38],
                [obj_x - 24, obj_y + 38]
            ], np.int32)
            cv2.fillConvexPoly(frame, mug_pts, (240, 230, 220))
            cv2.polylines(frame, [mug_pts], isClosed=True, color=(160, 150, 140), thickness=2)

            # Asa de la taza
            cv2.ellipse(frame, (obj_x + 32, obj_y + 8), (14, 20), 0, -80, 80, (160, 150, 140), 3)

            # Borde superior / boca de la taza
            cv2.ellipse(frame, (obj_x, obj_y - 20), (30, 10), 0, 0, 360, (160, 150, 140), 2)
            # Café oscuro dentro
            cv2.ellipse(frame, (obj_x, obj_y - 19), (28, 8), 0, 0, 360, (40, 60, 90), -1)

            # Vapor estilizado
            for dx, s_phase in [(-8, 0), (8, 1)]:
                steam_pts = []
                for step in range(25):
                    sy = obj_y - 25 - step
                    sx = int(obj_x + dx + 4.0 * math.sin(step * 0.3 + s_phase))
                    steam_pts.append((sx, sy))
                cv2.polylines(frame, [np.array(steam_pts, dtype=np.int32)], isClosed=False, color=(200, 210, 220), thickness=1, lineType=cv2.LINE_AA)

            cv2.putText(frame, "OBJETO EN CAMARA: TAZA DE CAFE", (obj_x - 85, obj_y - 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (30, 60, 120), 1)

            # Efector del Dobot (Puntero con ventosa)
            ex, ey = self.effector_pos
            # Sombra/Efector
            color = (0, 160, 255) if not self.suction_active else (0, 255, 0)
            cv2.circle(frame, (ex, ey), 14, color, -1)
            cv2.circle(frame, (ex, ey), 14, (50, 50, 50), 2)
            cv2.circle(frame, (ex, ey), 3, (0, 0, 0), -1)
            # Marcador cruz
            cv2.line(frame, (ex - 8, ey), (ex + 8, ey), (0, 0, 0), 1)
            cv2.line(frame, (ex, ey - 8), (ex, ey + 8), (0, 0, 0), 1)
            cv2.putText(frame, "DOBOT END EFFECTOR", (ex - 50, ey + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (50, 50, 50), 1)

            # Letrero de lente actual
            lens_text = "[LENTE: LINEAL]" if self.fov == "linear" else "[LENTE: GRAN ANGULAR]"
            lens_color = (255, 160, 0) if self.fov == "linear" else (0, 200, 100)
            cv2.putText(frame, lens_text, (self.width - 200, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, lens_color, 1)

            # En modo lineal, simular encuadre lineal (zoom óptico sin distorsión ojo de pez)
            if self.fov == "linear":
                crop_h = int(self.height * 0.85)
                crop_w = int(self.width * 0.85)
                sy = (self.height - crop_h) // 2
                sx = (self.width - crop_w) // 2
                cropped = frame[sy:sy + crop_h, sx:sx + crop_w]
                frame = cv2.resize(cropped, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
                cv2.putText(frame, lens_text, (self.width - 200, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, lens_color, 1)

            # Letrero de modo simulación
            cv2.putText(frame, "[MODO SIMULACION - MOCK CAMERA]", (10, self.height - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)

            return True, frame

    def release(self):
        pass


class GoProCapture:
    """
    Capturador de video especializado para GoPro y webcams en Linux.
    Usa un hilo lector en segundo plano para vaciar el búfer de OpenCV y entregar
    siempre el fotograma más reciente en tiempo real.
    """

    def __init__(
        self,
        source: Optional[Union[int, str]] = None,
        mock: bool = False,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        auto_activate_gopro: bool = True,
        fov: str = "linear"
    ):
        self.mock = mock
        self.width = width
        self.height = height
        self.fps = fps
        self.auto_activate_gopro = auto_activate_gopro
        self.fov = "linear" if str(fov).lower() in ("linear", "lineal", "4") else "wide"
        self.source = source
        self.gopro_ip: Optional[str] = None
        self._mock_cam: Optional[MockCamera] = None
        self.cap: Optional[Any] = None

        if cv2 is None:
            raise ImportError(
                "OpenCV no está instalado ('opencv-python'). "
                "La captura de cámara desde el servidor requiere opencv-python. "
                "Para la cámara del cliente/navegador no se requiere."
            )

        # Variables de hilo
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_count = 0
        self._last_frame_time = 0.0

        if self.mock:
            self._init_mock()
        else:
            self._init_capture()

    def set_fov(self, fov: str) -> bool:
        """
        Cambia el campo de visión (FOV) / lente entre 'linear' y 'wide'.
        """
        new_fov = "linear" if str(fov).lower() in ("linear", "lineal", "4") else "wide"
        self.fov = new_fov

        if self.mock or self._mock_cam:
            if self._mock_cam:
                self._mock_cam.set_fov(new_fov)
            return True

        if self.gopro_ip:
            fov_code = "4" if new_fov == "linear" else "0"
            res = "1080" if self.height >= 1080 else "720"
            return set_gopro_webcam_fov(self.gopro_ip, fov=fov_code, resolution=res)

        return True

    def _init_mock(self):
        """Inicia cámara simulada."""
        self._mock_cam = MockCamera(width=self.width, height=self.height, fov=self.fov)
        ret, frame = self._mock_cam.read()
        self._latest_frame = frame
        logger.info(f"GoProCapture configurado en modo MOCK (FOV: {self.fov}).")

    def _init_capture(self):
        """Detecta e inicializa la fuente de video real."""
        # 1. Si no se especificó fuente, intentar autodetectar GoPro vía red USB
        if self.source is None:
            gopro_net = find_gopro_network_interface()
            if gopro_net and self.auto_activate_gopro:
                self.gopro_ip = gopro_net["gopro_ip"]
                logger.info(f"GoPro detectada en red USB ({gopro_net['interface']}) con IP {self.gopro_ip}")
                fov_code = "4" if self.fov == "linear" else "0"
                if activate_gopro_webcam(self.gopro_ip, resolution="1080" if self.height >= 1080 else "720", fov=fov_code):
                    time.sleep(1.5)  # Esperar a que el stream UDP empiece
                    self.source = "udp://@0.0.0.0:8554?overrun_nonfatal=1&fifo_size=50000000"

        # 2. Si todavía no hay fuente, buscar dispositivos V4L2 (/dev/video*)
        if self.source is None:
            v4l2_devs = list_v4l2_devices()
            if v4l2_devs:
                # Tomar el primer dispositivo accesible
                for d in v4l2_devs:
                    if d["accessible"]:
                        self.source = d["path"]
                        logger.info(f"Usando dispositivo V4L2: {d['path']} ({d['name']})")
                        break

        # 3. Fallback a 0
        if self.source is None:
            self.source = 0

        logger.info(f"Abriendo fuente de video: {self.source}")
        
        # Abrir VideoCapture
        if isinstance(self.source, str) and self.source.startswith("udp://"):
            self.cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        else:
            self.cap = cv2.VideoCapture(self.source)

        if not self.cap.isOpened():
            logger.warning(f"No se pudo abrir la fuente de video {self.source}. Cayendo a MOCK.")
            self._init_mock()
            return

        # Configurar resolución y fps
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        # Iniciar hilo de lectura continuo
        self._running = True
        self._thread = threading.Thread(target=self._reader_loop, daemon=True, name="GoProCaptureThread")
        self._thread.start()

        # Esperar primer fotograma
        start_wait = time.time()
        while time.time() - start_wait < 3.0:
            if self._latest_frame is not None:
                break
            time.sleep(0.05)

        if self._latest_frame is None:
            logger.warning("No se recibieron fotogramas en 3s. Verificando...")

    def _reader_loop(self):
        """Bucle en hilo daemon que lee continuamente para vaciar búfer."""
        while self._running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret and frame is not None:
                with self._lock:
                    self._latest_frame = frame
                    self._frame_count += 1
                    self._last_frame_time = time.time()
            else:
                time.sleep(0.01)

    def get_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Obtiene el fotograma más reciente capturado.
        Retorna (True, frame) o (False, None).
        """
        if self.mock or self._mock_cam:
            return self._mock_cam.read()

        with self._lock:
            if self._latest_frame is None:
                return False, None
            return True, self._latest_frame.copy()

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Obtiene directamente el último frame capturado o None."""
        ret, frame = self.get_frame()
        return frame if ret else None

    def get_frame_base64(self, max_dimension: int = 1024, quality: int = 85) -> Optional[str]:
        """
        Captura el fotograma actual y lo codifica como string JPEG base64
        listo para ser enviado a Claude / Anthropic Vision API.
        """
        ret, frame = self.get_frame()
        if not ret or frame is None:
            return None

        if cv2 is None:
            return None

        # Redimensionar si excede max_dimension manteniendo aspecto
        h, w = frame.shape[:2]
        if max(h, w) > max_dimension:
            scale = max_dimension / float(max(h, w))
            new_w, new_h = int(w * scale), int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # Codificar a JPEG usando OpenCV directamente
        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ret:
            return None
        return base64.b64encode(buffer.tobytes()).decode("utf-8")

    def sync_mock_with_dobot(self, x: float, y: float, z: float, suction: bool = False):
        """Sincroniza el efector simulado con la posición real/mock del Dobot."""
        if self._mock_cam:
            self._mock_cam.update_effector_from_robot(x, y, z, suction)

    def save_snapshot(self, filepath: str) -> bool:
        """Guarda una instantánea del fotograma actual en disco."""
        ret, frame = self.get_frame()
        if ret and frame is not None:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            return cv2.imwrite(filepath, frame)
        return False

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Alias compatible con cv2.VideoCapture."""
        return self.get_frame()

    def release(self):
        """Alias compatible con cv2.VideoCapture."""
        self.close()

    def close(self):
        """Libera la cámara, detiene el hilo y envía stop a la GoPro si aplica."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        if self.gopro_ip:
            try:
                stop_gopro_webcam(self.gopro_ip)
            except Exception:
                pass

        logger.info("GoProCapture cerrada.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
