"""Módulo de generación y ejecución de trayectorias de dibujo para Dobot Magician."""

import math
import time
import logging
from typing import List, Tuple, Dict, Callable, Optional
from pydobotplus.dobotplus import MODE_PTP

from dobot_controller.controller import DobotController

logger = logging.getLogger(__name__)

Point2D = Tuple[float, float]


def generate_circle(cx: float, cy: float, radius: float, num_points: int = 36) -> List[Point2D]:
    """Genera los puntos de una circunferencia cerrada en el plano XY."""
    points = []
    for i in range(num_points + 1):
        angle = 2.0 * math.pi * (i / num_points)
        px = cx + radius * math.cos(angle)
        py = cy + radius * math.sin(angle)
        points.append((round(px, 2), round(py, 2)))
    return points


def generate_smile_arc(
    center_x: float,
    center_y: float,
    radius: float,
    angle_span_deg: float = 55.0,
    num_points: int = 16
) -> List[Point2D]:
    """
    Genera los puntos de la curva de la sonrisa en el plano XY.
    Orientación: La parte superior de la cara está en +X (lejos de la base) y la inferior en -X.
    La curvatura sube hacia +X en los extremos para formar una sonrisa visible.
    """
    points = []
    half_span = math.radians(angle_span_deg)
    r_smile = radius * 0.55
    base_x = center_x - radius * 0.35

    for i in range(num_points):
        # theta va de -half_span a +half_span
        theta = -half_span + (2.0 * half_span) * (i / (num_points - 1))
        # Y se desplaza a los lados
        py = center_y + r_smile * math.sin(theta)
        # X sube en los extremos: curvatura positiva
        px = base_x + r_smile * (1.0 - math.cos(theta)) * 0.8
        points.append((round(px, 2), round(py, 2)))
    return points


def generate_smiley_paths(
    center_x: float = 220.0,
    center_y: float = 0.0,
    radius: float = 30.0
) -> Dict[str, List[Point2D]]:
    """
    Genera todas las trayectorias de la carita feliz:
    1. Contorno de la cabeza (círculo)
    2. Ojo izquierdo (pequeño círculo)
    3. Ojo derecho (pequeño círculo)
    4. Sonrisa (arco curvado hacia arriba)
    """
    # 1. Contorno
    face_contour = generate_circle(center_x, center_y, radius, num_points=36)

    # 2. Ojos (ubicados hacia +X y a los lados +/- Y)
    eye_radius = max(2.5, radius * 0.1)
    eye_offset_x = radius * 0.32
    eye_offset_y = radius * 0.36

    left_eye = generate_circle(center_x + eye_offset_x, center_y - eye_offset_y, eye_radius, num_points=12)
    right_eye = generate_circle(center_x + eye_offset_x, center_y + eye_offset_y, eye_radius, num_points=12)

    # 3. Sonrisa
    smile = generate_smile_arc(center_x, center_y, radius, angle_span_deg=50.0, num_points=16)

    return {
        "Contorno": face_contour,
        "Ojo Izquierdo": left_eye,
        "Ojo Derecho": right_eye,
        "Sonrisa": smile
    }


def draw_stroke(
    bot: DobotController,
    points: List[Point2D],
    z_draw: float,
    z_hover: float,
    progress_callback: Optional[Callable[[str], None]] = None
):
    """
    Traza una línea continua (stroke):
    1. Se posiciona en el aire sobre el primer punto (z_hover)
    2. Baja el marcador sobre el papel (z_draw)
    3. Traza de forma lineal (MOVL_XYZ) punto por punto
    4. Levanta el marcador al aire (z_hover)
    """
    if not points:
        return

    first_x, first_y = points[0]

    # 1. Posicionamiento en el aire sobre el inicio del trazo
    bot.move_to(x=first_x, y=first_y, z=z_hover, wait=True, mode=MODE_PTP.MOVJ_XYZ)

    # 2. Bajar marcador al papel
    bot.move_to(x=first_x, y=first_y, z=z_draw, wait=True, mode=MODE_PTP.MOVL_XYZ)

    # 3. Dibujar todos los puntos subsecuentes linealmente
    for idx, (px, py) in enumerate(points[1:], start=1):
        bot.move_to(x=px, y=py, z=z_draw, wait=True, mode=MODE_PTP.MOVL_XYZ)
        if progress_callback and idx % 4 == 0:
            progress_callback(f"Punto {idx}/{len(points)}")

    # 4. Levantar marcador al aire
    last_x, last_y = points[-1]
    bot.move_to(x=last_x, y=last_y, z=z_hover, wait=True, mode=MODE_PTP.MOVL_XYZ)


def draw_smiley_face(
    bot: DobotController,
    center_x: float = 220.0,
    center_y: float = 0.0,
    radius: float = 30.0,
    z_draw: float = 0.0,
    z_hover: float = 15.0,
    velocity: float = 40.0,
    acceleration: float = 40.0,
    status_callback: Optional[Callable[[str], None]] = None
):
    """
    Dibuja una carita feliz completa usando el marcador montado en el efector final.
    """
    # Configurar velocidad adecuada para dibujo con marcador
    bot.set_speed(velocity=velocity, acceleration=acceleration)

    paths = generate_smiley_paths(center_x=center_x, center_y=center_y, radius=radius)

    for name, points in paths.items():
        if status_callback:
            status_callback(f"Dibujando {name} ({len(points)} puntos)...")
        logger.info(f"Iniciando trazo: {name}")
        draw_stroke(bot, points, z_draw=z_draw, z_hover=z_hover)

    # Regresar a posición de reposo en el aire sobre el centro
    bot.move_to(x=center_x, y=center_y, z=z_hover + 10.0, wait=True, mode=MODE_PTP.MOVJ_XYZ)
    if status_callback:
        status_callback("¡Carita feliz completada con éxito!")
