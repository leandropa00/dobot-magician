"""
Módulo de dibujo visual continuo (One-shot Visual-to-Trajectory Drawer).
Captura un único fotograma de la cámara (GoPro o USB), extrae la geometría
del boceto/figura a dibujar mediante Claude VLA, construye el mapa de
coordenadas normalizadas y envía la secuencia completa al Dobot Magician
para ejecutar el dibujo de forma continua y fluida sin pausas intermedias.
"""

import os
import cv2
import json
import math
import time
import base64
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable
import numpy as np
import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from pydobotplus.dobotplus import MODE_PTP

from dobot_controller.controller import DobotController
from dobot_controller.safety import SafetyLimits
from dobot_controller.drawing import draw_trajectory_sequence
from dobot_controller.vision.camera import GoProCapture
from dobot_controller.vision.agent import resolve_claude_model

logger = logging.getLogger(__name__)
console = Console()

DEFAULT_INSTRUCTION: str = "Identifica el objeto frente a la cámara y dibújalo en el cuaderno"

DRAWING_PROMPT = """Eres un artista robótico experto y dibujante visual acoplado a un Dobot Magician.
La cámara (GoPro o cámara USB) ha capturado una imagen de un OBJETO REAL DEL MUNDO EXTERIOR (por ejemplo: una taza de café, una manzana u otra fruta, unas tijeras, una herramienta, un juguete, una zapatilla, una planta, una botella, una mano, etc.).
NOTA CRÍTICA: La imagen capturada es del OBJETO a dibujar, NO del cuaderno ni de la mesa de dibujo.

El Dobot Magician va a plasmar e ilustrar artísticamente un boceto / dibujo lineal de este objeto sobre un cuaderno físico de 25x17 cm colocado en su mesa de trabajo.

Tu tarea:
1. Analizar la imagen para identificar con precisión el OBJETO real presente en la escena.
2. Sintetizar el objeto en un BOCETO VECTORIAL DE LÍNEAS LIMPIAS (line-art sketch / dibujo lineal estilizado):
   - Extrae el contorno/silueta exterior característico del objeto y sus rasgos interiores más reconocibles (ej. si es una taza: la boca elíptica, cuerpo, asa lateral, base y detalles).
   - El dibujo debe ser estético, nítido y reconocible, apto para ser trazado con un rotulador/marcador sobre papel.
3. Descomponer el boceto en una secuencia ordenada de TRAZOS CONTINUOS (strokes):
   - Cada trazo es una línea continua trazada con el marcador apoyado sobre el papel sin levantarlo.
   - Minimiza los levantamientos innecesarios del lápiz agrupando contornos conectados.
   - Coordenadas normalizadas [u, v] en el rango [-1.0, 1.0] centradas en el cuaderno (0.0, 0.0 es el centro del cuaderno).
   - Eje u: Horizontal (-1.0 es extremo izquierdo del cuaderno, +1.0 es extremo derecho).
   - Eje v: Vertical (-1.0 es parte inferior del cuaderno, +1.0 es parte superior).
   - Escala el objeto armoniosamente en el rango aproximado [-0.8, 0.8] para aprovechar el espacio sin tocar los bordes.
   - Genera curvas suaves con suficientes puntos (15 a 40 puntos por curva).
4. Invoca la herramienta `generate_drawing_trajectory` con la descripción del objeto y la lista ordenada de trazos continuos.
"""

DRAWING_TOOL = {
    "name": "generate_drawing_trajectory",
    "description": "Genera el mapa de coordenadas y la secuencia de trazos continuos para que el Dobot Magician dibuje la figura en el papel de forma fluida.",
    "input_schema": {
        "type": "object",
        "properties": {
            "identified_subject": {
                "type": "string",
                "description": "Descripción clara de la figura, boceto u objeto identificado en la imagen y lo que se va a plasmar."
            },
            "strokes": {
                "type": "array",
                "description": "Lista secuencial de trazos continuos. Cada trazo se dibuja con el marcador sobre el papel.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Nombre identificador del trazo (ej. 'contorno_exterior', 'ojo_izquierdo', 'sonrisa', 'linea_recta')."
                        },
                        "points": {
                            "type": "array",
                            "description": "Lista ordenada de puntos [u, v] normalizados en [-1.0, 1.0].",
                            "items": {
                                "type": "array",
                                "items": {"type": "number"},
                                "minItems": 2,
                                "maxItems": 2
                            },
                            "minItems": 2
                        }
                    },
                    "required": ["name", "points"]
                }
            }
        },
        "required": ["identified_subject", "strokes"]
    }
}


