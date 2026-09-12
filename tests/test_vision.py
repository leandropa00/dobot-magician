"""
Pruebas unitarias para el módulo de visión, cámara GoPro y bucle de control visual.
"""

import os
import tempfile
import base64
import pytest
from typer.testing import CliRunner

from dobot_controller.controller import DobotController
from dobot_controller.vision.camera import MockCamera, GoProCapture
from dobot_controller.vision.gopro_setup import list_v4l2_devices, find_gopro_network_interface
from dobot_controller.vision.visual_servo import VisualServoLoop
from dobot_controller.cli import app

runner = CliRunner()


def test_mock_camera_read():
    cam = MockCamera(width=640, height=480)
    ret, frame = cam.read()
    assert ret is True
    assert frame is not None
    assert frame.shape == (480, 640, 3)

    # Actualizar efector con coordenadas Dobot
    cam.update_effector_from_robot(220.0, 0.0, 50.0, suction=True)
    assert cam.suction_active is True
    ret2, frame2 = cam.read()
    assert ret2 is True
    assert frame2 is not None


def test_gopro_capture_mock_and_base64():
    with GoProCapture(mock=True, width=320, height=240) as cam:
        ret, frame = cam.get_frame()
        assert ret is True
        assert frame is not None
        assert frame.shape == (240, 320, 3)

        b64 = cam.get_frame_base64(max_dimension=300)
        assert b64 is not None
        assert isinstance(b64, str)
        assert len(b64) > 100

        # Verificar que es decodificable
        raw = base64.b64decode(b64)
        assert len(raw) > 0

        # Probar guardado de instantánea
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            saved = cam.save_snapshot(tmp_path)
            assert saved is True
            assert os.path.exists(tmp_path)
            assert os.path.getsize(tmp_path) > 0
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


def test_gopro_setup_devices():
    devices = list_v4l2_devices()
    assert isinstance(devices, list)
    for d in devices:
        assert "path" in d
        assert "name" in d
        assert "accessible" in d

    net = find_gopro_network_interface()
    # net puede ser None o dict si no hay GoPro USB conectada
    if net is not None:
        assert "interface" in net
        assert "gopro_ip" in net


class DummyAgent:
    """Mock agent para probar el despacho de herramientas en VisualServoLoop sin llamar a la API."""
    def __init__(self):
        self.last_tool_result = None

    def send_tool_result(self, tool_id: str, output: str):
        self.last_tool_result = output


def test_visual_servo_tool_execution():
    with DobotController(mock=True) as bot:
        with GoProCapture(mock=True) as cam:
            dummy_agent = DummyAgent()
            loop = VisualServoLoop(dobot=bot, camera=cam, agent=dummy_agent)

            # 1. Probar move_relative
            res = loop.execute_tool({
                "id": "t1",
                "name": "move_relative",
                "input": {"dx": 10.0, "dy": -5.0, "dz": 0.0, "reason": "Ajuste de prueba"}
            })
            assert "exitoso" in res.lower()
            pose = bot.get_pose()
            assert pose["x"] == 230.0
            assert pose["y"] == -5.0

            # 2. Probar límite de seguridad (movimiento fuera de rango seguro)
            res_err = loop.execute_tool({
                "id": "t2",
                "name": "move_absolute",
                "input": {"x": 500.0, "y": 0.0, "z": 0.0, "reason": "Fuera de alcance"}
            })
            assert "ERROR DE SEGURIDAD" in res_err

            # 3. Probar ventosa
            res_suck = loop.execute_tool({
                "id": "t3",
                "name": "set_suction",
                "input": {"enable": True, "reason": "Tomar objeto"}
            })
            assert "ACTIVADA" in res_suck

            # 4. Probar finish_task
            res_fin = loop.execute_tool({
                "id": "t4",
                "name": "finish_task",
                "input": {"success": True, "summary": "Meta alcanzada"}
            })
            assert "EXITOSA" in res_fin


