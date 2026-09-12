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


@app.command("gopro-scan")
def gopro_scan_cmd():
    """Escanea cámaras de video locales (V4L2) e interfaces de red GoPro por USB."""
    from dobot_controller.vision.gopro_setup import (
        list_v4l2_devices,
        find_gopro_usb_device,
        find_gopro_network_interface,
        check_gopro_status
    )

    console.print(Panel.fit("[bold blue]Diagnóstico y Detección de GoPro / Cámaras USB[/bold blue]"))

    # 1. Detección física en bus USB (lsusb)
    usb_dev = find_gopro_usb_device()
    if usb_dev:
        console.print(Panel(
            f"[bold green]✔ Hardware GoPro detectado en el bus USB:[/bold green]\n"
            f"  {usb_dev['description']}",
            title="Detección USB Física"
        ))
    else:
        console.print(Panel(
            "[yellow]✖ No se detectó hardware GoPro en el bus USB (lsusb).[/yellow]\n"
            "[dim]Verifica que:\n"
            "  1. La GoPro esté ENCENDIDA (Power On).\n"
            "  2. El cable USB-C sea de DATOS (muchos cables solo conducen carga eléctrica).\n"
            "  3. Esté conectada directamente a un puerto USB 3.0 / USB-C de tu PC.[/dim]",
            title="Detección USB Física"
        ))

    # 2. Dispositivos V4L2
    console.print()
    devices = list_v4l2_devices()
    t_v4l2 = Table(title="Dispositivos de Video V4L2 (/dev/video*)")
    t_v4l2.add_column("Ruta", style="cyan")
    t_v4l2.add_column("Nombre del Dispositivo", style="green")
    t_v4l2.add_column("Permisos de Lectura", justify="center")

    if devices:
        for d in devices:
            perm_str = "[green]OK[/green]" if d["accessible"] else "[red]Denegado[/red]"
            t_v4l2.add_row(d["path"], d["name"], perm_str)
        console.print(t_v4l2)
    else:
        console.print("[yellow]No se detectaron nodos /dev/video* en el sistema.[/yellow]")

    # 3. Interfaz de red USB GoPro (CDC-NCM)
    console.print()
    gopro_net = find_gopro_network_interface()
    if gopro_net:
        if gopro_net.get("needs_dhcp"):
            console.print(Panel(
                f"[bold yellow]⚠ Interfaz USB detectada pero requiere asignación IP (DHCP):[/bold yellow]\n"
                f"  - Interfaz: [cyan]{gopro_net['interface']}[/cyan]\n"
                f"  - Ejecuta en tu terminal: [bold green]sudo dhclient {gopro_net['interface']}[/bold green]",
                title="GoPro Hero 11/12 (CDC-NCM)"
            ))
        else:
            console.print(Panel(
                f"[bold green]✔ GoPro lista en interfaz de red USB:[/bold green]\n"
                f"  - Interfaz: [cyan]{gopro_net['interface']}[/cyan]\n"
                f"  - IP Host:  [yellow]{gopro_net['host_ip']}[/yellow]\n"
                f"  - IP GoPro: [bold magenta]{gopro_net['gopro_ip']}[/bold magenta]\n"
                f"  - Endpoint: [dim]http://{gopro_net['gopro_ip']}:8080/gopro/webcam/status[/dim]",
                title="GoPro Connect (Webcam USB)"
            ))
            status = check_gopro_status(gopro_net["gopro_ip"])
            if status:
                console.print(f"[green]Estado GoPro HTTP API:[/green] {status}")
    else:
        console.print(Panel(
            "[dim][bold]Nota sobre GoPro Hero 11 y Hero 12 Black:[/bold]\n"
            "GoPro eliminó el menú manual 'Conexiones > Conexión USB' en la Hero 12.\n"
            "La cámara entra en modo red/webcam AUTOMÁTICAMENTE al conectarse con cable de datos encendida.\n"
            "Una vez conectada y encendida, Linux creará una interfaz 'usb0' o 'enx...' automáticamente.[/dim]",
            title="Información Hero 12 Black"
        ))


@app.command("snapshot")
def snapshot_cmd(
    output: str = typer.Option("snapshot.jpg", "--output", "-o", help="Ruta del archivo a guardar"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Índice de cámara (0, 1) o URL de stream"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Modo simulación")
):
    """Captura un fotograma de la cámara GoPro/USB y lo guarda en disco."""
    from dobot_controller.vision.camera import GoProCapture

    cam_src = None
    if source is not None:
        cam_src = int(source) if source.isdigit() else source

    console.print(f"[cyan]Iniciando captura desde {source or 'autodetección'}...[/cyan]")
    try:
        with GoProCapture(source=cam_src, mock=mock) as cam:
            success = cam.save_snapshot(output)
            if success:
                console.print(f"[bold green]✔ Instantánea guardada exitosamente en:[/bold green] [cyan]{output}[/cyan]")
            else:
                console.print(f"[bold red]✖ No se pudo capturar fotograma.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]Error durante la captura:[/bold red] {e}")


