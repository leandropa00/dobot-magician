#!/usr/bin/env python3
"""Ejemplo 2: Movimiento cartesiano básico y lectura de pose."""

import sys
from dobot_controller import DobotController

def main():
    use_mock = "--mock" in sys.argv
    print(f"=== Movimiento Básico (Modo: {'Simulación' if use_mock else 'Hardware Real'}) ===")

    # Uso mediante context manager para liberar el puerto y desenergizar efectores al salir
    with DobotController(mock=use_mock) as bot:
        # 1. Leer posición inicial
        pose_init = bot.get_pose()
        print(f"Posición inicial: X={pose_init['x']} mm, Y={pose_init['y']} mm, Z={pose_init['z']} mm, R={pose_init['r']}°")
        print(f"Ángulos: J1={pose_init['j1']}°, J2={pose_init['j2']}°, J3={pose_init['j3']}°, J4={pose_init['j4']}°")

        # 2. Mover a una posición objetivo segura (X=230, Y=0, Z=40)
        target_x, target_y, target_z = 230.0, 0.0, 40.0
        print(f"\nMoviendo a posición segura: X={target_x}, Y={target_y}, Z={target_z}...")
        bot.move_to(x=target_x, y=target_y, z=target_z, wait=True)

        # 3. Movimiento relativo (+20mm en Y)
        print("Realizando desplazamiento relativo: delta Y = +30mm...")
        bot.move_rel(dy=30.0, wait=True)

        # 4. Movimiento relativo (-30mm en Y para regresar)
        print("Regresando a posición central: delta Y = -30mm...")
        bot.move_rel(dy=-30.0, wait=True)

        # 5. Pose final
        pose_final = bot.get_pose()
        print(f"\nPosición final: X={pose_final['x']} mm, Y={pose_final['y']} mm, Z={pose_final['z']} mm")

if __name__ == "__main__":
    main()