def test_visual_servo_unlimited_session_finishes():
    class AutoFinishAgent:
        def __init__(self):
            self.calls = 0

        def step(self, user_text, **kwargs):
            self.calls += 1
            if self.calls < 3:
                return "Acercándome", {
                    "id": f"t_{self.calls}",
                    "name": "move_relative",
                    "input": {"dx": 5.0, "dy": 0.0, "dz": 0.0, "reason": "Avanzar"}
                }
            else:
                return "He llegado al objetivo", {
                    "id": "t_finish",
                    "name": "finish_task",
                    "input": {"success": True, "summary": "Objetivo alcanzado con éxito"}
                }

        def send_tool_result(self, tool_id, output):
            pass

    with DobotController(mock=True) as bot:
        with GoProCapture(mock=True) as cam:
            agent = AutoFinishAgent()
            loop = VisualServoLoop(dobot=bot, camera=cam, agent=agent)
            # max_iterations=None significa autónomo sin límite
            loop.run_interactive_session(initial_goal="Prueba autónoma", max_iterations=None)
            assert agent.calls == 3


def test_cli_gopro_scan():
    result = runner.invoke(app, ["gopro-scan"])
    assert result.exit_code == 0
    assert "Diagnóstico y Detección de GoPro" in result.output


def test_cli_snapshot_mock():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = runner.invoke(app, ["snapshot", "--mock", "-o", tmp_path])
        assert result.exit_code == 0
        assert "Instantánea guardada exitosamente" in result.output
        assert os.path.exists(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_agent_save_and_load_session():
    from dobot_controller.vision.agent import VisionAgent

    agent = VisionAgent(api_key="test-dummy-key")
    agent.step_counter = 3
    agent.messages = [
        {"role": "user", "content": [{"type": "text", "text": "Aprende ejes"}, {"type": "image", "source": "dummy"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Eje X confirmado"}]}
    ]

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        session_file = tmp.name

    try:
        # 1. Guardar sesión
        success = agent.save_session(session_file)
        assert success is True
        assert os.path.exists(session_file)

        # 2. Cargar en un agente nuevo
        agent2 = VisionAgent(api_key="test-dummy-key")
        loaded = agent2.load_session(session_file)
        assert loaded is True
        assert agent2.step_counter == 3
        assert len(agent2.messages) == 2
        # La imagen se convierte en placeholder para mantener el archivo ligero
        assert agent2.messages[0]["content"][1]["text"] == "[Fotograma visual capturado en este paso]"
        assert agent2.messages[1]["content"][0]["text"] == "Eje X confirmado"
    finally:
        if os.path.exists(session_file):
            os.remove(session_file)


def test_draw_trajectory_sequence():
    from dobot_controller.controller import DobotController
    from dobot_controller.drawing import draw_trajectory_sequence

    with DobotController(mock=True) as bot:
        strokes = [
            {
                "name": "linea_1",
                "points": [(200.0, -20.0), (240.0, -20.0)]
            },
            {
                "name": "linea_2",
                "points": [(240.0, 20.0), (200.0, 20.0)]
            }
        ]

        status_messages = []
        draw_trajectory_sequence(
            bot=bot,
            strokes=strokes,
            z_draw=0.0,
            z_hover=15.0,
            status_callback=lambda msg: status_messages.append(msg)
        )

        assert len(status_messages) >= 2
        assert "Secuencia continua de dibujo completada con éxito." in status_messages[-1]


def test_visual_trajectory_drawer_coordinate_conversion_and_preview():
    from dobot_controller.controller import DobotController
    from dobot_controller.vision.camera import GoProCapture
    from dobot_controller.vision.visual_drawer import VisualTrajectoryDrawer

    with DobotController(mock=True) as bot:
        with GoProCapture(mock=True) as cam:
            drawer = VisualTrajectoryDrawer(
                dobot=bot,
                camera=cam,
                api_key="test-dummy-key",
                center_x=220.0,
                center_y=0.0,
                canvas_width=80.0,
                canvas_height=80.0
            )

            raw_strokes = [
                {
                    "name": "cuadrado",
                    "points": [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0), (-1.0, -1.0)]
                }
            ]

            # Conversión
            robot_strokes = drawer.convert_to_robot_coordinates(raw_strokes)
            assert len(robot_strokes) == 1
            pts = robot_strokes[0]["points"]
            assert len(pts) == 5

            # u = -1.0 -> ry = center_y - 40 = -40; v = -1.0 -> rx = center_x - 40 = 180
            assert pts[0] == (180.0, -40.0)
            # u = 1.0 -> ry = +40; v = -1.0 -> rx = 180
            assert pts[1] == (180.0, 40.0)
            # u = 1.0 -> ry = +40; v = 1.0 -> rx = 260
            assert pts[2] == (260.0, 40.0)

            # Previsualización
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                preview_path = tmp.name

            try:
                drawer.generate_preview(robot_strokes, output_path=preview_path)
                assert os.path.exists(preview_path)
                assert os.path.getsize(preview_path) > 1000
            finally:
                if os.path.exists(preview_path):
                    os.remove(preview_path)


def test_visual_servo_executes_draw_trajectory():
    from dobot_controller.controller import DobotController
    from dobot_controller.vision.camera import GoProCapture
    from dobot_controller.vision.agent import VisionAgent
    from dobot_controller.vision.visual_servo import VisualServoLoop

    with DobotController(mock=True) as bot:
        with GoProCapture(mock=True) as cam:
            agent = VisionAgent(api_key="test-dummy-key")
            loop = VisualServoLoop(dobot=bot, camera=cam, agent=agent)

            args = {
                "drawing_description": "Cuadrado continuo",
                "normalized": True,
                "strokes": [
                    {
                        "name": "cuadrado",
                        "points": [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5], [-0.5, -0.5]]
                    }
                ]
            }

            result = loop.execute_tool({"id": "tool_draw_1", "name": "draw_trajectory", "input": args})
            assert "Secuencia continua de dibujo completada con éxito" in result
            assert "Cuadrado continuo" in result


def test_visual_trajectory_drawer_notebook_centering_and_approval():
    from unittest.mock import patch
    from dobot_controller.controller import DobotController
    from dobot_controller.vision.camera import GoProCapture
    from dobot_controller.vision.visual_drawer import VisualTrajectoryDrawer

    with DobotController(mock=True) as bot:
        with GoProCapture(mock=True) as cam:
            drawer = VisualTrajectoryDrawer(
                dobot=bot,
                camera=cam,
                api_key="test-dummy-key"
            )

            # Verificar valores por defecto del cuaderno y posición inicial física
            assert drawer.notebook_width == 250.0
            assert drawer.notebook_height == 170.0
            assert drawer.center_x == 235.50
            assert drawer.center_y == -10.45
            assert drawer.z_draw == -38.59
            assert drawer.z_hover == -23.59
            assert drawer.r == 5.67

            # Probar move_to_center en contacto con el papel (hover=False por defecto)
            cx, cy, cz = drawer.move_to_center(hover=False)
            assert (cx, cy, cz) == (235.50, -10.45, -38.59)
            pose = bot.get_pose()
            assert round(pose["x"], 2) == 235.50
            assert round(pose["y"], 2) == -10.45
            assert round(pose["z"], 2) == -38.59
            assert round(pose["r"], 2) == 5.67

            # Mock create_coordinate_map para no invocar Anthropic API
            mock_traj = {
                "identified_subject": "Boceto de prueba en cuaderno 25x17",
                "strokes": [
                    {
                        "name": "linea_centro",
                        "points": [(-0.2, 0.0), (0.2, 0.0)]
                    }
                ]
            }

            with patch.object(drawer, "create_coordinate_map", return_value=mock_traj):
                # 1. Probar rechazo de aprobación (permanece en reposo en el centro)
                with patch("rich.console.Console.input", return_value="r"):
                    res_reject = drawer.run_pipeline(confirm_before_draw=True)
                    assert not res_reject["success"]
                    assert "no aprobado" in res_reject["reason"].lower()

                # 2. Probar aprobación (Enter / "a")
                with patch("rich.console.Console.input", return_value="a"):
                    res_approve = drawer.run_pipeline(confirm_before_draw=True)
                    assert res_approve["success"]
                    assert res_approve["subject"] == "Boceto de prueba en cuaderno 25x17"
                    # Verificar que al finalizar retornó al centro en contacto con el papel
                    final_pose = bot.get_pose()
                    assert round(final_pose["x"], 2) == 235.50
                    assert round(final_pose["y"], 2) == -10.45
                    assert round(final_pose["z"], 2) == -38.59
                    assert round(final_pose["r"], 2) == 5.67


def test_visual_trajectory_drawer_arbitrary_object_and_image_file():
    from unittest.mock import patch
    import cv2
    import numpy as np
    from dobot_controller.controller import DobotController
    from dobot_controller.vision.camera import GoProCapture
    from dobot_controller.vision.visual_drawer import VisualTrajectoryDrawer

    with DobotController(mock=True) as bot:
        with GoProCapture(mock=True) as cam:
            drawer = VisualTrajectoryDrawer(
                dobot=bot,
                camera=cam,
                api_key="test-dummy-key"
            )

            # Crear una imagen temporal de un objeto (ej. manzana / taza)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                img_path = tmp.name

            try:
                # Generar imagen sintética de un objeto (taza)
                dummy_obj = np.zeros((200, 200, 3), dtype=np.uint8)
                cv2.circle(dummy_obj, (100, 100), 50, (0, 200, 200), -1)
                cv2.imwrite(img_path, dummy_obj)

                # Verificar capture_subject cargando desde el archivo de imagen
                frame, b64 = drawer.capture_subject(image_path=img_path)
                assert frame is not None
                assert len(b64) > 100

                # Ejecutar pipeline con el objeto
                mock_traj = {
                    "identified_subject": "Taza de café sobre mesa",
                    "strokes": [
                        {
                            "name": "contorno_taza",
                            "points": [(-0.3, -0.3), (0.3, -0.3), (0.3, 0.3), (-0.3, 0.3), (-0.3, -0.3)]
                        }
                    ]
                }
                with patch.object(drawer, "create_coordinate_map", return_value=mock_traj):
                    with patch("rich.console.Console.input", return_value="a"):
                        res = drawer.run_pipeline(
                            instruction="Dibuja la taza de café",
                            image_path=img_path,
                            confirm_before_draw=True,
                            prompt_before_capture=False
                        )
                        assert res["success"]
                        assert res["subject"] == "Taza de café sobre mesa"
            finally:
                if os.path.exists(img_path):
                    os.remove(img_path)


def test_resolve_claude_model_and_env(monkeypatch):
    """Verifica que el modelo de Claude sea configurable vía .env (ANTHROPIC_MODEL)."""
    from dobot_controller.vision.agent import (
        resolve_claude_model,
        DEFAULT_CLAUDE_MODEL,
        ALLOWED_CLAUDE_MODELS,
        VisionAgent
    )

    # 1. Por defecto devuelve DEFAULT_CLAUDE_MODEL
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("DOBOT_VISION_MODEL", raising=False)
    assert resolve_claude_model() == DEFAULT_CLAUDE_MODEL

    # 2. Respeta ANTHROPIC_MODEL desde el entorno/.env
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-7-sonnet-20250219")
    assert resolve_claude_model() == "claude-3-7-sonnet-20250219"

    # 3. Argumento explícito tiene prioridad sobre variable de entorno
    assert resolve_claude_model("claude-3-5-haiku-20241022") == "claude-3-5-haiku-20241022"

    # 4. VisionAgent inicializado sin argumento usa el modelo configurado
    agent = VisionAgent(api_key="test-dummy-key")
    assert agent.model == "claude-3-7-sonnet-20250219"

    # 5. Lista de permitidos contiene los modelos estándar
    assert "claude-sonnet-4-5-20250929" in ALLOWED_CLAUDE_MODELS
    assert "claude-3-7-sonnet-20250219" in ALLOWED_CLAUDE_MODELS
    assert "claude-3-5-sonnet-20241022" in ALLOWED_CLAUDE_MODELS
    assert "claude-3-5-haiku-20241022" in ALLOWED_CLAUDE_MODELS
    assert "claude-3-opus-20240229" in ALLOWED_CLAUDE_MODELS

