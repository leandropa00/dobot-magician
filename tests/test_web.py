"""
Pruebas automatizadas para la interfaz web y API REST de Dobot Magician.
Verifica captura, movimientos con flechas (jogging), fijación de punto de inicio,
generación de bocetos y ejecución del dibujo continuo.
"""

import os
import base64
import time
import pytest
from fastapi.testclient import TestClient

from dobot_controller.web.app import app, get_manager
from dobot_controller.web.robot_manager import RobotManager


@pytest.fixture
def client(monkeypatch):
    # Evitar llamadas de red externas a la API de Anthropic durante pruebas unitarias locales
    monkeypatch.setattr("dobot_controller.web.robot_manager.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    mgr = RobotManager(mock=True)
    mgr.anthropic_key = None
    from dobot_controller.web import app as app_module
    app_module.robot_manager = mgr
    return TestClient(app)


def test_index_page(client):
    """Verifica que la página principal HTML cargue correctamente."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Dobot Magician" in response.text
    assert "btnCapturePhoto" in response.text
    assert "btnSendToModel" in response.text
    assert "btnConfirmAndDraw" in response.text
    assert "btnSetOriginFromCurrent" in response.text


def test_robot_status(client):
    """Verifica el endpoint de estado del robot y punto de inicio."""
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert data["mock"] is True
    assert "pose" in data
    assert "origin" in data
    assert "x" in data["origin"]
    assert "y" in data["origin"]


def test_jog_arrows_movement(client):
    """Verifica el movimiento relativo del brazo robótico mediante las flechas de control."""
    status_before = client.get("/api/status").json()
    init_x = status_before["pose"]["x"]
    init_y = status_before["pose"]["y"]

    # Mover +X (+10 mm)
    res_x = client.post("/api/robot/move-rel", json={"dx": 10.0, "dy": 0.0, "dz": 0.0, "dr": 0.0})
    assert res_x.status_code == 200
    data_x = res_x.json()
    assert round(data_x["pose"]["x"], 1) == round(init_x + 10.0, 1)

    # Mover -Y (-5 mm)
    res_y = client.post("/api/robot/move-rel", json={"dx": 0.0, "dy": -5.0, "dz": 0.0, "dr": 0.0})
    assert res_y.status_code == 200
    data_y = res_y.json()
    assert round(data_y["pose"]["y"], 1) == round(init_y - 5.0, 1)


def test_jog_safety_limit_protection(client):
    """Verifica que el jogging no permita exceder los límites mecánicos de seguridad."""
    # Intentar mover X a una distancia fuera de rango
    res = client.post("/api/robot/move-rel", json={"dx": 500.0, "dy": 0.0, "dz": 0.0, "dr": 0.0})
    assert res.status_code == 400
    assert "Límite de seguridad alcanzado" in res.json()["detail"]


def test_set_origin_and_start_drawing_from_point(client):
    """
    Verifica que el usuario pueda mover el brazo a una posición y fijarla como punto de inicio,
    y que el dibujo comience a trazarse a partir de ese punto indicado.
    """
    # 1. Posicionar el robot con las flechas en un punto deseado
    client.post("/api/robot/move-abs", json={"x": 240.0, "y": 15.0, "z": -35.0, "r": 0.0})

    # 2. Fijar posición actual como punto de inicio indicado
    res_set = client.post("/api/robot/set-origin-from-current")
    assert res_set.status_code == 200
    origin_data = res_set.json()["origin"]
    assert round(origin_data["x"], 1) == 240.0
    assert round(origin_data["y"], 1) == 15.0
    assert round(origin_data["z_draw"], 1) == -35.0
    assert round(origin_data["z_hover"], 1) == -20.0  # -35 + 15

    # 3. Generar un boceto
    # Crear imagen dummy de 100x100 píxeles en base64
    import numpy as np
    import cv2
    dummy_frame = np.full((100, 100, 3), 128, dtype=np.uint8)
    _, buffer = cv2.imencode(".jpg", dummy_frame)
    b64_img = "data:image/jpeg;base64," + base64.b64encode(buffer).decode("utf-8")

    res_sketch = client.post("/api/generate-sketch", json={
        "image": b64_img,
        "instruction": "Dibuja un objeto de prueba"
    })
    assert res_sketch.status_code == 200
    sketch = res_sketch.json()
    assert sketch["success"] is True
    assert sketch["stroke_count"] > 0
    assert "preview_image" in sketch
    assert sketch["preview_image"].startswith("data:image/png;base64,")

    # Los trazos convertidos deben estar centrados en torno al origen fijado (240.0, 15.0)
    first_stroke = sketch["robot_strokes"][0]
    first_pt = first_stroke["points"][0]
    # Comprobar que las coordenadas están en la cercanía del origen fijado (X~240, Y~15)
    assert abs(first_pt[0] - 240.0) < 100.0
    assert abs(first_pt[1] - 15.0) < 100.0

    # 4. Iniciar dibujo robótico a partir del punto indicado
    res_draw = client.post("/api/start-drawing")
    assert res_draw.status_code == 200
    assert res_draw.json()["status"] == "started"

    # 5. Consultar progreso de dibujo
    time.sleep(0.3)
    res_prog = client.get("/api/drawing/progress")
    assert res_prog.status_code == 200
    prog = res_prog.json()
    assert "percent" in prog
    assert "is_drawing" in prog

    # 6. Detener dibujo de forma controlada
    res_stop = client.post("/api/stop-drawing")
    assert res_stop.status_code == 200
    assert res_stop.json()["status"] in ("cancelling", "not_drawing")


def test_camera_devices_and_selection(client):
    """Verifica detección de cámaras (incluyendo GoPro) y selección de fuente de video."""
    # 1. Listar dispositivos disponibles
    res = client.get("/api/camera/devices")
    assert res.status_code == 200
    devices = res.json()["devices"]
    assert len(devices) > 0

    # 2. Seleccionar cámara simulada / mock
    res_sel = client.post("/api/camera/select", json={"source": "mock"})
    assert res_sel.status_code == 200
    assert res_sel.json()["status"] == "ok"

    # 3. Obtener instantánea fotográfica de la cámara
    res_snap = client.get("/api/camera/snapshot")
    assert res_snap.status_code == 200
    data = res_snap.json()
    assert "image_base64" in data
    assert data["image_base64"].startswith("data:image/jpeg;base64,")


def test_start_drawing_preserves_z_height(client):
    """
    Verifica que al comenzar a dibujar, se conserve estrictamente la altura Z de Punto de Inicio Indicado.
    """
    # 1. Modificar punto de inicio con una altura Z de dibujo y de tránsito específica
    res_set = client.post("/api/robot/set-origin", json={
        "x": 230.0,
        "y": 10.0,
        "z_draw": -42.5,
        "z_hover": -27.5
    })
    assert res_set.status_code == 200
    origin = res_set.json()["origin"]
    assert origin["z_draw"] == -42.5
    assert origin["z_hover"] == -27.5

    # 2. Generar boceto
    import numpy as np
    import cv2
    dummy_frame = np.full((100, 100, 3), 128, dtype=np.uint8)
    _, buffer = cv2.imencode(".jpg", dummy_frame)
    b64_img = "data:image/jpeg;base64," + base64.b64encode(buffer).decode("utf-8")
    client.post("/api/generate-sketch", json={"image": b64_img})

    # 3. Iniciar dibujo conservando las alturas Z indicadas
    res_draw = client.post("/api/start-drawing", json={
        "origin_x": 230.0,
        "origin_y": 10.0,
        "origin_z_draw": -42.5,
        "origin_z_hover": -27.5
    })
    assert res_draw.status_code == 200
    data = res_draw.json()
    assert data["status"] == "started"
    assert data["origin"]["z_draw"] == -42.5
    assert data["origin"]["z_hover"] == -27.5

    # 4. Detener dibujo
    client.post("/api/stop-drawing")


def test_web_status_reports_env_model(client, monkeypatch):
    """Verifica que /api/status reporte el modelo configurado en ANTHROPIC_MODEL."""
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-7-sonnet-20250219")
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["model"] == "claude-3-7-sonnet-20250219"



