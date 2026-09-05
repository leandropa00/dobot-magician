"""Controlador de alto nivel para Dobot Magician con soporte para hardware real o simulado."""

import time
import logging
from typing import Optional, Dict, Tuple, Any

from pydobotplus import Dobot
from dobot_controller.connection import find_dobot_port, check_dialout_permission
from dobot_controller.safety import SafetyLimits, SafetyBoundaryError
from dobot_controller.mock import MockDobot

logger = logging.getLogger(__name__)


class DobotController:
    """
    Controlador principal para el brazo robótico Dobot Magician.
    Soporta gestión de contexto (`with DobotController() as bot:`),
    verificación de límites de seguridad y modo de simulación.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        mock: bool = False,
        enforce_safety: bool = True,
        velocity: float = 100.0,
        acceleration: float = 100.0
    ):
        self.mock = mock
        self.enforce_safety = enforce_safety
        self.port = port
        self.raw_device: Any = None

        if not self.mock:
            if not self.port:
                detected_port = find_dobot_port()
                if not detected_port:
                    dialout = check_dialout_permission()
                    err_msg = (
                        "No se encontró un puerto serie conectado al Dobot Magician.\n"
                        "Verifica que el cable USB esté conectado y encendido.\n"
                    )
                    if not dialout["in_dialout"]:
                        err_msg += (
                            f"Atención: Tu usuario '{dialout['user']}' no está en el grupo 'dialout'.\n"
                            f"Ejecuta: {dialout['fix_command']}\n"
                        )
                    err_msg += "Si deseas probar sin hardware físico, usa el modo simulación (mock=True)."
                    raise ConnectionError(err_msg)
                self.port = detected_port

            logger.info(f"Conectando a Dobot en {self.port}...")
            self.raw_device = Dobot(port=self.port)
        else:
            logger.info("Iniciando en MODO SIMULACIÓN (MockDobot)...")
            self.raw_device = MockDobot(port=self.port or "/dev/ttyUSB_SIMULATED")

        # Configurar velocidades iniciales
        self.set_speed(velocity, acceleration)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Cierra la conexión con el robot y desactiva efectores de forma segura."""
        if self.raw_device is not None:
            try:
                self.set_suction(False)
            except Exception:
                pass
            try:
                self.raw_device.close()
            except Exception:
                pass
            self.raw_device = None

    def get_pose(self) -> Dict[str, Any]:
        """Obtiene la posición cartesiana y articular actual."""
        p = self.raw_device.get_pose()
        return {
            "x": round(float(p.position.x), 2),
            "y": round(float(p.position.y), 2),
            "z": round(float(p.position.z), 2),
            "r": round(float(p.position.r), 2),
            "j1": round(float(p.joints.j1), 2),
            "j2": round(float(p.joints.j2), 2),
            "j3": round(float(p.joints.j3), 2),
            "j4": round(float(p.joints.j4), 2),
        }

    def move_to(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        r: Optional[float] = None,
        wait: bool = True,
        mode: Optional[int] = None
    ) -> int:
        """Mueve el robot a la posición cartesiana indicada (mm y grados)."""
        current = self.get_pose()
        target_x = current["x"] if x is None else float(x)
        target_y = current["y"] if y is None else float(y)
        target_z = current["z"] if z is None else float(z)
        target_r = current["r"] if r is None else float(r)

        if self.enforce_safety:
            SafetyLimits.enforce(target_x, target_y, target_z, target_r)

        kwargs = {"x": target_x, "y": target_y, "z": target_z, "r": target_r, "wait": wait}
        if mode is not None:
            kwargs["mode"] = mode

        return self.raw_device.move_to(**kwargs)

    def move_rel(
        self,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
        dr: float = 0.0,
        wait: bool = True,
        mode: Optional[int] = None
    ) -> int:
        """Mueve el robot de forma relativa respecto a su posición actual."""
        current = self.get_pose()
        target_x = current["x"] + dx
        target_y = current["y"] + dy
        target_z = current["z"] + dz
        target_r = current["r"] + dr

        if self.enforce_safety:
            SafetyLimits.enforce(target_x, target_y, target_z, target_r)

        kwargs = {"x": target_x, "y": target_y, "z": target_z, "r": target_r, "wait": wait}
        if mode is not None:
            kwargs["mode"] = mode

        return self.raw_device.move_to(**kwargs)

    def home(self):
        """Ejecuta la calibración a posición HOME."""
        logger.info("Ejecutando homing del Dobot Magician...")
        return self.raw_device.home()

    def set_suction(self, enable: bool):
        """Activa o desactiva la ventosa de succión."""
        return self.raw_device.suck(enable)

    def set_gripper(self, enable: bool):
        """Cierra (enable=True) o abre (enable=False) el gripper."""
        return self.raw_device.grip(enable)

    def set_speed(self, velocity: float, acceleration: float):
        """Configura la velocidad y aceleración del efector final."""
        return self.raw_device.speed(velocity=velocity, acceleration=acceleration)

    def get_alarms(self):
        """Retorna la lista de alarmas activas."""
        return self.raw_device.get_alarms()

    def clear_alarms(self):
        """Limpia las alarmas activas."""
        return self.raw_device.clear_alarms()

    def pick_and_place(
        self,
        pick_pos: Tuple[float, float, float],
        place_pos: Tuple[float, float, float],
        safe_z: float = 60.0,
        dwell_seconds: float = 0.5,
        use_gripper: bool = False
    ):
        """
        Rutina estándar de Pick & Place:
        1. Sube a safe_z sobre pick_pos
        2. Baja a pick_pos y activa efector
        3. Sube a safe_z
        4. Se desplaza a safe_z sobre place_pos
        5. Baja a place_pos y desactiva efector
        6. Retorna a safe_z
        """
        px, py, pz = pick_pos
        dx, dy, dz = place_pos

        effector_func = self.set_gripper if use_gripper else self.set_suction

        # 1. Posición segura sobre punto de recogida
        self.move_to(x=px, y=py, z=safe_z)
        # 2. Bajar a recoger
        self.move_to(x=px, y=py, z=pz)
        effector_func(True)
        time.sleep(dwell_seconds)
        # 3. Elevar a altura segura
        self.move_to(x=px, y=py, z=safe_z)

        # 4. Desplazar sobre punto de entrega
        self.move_to(x=dx, y=dy, z=safe_z)
        # 5. Bajar a soltar
        self.move_to(x=dx, y=dy, z=dz)
        effector_func(False)
        time.sleep(dwell_seconds)
        # 6. Regresar a altura segura
        self.move_to(x=dx, y=dy, z=safe_z)
