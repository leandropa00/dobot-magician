"""
Módulo de visión robótica y control multimodal para Dobot Magician + GoPro + Claude.
"""

from dobot_controller.vision.camera import GoProCapture, MockCamera
from dobot_controller.vision.agent import (
    VisionAgent,
    DEFAULT_CLAUDE_MODEL,
    ALLOWED_CLAUDE_MODELS,
    resolve_claude_model
)
from dobot_controller.vision.visual_servo import VisualServoLoop
from dobot_controller.vision.gopro_setup import (
    list_v4l2_devices,
    find_gopro_network_interface,
    activate_gopro_webcam,
    stop_gopro_webcam,
    check_gopro_status,
    set_gopro_webcam_fov
)

__all__ = [
    "GoProCapture",
    "MockCamera",
    "VisionAgent",
    "VisualServoLoop",
    "DEFAULT_CLAUDE_MODEL",
    "ALLOWED_CLAUDE_MODELS",
    "resolve_claude_model",
    "list_v4l2_devices",
    "find_gopro_network_interface",
    "activate_gopro_webcam",
    "stop_gopro_webcam",
    "check_gopro_status",
    "set_gopro_webcam_fov"
]
