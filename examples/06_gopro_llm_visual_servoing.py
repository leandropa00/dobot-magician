#!/usr/bin/env python3
"""
Ejemplo 06: Control en bucle cerrado (Visual Servoing) y aprendizaje visual-motor
con GoPro conectada por USB, Dobot Magician y Modelo Multimodal Claude (Anthropic).

Uso:
  # En simulación (sin robot ni cámara conectados):
  python examples/06_gopro_llm_visual_servoing.py --mock --goal "Centra el efector sobre el objeto rojo"

  # Con hardware físico:
  python examples/06_gopro_llm_visual_servoing.py --goal "Aprende la relación de ejes y acércate al cubo"
"""

import os
import sys
import argparse
import logging
from dotenv import load_dotenv

# Cargar variables de entorno (.env)
load_dotenv()

from dobot_controller.controller import DobotController
from dobot_controller.vision.camera import GoProCapture
from dobot_controller.vision.agent import VisionAgent
from dobot_controller.vision.visual_servo import VisualServoLoop
from rich.console import Console

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Dobot Magician + GoPro + Claude VLA Visual Servoing")
    parser.add_argument("--mock", action="store_true", help="Ejecutar en modo simulación (Mock Dobot y Mock Camera)")
    parser.add_argument("--port", type=str, default=None, help="Puerto serie del Dobot (ej. /dev/ttyUSB0)")
    parser.add_argument("--camera-source", type=str, default=None, help="Índice de cámara (0, 1), URL de stream o /dev/videoX")
    parser.add_argument("--goal", type=str, default="Aprende los ejes de la cámara mediante un micro-movimiento y acércate al objetivo rojo", help="Objetivo o instrucción en lenguaje natural")
    parser.add_argument("--steps", type=int, default=None, help="Número máximo de pasos (por defecto None = autónomo sin límite hasta finish_task)")
    parser.add_argument("--confirm", action="store_true", help="Solicitar confirmación manual antes de ejecutar cada movimiento")
    parser.add_argument("--model", type=str, default="claude-sonnet-4-5-20250929", help="Modelo de Claude a utilizar")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[bold red]Error:[/bold red] ANTHROPIC_API_KEY no encontrada. Define la variable de entorno o añádela en .env")
        sys.exit(1)

    console.print(f"[bold cyan]Iniciando sistema...[/bold cyan] (Modo: {'SIMULACIÓN / MOCK' if args.mock else 'HARDWARE FÍSICO'})")

    # 1. Conectar Dobot
    try:
        dobot = DobotController(port=args.port, mock=args.mock)
    except Exception as e:
        console.print(f"[bold red]Error conectando Dobot:[/bold red] {e}")
        console.print("[yellow]Tip: Puedes probar con el flag --mock para ejecutar en modo simulación.[/yellow]")
        sys.exit(1)

    # 2. Iniciar Cámara GoPro
    try:
        # Convertir fuente si es número
        cam_src = None
        if args.camera_source is not None:
            cam_src = int(args.camera_source) if args.camera_source.isdigit() else args.camera_source
        
        camera = GoProCapture(source=cam_src, mock=args.mock)
    except Exception as e:
        console.print(f"[bold red]Error iniciando cámara:[/bold red] {e}")
        dobot.close()
        sys.exit(1)

    # 3. Iniciar Agente Claude
    try:
        agent = VisionAgent(api_key=api_key, model=args.model)
    except Exception as e:
        console.print(f"[bold red]Error iniciando VisionAgent:[/bold red] {e}")
        dobot.close()
        camera.close()
        sys.exit(1)

    # 4. Crear Bucle de Servocontrol Visual
    servo = VisualServoLoop(
        dobot=dobot,
        camera=camera,
        agent=agent,
        max_step_mm=30.0,
        settle_time=0.4
    )

    try:
        servo.run_interactive_session(
            initial_goal=args.goal,
            max_iterations=args.steps,
            confirm_each_move=args.confirm
        )
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Sesión detenida por el usuario.[/bold yellow]")
    finally:
        console.print("[cyan]Cerrando conexiones...[/cyan]")
        dobot.close()
        camera.close()
        console.print("[green]Conexiones cerradas limpiamente.[/green]")


if __name__ == "__main__":
    main()
