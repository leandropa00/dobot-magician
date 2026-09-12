#!/usr/bin/env python3
"""
Ejemplo 07: Dibujo continuo guiado por visión con Dobot Magician + GoPro + Claude VLA.

En lugar de capturar imágenes por cada movimiento, este script:
1. Captura UN SOLO fotograma con la GoPro del boceto o figura a dibujar.
2. Claude analiza la imagen y genera el mapa vectorial de coordenadas continuo (strokes).
3. Genera una previsualización gráfica (drawing_preview.png).
4. Envía la secuencia completa de trazos al Dobot Magician, que la dibuja de manera
   continua y fluida sin pausas intermedias.
"""

import os
import sys
import argparse
from dotenv import load_dotenv

from dobot_controller.controller import DobotController
from dobot_controller.vision.camera import GoProCapture
from dobot_controller.vision.visual_drawer import VisualTrajectoryDrawer

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Dibujo continuo con visión para Dobot Magician")
    parser.add_argument(
        "--instruction", "-i",
        default="Identifica el objeto frente a la cámara y dibújalo en el cuaderno",
        help="Instrucción para Claude (opcional, por defecto fija)"
    )
    parser.add_argument("--port", "-p", default=None, help="Puerto serie del Dobot (ej. /dev/ttyUSB0)")
    parser.add_argument("--source", "-s", default=None, help="Fuente de video (índice 0, 1 o URL)")
    parser.add_argument("--mock", "-m", action="store_true", help="Ejecutar en modo simulación (Mock Dobot + Mock Camera)")
    parser.add_argument("--center-x", type=float, default=235.50, help="Centro X del cuaderno en mm (default: 235.50)")
    parser.add_argument("--center-y", type=float, default=-10.45, help="Centro Y del cuaderno en mm (default: -10.45)")
    parser.add_argument("--notebook-width", type=float, default=250.0, help="Ancho del cuaderno en mm (25 cm = 250 mm)")
    parser.add_argument("--notebook-height", type=float, default=170.0, help="Alto del cuaderno en mm (17 cm = 170 mm)")
    parser.add_argument("--margin", type=float, default=15.0, help="Margen de seguridad respecto al borde en mm")
    parser.add_argument("--width", "-w", type=float, default=None, help="Ancho del área de dibujo en mm")
    parser.add_argument("--height", type=float, default=None, help="Alto del área de dibujo en mm")
    parser.add_argument("--z-draw", type=float, default=-38.59, help="Altura Z del marcador sobre el papel (default: -38.59)")
    parser.add_argument("--z-hover", type=float, default=-23.59, help="Altura Z de tránsito en el aire (default: -23.59)")
    parser.add_argument("--rotation", "-r", type=float, default=5.67, help="Orientación R del efector en grados (default: 5.67)")
    parser.add_argument("--velocity", "-v", type=float, default=40.0, help="Velocidad lineal de dibujo en mm/s (default: 40.0)")
    parser.add_argument("--image", "-f", default=None, help="Ruta a una fotografía local del objeto (opcional, si no se usa la cámara en vivo)")
    parser.add_argument("--no-confirm", action="store_true", help="Saltar aprobación manual (por defecto requiere aprobación)")
    parser.add_argument("--auto-capture", action="store_true", help="Capturar automáticamente sin esperar Enter frente a la cámara")
    parser.add_argument("--preview", default="drawing_preview.png", help="Archivo de imagen para la previsualización")
    parser.add_argument(
        "--model",
        default=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
        help="Modelo de Claude a utilizar (configurable vía ANTHROPIC_MODEL en .env)"
    )

    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY no encontrada. Define la variable en tu entorno o en el archivo .env")
        sys.exit(1)

    cam_src = None
    if args.source is not None:
        cam_src = int(args.source) if args.source.isdigit() else args.source

    with DobotController(port=args.port, mock=args.mock) as bot:
        with GoProCapture(source=cam_src, mock=args.mock) as cam:
            drawer = VisualTrajectoryDrawer(
                dobot=bot,
                camera=cam,
                api_key=api_key,
                model=args.model,
                center_x=args.center_x,
                center_y=args.center_y,
                r=args.rotation,
                notebook_width=args.notebook_width,
                notebook_height=args.notebook_height,
                margin=args.margin,
                canvas_width=args.width,
                canvas_height=args.height,
                z_draw=args.z_draw,
                z_hover=args.z_hover,
                velocity=args.velocity
            )

            result = drawer.run_pipeline(
                instruction=args.instruction,
                image_path=args.image,
                captured_image_path=args.snapshot,
                preview_image_path=args.preview,
                confirm_before_draw=not args.no_confirm,
                prompt_before_capture=not args.auto_capture
            )

            if result["success"]:
                print(f"\nDibujo '{result['subject']}' completado exitosamente en {result['duration']:.1f}s.")
            else:
                print(f"\nProceso detenido: {result.get('reason', 'Desconocido')}")


if __name__ == "__main__":
    main()
