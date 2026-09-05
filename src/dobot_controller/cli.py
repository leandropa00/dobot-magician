"""Interfaz de línea de comandos (CLI) para Dobot Magician."""

import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from dobot_controller.connection import list_serial_ports, find_dobot_port, check_dialout_permission
from dobot_controller.controller import DobotController
from dobot_controller.safety import SafetyBoundaryError

app = typer.Typer(help="Herramienta CLI para control y diagnóstico de Dobot Magician en Ubuntu")
console = Console()


@app.command("scan")
def scan_cmd():
    """Escanea los puertos serie del sistema e informa sobre la conectividad del Dobot Magician."""
    console.print(Panel.fit("[bold blue]Escaneo de Puertos Serie - Dobot Magician[/bold blue]"))

    ports = list_serial_ports()
    table = Table(title="Puertos Serie Detectados")
    table.add_column("Dispositivo", style="cyan")
    table.add_column("VID:PID", style="magenta")
    table.add_column("Chipset / Descripción", style="green")
    table.add_column("¿Es Dobot?", justify="center")

    dobot_found = False
    for p in ports:
        is_dobot = "[bold green]SÍ[/bold green]" if p["is_dobot"] else "[dim]No[/dim]"
        if p["is_dobot"]:
            dobot_found = True
        vid_pid = f"{p['vid'] or 'N/A'}:{p['pid'] or 'N/A'}"
        desc = f"{p['chip_info']} ({p['description']})"
        table.add_row(p["device"], vid_pid, desc, is_dobot)

    if ports:
        console.print(table)
    else:
        console.print("[yellow]No se detectaron puertos serie USB conectados actualmente.[/yellow]")

    # Diagnóstico de permisos dialout
    perm = check_dialout_permission()
    console.print()
    if perm["in_dialout"]:
        console.print(f"[green]✔ Permisos OK:[/green] El usuario '{perm['user']}' pertenece al grupo 'dialout'.")
    else:
        console.print(f"[red]✖ Falta permiso:[/red] El usuario '{perm['user']}' no pertenece al grupo 'dialout'.")
        console.print(f"  Ejecuta: [bold cyan]{perm['fix_command']}[/bold cyan] y vuelve a iniciar sesión.")

    if not dobot_found and not ports:
        console.print("\n[yellow]Consejo:[/yellow] Conecta el robot por USB y enciéndelo. Puedes ejecutar pruebas en simulación usando [bold cyan]--mock[/bold cyan].")


