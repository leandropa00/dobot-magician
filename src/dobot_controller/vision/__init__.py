"""
Módulo de visión robótica y control multimodal para Dobot Magician + GoPro + Claude.
"""

from dobot_controller.vision.camera import GoProCapture, MockCamera
from dobot_controller.vision.agent import VisionAgent
from dobot_controller.vision.visual_servo import VisualServoLoop
from dobot_controller.vision.gopro_setup import (
    list_v4l2_devices,
    find_gopro_network_interface,
    activate_gopro_webcam,
    stop_gopro_webcam,
    check_gopro_status
)

__all__ = [
    "GoProCapture",
    "MockCamera",
    "VisionAgent",
    "VisualServoLoop",
    "list_v4l2_devices",
    "find_gopro_network_interface",
    "activate_gopro_webcam",
    "stop_gopro_webcam",
    "check_gopro_status"
]