class VisualTrajectoryDrawer:
    """
    Controlador de dibujo visual de un solo disparo (One-shot Visual Drawer).
    1. Captura 1 fotograma de la GoPro.
    2. Claude crea el mapa de coordenadas continuas.
    3. Convierte y valida con los límites mecánicos del Dobot.
    4. Ejecuta el dibujo continuo en el robot sin capturas intermedias.
    """

    # Dimensiones por defecto del cuaderno: 25 x 17 cm (250 x 170 mm)
    DEFAULT_NOTEBOOK_WIDTH_MM: float = 250.0   # 25 cm (ancho en eje lateral Y)
    DEFAULT_NOTEBOOK_HEIGHT_MM: float = 170.0  # 17 cm (alto en eje radial X)

    # Posición inicial del efector final calibrada físicamente sobre el cuaderno (contacto en reposo)
    DEFAULT_CENTER_X: float = 235.50           # Coordenada X (mm)
    DEFAULT_CENTER_Y: float = -10.45           # Coordenada Y (mm)
    DEFAULT_Z_DRAW: float = -38.59             # Altura Z de contacto con el papel (mm)
    DEFAULT_Z_HOVER: float = -23.59            # Altura Z de tránsito en el aire (-38.59 + 15.0 mm)
    DEFAULT_R: float = 5.67                    # Rotación R del efector (grados)
    DEFAULT_MARGIN_MM: float = 15.0            # Margen de seguridad respecto al borde de la hoja

    def __init__(
        self,
        dobot: DobotController,
        camera: GoProCapture,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        center_x: float = DEFAULT_CENTER_X,
        center_y: float = DEFAULT_CENTER_Y,
        notebook_width: float = DEFAULT_NOTEBOOK_WIDTH_MM,
        notebook_height: float = DEFAULT_NOTEBOOK_HEIGHT_MM,
        margin: float = DEFAULT_MARGIN_MM,
        canvas_width: Optional[float] = None,
        canvas_height: Optional[float] = None,
        z_draw: float = DEFAULT_Z_DRAW,
        z_hover: float = DEFAULT_Z_HOVER,
        r: float = DEFAULT_R,
        velocity: float = 40.0,
        acceleration: float = 40.0
    ):
        self.dobot = dobot
        self.camera = camera
        self.model = resolve_claude_model(model)
        self.center_x = center_x
        self.center_y = center_y
        self.r = r
        self.notebook_width = notebook_width
        self.notebook_height = notebook_height
        self.margin = margin
        self.canvas_width = canvas_width if canvas_width is not None else max(20.0, notebook_width - 2.0 * margin)
        self.canvas_height = canvas_height if canvas_height is not None else max(20.0, notebook_height - 2.0 * margin)
        self.z_draw = z_draw
        self.z_hover = z_hover
        self.velocity = velocity
        self.acceleration = acceleration

        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY no configurada.")
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def move_to_center(self, hover: bool = False) -> Tuple[float, float, float]:
        """
        Posiciona el efector final en la posición inicial exacta del cuaderno (center_x, center_y, z_draw, r).
        - Por defecto inicia en contacto con el papel (hover=False, Z=z_draw).
        - Si el brazo está en una posición previa distante en el plano horizontal,
          se eleva a z_hover antes de trasladarse y desciende de forma puramente vertical (MOVL_XYZ).
        """
        target_z = self.z_hover if hover else self.z_draw
        current_pose = self.dobot.get_pose()
        cur_x = current_pose.get("x", self.center_x)
        cur_y = current_pose.get("y", self.center_y)
        cur_z = current_pose.get("z", target_z)

        dist_xy = math.sqrt((cur_x - self.center_x)**2 + (cur_y - self.center_y)**2)
        if dist_xy > 5.0 and cur_z < self.z_hover:
            # Elevar primero verticalmente si no está en hover para evitar rayar el papel
            self.dobot.move_to(x=cur_x, y=cur_y, z=self.z_hover, r=self.r, wait=True, mode=MODE_PTP.MOVL_XYZ)
            self.dobot.move_to(x=self.center_x, y=self.center_y, z=self.z_hover, r=self.r, wait=True, mode=MODE_PTP.MOVJ_XYZ)
        elif dist_xy > 5.0:
            self.dobot.move_to(x=self.center_x, y=self.center_y, z=self.z_hover, r=self.r, wait=True, mode=MODE_PTP.MOVJ_XYZ)

        logger.info(f"Moviendo efector final a posición inicial: (X={self.center_x:.2f}, Y={self.center_y:.2f}, Z={target_z:.2f}, R={self.r:.2f}°) mm")
        self.dobot.move_to(x=self.center_x, y=self.center_y, z=target_z, r=self.r, wait=True, mode=MODE_PTP.MOVL_XYZ)
        return (self.center_x, self.center_y, target_z)

    def capture_subject(
        self,
        image_path: Optional[str] = None,
        save_path: Optional[str] = "captured_subject.jpg"
    ) -> Tuple[Optional[np.ndarray], str]:
        """
        Obtiene la fotografía del objeto a dibujar:
        - Si image_path existe en disco, carga directamente esa foto del objeto.
        - Si no, captura un fotograma con la cámara (GoPro o webcam USB).
        """
        if image_path and os.path.exists(image_path):
            frame = cv2.imread(image_path)
            if frame is None:
                raise RuntimeError(f"No se pudo cargar la imagen del objeto desde: {image_path}")
            logger.info(f"Imagen del objeto cargada desde: {image_path}")
            if save_path and os.path.abspath(image_path) != os.path.abspath(save_path):
                cv2.imwrite(save_path, frame)
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            b64 = base64.b64encode(buffer).decode("utf-8")
            return frame, b64

        frame = self.camera.get_latest_frame()
        if frame is None:
            time.sleep(0.3)
            frame = self.camera.get_latest_frame()

        if frame is None:
            raise RuntimeError("No se pudo capturar fotograma del objeto desde la cámara.")

        if save_path:
            cv2.imwrite(save_path, frame)
            logger.info(f"Fotograma del objeto guardado en: {save_path}")

        b64 = self.camera.get_frame_base64()
        if not b64:
            raise RuntimeError("Error al codificar imagen del objeto en base64.")

        return frame, b64

    def create_coordinate_map(
        self,
        image_base64: str,
        user_instruction: str = "Identifica el objeto en la imagen y genera el mapa de coordenadas para ilustrarlo en el cuaderno"
    ) -> Dict[str, Any]:
        """
        Envía la imagen a Claude para extraer el mapa de coordenadas vectoriales continuas.
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Instrucción: {user_instruction}\n"
                            "Analiza minuciosamente el OBJETO real en la fotografía (la imagen es del objeto, no del cuaderno). "
                            "Identifícalo y sintetiza un boceto de líneas limpias y estilizadas para dibujarlo en el cuaderno con trazos continuos."
                        )
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_base64
                        }
                    }
                ]
            }
        ]

        logger.info(f"Consultando modelo {self.model} para generar mapa de coordenadas del objeto...")
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=DRAWING_PROMPT,
            messages=messages,
            tools=[DRAWING_TOOL]
        )

        identified_subject = "Objeto detectado"
        strokes = []

        for block in response.content:
            if block.type == "tool_use" and block.name == "generate_drawing_trajectory":
                traj_data = block.input
                identified_subject = traj_data.get("identified_subject", "Objeto detectado")
                strokes = traj_data.get("strokes", [])
                logger.info(f"Objeto identificado: '{identified_subject}' con {len(strokes)} trazos continuos.")
                break

        if not strokes:
            # Fallback en caso de que el modelo haya devuelto texto en vez del tool_use
            logger.warning("El modelo no invocó la herramienta con trazos. Intentando extraer trazos de respaldo...")
            strokes = [
                {
                    "name": "contorno_objeto",
                    "points": [(-0.4, -0.4), (0.4, -0.4), (0.4, 0.4), (-0.4, 0.4), (-0.4, -0.4)]
                }
            ]

        return {
            "identified_subject": identified_subject,
            "strokes": strokes
        }

    def convert_to_robot_coordinates(self, raw_strokes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convierte coordenadas normalizadas [-1.0, 1.0] a coordenadas físicas en milímetros
        del Dobot Magician sobre el papel, verificando y garantizando límites mecánicos.
        """
        robot_strokes = []

        for stroke in raw_strokes:
            name = stroke.get("name", "trazo")
            points = stroke.get("points", [])
            converted_pts = []

            for pt in points:
                u, v = float(pt[0]), float(pt[1])
                # u (horizontal en imagen) mapea al eje Y del robot
                # v (vertical en imagen) mapea al eje X del robot (+X avanza hacia arriba del papel)
                rx = self.center_x + (v * (self.canvas_height / 2.0))
                ry = self.center_y + (u * (self.canvas_width / 2.0))

                # Clamping de seguridad
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

                converted_pts.append((round(rx, 2), round(ry, 2)))

            if len(converted_pts) >= 2:
                robot_strokes.append({
                    "name": name,
                    "points": converted_pts
                })

        return robot_strokes

    def generate_preview(
        self,
        robot_strokes: List[Dict[str, Any]],
        output_path: str = "drawing_preview.png"
    ) -> str:
        """
        Renderiza una imagen gráfica de vista previa del cuaderno de 25x17 cm (250x170 mm),
        el punto central inicial del efector y los trazos a dibujar para aprobación del usuario.
        """
        # Dimensiones de la imagen de previsualización (proporcional al cuaderno 250x170 mm)
        scale = 3.0  # 1 mm = 3 px
        margin_px = 50
        notebook_w_px = int(self.notebook_width * scale)   # 250 * 3 = 750 px
        notebook_h_px = int(self.notebook_height * scale)  # 170 * 3 = 510 px

        img_w = notebook_w_px + (margin_px * 2)
        img_h = notebook_h_px + (margin_px * 2) + 40  # Espacio superior para cabecera

        preview = np.full((img_h, img_w, 3), 248, dtype=np.uint8)

        # 1. Borde y fondo del cuaderno (25x17 cm)
        nb_x1 = margin_px
        nb_y1 = margin_px + 30
        nb_x2 = nb_x1 + notebook_w_px
        nb_y2 = nb_y1 + notebook_h_px

        # Hoja del cuaderno en blanco puro con sombra ligera
        cv2.rectangle(preview, (nb_x1 + 4, nb_y1 + 4), (nb_x2 + 4, nb_y2 + 4), (210, 210, 210), -1)
        cv2.rectangle(preview, (nb_x1, nb_y1), (nb_x2, nb_y2), (255, 255, 255), -1)
        cv2.rectangle(preview, (nb_x1, nb_y1), (nb_x2, nb_y2), (160, 160, 160), 2)

        # Cabecera con dimensiones
        cv2.putText(
            preview,
            f"CUADERNO: {self.notebook_width / 10.0:.0f}x{self.notebook_height / 10.0:.0f} cm ({self.notebook_width:.0f}x{self.notebook_height:.0f} mm)",
            (nb_x1, nb_y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (40, 40, 40), 2
        )

        # 2. Área útil de dibujo (margen interno)
        pad_x_px = int((notebook_w_px - (self.canvas_width * scale)) / 2.0)
        pad_y_px = int((notebook_h_px - (self.canvas_height * scale)) / 2.0)
        canv_x1 = nb_x1 + pad_x_px
        canv_y1 = nb_y1 + pad_y_px
        canv_x2 = canv_x1 + int(self.canvas_width * scale)
        canv_y2 = canv_y1 + int(self.canvas_height * scale)

        cv2.rectangle(preview, (canv_x1, canv_y1), (canv_x2, canv_y2), (235, 240, 245), -1)
        cv2.rectangle(preview, (canv_x1, canv_y1), (canv_x2, canv_y2), (200, 210, 220), 1)
        cv2.putText(
            preview,
            f"Area de dibujo util: {self.canvas_width:.0f}x{self.canvas_height:.0f} mm",
            (canv_x1 + 8, canv_y1 + 18),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 130, 140), 1
        )

        # 3. Centro del cuaderno y punto de inicio del efector final
        cx_px = nb_x1 + (notebook_w_px // 2)
        cy_px = nb_y1 + (notebook_h_px // 2)

        # Retícula y marcador en el centro
        cv2.drawMarker(preview, (cx_px, cy_px), (0, 0, 220), cv2.MARKER_CROSS, 24, 2)
        cv2.circle(preview, (cx_px, cy_px), 6, (0, 0, 220), 1)
        cv2.putText(
            preview,
            f"INICIO EFECTOR / CENTRO (X={self.center_x:.1f}, Y={self.center_y:.1f})",
            (cx_px - 140, cy_px - 14),
            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 180), 1
        )

        # Función para transformar coordenadas Dobot (rx, ry) a píxeles
        def to_px(rx: float, ry: float) -> Tuple[int, int]:
            # ry mapea al eje horizontal de la imagen (+Y robot hacia la izquierda/derecha)
            px = int(cx_px + ((ry - self.center_y) * scale))
            # rx mapea al eje vertical de la imagen (+X robot hacia arriba/adelante)
            py = int(cy_px - ((rx - self.center_x) * scale))
            return max(0, min(img_w - 1, px)), max(0, min(img_h - 1, py))

        # 4. Dibujar los trazos calculados
        colors = [
            (210, 40, 40),    # Azul
            (30, 160, 30),    # Verde
            (40, 40, 220),    # Rojo
            (160, 40, 180),   # Magenta
            (30, 140, 210)    # Naranja
        ]

        for s_idx, stroke in enumerate(robot_strokes):
            pts = stroke["points"]
            color = colors[s_idx % len(colors)]
            px_pts = [to_px(p[0], p[1]) for p in pts]

            for i in range(len(px_pts) - 1):
                cv2.line(preview, px_pts[i], px_pts[i + 1], color, 2, cv2.LINE_AA)

            # Punto de inicio del trazo (verde)
            cv2.circle(preview, px_pts[0], 5, (0, 190, 0), -1)
            # Punto de fin del trazo (rojo)
            cv2.circle(preview, px_pts[-1], 5, (0, 0, 200), -1)

        # Pie con leyenda
        cv2.putText(
            preview,
            "Verde: Inicio de trazo | Rojo: Fin de trazo | Cruz Roja: Centro inicial del brazo",
            (nb_x1, img_h - 12),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (90, 90, 90), 1
        )

        cv2.imwrite(output_path, preview)
        logger.info(f"Previsualización del cuaderno guardada en: {output_path}")
        return output_path

    def run_pipeline(
        self,
        instruction: str = DEFAULT_INSTRUCTION,
        image_path: Optional[str] = None,
        captured_image_path: str = "captured_subject.jpg",
        preview_image_path: str = "drawing_preview.png",
        confirm_before_draw: bool = True,
        prompt_before_capture: bool = True
    ) -> Dict[str, Any]:
        """
        Ejecuta el flujo completo:
        0. Posiciona el efector final en contacto con el papel en el centro exacto del cuaderno (25x17 cm).
        1. Captura única de la imagen del OBJETO (no del cuaderno). Sin movimientos verticales.
        2. Extracción artística y mapa de coordenadas del objeto con Claude. Sin movimientos verticales.
        3. Previsualización gráfica sobre el cuaderno de 25x17 cm.
        4. Aprobación obligatoria antes de dibujar. Al aprobar, sube el brazo verticalmente.
        5. Trazado continuo en el robot y retorno final al centro en contacto con el papel.
        """
        console.print(Panel(
            f"[bold cyan]🎯 Instrucción:[/bold cyan] {instruction}\n"
            f"[bold yellow]Cuaderno físico de dibujo:[/bold yellow] {self.notebook_width / 10.0:.0f}x{self.notebook_height / 10.0:.0f} cm ({self.notebook_width:.0f}x{self.notebook_height:.0f} mm)\n"
            f"[bold yellow]Centro inicial del efector:[/bold yellow] X={self.center_x:.2f} mm, Y={self.center_y:.2f} mm, R={self.r:.2f}° (en contacto con papel)\n"
            f"[bold yellow]Área útil de dibujo:[/bold yellow] {self.canvas_width:.1f}x{self.canvas_height:.1f} mm (margen {self.margin:.1f} mm)\n"
            f"[bold green]Alturas:[/bold green] Z_draw={self.z_draw:.2f} mm (contacto), Z_hover={self.z_hover:.2f} mm (tránsito)\n"
            f"[bold magenta]Modo:[/bold magenta] {'SIMULACIÓN (Mock Dobot)' if self.dobot.mock else 'HARDWARE FÍSICO'}",
            title="[bold green]Dobot Magician — Trazado Visual de Objetos en Cuaderno[/bold green]"
        ))

        # Paso 0: Efector final siempre inicia en contacto con el papel en el centro del cuaderno
        console.rule("[bold cyan]Paso 0: Posicionando efector en contacto con el papel en el centro...[/bold cyan]")
        cx, cy, cz = self.move_to_center(hover=False)
        console.print(
            f"[bold green]✔ Efector en contacto con el papel en la posición inicial:[/bold green] "
            f"X={cx:.2f} mm, Y={cy:.2f} mm, Z={cz:.2f} mm (Z_draw), R={self.r:.2f}°\n"
            f"[dim]El marcador está en contacto físico con el papel en ({self.center_x:.2f}, {self.center_y:.2f}, {self.z_draw:.2f}). Alinea el cuaderno bajo la punta.[/dim]"
        )

        # Paso 1: Captura de la imagen del OBJETO (no del cuaderno) - Sin movimiento vertical
        console.rule("[bold cyan]Paso 1: Capturando imagen del OBJETO a dibujar...[/bold cyan]")
        if image_path and os.path.exists(image_path):
            console.print(f"[bold green]✔ Usando fotografía del objeto desde archivo:[/bold green] [cyan]{image_path}[/cyan]")
            _, img_b64 = self.capture_subject(image_path=image_path, save_path=captured_image_path)
        else:
            if prompt_before_capture and not self.dobot.mock:
                console.print(
                    "[bold yellow]📸 Enfoque del Objeto:[/bold yellow] "
                    "Apunta la cámara al OBJETO que deseas que el Dobot dibuje (ej. una taza, una fruta, unas tijeras, un juguete, etc.)."
                )
                console.input("[bold cyan]Presiona Enter cuando el objeto esté listo frente a la cámara...[/bold cyan]")
            _, img_b64 = self.capture_subject(save_path=captured_image_path)
            console.print(f"[bold green]✔ Fotograma del objeto capturado y guardado en:[/bold green] [cyan]{captured_image_path}[/cyan]")

        # Paso 2: Análisis del objeto y síntesis del boceto con Claude - Sin movimiento vertical
        console.rule("[bold cyan]Paso 2: Análisis del objeto y síntesis del boceto con Claude...[/bold cyan]")
        with console.status("[bold green]Claude está analizando el objeto y sintetizando los trazos vectoriales del boceto...[/bold green]"):
            traj_data = self.create_coordinate_map(image_base64=img_b64, user_instruction=instruction)

        subject = traj_data["identified_subject"]
        raw_strokes = traj_data["strokes"]
        console.print(f"[bold green]✔ Objeto identificado y sintetizado:[/bold green] [yellow]{subject}[/yellow]")
        console.print(f"[bold green]✔ Total de trazos continuos generados:[/bold green] {len(raw_strokes)}")

        # Paso 3: Conversión a coordenadas del Dobot y Previsualización - Sin movimiento vertical
        console.rule("[bold cyan]Paso 3: Convirtiendo a milímetros del Dobot y generando previsualización...[/bold cyan]")
        robot_strokes = self.convert_to_robot_coordinates(raw_strokes)
        preview_file = self.generate_preview(robot_strokes, output_path=preview_image_path)

        table = Table(title=f"Trazos a ejecutar en el Cuaderno ({self.notebook_width:.0f}x{self.notebook_height:.0f} mm)")
        table.add_column("Trazo", style="cyan")
        table.add_column("Puntos", style="yellow")
        table.add_column("Punto Inicio (X, Y mm)", style="magenta")
        table.add_column("Punto Fin (X, Y mm)", style="magenta")

        total_points = 0
        for s in robot_strokes:
            pts = s["points"]
            total_points += len(pts)
            table.add_row(
                s["name"],
                str(len(pts)),
                f"({pts[0][0]:.1f}, {pts[0][1]:.1f})",
                f"({pts[-1][0]:.1f}, {pts[-1][1]:.1f})"
            )
        console.print(table)
        console.print(f"[bold green]✔ Previsualización gráfica generada en:[/bold green] [cyan]{os.path.abspath(preview_file)}[/cyan]")
        console.print(f"[dim]Total de puntos en la trayectoria: {total_points}[/dim]")

        # Paso 4: Aprobación obligatoria antes de dibujar
        # "Al aprobar por primera vez, sube el brazo. No lo muevas verticalmente hasta iniciar el dibujo."
        if confirm_before_draw:
            console.rule("[bold yellow]Paso 4: Aprobación del boceto requerida[/bold yellow]")
            console.print(Panel(
                f"[bold yellow]⚠️  EL BOCETO REQUIERE TU APROBACIÓN ANTES DE SER DIBUJADO[/bold yellow]\n\n"
                f"El efector final permanece quieto en el centro en contacto con el papel.\n"
                f"Inspecciona la imagen con los trazos planificados en:\n"
                f"👉 [bold underline cyan]{os.path.abspath(preview_file)}[/bold underline cyan]\n\n"
                f"• [bold green]A[/bold green] o [bold green]Enter[/bold green]: [green]APROBAR[/green] (sube el brazo y comienza a dibujar en el cuaderno).\n"
                f"• [bold red]R[/bold red]: [red]RECHAZAR / CANCELAR[/red] (el brazo permanecerá seguro en el centro sin trazar).\n"
                f"• [bold yellow]O[/bold yellow]: [yellow]ABRIR[/yellow] la imagen de previsualización con el visor del sistema.",
                title="[bold yellow]Panel de Aprobación[/bold yellow]",
                border_style="yellow"
            ))

            while True:
                resp = console.input("\n[bold yellow]¿Autorizar al Dobot para dibujar este boceto en el cuaderno? [A/r/o] (Enter = Aprobar): [/bold yellow]").strip().lower()
                if resp in ["", "a", "s", "si", "y", "yes", "aprobar"]:
                    console.print("[bold green]✔ Boceto APROBADO por el usuario.[/bold green]")
                    # Al aprobar por primera vez, sube el brazo verticalmente antes de iniciar el dibujo
                    console.print(f"[bold cyan]➜ Subiendo el brazo verticalmente a altura de tránsito (Z={self.z_hover:.2f} mm)...[/bold cyan]")
                    self.dobot.move_to(x=self.center_x, y=self.center_y, z=self.z_hover, r=self.r, wait=True, mode=MODE_PTP.MOVL_XYZ)
                    break
                elif resp in ["o", "open", "abrir"]:
                    try:
                        import subprocess
                        subprocess.Popen(["xdg-open", preview_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        console.print(f"[dim]Abriendo {preview_file}...[/dim]")
                    except Exception:
                        console.print(f"[dim]No se pudo abrir automáticamente. Puedes abrir {preview_file} manualmente.[/dim]")
                else:
                    console.print("[red]❌ Boceto RECHAZADO o cancelado por el usuario. No se realizará ningún trazado.[/red]")
                    return {
                        "success": False,
                        "subject": subject,
                        "strokes": robot_strokes,
                        "reason": "Boceto no aprobado por el usuario."
                    }
        else:
            # Si no requiere confirmación previa, sube el brazo verticalmente justo antes de iniciar el trazado
            console.print(f"[bold cyan]➜ Subiendo el brazo verticalmente a altura de tránsito (Z={self.z_hover:.2f} mm)...[/bold cyan]")
            self.dobot.move_to(x=self.center_x, y=self.center_y, z=self.z_hover, r=self.r, wait=True, mode=MODE_PTP.MOVL_XYZ)

        # Paso 5: Trazado continuo en el robot (sin capturar fotos intermedias)
        console.rule("[bold cyan]Paso 5: Trazado continuo en el Dobot Magician...[/bold cyan]")
        start_time = time.time()
        draw_trajectory_sequence(
            bot=self.dobot,
            strokes=robot_strokes,
            z_draw=self.z_draw,
            z_hover=self.z_hover,
            velocity=self.velocity,
            acceleration=self.acceleration,
            status_callback=lambda msg: console.print(f"[cyan]➜[/cyan] {msg}")
        )
        duration = time.time() - start_time

        # Retornar el efector final al centro del cuaderno y descender a contacto con el papel
        console.print("[dim]Retornando efector final al centro del cuaderno en contacto con el papel...[/dim]")
        self.move_to_center(hover=False)

        console.print(Panel(
            f"[bold green]✅ ¡Dibujo continuo completado con éxito![/bold green]\n"
            f"[cyan]Figura:[/cyan] {subject}\n"
            f"[yellow]Trazos ejecutados:[/yellow] {len(robot_strokes)} ({total_points} puntos)\n"
            f"[magenta]Tiempo de ejecución:[/magenta] {duration:.1f} segundos\n"
            f"[green]Posición final:[/green] Centro del cuaderno en contacto con papel (X={self.center_x:.2f}, Y={self.center_y:.2f}, Z={self.z_draw:.2f}, R={self.r:.2f}°) mm\n"
            f"[dim]Vista previa de la trayectoria disponible en: {preview_file}[/dim]",
            title="[bold green]Dobot Magician — Tarea Finalizada[/bold green]",
            border_style="green"
        ))

        return {
            "success": True,
            "subject": subject,
            "strokes": robot_strokes,
            "total_points": total_points,
            "duration": duration,
            "preview_image": preview_file
        }
