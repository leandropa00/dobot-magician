"""
Aplicación FastAPI que expone la API REST y sirve la interfaz web
para el control del Dobot Magician, captura de video de la cámara del usuario,
síntesis de bocetos con IA y ejecución a partir del punto indicado.
"""

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dobot_controller.web.robot_manager import RobotManager
from dobot_controller.safety import SafetyBoundaryError

logger = logging.getLogger(__name__)

# Directorio estático
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Dobot Magician Web Studio",
    description="Interfaz web para captura con cámara, bocetos IA con Claude y dibujo robótico",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instancia global de RobotManager
robot_manager: Optional[RobotManager] = None


def get_manager() -> RobotManager:
    global robot_manager
    if robot_manager is None:
        mock_env = os.environ.get("DOBOT_MOCK", "false").lower() in ("true", "1", "yes")
        robot_manager = RobotManager(mock=mock_env)
    return robot_manager


# Modelos Pydantic para peticiones
class ConnectRequest(BaseModel):
    mock: Optional[bool] = None
    port: Optional[str] = None


class MoveRelativeRequest(BaseModel):
    dx: float = Field(0.0, description="Desplazamiento X en mm")
    dy: float = Field(0.0, description="Desplazamiento Y en mm")
    dz: float = Field(0.0, description="Desplazamiento Z en mm")
    dr: float = Field(0.0, description="Rotación R en grados")


class MoveAbsoluteRequest(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    r: Optional[float] = None


class SetOriginRequest(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None
    z_draw: Optional[float] = None
    z_hover: Optional[float] = None
    r: Optional[float] = None


class GenerateSketchRequest(BaseModel):
    image: str = Field(..., description="Imagen en formato base64 JPEG capturada por la cámara del usuario")
    instruction: Optional[str] = "Identifica el objeto en la imagen y sintetiza un boceto de líneas limpias para dibujarlo en el cuaderno"


# ==========================================
# RUTAS DE LA API
# ==========================================

@app.get("/api/status")
def get_status():
    mgr = get_manager()
    return mgr.get_status()


@app.post("/api/robot/connect")
def connect_robot(req: ConnectRequest):
    mgr = get_manager()
    status = mgr.reconnect(mock=req.mock, port=req.port)
    return status


@app.post("/api/robot/move-rel")
def move_relative(req: MoveRelativeRequest):
    mgr = get_manager()
    try:
        new_pose = mgr.jog_relative(dx=req.dx, dy=req.dy, dz=req.dz, dr=req.dr)
        return {"status": "ok", "pose": new_pose}
    except SafetyBoundaryError as se:
        raise HTTPException(status_code=400, detail=f"Límite de seguridad alcanzado: {se}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/robot/move-abs")
def move_absolute(req: MoveAbsoluteRequest):
    mgr = get_manager()
    try:
        new_pose = mgr.jog_absolute(x=req.x, y=req.y, z=req.z, r=req.r)
        return {"status": "ok", "pose": new_pose}
    except SafetyBoundaryError as se:
        raise HTTPException(status_code=400, detail=f"Límite de seguridad alcanzado: {se}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/robot/home")
def home_robot():
    mgr = get_manager()
    try:
        pose = mgr.home()
        return {"status": "ok", "pose": pose}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/robot/set-origin-from-current")
def set_origin_from_current():
    """Fija la posición actual del brazo como el punto de inicio / centro de dibujo indicado."""
    mgr = get_manager()
    try:
        origin = mgr.set_current_as_origin()
        return {"status": "ok", "origin": origin, "sketch_updated": mgr.current_sketch is not None}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/robot/set-origin")
def set_origin(req: SetOriginRequest):
    """Establece manualmente el punto de inicio de dibujo."""
    mgr = get_manager()
    try:
        origin = mgr.set_origin(x=req.x, y=req.y, z_draw=req.z_draw, z_hover=req.z_hover, r=req.r)
        return {"status": "ok", "origin": origin, "sketch_updated": mgr.current_sketch is not None}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/robot/move-to-origin")
def move_to_origin(hover: bool = True):
    """Mueve el efector final al punto de inicio indicado."""
    mgr = get_manager()
    try:
        pose = mgr.move_to_origin(hover=hover)
        return {"status": "ok", "pose": pose}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/generate-sketch")
def generate_sketch(req: GenerateSketchRequest):
    """
    Recibe la foto capturada por la cámara del usuario y la envía al modelo para sintetizar el boceto.
    Calcula los trazos relativos al punto de inicio indicado y retorna la vista previa.
    """
    mgr = get_manager()
    try:
        result = mgr.generate_sketch_from_image(image_base64=req.image, user_instruction=req.instruction)
        return result
    except Exception as e:
        logger.error(f"Error generando boceto: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al generar boceto: {e}")


@app.post("/api/update-preview")
def update_preview():
    """Actualiza la vista previa del boceto con la posición de inicio actual."""
    mgr = get_manager()
    if not mgr.current_sketch:
        raise HTTPException(status_code=400, detail="No hay boceto activo.")
    mgr._recalculate_current_sketch()
    return {
        "status": "ok",
        "preview_image": mgr.current_sketch["preview_base64"],
        "origin": {
            "x": mgr.origin_x,
            "y": mgr.origin_y,
            "z_draw": mgr.origin_z_draw,
            "z_hover": mgr.origin_z_hover
        }
    }


@app.post("/api/start-drawing")
def start_drawing():
    """Confirma el boceto e inicia el dibujo en el Dobot Magician a partir del punto indicado."""
    mgr = get_manager()
    try:
        res = mgr.start_drawing()
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/stop-drawing")
def stop_drawing():
    """Detiene el dibujo de emergencia."""
    mgr = get_manager()
    res = mgr.stop_drawing()
    return res


@app.get("/api/drawing/progress")
def drawing_progress():
    mgr = get_manager()
    return mgr.drawing_progress


# ==========================================
# RUTAS DE ARCHIVOS ESTÁTICOS Y FRONTEND
# ==========================================

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse({"status": "error", "message": "index.html no encontrado"}, status_code=404)
    return FileResponse(index_file)
