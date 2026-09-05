#!/usr/bin/env python3
"""Ejemplo 4: Demostración de simulación y validación de límites de seguridad."""

from dobot_controller import DobotController, SafetyBoundaryError

def main():
    print("=== Demostración de Límites de Seguridad en Simulación ===")

    with DobotController(mock=True, enforce_safety=True) as bot:
        pose = bot.get_pose()
        print(f"Pose inicial: {pose}")

        # 1. Movimiento dentro de límites
        print("\n1. Probando posición válida (X=250, Y=50, Z=30)...")
        bot.move_to(x=250, y=50, z=30)
        print("✔ Movimiento permitido.")

        # 2. Intento de movimiento fuera de alcance máximo (>330mm)
        print("\n2. Probando posición fuera de alcance máximo (X=350, Y=100, Z=30)...")
        try:
            bot.move_to(x=350, y=100, z=30)
        except SafetyBoundaryError as e:
            print(f"✔ Interceptado correctamente por el sistema de seguridad:\n   -> {e}")

        # 3. Intento de movimiento por debajo de la altura mínima de la mesa
        print("\n3. Probando altura peligrosa hacia la mesa (Z=-100mm)...")
        try:
            bot.move_to(x=200, y=0, z=-100)
        except SafetyBoundaryError as e:
            print(f"✔ Interceptado correctamente por el sistema de seguridad:\n   -> {e}")

        # 4. Intento de movimiento demasiado cerca de la base (<160mm)
        print("\n4. Probando punto muy cercano a la base (X=100, Y=0, Z=50)...")
        try:
            bot.move_to(x=100, y=0, z=50)
        except SafetyBoundaryError as e:
            print(f"✔ Interceptado correctamente por el sistema de seguridad:\n   -> {e}")

if __name__ == "__main__":
    main()
