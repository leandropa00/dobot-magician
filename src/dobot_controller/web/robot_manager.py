"""
Manejador central del robot Dobot Magician para la interfaz web.
Gestiona el ciclo de vida del robot (hardware real o simulación),
movimientos por flechas (jogging), generación de bocetos con IA
y ejecución continua del dibujo a partir del punto indicado.
"""

import os
import cv2
import math
import time
import base64
import logging
import threading
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import numpy as np

import anthropic
from dotenv import load_dotenv

from dobot_controller.controller import DobotController
from dobot_controller.safety import SafetyLimits, SafetyBoundaryError
from dobot_controller.drawing import draw_stroke
from dobot_controller.vision.visual_drawer import DRAWING_PROMPT, DRAWING_TOOL
from dobot_controller.vision.agent import resolve_claude_model
from pydobotplus.dobotplus import MODE_PTP

load_dotenv()
logger = logging.getLogger(__name__)

ORIGIN_CONFIG_FILE = Path(".dobot_origin.json")


class RobotManager:
    """Manejador thread-safe del Dobot Magician para la aplicación web."""

    def __init__(self, mock: bool = False, port: Optional[str] = None, model: Optional[str] = None):
        self._lock = threading.RLock()
        self.mock_requested = mock
        self.specified_port = port
        self._model = model

        # Parámetros del papel y dibujo
        self.notebook_width: float = 250.0   # mm
        self.notebook_height: float = 170.0  # mm
        self.margin: float = 15.0            # mm
        self.canvas_width: float = 220.0     # mm
        self.canvas_height: float = 140.0    # mm

        # Punto de inicio / referencia indicado para dibujar
        self.origin_x: float = 235.50
        self.origin_y: float = -10.45
        self.origin_z_draw: float = -38.59
        self.origin_z_hover: float = -23.59
        self.origin_r: float = 5.67

        # Cargar configuración persistente de punto de inicio si existe
        self._load_saved_origin()

        # Velocidad y aceleración
        self.velocity: float = 40.0
        self.acceleration: float = 40.0

        # Estado del boceto y dibujo
        self.current_sketch: Optional[Dict[str, Any]] = None
        self.is_drawing: bool = False
        self._cancel_drawing = threading.Event()
        self.drawing_thread: Optional[threading.Thread] = None
        self.drawing_progress: Dict[str, Any] = {
            "is_drawing": False,
            "current_stroke": 0,
            "total_strokes": 0,
            "stroke_name": "",
            "percent": 0.0,
            "message": "En espera",
            "error": None
        }

        # Conexión del robot
        self.bot: Optional[DobotController] = None
        self.is_connected: bool = False
        self.is_mock: bool = False
        self.last_error: Optional[str] = None

        # Cliente Anthropic y modelo
        load_dotenv(override=True)
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

        self._connect_internal()

    @property
    def model(self) -> str:
        return resolve_claude_model(self._model)

    @model.setter
    def model(self, value: Optional[str]):
        self._model = value

    def _connect_internal(self):
        """Conecta al robot físico o conmuta a simulación si no se detecta hardware."""
        with self._lock:
            if self.bot is not None:
                try:
                    self.bot.close()
                except Exception:
                    pass
                self.bot = None

            self.is_connected = False
            self.last_error = None

            if not self.mock_requested:
                try:
                    logger.info("Intentando conectar con Dobot Magician físico...")
                    self.bot = DobotController(
                        port=self.specified_port,
                        mock=False,
                        enforce_safety=True,
                        velocity=self.velocity,
                        acceleration=self.acceleration
                    )
                    self.is_connected = True
                    self.is_mock = False
                    logger.info("Conectado exitosamente al hardware físico de Dobot.")
                    return
                except Exception as e:
                    logger.warning(f"No se pudo conectar a hardware físico ({e}). Conmutando automáticamente a SIMULACIÓN.")
                    self.last_error = f"Hardware no detectado: {e}. Activo en modo simulación."

            try:
                self.bot = DobotController(
                    port=self.specified_port,
                    mock=True,
                    enforce_safety=True,
                    velocity=self.velocity,
                    acceleration=self.acceleration
                )
                self.is_connected = True
                self.is_mock = True
                logger.info("Conectado exitosamente en modo simulación (MockDobot).")
            except Exception as e:
                self.last_error = f"Error al inicializar simulador: {e}"
                logger.error(self.last_error)

    def reconnect(self, mock: Optional[bool] = None, port: Optional[str] = None) -> Dict[str, Any]:
        """Fuerza reconexión permitiendo alternar modo mock."""
        if mock is not None:
            self.mock_requested = mock
        if port is not None:
            self.specified_port = port if port.strip() else None
        self._connect_internal()
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        """Devuelve el estado completo del robot y el dibujo."""
        pose = {"x": 0.0, "y": 0.0, "z": 0.0, "r": 0.0, "j1": 0.0, "j2": 0.0, "j3": 0.0, "j4": 0.0}
        alarms: List[int] = []

        if self.bot and self.is_connected:
            with self._lock:
                try:
                    pose = self.bot.get_pose()
                    alarms = self.bot.get_alarms()
                except Exception as e:
                    self.last_error = f"Error leyendo pose: {e}"

        return {
            "connected": self.is_connected,
            "mock": self.is_mock,
            "port": self.bot.port if self.bot else None,
            "pose": pose,
            "alarms": alarms,
            "origin": {
                "x": self.origin_x,
                "y": self.origin_y,
                "z_draw": self.origin_z_draw,
                "z_hover": self.origin_z_hover,
                "r": self.origin_r
            },
            "drawing_progress": dict(self.drawing_progress),
            "has_sketch": self.current_sketch is not None,
            "sketch_info": {
                "subject": self.current_sketch["subject"] if self.current_sketch else None,
                "stroke_count": len(self.current_sketch["robot_strokes"]) if self.current_sketch else 0,
                "total_points": self.current_sketch["total_points"] if self.current_sketch else 0
            } if self.current_sketch else None,
            "model": self.model,
            "last_error": self.last_error
        }

    # ==========================================
    # MOVIMIENTO Y FLECHAS (JOGGING)
    # ==========================================

    def jog_relative(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, dr: float = 0.0) -> Dict[str, Any]:
        """Mueve el brazo de forma relativa usando las flechas de control."""
        if not self.bot or not self.is_connected:
            raise RuntimeError("Robot no conectado.")

        if self.is_drawing:
            raise RuntimeError("No se puede mover manualmente mientras se está dibujando.")

        with self._lock:
            cur = self.bot.get_pose()
            target_x = cur["x"] + dx
            target_y = cur["y"] + dy
            target_z = cur["z"] + dz
            target_r = cur["r"] + dr

            # Enforce safety
            SafetyLimits.enforce(target_x, target_y, target_z, target_r)

            self.bot.move_to(x=target_x, y=target_y, z=target_z, r=target_r, wait=True, mode=MODE_PTP.MOVL_XYZ)
            return self.bot.get_pose()

    def jog_absolute(self, x: Optional[float] = None, y: Optional[float] = None, z: Optional[float] = None, r: Optional[float] = None) -> Dict[str, Any]:
        """Mueve el brazo a coordenadas cartesianas absolutas."""
        if not self.bot or not self.is_connected:
            raise RuntimeError("Robot no conectado.")

        if self.is_drawing:
            raise RuntimeError("No se puede mover manualmente mientras se está dibujando.")

        with self._lock:
            cur = self.bot.get_pose()
            target_x = cur["x"] if x is None else float(x)
            target_y = cur["y"] if y is None else float(y)
            target_z = cur["z"] if z is None else float(z)
            target_r = cur["r"] if r is None else float(r)

            SafetyLimits.enforce(target_x, target_y, target_z, target_r)
            self.bot.move_to(x=target_x, y=target_y, z=target_z, r=target_r, wait=True, mode=MODE_PTP.MOVJ_XYZ)
            return self.bot.get_pose()

    def home(self) -> Dict[str, Any]:
        """Ejecuta homing del brazo."""
        if not self.bot or not self.is_connected:
            raise RuntimeError("Robot no conectado.")
        with self._lock:
            self.bot.home()
            return self.bot.get_pose()

    # ==========================================
    # PUNTO DE INICIO INDICADO PARA DIBUJAR
    # ==========================================

    def _load_saved_origin(self):
        """Carga el punto de inicio previamente configurado si existe para no perder la calibración."""
        try:
            if ORIGIN_CONFIG_FILE.exists():
                with open(ORIGIN_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.origin_x = round(float(data.get("x", self.origin_x)), 2)
                    self.origin_y = round(float(data.get("y", self.origin_y)), 2)
                    self.origin_z_draw = round(float(data.get("z_draw", self.origin_z_draw)), 2)
                    self.origin_z_hover = round(float(data.get("z_hover", self.origin_z_draw + 15.0)), 2)
                    self.origin_r = round(float(data.get("r", self.origin_r)), 2)
                    logger.info(
                        f"Punto de inicio persistido cargado: X={self.origin_x}, Y={self.origin_y}, "
                        f"Z_draw={self.origin_z_draw}, Z_hover={self.origin_z_hover}"
                    )
        except Exception as e:
            logger.warning(f"No se pudo cargar {ORIGIN_CONFIG_FILE}: {e}")

    def _save_origin_to_disk(self):
        """Persiste el punto de inicio en disco para que se conserve entre sesiones y ejecuciones."""
        try:
            data = {
                "x": self.origin_x,
                "y": self.origin_y,
                "z_draw": self.origin_z_draw,
                "z_hover": self.origin_z_hover,
                "r": self.origin_r
            }
            with open(ORIGIN_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Punto de inicio guardado en {ORIGIN_CONFIG_FILE}")
        except Exception as e:
            logger.warning(f"No se pudo guardar {ORIGIN_CONFIG_FILE}: {e}")

    def set_current_as_origin(self) -> Dict[str, Any]:
        """
        Fija la posición cartesiana actual del brazo como el punto de inicio / centro de dibujo.
        El Z actual se establece como z_draw (contacto con papel), y z_hover = z_draw + 15mm.
        """
        if not self.bot or not self.is_connected:
            raise RuntimeError("Robot no conectado.")

        with self._lock:
            pose = self.bot.get_pose()
            self.origin_x = round(float(pose["x"]), 2)
            self.origin_y = round(float(pose["y"]), 2)
            self.origin_z_draw = round(float(pose["z"]), 2)
            self.origin_z_hover = round(self.origin_z_draw + 15.0, 2)
            self.origin_r = round(float(pose["r"]), 2)
            self._save_origin_to_disk()

        # Si ya hay un boceto cargado, recalculamos los trazos para que comience desde este nuevo punto
        if self.current_sketch:
            self._recalculate_current_sketch()

        return {
            "x": self.origin_x,
            "y": self.origin_y,
            "z_draw": self.origin_z_draw,
            "z_hover": self.origin_z_hover,
            "r": self.origin_r
        }

    def set_origin(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z_draw: Optional[float] = None,
        z_hover: Optional[float] = None,
        r: Optional[float] = None
    ) -> Dict[str, Any]:
        """Establece manualmente el punto de inicio de dibujo y conserva las alturas."""
        with self._lock:
            if x is not None:
                self.origin_x = round(float(x), 2)
            if y is not None:
                self.origin_y = round(float(y), 2)
            if z_draw is not None:
                self.origin_z_draw = round(float(z_draw), 2)
                if z_hover is None:
                    self.origin_z_hover = round(self.origin_z_draw + 15.0, 2)
            if z_hover is not None:
                self.origin_z_hover = round(float(z_hover), 2)
            if r is not None:
                self.origin_r = round(float(r), 2)

            self._save_origin_to_disk()

        if self.current_sketch:
            self._recalculate_current_sketch()

        return {
            "x": self.origin_x,
            "y": self.origin_y,
            "z_draw": self.origin_z_draw,
            "z_hover": self.origin_z_hover,
            "r": self.origin_r
        }

    def move_to_origin(self, hover: bool = True) -> Dict[str, Any]:
        """Mueve el efector al punto de inicio indicado."""
        if not self.bot or not self.is_connected:
            raise RuntimeError("Robot no conectado.")
        target_z = self.origin_z_hover if hover else self.origin_z_draw
        return self.jog_absolute(x=self.origin_x, y=self.origin_y, z=target_z, r=self.origin_r)

    # ==========================================
    # GENERACIÓN Y SÍNTESIS DE BOCETO CON IA
    # ==========================================

    def generate_sketch_from_image(
        self,
        image_base64: str,
        user_instruction: str = "Identifica el objeto en la imagen y sintetiza un boceto de líneas limpias para dibujarlo"
    ) -> Dict[str, Any]:
        """
        Envía la fotografía capturada por el usuario a Claude VLA para generar el boceto vectorial,
        lo convierte a coordenadas de robot según el punto de inicio indicado y crea la vista previa.
        """
        # Limpiar encabezado data:image/...;base64, si viene incluido
        raw_b64 = image_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]

        subject = "Objeto detectado"
        raw_strokes: List[Dict[str, Any]] = []

        load_dotenv(override=True)
        api_key = self.anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = resolve_claude_model(self.model)

        if api_key:
            try:
                client = anthropic.Anthropic(api_key=api_key)
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Instrucción: {user_instruction}\n"
                                    "Analiza minuciosamente el OBJETO real en la fotografía capturada por el usuario. "
                                    "Identifícalo y sintetiza un boceto de líneas limpias y estilizadas para dibujarlo con trazos continuos."
                                )
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": raw_b64
                                }
                            }
                        ]
                    }
                ]

                logger.info(f"Enviando imagen al modelo {self.model}...")
                response = client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=DRAWING_PROMPT,
                    messages=messages,
                    tools=[DRAWING_TOOL]
                )

                for block in response.content:
                    if block.type == "tool_use" and block.name == "generate_drawing_trajectory":
                        traj_data = block.input
                        subject = traj_data.get("identified_subject", "Objeto detectado")
                        raw_strokes = traj_data.get("strokes", [])
                        break

            except Exception as e:
                logger.error(f"Error consultando modelo Claude: {e}")
                self.last_error = f"Error en Claude API: {e}. Usando boceto alternativo."

        if not raw_strokes:
            logger.warning("Generando boceto estilizado sintético (fallback)...")
            subject = "Taza de café estilizada (Simulación/Fallback)"
            raw_strokes = self._generate_fallback_strokes()

        # Convertir a coordenadas físicas usando el punto de inicio indicado
        robot_strokes, total_points = self._convert_strokes(raw_strokes)
        preview_base64 = self._render_preview_base64(robot_strokes, subject)

        self.current_sketch = {
            "subject": subject,
            "raw_strokes": raw_strokes,
            "robot_strokes": robot_strokes,
            "total_points": total_points,
            "preview_base64": preview_base64
        }

        return {
            "success": True,
            "subject": subject,
            "stroke_count": len(robot_strokes),
            "total_points": total_points,
            "preview_image": preview_base64,
            "robot_strokes": robot_strokes
        }

    def _recalculate_current_sketch(self):
        """Recalcula las coordenadas del robot y la vista previa del boceto actual con el nuevo punto de inicio."""
        if not self.current_sketch:
            return
        raw_strokes = self.current_sketch.get("raw_strokes", [])
        robot_strokes, total_points = self._convert_strokes(raw_strokes)
        preview_base64 = self._render_preview_base64(robot_strokes, self.current_sketch["subject"])
        self.current_sketch["robot_strokes"] = robot_strokes
        self.current_sketch["total_points"] = total_points
        self.current_sketch["preview_base64"] = preview_base64

    def _convert_strokes(self, raw_strokes: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """Convierte coordenadas normalizadas [-1, 1] a milímetros físicos centradas en (origin_x, origin_y)."""
        robot_strokes = []
        total_points = 0

        for s in raw_strokes:
            name = s.get("name", "trazo")
            points = s.get("points", [])
            converted = []

            for pt in points:
                u, v = float(pt[0]), float(pt[1])
                # u (horizontal) -> Y robot
                # v (vertical) -> X robot
                rx = self.origin_x + (v * (self.canvas_height / 2.0))
                ry = self.origin_y + (u * (self.canvas_width / 2.0))

                # Clamping de seguridad mecánica
                rx = max(150.0, min(320.0, rx))
                ry = max(-180.0, min(180.0, ry))

                rad = math.hypot(rx, ry)
                if rad > SafetyLimits.MAX_RADIUS_MM - 5.0:
                    scale = (SafetyLimits.MAX_RADIUS_MM - 5.0) / rad
                    rx *= scale
                    ry *= scale
                elif rad < SafetyLimits.MIN_RADIUS_MM + 5.0:
                    scale = (SafetyLimits.MIN_RADIUS_MM + 5.0) / rad
                    rx *= scale
                    ry *= scale

                converted.append((round(rx, 2), round(ry, 2)))

            if len(converted) >= 2:
                robot_strokes.append({
                    "name": name,
                    "points": converted
                })
                total_points += len(converted)

        return robot_strokes, total_points

    def _render_preview_base64(self, robot_strokes: List[Dict[str, Any]], subject: str) -> str:
        """Genera una imagen gráfica representativa del papel y los trazos, codificada en base64."""
        scale = 3.0  # 1 mm = 3 px
        margin_px = 40
        paper_w_px = int(self.notebook_width * scale)   # 750 px
        paper_h_px = int(self.notebook_height * scale)  # 510 px

        img_w = paper_w_px + (margin_px * 2)
        img_h = paper_h_px + (margin_px * 2) + 50

        img = np.full((img_h, img_w, 3), 245, dtype=np.uint8)

        # 1. Cuaderno / Hoja
        x1 = margin_px
        y1 = margin_px + 35
        x2 = x1 + paper_w_px
        y2 = y1 + paper_h_px

        # Sombra y papel blanco
        cv2.rectangle(img, (x1 + 4, y1 + 4), (x2 + 4, y2 + 4), (210, 210, 210), -1)
        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 255, 255), -1)
        cv2.rectangle(img, (x1, y1), (x2, y2), (180, 180, 180), 2)

        # Título superior
        cv2.putText(img, f"Boceto: {subject}", (x1, y1 - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 30, 30), 2)

        # 2. Área útil de dibujo
        pad_x_px = int((paper_w_px - (self.canvas_width * scale)) / 2.0)
        pad_y_px = int((paper_h_px - (self.canvas_height * scale)) / 2.0)
        cx1, cy1 = x1 + pad_x_px, y1 + pad_y_px
        cx2, cy2 = cx1 + int(self.canvas_width * scale), cy1 + int(self.canvas_height * scale)

        cv2.rectangle(img, (cx1, cy1), (cx2, cy2), (242, 246, 250), -1)
        cv2.rectangle(img, (cx1, cy1), (cx2, cy2), (210, 220, 230), 1)

        # 3. Centro / Punto de inicio indicado
        center_px_x = x1 + (paper_w_px // 2)
        center_px_y = y1 + (paper_h_px // 2)

        # Marcador del origen indicado
        cv2.drawMarker(img, (center_px_x, center_px_y), (0, 0, 220), cv2.MARKER_CROSS, 20, 2)
        cv2.circle(img, (center_px_x, center_px_y), 6, (0, 0, 220), 1)
        cv2.putText(
            img,
            f"PUNTO INICIO (X={self.origin_x:.1f}, Y={self.origin_y:.1f})",
            (center_px_x - 130, center_px_y - 12),
            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 180), 1
        )

        # Función de mapeo (rx, ry) -> px
        def to_px(rx: float, ry: float) -> Tuple[int, int]:
            px = int(center_px_x + ((ry - self.origin_y) * scale))
            py = int(center_px_y - ((rx - self.origin_x) * scale))
            return max(0, min(img_w - 1, px)), max(0, min(img_h - 1, py))

        colors = [
            (200, 30, 30),   # Azul BGR
            (20, 150, 20),   # Verde BGR
            (30, 30, 210),   # Rojo BGR
            (160, 30, 160),  # Púrpura BGR
            (20, 130, 200)   # Naranja BGR
        ]

        for s_idx, stroke in enumerate(robot_strokes):
            pts = stroke["points"]
            color = colors[s_idx % len(colors)]
            px_pts = [to_px(p[0], p[1]) for p in pts]

            for i in range(len(px_pts) - 1):
                cv2.line(img, px_pts[i], px_pts[i + 1], color, 2, cv2.LINE_AA)

            # Inicio (verde) y fin (rojo) del trazo
            cv2.circle(img, px_pts[0], 4, (0, 180, 0), -1)
            cv2.circle(img, px_pts[-1], 4, (0, 0, 180), -1)

        # Pie
        cv2.putText(
            img,
            f"Punto de inicio indicado: ({self.origin_x:.1f}, {self.origin_y:.1f}) mm | Trazos: {len(robot_strokes)}",
            (x1, img_h - 12),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 80, 80), 1
        )

        _, buf = cv2.imencode(".png", img)
        return "data:image/png;base64," + base64.b64encode(buf).decode("utf-8")

    def _generate_fallback_strokes(self) -> List[Dict[str, Any]]:
        """Genera un dibujo lineal geométrico de una taza de café en caso de fallback."""
        strokes = []
        # Boca elíptica
        mouth = []
        for i in range(25):
            th = 2.0 * math.pi * (i / 24.0)
            mouth.append((round(0.35 * math.cos(th), 3), round(0.45 + 0.12 * math.sin(th), 3)))
        strokes.append({"name": "boca_taza", "points": mouth})

        # Cuerpo
        body = [(-0.35, 0.45), (-0.28, -0.35), (0.28, -0.35), (0.35, 0.45)]
        strokes.append({"name": "cuerpo_taza", "points": body})

        # Base
        base = [(-0.38, -0.38), (0.38, -0.38)]
        strokes.append({"name": "plato_base", "points": base})

        # Asa lateral
        handle = []
        for i in range(16):
            th = -math.pi / 2.0 + math.pi * (i / 15.0)
            handle.append((round(0.32 + 0.22 * math.cos(th), 3), round(0.1 + 0.25 * math.sin(th), 3)))
        strokes.append({"name": "asa_lateral", "points": handle})

        return strokes

    # ==========================================
    # EJECUCIÓN CONTINUA DEL DIBUJO
    # ==========================================

    def start_drawing(
        self,
        origin_x: Optional[float] = None,
        origin_y: Optional[float] = None,
        origin_z_draw: Optional[float] = None,
        origin_z_hover: Optional[float] = None
    ) -> Dict[str, Any]:
        """Inicia el dibujo de forma asíncrona a partir del punto indicado, conservando la altura Z."""
        if not self.bot or not self.is_connected:
            raise RuntimeError("Robot no conectado.")

        with self._lock:
            # Si se proporcionan coordenadas explícitas, actualizarlas y persistirlas inmediatamente
            if (
                origin_x is not None or
                origin_y is not None or
                origin_z_draw is not None or
                origin_z_hover is not None
            ):
                self.set_origin(
                    x=origin_x,
                    y=origin_y,
                    z_draw=origin_z_draw,
                    z_hover=origin_z_hover
                )

            if not self.current_sketch or not self.current_sketch.get("robot_strokes"):
                raise RuntimeError("No hay un boceto confirmado para dibujar.")

            if self.is_drawing:
                raise RuntimeError("Ya se está ejecutando un dibujo actualmente.")

            self._cancel_drawing.clear()
            self.is_drawing = True
            self.drawing_progress = {
                "is_drawing": True,
                "current_stroke": 0,
                "total_strokes": len(self.current_sketch["robot_strokes"]),
                "stroke_name": "Iniciando",
                "percent": 0.0,
                "message": f"Elevando a altura de tránsito (Z_hover={self.origin_z_hover} mm) y preparando lápiz (Z_draw={self.origin_z_draw} mm)...",
                "error": None
            }

            self.drawing_thread = threading.Thread(target=self._run_drawing_worker, daemon=True)
            self.drawing_thread.start()

        return {
            "status": "started",
            "strokes": len(self.current_sketch["robot_strokes"]),
            "origin": {
                "x": self.origin_x,
                "y": self.origin_y,
                "z_draw": self.origin_z_draw,
                "z_hover": self.origin_z_hover
            }
        }

    def stop_drawing(self) -> Dict[str, Any]:
        """Detiene inmediatamente el proceso de dibujo."""
        if not self.is_drawing:
            return {"status": "not_drawing"}

        self._cancel_drawing.set()
        self.drawing_progress["message"] = "Cancelando dibujo por solicitud del usuario..."
        return {"status": "cancelling"}

    def _run_drawing_worker(self):
        """Hilo trabajador que ejecuta los trazos secuenciales sobre el Dobot."""
        strokes = self.current_sketch["robot_strokes"]
        total_strokes = len(strokes)
        start_time = time.time()

        try:
            with self._lock:
                # 1. Configurar velocidad
                self.bot.set_speed(velocity=self.velocity, acceleration=self.acceleration)

                # 2. Conservar estrictamente las alturas Z del Punto de Inicio Indicado
                z_draw = float(self.origin_z_draw)
                z_hover = float(self.origin_z_hover)
                logger.info(
                    f"Comenzando dibujo con altura Z conservada de Punto de Inicio Indicado: "
                    f"Z_draw={z_draw} mm, Z_hover={z_hover} mm"
                )

                # 3. Elevar verticalmente a altura de tránsito sobre la posición actual
                self.drawing_progress["message"] = f"Subiendo brazo verticalmente a Z_hover={z_hover} mm..."
                cur = self.bot.get_pose()
                self.bot.move_to(x=cur["x"], y=cur["y"], z=z_hover, r=self.origin_r, wait=True, mode=MODE_PTP.MOVL_XYZ)

                # 4. Ejecutar trazos continuos
                for idx, stroke in enumerate(strokes, start=1):
                    if self._cancel_drawing.is_set():
                        logger.warning("Dibujo cancelado por el usuario.")
                        self.drawing_progress["message"] = "Dibujo interrumpido por el usuario."
                        break

                    name = stroke.get("name", f"Trazo {idx}")
                    pts = stroke["points"]
                    self.drawing_progress["current_stroke"] = idx
                    self.drawing_progress["stroke_name"] = name
                    self.drawing_progress["percent"] = round(((idx - 1) / total_strokes) * 100.0, 1)
                    self.drawing_progress["message"] = f"Dibujando {idx}/{total_strokes}: {name} ({len(pts)} puntos) [Z={z_draw} mm]"

                    # Dibujar trazo continuo conservando estrictamente z_draw
                    draw_stroke(
                        bot=self.bot,
                        points=pts,
                        z_draw=z_draw,
                        z_hover=z_hover
                    )

                # 5. Finalizar y regresar al punto de inicio indicado conservando z_draw
                if not self._cancel_drawing.is_set():
                    self.drawing_progress["percent"] = 100.0
                    duration = time.time() - start_time
                    self.drawing_progress["message"] = f"¡Dibujo completado con éxito en {duration:.1f} s!"
                    logger.info("Dibujo completado. Regresando al punto de inicio indicado...")
                    self.bot.move_to(x=self.origin_x, y=self.origin_y, z=z_hover, r=self.origin_r, wait=True, mode=MODE_PTP.MOVJ_XYZ)
                    self.bot.move_to(x=self.origin_x, y=self.origin_y, z=z_draw, r=self.origin_r, wait=True, mode=MODE_PTP.MOVL_XYZ)
                else:
                    cur = self.bot.get_pose()
                    self.bot.move_to(x=cur["x"], y=cur["y"], z=z_hover, wait=True, mode=MODE_PTP.MOVL_XYZ)

        except Exception as e:
            logger.error(f"Error durante la ejecución del dibujo: {e}", exc_info=True)
            self.drawing_progress["error"] = str(e)
            self.drawing_progress["message"] = f"Error en dibujo: {e}"
        finally:
            self.is_drawing = False
            self.drawing_progress["is_drawing"] = False
