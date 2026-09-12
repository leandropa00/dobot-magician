"""
Bucle cerrado de control visual (Visual Servoing) y aprendizaje visual-motor
para Dobot Magician + GoPro + Claude VLA.
"""

import time
import logging
from typing import Optional, Dict, Any, Callable
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dobot_controller.controller import DobotController
from dobot_controller.safety import SafetyBoundaryError
from dobot_controller.vision.camera import GoProCapture
from dobot_controller.vision.agent import VisionAgent

logger = logging.getLogger(__name__)
console = Console()

# Límites de seguridad para movimientos individuales en visual servoing
MAX_RELATIVE_STEP_MM = 35.0  # Máximo desplazamiento por iteración para evitar sacudidas


class VisualServoLoop:
    """
    Controlador en bucle cerrado que conecta la cámara GoPro,
    el robot Dobot Magician y el agente Claude Vision.
    """

    def __init__(
        self,
        dobot: DobotController,
        camera: GoProCapture,
        agent: VisionAgent,
        max_step_mm: float = MAX_RELATIVE_STEP_MM,
        settle_time: float = 0.4
    ):
        self.dobot = dobot
        self.camera = camera
        self.agent = agent
        self.max_step_mm = max_step_mm
        self.settle_time = settle_time
        self.history = []

        # Sincronización inicial si es simulación
        pose = self.dobot.get_pose()
        self.camera.sync_mock_with_dobot(pose["x"], pose["y"], pose["z"])

    def execute_tool(self, tool_call: Dict[str, Any]) -> str:
        """
        Ejecuta la herramienta solicitada por Claude con verificación de seguridad.
        """
        name = tool_call["name"]
        args = tool_call.get("input", {})
        tool_id = tool_call.get("id", "")

        try:
            if name == "move_relative":
                dx = float(args.get("dx", 0.0))
                dy = float(args.get("dy", 0.0))
                dz = float(args.get("dz", 0.0))
                reason = args.get("reason", "")

                # Aplicar limitador de paso seguro
                step_mag = (dx**2 + dy**2 + dz**2) ** 0.5
                if step_mag > self.max_step_mm:
                    scale = self.max_step_mm / step_mag
                    dx *= scale
                    dy *= scale
                    dz *= scale
                    logger.warning(f"Paso recortado por seguridad a {self.max_step_mm} mm máx.")

                logger.info(f"Ejecutando move_rel(dx={dx:.1f}, dy={dy:.1f}, dz={dz:.1f}) | Razón: {reason}")
                self.dobot.move_rel(dx=dx, dy=dy, dz=dz, wait=True)
                time.sleep(self.settle_time)

                new_pose = self.dobot.get_pose()
                self.camera.sync_mock_with_dobot(new_pose["x"], new_pose["y"], new_pose["z"])
                
                result_str = (
                    f"Movimiento relativo exitoso (dx={dx:.1f}, dy={dy:.1f}, dz={dz:.1f}). "
                    f"Nueva posición Dobot: X={new_pose['x']:.1f}, Y={new_pose['y']:.1f}, Z={new_pose['z']:.1f} mm."
                )
                self.agent.send_tool_result(tool_id, result_str)
                return result_str

            elif name == "move_absolute":
                x = float(args.get("x"))
                y = float(args.get("y"))
                z = float(args.get("z"))
                reason = args.get("reason", "")

                logger.info(f"Ejecutando move_to(x={x:.1f}, y={y:.1f}, z={z:.1f}) | Razón: {reason}")
                self.dobot.move_to(x=x, y=y, z=z, wait=True)
                time.sleep(self.settle_time)

                new_pose = self.dobot.get_pose()
                self.camera.sync_mock_with_dobot(new_pose["x"], new_pose["y"], new_pose["z"])

                result_str = f"Movimiento absoluto a X={x:.1f}, Y={y:.1f}, Z={z:.1f} exitoso."
                self.agent.send_tool_result(tool_id, result_str)
                return result_str

            elif name == "set_suction":
                enable = bool(args.get("enable"))
                self.dobot.set_suction(enable)
                new_pose = self.dobot.get_pose()
                self.camera.sync_mock_with_dobot(new_pose["x"], new_pose["y"], new_pose["z"], suction=enable)
                result_str = f"Ventosa neumática {'ACTIVADA (succionando)' if enable else 'DESACTIVADA (apagada)'}."
                self.agent.send_tool_result(tool_id, result_str)
                return result_str

            elif name == "set_gripper":
                enable = bool(args.get("enable"))
                self.dobot.set_grip(enable)
                result_str = f"Pinza / Gripper {'CERRADO' if enable else 'ABIERTO'}."
                self.agent.send_tool_result(tool_id, result_str)
                return result_str

            elif name == "calibrate_axes":
                axis = args.get("axis", "X").upper()
                dist = min(25.0, max(5.0, float(args.get("distance_mm", 15.0))))
                dx, dy, dz = 0.0, 0.0, 0.0
                if axis == "X":
                    dx = dist
                elif axis == "Y":
                    dy = dist
                elif axis == "Z":
                    dz = dist

                logger.info(f"Calibrando eje {axis}: desplazamiento de prueba +{dist} mm...")
                self.dobot.move_rel(dx=dx, dy=dy, dz=dz, wait=True)
                time.sleep(self.settle_time)
                new_pose = self.dobot.get_pose()
                self.camera.sync_mock_with_dobot(new_pose["x"], new_pose["y"], new_pose["z"])

                result_str = (
                    f"Micro-movimiento de calibración ejecutado en eje {axis} (+{dist} mm). "
                    f"Observa el nuevo fotograma para medir el cambio (du, dv) en píxeles."
                )
                self.agent.send_tool_result(tool_id, result_str)
                return result_str

            elif name == "draw_trajectory":
                from dobot_controller.drawing import draw_trajectory_sequence
                from dobot_controller.safety import SafetyLimits

                desc = args.get("drawing_description", "")
                raw_strokes = args.get("strokes", [])
                normalized = bool(args.get("normalized", True))

                center_x = 220.0
                center_y = 0.0
                width = 70.0
                height = 70.0
                z_draw = 0.0
                z_hover = 15.0

                converted_strokes = []
                for s in raw_strokes:
                    s_name = s.get("name", "trazo")
                    pts = s.get("points", [])
                    conv_pts = []
                    for pt in pts:
                        px, py = float(pt[0]), float(pt[1])
                        if normalized:
                            # Normalizado [-1, 1]: horizontal -> Y, vertical -> X
                            rx = center_x + py * (width / 2.0)
                            ry = center_y + px * (height / 2.0)
                        else:
                            rx, ry = px, py

                        valid, _ = SafetyLimits.validate_cartesian(rx, ry, z_draw)
                        if not valid:
                            rx = max(150.0, min(320.0, rx))
                            ry = max(-180.0, min(180.0, ry))
                            rad = math.hypot(rx, ry)
                            if rad > SafetyLimits.MAX_RADIUS_MM - 5.0:
                                rx *= (SafetyLimits.MAX_RADIUS_MM - 5.0) / rad
                                ry *= (SafetyLimits.MAX_RADIUS_MM - 5.0) / rad
                            elif rad < SafetyLimits.MIN_RADIUS_MM + 5.0:
                                rx *= (SafetyLimits.MIN_RADIUS_MM + 5.0) / rad
                                ry *= (SafetyLimits.MIN_RADIUS_MM + 5.0) / rad
                        conv_pts.append((rx, ry))
                    if conv_pts:
                        converted_strokes.append({"name": s_name, "points": conv_pts})

                logger.info(f"Ejecutando secuencia continua de dibujo: {desc} ({len(converted_strokes)} trazos)")
                draw_trajectory_sequence(
                    bot=self.dobot,
                    strokes=converted_strokes,
                    z_draw=z_draw,
                    z_hover=z_hover,
                    velocity=40.0,
                    acceleration=40.0
                )
                new_pose = self.dobot.get_pose()
                self.camera.sync_mock_with_dobot(new_pose["x"], new_pose["y"], new_pose["z"])

                result_str = (
                    f"Secuencia continua de dibujo completada con éxito. "
                    f"Trazados {len(converted_strokes)} trazos según la descripción: '{desc}'."
                )
                self.agent.send_tool_result(tool_id, result_str)
                return result_str

            elif name == "finish_task":
                success = bool(args.get("success", True))
                summary = args.get("summary", "")
                result_str = f"Tarea finalizada ({'EXITOSA' if success else 'INCOMPLETA'}): {summary}"
                self.agent.send_tool_result(tool_id, result_str)
                return result_str

            else:
                err = f"Herramienta desconocida: {name}"
                self.agent.send_tool_result(tool_id, err)
                return err

        except SafetyBoundaryError as sbe:
            err_msg = f"ERROR DE SEGURIDAD (Movimiento fuera de límites mecánicos): {sbe}. Corrige la dirección."
            logger.warning(err_msg)
            self.agent.send_tool_result(tool_id, err_msg)
            return err_msg
        except Exception as ex:
            err_msg = f"Error ejecutando {name}: {ex}"
            logger.error(err_msg)
            self.agent.send_tool_result(tool_id, err_msg)
            return err_msg

    def step(self, user_instruction: str, last_action_summary: Optional[str] = None) -> Dict[str, Any]:
        """
        Ejecuta un ciclo completo de:
        1. Captura de video real
        2. Inferencia y razonamiento visual de Claude
        3. Ejecución segura en Dobot
        4. Verificación de resultado
        """
        # 1. Obtener pose actual
        pose = self.dobot.get_pose()

        # 2. Capturar fotograma fresco
        img_b64 = self.camera.get_frame_base64()
        if not img_b64:
            raise RuntimeError("No se pudo capturar fotograma de la cámara.")

        # 3. Invocar al agente Claude
        thought, tool_call = self.agent.step(
            user_text=user_instruction,
            image_base64=img_b64,
            robot_pose=pose,
            last_action_result=last_action_summary
        )

        execution_result = None
        if tool_call:
            execution_result = self.execute_tool(tool_call)

        new_pose = self.dobot.get_pose()
        return {
            "thought": thought,
            "tool_call": tool_call,
            "execution_result": execution_result,
            "pose": new_pose,
            "is_finished": tool_call is not None and tool_call.get("name") == "finish_task"
        }

    def run_interactive_session(
        self,
        initial_goal: str,
        max_iterations: Optional[int] = None,
        confirm_each_move: bool = False
    ):
        """
        Bucle de aprendizaje e interacción continuo guiado por objetivos.
        Si max_iterations es None o <= 0, el bucle se ejecuta de manera autónoma
        sin límite hasta que el propio modelo decida que terminó invocando finish_task.
        """
        import itertools

        has_limit = max_iterations is not None and max_iterations > 0
        limit_desc = f"{max_iterations} pasos" if has_limit else "Sin límite (el modelo finaliza autónomamente)"

        console.print(Panel(
            f"[bold cyan]🎯 Objetivo Inicial:[/bold cyan] {initial_goal}\n"
            f"[bold yellow]Límite de iteraciones:[/bold yellow] {limit_desc}\n"
            f"[bold yellow]Confirmación manual:[/bold yellow] {confirm_each_move}",
            title="[bold green]Dobot Magician + GoPro + Claude VLA[/bold green]"
        ))

        current_instruction = initial_goal
        last_action = None

        iterator = range(1, max_iterations + 1) if has_limit else itertools.count(1)

        for iteration in iterator:
            rule_title = f"Iteración {iteration} / {max_iterations}" if has_limit else f"Iteración {iteration} (Autónoma)"
            console.rule(f"[bold blue]{rule_title}[/bold blue]")

            result = self.step(
                user_instruction=current_instruction,
                last_action_summary=last_action
            )

            # Mostrar razonamiento
            if result["thought"]:
                console.print(Panel(result["thought"], title="🧠 Razonamiento del Modelo (Claude)", border_style="cyan"))

            # Mostrar acción
            tool = result["tool_call"]
            if tool:
                tool_name = tool["name"]
                tool_args = tool["input"]

                table = Table(title=f"Acción a ejecutar: [bold green]{tool_name}[/bold green]")
                table.add_column("Parámetro", style="magenta")
                table.add_column("Valor", style="yellow")
                for k, v in tool_args.items():
                    table.add_row(str(k), str(v))
                console.print(table)

                if confirm_each_move:
                    resp = console.input("[bold yellow]¿Autorizar este movimiento? [Y/n/nuevo comando]: [/bold yellow]").strip()
                    if resp.lower() == "n":
                        console.print("[red]Movimiento cancelado por el usuario.[/red]")
                        current_instruction = "El usuario canceló el movimiento. Propón otra alternativa o pregúntale qué hacer."
                        last_action = "Movimiento cancelado manualmente."
                        continue
                    elif resp.lower() not in ["", "y", "s"]:
                        # El usuario escribió una nueva instrucción
                        current_instruction = resp
                        last_action = f"El usuario corrigió la instrucción: {resp}"
                        continue

                console.print(f"[bold green]✔ Resultado:[/bold green] {result['execution_result']}")
                last_action = result["execution_result"]

                if result["is_finished"]:
                    success = tool_args.get("success", True)
                    summary = tool_args.get("summary", "Meta alcanzada.")
                    status_style = "bold green" if success else "bold yellow"
                    console.print(Panel(
                        f"[{status_style}]Estado:[/ {status_style}] {'Completado con Éxito' if success else 'Finalizado sin éxito'}\n"
                        f"[{status_style}]Resumen del modelo:[/ {status_style}] {summary}\n"
                        f"[dim]Total de iteraciones ejecutadas: {iteration}[/dim]",
                        title="[bold green]🏁 Tarea Finalizada por el Agente[/bold green]",
                        border_style="green" if success else "yellow"
                    ))
                    break
            else:
                console.print("[italic yellow]El modelo no requirió mover el robot en este paso.[/italic yellow]")
                # Solicitar entrada al usuario si no hubo herramienta
                user_input = console.input("\n[bold cyan]Escribe tu siguiente instrucción o presiona Enter para continuar:[/bold cyan] ").strip()
                if user_input:
                    current_instruction = user_input
                else:
                    current_instruction = "Continúa con el objetivo y evalúa el siguiente movimiento."

            # Instrucción de seguimiento para el próximo paso
            current_instruction = (
                "Evalúa el nuevo fotograma. Compara con la posición previa. "
                "¿Te acercaste al objetivo? Decide el siguiente movimiento para seguir aprendiendo o alcanzar la meta. "
                "Si el objetivo ya está plenamente alcanzado, invoca finish_task."
            )
            time.sleep(0.5)

        console.print("[bold green]Sesión de interacción finalizada.[/bold green]")
