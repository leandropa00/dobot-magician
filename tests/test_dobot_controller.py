"""Pruebas unitarias para dobot-controller."""

import pytest
from typer.testing import CliRunner

from dobot_controller.safety import SafetyLimits, SafetyBoundaryError
from dobot_controller.mock import MockDobot
from dobot_controller.controller import DobotController
from dobot_controller.cli import app

runner = CliRunner()


def test_safety_limits_valid():
    valid, msg = SafetyLimits.validate_cartesian(220.0, 0.0, 50.0, 0.0)
    assert valid is True
    assert msg == "OK"


def test_safety_limits_out_of_reach():
    valid, msg = SafetyLimits.validate_cartesian(350.0, 100.0, 50.0, 0.0)
    assert valid is False
    assert "excede el alcance máximo" in msg

    with pytest.raises(SafetyBoundaryError):
        SafetyLimits.enforce(350.0, 100.0, 50.0, 0.0)


def test_safety_limits_too_low():
    valid, msg = SafetyLimits.validate_cartesian(200.0, 0.0, -100.0, 0.0)
    assert valid is False
    assert "por debajo del límite seguro" in msg

    with pytest.raises(SafetyBoundaryError):
        SafetyLimits.enforce(200.0, 0.0, -100.0, 0.0)


def test_safety_limits_too_close_to_base():
    valid, msg = SafetyLimits.validate_cartesian(100.0, 0.0, 50.0, 0.0)
    assert valid is False
    assert "menor al mínimo seguro" in msg

    with pytest.raises(SafetyBoundaryError):
        SafetyLimits.enforce(100.0, 0.0, 50.0, 0.0)


def test_mock_dobot_motion():
    mock = MockDobot()
    pose = mock.get_pose()
    assert pose.position.x == 220.0
    assert pose.position.y == 0.0

    mock.move_to(x=240.0, y=20.0, z=30.0)
    new_pose = mock.get_pose()
    assert new_pose.position.x == 240.0
    assert new_pose.position.y == 20.0
    assert new_pose.position.z == 30.0

    mock.move_rel(x=10.0, y=-5.0)
    rel_pose = mock.get_pose()
    assert rel_pose.position.x == 250.0
    assert rel_pose.position.y == 15.0


def test_mock_dobot_effectors():
    mock = MockDobot()
    assert mock.suction_enabled is False
    mock.suck(True)
    assert mock.suction_enabled is True
    mock.suck(False)
    assert mock.suction_enabled is False

    assert mock.gripper_enabled is False
    mock.grip(True)
    assert mock.gripper_enabled is True
    mock.grip(False)
    assert mock.gripper_enabled is False


def test_dobot_controller_context_and_pick_and_place():
    with DobotController(mock=True) as bot:
        pose = bot.get_pose()
        assert "x" in pose
        assert "j1" in pose

        bot.pick_and_place(
            pick_pos=(220.0, -50.0, 0.0),
            place_pos=(220.0, 50.0, 0.0),
            safe_z=40.0,
            dwell_seconds=0.01
        )
        assert len(bot.raw_device.command_history) > 5


def test_cli_scan():
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0
    assert "Escaneo de Puertos Serie" in result.stdout


def test_cli_status_mock():
    result = runner.invoke(app, ["status", "--mock"])
    assert result.exit_code == 0
    assert "Estado del Robot" in result.stdout
    assert "SIMULACIÓN" in result.stdout


def test_cli_move_mock():
    result = runner.invoke(app, ["move", "--x", "230", "--y", "10", "--z", "40", "--mock"])
    assert result.exit_code == 0
    assert "Movimiento completado con éxito" in result.stdout


def test_cli_demo_mock():
    result = runner.invoke(app, ["demo", "--mock"])
    assert result.exit_code == 0
    assert "Demostración finalizada exitosamente" in result.stdout
