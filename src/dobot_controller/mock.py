"""Simulador/Mock de Dobot Magician para pruebas offline y desarrollo sin hardware físico."""

import logging
from typing import List, Optional
from pydobotplus.dobotplus import Pose, Position, Joints

logger = logging.getLogger(__name__)


class MockDobot:
    """Implementa la misma interfaz que pydobotplus.Dobot pero simulada en memoria."""

    def __init__(self, port: Optional[str] = None):
        self.port = port or "/dev/ttyUSB_SIMULATED"
        self._x = 220.0
        self._y = 0.0
        self._z = 50.0
        self._r = 0.0
        self._j1 = 0.0
        self._j2 = 20.0
        self._j3 = 45.0
        self._j4 = 0.0

        self.suction_enabled = False
        self.gripper_enabled = False
        self.alarms: List[int] = []
        self.command_history: List[dict] = []
        self.is_open = True
        logger.info(f"[MOCK DOBOT] Conectado en puerto simulado {self.port}")

    def get_pose(self) -> Pose:
        return Pose(
            position=Position(x=self._x, y=self._y, z=self._z, r=self._r),
            joints=Joints(j1=self._j1, j2=self._j2, j3=self._j3, j4=self._j4)
        )

    def move_to(self, x=None, y=None, z=None, r=None, wait=True, mode=None, position=None):
        if position is not None:
            x, y, z, r = position.x, position.y, position.z, position.r

        if x is not None:
            self._x = float(x)
        if y is not None:
            self._y = float(y)
        if z is not None:
            self._z = float(z)
        if r is not None:
            self._r = float(r)

        cmd = {"cmd": "move_to", "x": self._x, "y": self._y, "z": self._z, "r": self._r, "wait": wait}
        self.command_history.append(cmd)
        logger.debug(f"[MOCK DOBOT] Desplazado a x={self._x:.1f}, y={self._y:.1f}, z={self._z:.1f}, r={self._r:.1f}")
        return len(self.command_history)

    def move_rel(self, x=0.0, y=0.0, z=0.0, r=0.0, wait=True):
        self._x += float(x)
        self._y += float(y)
        self._z += float(z)
        self._r += float(r)
        cmd = {"cmd": "move_rel", "x": self._x, "y": self._y, "z": self._z, "r": self._r, "wait": wait}
        self.command_history.append(cmd)
        logger.debug(f"[MOCK DOBOT] Desplazamiento relativo a x={self._x:.1f}, y={self._y:.1f}, z={self._z:.1f}, r={self._r:.1f}")
        return len(self.command_history)

    def home(self):
        self._x = 220.0
        self._y = 0.0
        self._z = 50.0
        self._r = 0.0
        self._j1 = 0.0
        self._j2 = 20.0
        self._j3 = 45.0
        self._j4 = 0.0
        cmd = {"cmd": "home"}
        self.command_history.append(cmd)
        logger.info("[MOCK DOBOT] Ejecutando rutina de homing...")
        return len(self.command_history)

    def suck(self, enable: bool):
        self.suction_enabled = bool(enable)
        cmd = {"cmd": "suck", "enable": self.suction_enabled}
        self.command_history.append(cmd)
        logger.info(f"[MOCK DOBOT] Succión {'ACTIVADA' if self.suction_enabled else 'DESACTIVADA'}")
        return len(self.command_history)

    def grip(self, enable: bool):
        self.gripper_enabled = bool(enable)
        cmd = {"cmd": "grip", "enable": self.gripper_enabled}
        self.command_history.append(cmd)
        logger.info(f"[MOCK DOBOT] Gripper {'CERRADO' if self.gripper_enabled else 'ABIERTO'}")
        return len(self.command_history)

    def speed(self, velocity: float, acceleration: float):
        cmd = {"cmd": "speed", "velocity": velocity, "acceleration": acceleration}
        self.command_history.append(cmd)
        return len(self.command_history)

    def get_alarms(self) -> List[int]:
        return list(self.alarms)

    def clear_alarms(self):
        self.alarms.clear()
        cmd = {"cmd": "clear_alarms"}
        self.command_history.append(cmd)

    def close(self):
        self.is_open = False
        logger.info("[MOCK DOBOT] Conexión cerrada.")