@app.command("ai-agent")
def ai_agent_cmd(
    goal: str = typer.Option("Aprende la relación de ejes de la cámara y acércate al objetivo rojo", "--goal", "-g", help="Objetivo en lenguaje natural para el modelo"),
    steps: Optional[int] = typer.Option(None, "--steps", "-s", help="Límite máximo de iteraciones (por defecto sin límite: el modelo evalúa cuándo terminó y finaliza con finish_task)"),
    confirm: bool = typer.Option(False, "--confirm", "-c", help="Confirmar interactivamente antes de cada movimiento"),
    resume: bool = typer.Option(False, "--resume", "-r", help="Reanudar la sesión previa (conserva aprendizajes de ejes y memoria acumulada)"),
    session_file: str = typer.Option(".dobot_ai_session.json", "--session-file", help="Ruta del archivo de guardado de sesión"),
    no_save: bool = typer.Option(False, "--no-save", help="Deshabilitar guardado automático de la sesión al finalizar"),
    port: Optional[str] = typer.Option(None, "--port", "-p", help="Puerto serie del Dobot"),
    source: Optional[str] = typer.Option(None, "--source", help="Fuente de video (índice 0, 1 o URL)"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Ejecutar en modo simulación (Mock Dobot + Mock Camera)"),
    model: str = typer.Option("claude-sonnet-4-5-20250929", "--model", help="Modelo de Claude a utilizar")
):
    """Inicia el agente inteligente de visión y control visual-motor guiado por Claude."""
    import os
    from dotenv import load_dotenv
    load_dotenv()

    from dobot_controller.vision.camera import GoProCapture
    from dobot_controller.vision.agent import VisionAgent
    from dobot_controller.vision.visual_servo import VisualServoLoop

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[bold red]Error:[/bold red] ANTHROPIC_API_KEY no encontrada. Define la variable en tu entorno o en el archivo .env")
        raise typer.Exit(code=1)

    cam_src = None
    if source is not None:
        cam_src = int(source) if source.isdigit() else source

    console.print(Panel(
        f"[bold cyan]🎯 Objetivo:[/bold cyan] {goal}\n"
        f"[bold yellow]Modo:[/bold yellow] {'SIMULACIÓN (Mock Robot + Mock Camera)' if mock else 'HARDWARE FÍSICO'}\n"
        f"[bold green]Modelo LLM:[/bold green] {model}\n"
        f"[bold magenta]Persistencia:[/bold magenta] {'Reanudando sesión previa' if resume else 'Nueva sesión'} ([dim]{session_file}[/dim])",
        title="Dobot Magician + GoPro + Claude VLA"
    ))

    with DobotController(port=port, mock=mock) as bot:
        with GoProCapture(source=cam_src, mock=mock) as cam:
            agent = VisionAgent(api_key=api_key, model=model)

            if resume:
                if os.path.exists(session_file):
                    if agent.load_session(session_file):
                        console.print(f"[bold green]✔ Sesión previa cargada desde {session_file}[/bold green] (Paso {agent.step_counter}, {len(agent.messages)} mensajes en memoria)")
                    else:
                        console.print(f"[yellow]No se pudo cargar {session_file}, iniciando sesión nueva.[/yellow]")
                else:
                    console.print(f"[yellow]No existe archivo previo {session_file}. Iniciando sesión desde cero.[/yellow]")

            loop = VisualServoLoop(dobot=bot, camera=cam, agent=agent)
            try:
                loop.run_interactive_session(
                    initial_goal=goal,
                    max_iterations=steps,
                    confirm_each_move=confirm
                )
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrumpido por el usuario.[/yellow]")
            finally:
                if not no_save:
                    saved = agent.save_session(session_file)
                    if saved:
                        console.print(f"[dim]💾 Estado y aprendizajes guardados en: {session_file} (Usa --resume para continuar la próxima vez)[/dim]")


@app.command("ai-draw")
def ai_draw_cmd(
    instruction: str = typer.Option("Identifica el objeto frente a la cámara y dibújalo en el cuaderno", "--instruction", "-i", help="Instrucción predeterminada para Claude (opcional, no es necesario especificar -i)"),
    image: Optional[str] = typer.Option(None, "--image", "-f", help="Ruta a una foto local de cualquier objeto (opcional; si no se especifica, se captura con la cámara)"),
    center_x: float = typer.Option(235.50, "--center-x", help="Coordenada X del centro inicial en mm (calibración física: 235.50 mm)"),
    center_y: float = typer.Option(-10.45, "--center-y", help="Coordenada Y del centro inicial en mm (calibración física: -10.45 mm)"),
    notebook_width: float = typer.Option(250.0, "--notebook-width", help="Ancho del cuaderno en mm (25 cm = 250 mm)"),
    notebook_height: float = typer.Option(170.0, "--notebook-height", help="Alto del cuaderno en mm (17 cm = 170 mm)"),
    margin: float = typer.Option(15.0, "--margin", help="Margen de seguridad respecto al borde de la hoja en mm"),
    width: Optional[float] = typer.Option(None, "--width", "-w", help="Ancho del área de dibujo en mm (por defecto: notebook_width - 2*margin)"),
    height: Optional[float] = typer.Option(None, "--height", help="Alto del área de dibujo en mm (por defecto: notebook_height - 2*margin)"),
    z_draw: float = typer.Option(-38.59, "--z-draw", help="Altura Z de contacto con el papel en mm (calibración física: -38.59 mm)"),
    z_hover: float = typer.Option(-23.59, "--z-hover", help="Altura Z de tránsito en el aire en mm (calibración física: -23.59 mm)"),
    r: float = typer.Option(5.67, "--rotation", "-r", help="Orientación angular R del efector final en grados (calibración física: 5.67°)"),
    velocity: float = typer.Option(40.0, "--velocity", "-v", help="Velocidad lineal de dibujo en mm/s"),
    acceleration: float = typer.Option(40.0, "--acceleration", "-a", help="Aceleración de dibujo en mm/s²"),
    confirm: bool = typer.Option(True, "--confirm/--no-confirm", "-c/-y", help="Solicitar aprobación obligatoria del boceto antes de trazarlo (activado por defecto)"),
    interactive_capture: bool = typer.Option(True, "--interactive-capture/--auto-capture", help="Esperar confirmación para enfocar el objeto frente a la cámara antes de capturar"),
    port: Optional[str] = typer.Option(None, "--port", "-p", help="Puerto serie del Dobot"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Fuente de video (índice 0, 1 o URL)"),
    mock: bool = typer.Option(False, "--mock", "-m", help="Ejecutar en modo simulación"),
    model: str = typer.Option("claude-sonnet-4-5-20250929", "--model", help="Modelo de Claude a utilizar"),
    preview: str = typer.Option("drawing_preview.png", "--preview", help="Ruta para guardar imagen de previsualización"),
    snapshot: str = typer.Option("captured_subject.jpg", "--snapshot", help="Ruta para guardar la foto capturada del objeto")
):
    """
    Captura la foto de CUALQUIER OBJETO (con la GoPro, webcam USB o archivo de imagen),
    Claude analiza el objeto y sintetiza un boceto vectorial continuo, solicita aprobación
    interactiva al usuario y envía la secuencia completa al Dobot Magician para dibujarlo en el cuaderno (25x17 cm).
    El efector final siempre inicia en contacto con el papel en la posición inicial (X=235.50, Y=-10.45, Z=-38.59, R=5.67°).
    Al aprobar por primera vez, sube el brazo y comienza a dibujar.
    """
    import os
    from dotenv import load_dotenv
    load_dotenv()

    from dobot_controller.vision.camera import GoProCapture
    from dobot_controller.vision.visual_drawer import VisualTrajectoryDrawer

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[bold red]Error:[/bold red] ANTHROPIC_API_KEY no encontrada. Define la variable en tu entorno o en el archivo .env")
        raise typer.Exit(code=1)

    cam_src = None
    if source is not None:
        cam_src = int(source) if source.isdigit() else source

    with DobotController(port=port, mock=mock) as bot:
        with GoProCapture(source=cam_src, mock=mock) as cam:
            drawer = VisualTrajectoryDrawer(
                dobot=bot,
                camera=cam,
                api_key=api_key,
                model=model,
                center_x=center_x,
                center_y=center_y,
                r=r,
                notebook_width=notebook_width,
                notebook_height=notebook_height,
                margin=margin,
                canvas_width=width,
                canvas_height=height,
                z_draw=z_draw,
                z_hover=z_hover,
                velocity=velocity,
                acceleration=acceleration
            )
            drawer.run_pipeline(
                instruction=instruction,
                image_path=image,
                captured_image_path=snapshot,
                preview_image_path=preview,
                confirm_before_draw=confirm,
                prompt_before_capture=interactive_capture
            )


def main():
    app()


if __name__ == "__main__":
    main()