@app.command("status")
def status_cmd(
    port: Optional[str] = typer.Option(None, "--port", "-p", help="Puerto serie (ej. /dev/ttyUSB0)"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Ejecutar en modo simulación")
):
    """Muestra la posición cartesiana, ángulos de articulaciones y alarmas actuales."""
    try:
        with DobotController(port=port, mock=mock) as bot:
            pose = bot.get_pose()
            alarms = bot.get_alarms()

            mode_str = "[bold yellow]SIMULACIÓN (Mock)[/bold yellow]" if mock else f"[green]{bot.port}[/green]"
            console.print(Panel(f"Estado del Robot ({mode_str})", title="Dobot Magician"))

            t = Table(show_header=True, header_style="bold magenta")
            t.add_column("Eje Cartesiano", justify="center")
            t.add_column("Valor (mm / deg)", justify="center")
            t.add_column("Articulación", justify="center")
            t.add_column("Ángulo (°)", justify="center")

            t.add_row("X", f"{pose['x']} mm", "J1 (Base)", f"{pose['j1']}°")
            t.add_row("Y", f"{pose['y']} mm", "J2 (Hombro)", f"{pose['j2']}°")
            t.add_row("Z", f"{pose['z']} mm", "J3 (Codo)", f"{pose['j3']}°")
            t.add_row("R", f"{pose['r']}°", "J4 (Muñeca)", f"{pose['j4']}°")

            console.print(t)

            if alarms:
                console.print(f"[bold red]Alarmas activas:[/bold red] {alarms}")
            else:
                console.print("[green]✔ Sin alarmas activas.[/green]")
    except Exception as e:
        console.print(f"[red]Error al consultar estado:[/red] {e}")


@app.command("move")
def move_cmd(
    x: Optional[float] = typer.Option(None, "--x", help="Coordenada X en mm"),
    y: Optional[float] = typer.Option(None, "--y", help="Coordenada Y en mm"),
    z: Optional[float] = typer.Option(None, "--z", help="Coordenada Z en mm"),
    r: Optional[float] = typer.Option(0.0, "--r", help="Rotación R en grados"),
    port: Optional[str] = typer.Option(None, "--port", "-p", help="Puerto serie"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Modo simulación")
):
    """Mueve el brazo a una coordenada cartesiana específica."""
    try:
        with DobotController(port=port, mock=mock) as bot:
            console.print(f"Moviendo a X={x}, Y={y}, Z={z}, R={r}...")
            bot.move_to(x=x, y=y, z=z, r=r)
            console.print("[green]✔ Movimiento completado con éxito.[/green]")
            pose = bot.get_pose()
            console.print(f"Nueva pose: X={pose['x']} Y={pose['y']} Z={pose['z']} R={pose['r']}")
    except SafetyBoundaryError as sbe:
        console.print(f"[bold red]Error de Seguridad:[/bold red] {sbe}")
    except Exception as e:
        console.print(f"[red]Error en el movimiento:[/red] {e}")


@app.command("home")
def home_cmd(
    port: Optional[str] = typer.Option(None, "--port", "-p", help="Puerto serie"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Modo simulación")
):
    """Ejecuta la calibración a la posición de inicio (Home)."""
    try:
        with DobotController(port=port, mock=mock) as bot:
            console.print("[bold yellow]Iniciando procedimiento HOME...[/bold yellow]")
            bot.home()
            console.print("[green]✔ Homing completado.[/green]")
    except Exception as e:
        console.print(f"[red]Error en homing:[/red] {e}")


@app.command("suction")
def suction_cmd(
    state: str = typer.Argument(..., help="'on' para activar succión, 'off' para desactivar"),
    port: Optional[str] = typer.Option(None, "--port", "-p", help="Puerto serie"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Modo simulación")
):
    """Controla la ventosa de succión neumática."""
    enable = state.lower() in ("on", "1", "true", "si", "sí", "activar")
    try:
        with DobotController(port=port, mock=mock) as bot:
            bot.set_suction(enable)
            estado = "ACTIVADA" if enable else "DESACTIVADA"
            console.print(f"[green]✔ Ventosa de succión {estado}.[/green]")
    except Exception as e:
        console.print(f"[red]Error controlando succión:[/red] {e}")


@app.command("demo")
def demo_cmd(
    mock: bool = typer.Option(False, "--mock", "-m", help="Ejecutar en modo simulación"),
    port: Optional[str] = typer.Option(None, "--port", "-p", help="Puerto serie")
):
    """Ejecuta una demostración de Pick & Place."""
    console.print(Panel("[bold cyan]Iniciando Demostración de Pick & Place[/bold cyan]"))
    try:
        with DobotController(port=port, mock=mock) as bot:
            pick = (220.0, -80.0, -10.0)
            place = (220.0, 80.0, -10.0)

            console.print(f"1. Punto de recogida: {pick}")
            console.print(f"2. Punto de entrega:  {place}")
            console.print("Ejecutando secuencia...")

            bot.pick_and_place(pick_pos=pick, place_pos=place, safe_z=50.0)

            console.print("[bold green]✔ Demostración finalizada exitosamente.[/bold green]")
    except Exception as e:
        console.print(f"[red]Error durante la demostración:[/red] {e}")


@app.command("draw-face")
def draw_face_cmd(
    z_draw: float = typer.Option(0.0, "--z-draw", "-z", help="Altura Z (mm) de contacto del marcador sobre el papel"),
    z_hover: float = typer.Option(15.0, "--z-hover", help="Altura Z (mm) de levante del marcador en el aire"),
    radius: float = typer.Option(30.0, "--radius", "-r", help="Radio de la carita en mm"),
    cx: float = typer.Option(220.0, "--cx", help="Coordenada X del centro de la carita en mm"),
    cy: float = typer.Option(0.0, "--cy", help="Coordenada Y del centro de la carita en mm"),
    air_draw: bool = typer.Option(False, "--air-draw", help="Dibujar en el aire para verificar sin tocar el papel"),
    velocity: float = typer.Option(35.0, "--speed", "-v", help="Velocidad lineal de dibujo en mm/s"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Ejecutar en modo simulación"),
    port: Optional[str] = typer.Option(None, "--port", "-p", help="Puerto serie")
):
    """Dibuja una carita feliz usando el marcador montado en el robot."""
    actual_z_draw = 35.0 if air_draw else z_draw
    actual_z_hover = 45.0 if air_draw else z_hover

    mode_title = "AIR DRAW (Prueba en el aire)" if air_draw else ("SIMULACIÓN" if mock else "HARDWARE REAL")
    console.print(Panel(f"[bold magenta]Dibujando Carita Feliz ({mode_title})[/bold magenta]"))
    console.print(f"• Centro: ({cx}, {cy}) mm | Radio: {radius} mm")
    console.print(f"• Altura de trazo (Z_draw): {actual_z_draw} mm | Altura de tránsito (Z_hover): {actual_z_hover} mm")
    console.print(f"• Velocidad: {velocity} mm/s\n")

    try:
        from dobot_controller.drawing import draw_smiley_face

        with DobotController(port=port, mock=mock) as bot:
            def on_status(msg: str):
                console.print(f"[cyan]➜[/cyan] {msg}")

            draw_smiley_face(
                bot=bot,
                center_x=cx,
                center_y=cy,
                radius=radius,
                z_draw=actual_z_draw,
                z_hover=actual_z_hover,
                velocity=velocity,
                acceleration=velocity,
                status_callback=on_status
            )
            console.print("\n[bold green]✔ ¡Carita feliz dibujada exitosamente![/bold green]")
    except SafetyBoundaryError as sbe:
        console.print(f"[bold red]Límite de seguridad alcanzado:[/bold red] {sbe}")
    except Exception as e:
        console.print(f"[bold red]Error durante el dibujo:[/bold red] {e}")


@app.command("calibrate-pen")
def calibrate_pen_cmd(
    start_z: float = typer.Option(40.0, "--start-z", help="Altura Z inicial segura"),
    cx: float = typer.Option(220.0, "--cx", help="Coordenada X del centro"),
    cy: float = typer.Option(0.0, "--cy", help="Coordenada Y del centro"),
    port: Optional[str] = typer.Option(None, "--port", "-p", help="Puerto serie"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Modo simulación")
):
    """Herramienta interactiva para calibrar la altura Z exacta de contacto del marcador sobre el papel."""
    console.print(Panel("[bold yellow]Calibración Interactiva de Altura Z para Marcador[/bold yellow]"))
    console.print("El robot se posicionará en el centro y te permitirá bajar el marcador paso a paso")
    console.print("hasta que la punta toque ligeramente el papel.\n")

    try:
        with DobotController(port=port, mock=mock) as bot:
            curr_z = start_z
            bot.move_to(x=cx, y=cy, z=curr_z, wait=True)
            console.print(f"Robot posicionado en X={cx}, Y={cy}, Z={curr_z} mm.")
            console.print("[dim]Usa comandos: -5 (baja 5mm), -1 (baja 1mm), -0.2 (baja 0.2mm), +1 (sube 1mm), ok (finalizar y guardar)[/dim]")

            while True:
                console.print(f"\n[bold]Altura Z actual: [cyan]{curr_z:.2f} mm[/cyan][/bold]")
                cmd = input("Acción [-5 / -1 / -0.2 / +1 / +5 / ok / salir]: ").strip().lower()

                if cmd in ("ok", "guardar", "listo", "done"):
                    console.print(f"\n[bold green]✔ Calibración finalizada. Tu altura de contacto es Z = {curr_z:.2f} mm[/bold green]")
                    console.print(f"Para dibujar, ejecuta:")
                    console.print(f"  [bold cyan]dobot draw-face --z-draw {curr_z:.2f} --z-hover {curr_z + 15.0:.2f}[/bold cyan]")
                    # Subir marcador antes de salir
                    bot.move_to(x=cx, y=cy, z=curr_z + 20.0, wait=True)
                    break
                elif cmd in ("salir", "exit", "q", "cancel"):
                    console.print("[yellow]Calibración cancelada.[/yellow]")
                    bot.move_to(x=cx, y=cy, z=curr_z + 20.0, wait=True)
                    break
                else:
                    try:
                        delta = float(cmd)
                        new_z = round(curr_z + delta, 2)
                        bot.move_to(x=cx, y=cy, z=new_z, wait=True)
                        curr_z = new_z
                    except ValueError:
                        console.print("[red]Opción no válida. Escribe un número (ej. -1 o +0.5) o 'ok' para guardar.[/red]")
                    except SafetyBoundaryError as sbe:
                        console.print(f"[red]Límite de seguridad alcanzado:[/red] {sbe}")
    except Exception as e:
        console.print(f"[red]Error durante la calibración:[/red] {e}")


def main():
    app()


if __name__ == "__main__":
    main()
