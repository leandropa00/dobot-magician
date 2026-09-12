"""Módulo de generación y ejecución de trayectorias de dibujo para Dobot Magician."""

import math
import time
import logging
from typing import List, Tuple, Dict, Callable, Optional, Any
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
    1. Si no está posicionado sobre el primer punto a la altura z_draw, transita en el aire (z_hover) y baja (z_draw).
       Si ya está en el primer punto a z_draw, dibuja directamente sin subir en Z.
    2. Traza linealmente (MOVL_XYZ) punto por punto a z_draw, conservando la altura configurada.
    3. Levanta el marcador al aire (z_hover) solo al concluir el trazo para desplazarse al siguiente.
    """
    if not points:
        return

    first_x, first_y = points[0]
    cur = bot.get_pose()

    # Si ya se encuentra en el primer punto del trazo a la altura de dibujo Z_draw, no elevar en Z
    already_at_start = (
        math.hypot(cur["x"] - first_x, cur["y"] - first_y) < 1.0 and
        abs(cur["z"] - z_draw) < 1.0
    )

    if not already_at_start:
        # 1. Posicionamiento en el aire sobre el inicio del trazo
        bot.move_to(x=first_x, y=first_y, z=z_hover, wait=True, mode=MODE_PTP.MOVJ_XYZ)
        # 2. Bajar marcador al papel conservando estrictamente la altura Z_draw configurada
        bot.move_to(x=first_x, y=first_y, z=z_draw, wait=True, mode=MODE_PTP.MOVL_XYZ)

    # 3. Dibujar todos los puntos subsecuentes linealmente a z_draw
    for idx, (px, py) in enumerate(points[1:], start=1):
        bot.move_to(x=px, y=py, z=z_draw, wait=True, mode=MODE_PTP.MOVL_XYZ)
        if progress_callback and idx % 4 == 0:
            progress_callback(f"Punto {idx}/{len(points)}")

    # 4. Levantar marcador al aire al concluir el trazo
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


def draw_trajectory_sequence(
    bot: DobotController,
    strokes: List[Dict[str, Any]],
    z_draw: float = 0.0,
    z_hover: float = 15.0,
    velocity: float = 40.0,
    acceleration: float = 40.0,
    status_callback: Optional[Callable[[str], None]] = None
):
    """
    Ejecuta una secuencia continua de trazos en el Dobot Magician sin interrupción:
    1. Configura velocidad y aceleración de dibujo.
    2. Para cada trazo en strokes, levanta el marcador, se posiciona, desciende a z_draw,
       dibuja todos los puntos de forma lineal continua y vuelve a levantarse.
    3. Al finalizar, regresa a posición de reposo en el aire.
    """
    if not strokes:
        return

    bot.set_speed(velocity=velocity, acceleration=acceleration)
    total_strokes = len(strokes)

    for i, stroke in enumerate(strokes, start=1):
        name = stroke.get("name", f"Trazo_{i}")
        points = stroke.get("points", [])
        if not points:
            continue
        pt_list = [(float(p[0]), float(p[1])) for p in points]
        if status_callback:
            status_callback(f"Dibujando trazo {i}/{total_strokes}: {name} ({len(pt_list)} puntos)...")
        logger.info(f"Dibujando {name} ({len(pt_list)} puntos)")
        draw_stroke(bot, pt_list, z_draw=z_draw, z_hover=z_hover)

    # Posición de reposo al aire sobre el centro o último trazo
    if strokes and strokes[-1].get("points"):
        last_pt = strokes[-1]["points"][-1]
        bot.move_to(x=float(last_pt[0]), y=float(last_pt[1]), z=z_hover + 10.0, wait=True, mode=MODE_PTP.MOVJ_XYZ)

    if status_callback:
        status_callback("Secuencia continua de dibujo completada con éxito.")
