"""Paquete de control modular para Dobot Magician en Ubuntu."""

from dobot_controller.controller import DobotController
from dobot_controller.safety import SafetyLimits, SafetyBoundaryError
from dobot_controller.connection import list_serial_ports, find_dobot_port, check_dialout_permission
from dobot_controller.mock import MockDobot
from dobot_controller.drawing import draw_smiley_face, draw_stroke, generate_smiley_paths

__all__ = [
    "DobotController",
    "SafetyLimits",
    "SafetyBoundaryError",
    "list_serial_ports",
    "find_dobot_port",
    "check_dialout_permission",
    "MockDobot",
    "draw_smiley_face",
    "draw_stroke",
    "generate_smiley_paths",
]
