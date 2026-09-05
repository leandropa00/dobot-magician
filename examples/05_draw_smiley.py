#!/usr/bin/env python3
"""
Ejemplo 5: Dibujo de una Carita Feliz con el marcador en el Dobot Magician.

Uso:
  # Probar primero en el aire (seguro, sin tocar la mesa ni papel):
  python examples/05_draw_smiley.py --air-draw

  # Dibujar sobre papel indicando la altura Z de contacto (por ejemplo Z = 0 mm):
  python examples/05_draw_smiley.py --z-draw 0.0

  # En modo simulación (sin conectar robot):
  python examples/05_draw_smiley.py --mock
"""

import sys
import argparse
from dobot_controller import DobotController
from dobot_controller.drawing import draw_smiley_face

def main():
    parser = argparse.ArgumentParser(description="Dibuja una carita feliz con el marcador en Dobot Magician")
    parser.add_argument("--z-draw", type=float, default=0.0, help="Altura Z (mm) donde el marcador toca el papel (default: 0.0)")
    parser.add_argument("--z-hover", type=float, default=15.0, help="Altura Z (mm) de tránsito en el aire (default: 15.0)")
    parser.add_argument("--radius", type=float, default=30.0, help="Radio de la cara en mm (default: 30.0)")
    parser.add_argument("--cx", type=float, default=220.0, help="Centro X en mm (default: 220.0)")
    parser.add_argument("--cy", type=float, default=0.0, help="Centro Y en mm (default: 0.0)")
    parser.add_argument("--speed", type=float, default=35.0, help="Velocidad lineal de dibujo en mm/s (default: 35.0)")
    parser.add_argument("--air-draw", action="store_true", help="Dibuja a 35mm en el aire como prueba de seguridad")
    parser.add_argument("--mock", action="store_true", help="Ejecutar en modo simulado en memoria")
    args = parser.parse_args()

    actual_z_draw = 35.0 if args.air_draw else args.z_draw
    actual_z_hover = 45.0 if args.air_draw else args.z_hover

    print("=" * 60)
    print(f" DIBUJO DE CARITA FELIZ - DOBOT MAGICIAN")
    print(f" Modo: {'AIR DRAW (En el aire)' if args.air_draw else ('Simulación' if args.mock else 'HARDWARE REAL')}")
    print(f" Centro: ({args.cx}, {args.cy}) mm | Radio: {args.radius} mm")
    print(f" Z_draw (contacto): {actual_z_draw} mm | Z_hover (tránsito): {actual_z_hover} mm")
    print("=" * 60)

    with DobotController(mock=args.mock) as bot:
        def callback(msg):
            print(f" -> {msg}")

        draw_smiley_face(
            bot=bot,
            center_x=args.cx,
            center_y=args.cy,
            radius=args.radius,
            z_draw=actual_z_draw,
            z_hover=actual_z_hover,
            velocity=args.speed,
            acceleration=args.speed,
            status_callback=callback
        )

    print("\n✔ ¡Proceso finalizado con éxito!")

if __name__ == "__main__":
    main()
