#!/usr/bin/env python3
"""Ejemplo 3: Rutina completa de Pick & Place (recogida y colocación)."""

import sys
import time
from dobot_controller import DobotController

def main():
    use_mock = "--mock" in sys.argv
    print(f"=== Pick & Place (Modo: {'Simulación' if use_mock else 'Hardware Real'}) ===")

    # Coordenadas seguras de trabajo (en mm)
    # Punto A: Recogida
    pos_pick = (220.0, -80.0, 10.0)
    # Punto B: Entrega
    pos_place = (220.0, 80.0, 10.0)
    # Altura de viaje seguro para evitar obstáculos
    safe_altitude_z = 60.0

    with DobotController(mock=use_mock, velocity=80.0, acceleration=80.0) as bot:
        print(f"Punto de recogida: {pos_pick}")
        print(f"Punto de depósito: {pos_place}")
        print(f"Altura de tránsito seguro: Z={safe_altitude_z} mm\n")

        print("1. Moviendo sobre el punto de recogida...")
        bot.move_to(x=pos_pick[0], y=pos_pick[1], z=safe_altitude_z)

        print("2. Descendiendo a recoger el objeto...")
        bot.move_to(x=pos_pick[0], y=pos_pick[1], z=pos_pick[2])

        print("3. Activando ventosa de succión...")
        bot.set_suction(True)
        time.sleep(0.5)

        print("4. Elevando objeto a cota segura...")
        bot.move_to(x=pos_pick[0], y=pos_pick[1], z=safe_altitude_z)

        print("5. Trasladando a posición sobre destino...")
        bot.move_to(x=pos_place[0], y=pos_place[1], z=safe_altitude_z)

        print("6. Descendiendo a soltar objeto...")
        bot.move_to(x=pos_place[0], y=pos_place[1], z=pos_place[2])

        print("7. Desactivando succión...")
        bot.set_suction(False)
        time.sleep(0.5)

        print("8. Regresando a altura segura...")
        bot.move_to(x=pos_place[0], y=pos_place[1], z=safe_altitude_z)

        print("\n✔ Ciclo de Pick & Place completado.")

if __name__ == "__main__":
    main()
