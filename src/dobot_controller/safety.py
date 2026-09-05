"""Módulo de seguridad y validación de envolvente de trabajo para Dobot Magician."""

import math
from typing import Tuple


class SafetyBoundaryError(Exception):
    """Excepción lanzada cuando una coordenada solicitada excede la envolvente segura de trabajo."""
    pass


class SafetyLimits:
    """Límites de seguridad del Dobot Magician (en mm)."""
    # Radio mínimo y máximo desde la base
    MIN_RADIUS_MM: float = 160.0
    MAX_RADIUS_MM: float = 330.0

    # Altura Z permitida (por seguridad, evitar valores excesivamente bajos que golpeen la mesa)
    MIN_Z_MM: float = -60.0
    MAX_Z_MM: float = 160.0

    # Rotación del cabezal (r en grados)
    MIN_R_DEG: float = -150.0
    MAX_R_DEG: float = 150.0

    @classmethod
    def validate_cartesian(cls, x: float, y: float, z: float, r: float = 0.0) -> Tuple[bool, str]:
        """
        Valida que el punto (x, y, z, r) esté dentro de la zona operativa segura.
        Retorna (es_valido, mensaje_error).
        """
        radius = math.hypot(x, y)

        if radius < cls.MIN_RADIUS_MM:
            return (
                False,
                f"Radio ({radius:.1f} mm) menor al mínimo seguro ({cls.MIN_RADIUS_MM} mm). Peligro de colisión interna."
            )

        if radius > cls.MAX_RADIUS_MM:
            return (
                False,
                f"Radio ({radius:.1f} mm) excede el alcance máximo del brazo ({cls.MAX_RADIUS_MM} mm)."
            )

        if z < cls.MIN_Z_MM:
            return (
                False,
                f"Altura Z ({z:.1f} mm) por debajo del límite seguro ({cls.MIN_Z_MM} mm). Riesgo de golpear la superficie."
            )

        if z > cls.MAX_Z_MM:
            return (
                False,
                f"Altura Z ({z:.1f} mm) por encima del límite seguro ({cls.MAX_Z_MM} mm)."
            )

        if not (cls.MIN_R_DEG <= r <= cls.MAX_R_DEG):
            return (
                False,
                f"Rotación R ({r:.1f}°) fuera de rango seguro [{cls.MIN_R_DEG}°, {cls.MAX_R_DEG}°]."
            )

        return True, "OK"

    @classmethod
    def enforce(cls, x: float, y: float, z: float, r: float = 0.0):
        """Lanza SafetyBoundaryError si la posición no es segura."""
        valid, msg = cls.validate_cartesian(x, y, z, r)
        if not valid:
            raise SafetyBoundaryError(msg)
