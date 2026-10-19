"""Simulation must exercise current generator output, even on a clean checkout."""

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_simulation as simulation
import test_stress as stress
from cocotb_tools import runner


@pytest.mark.parametrize("stale", [False, True])
def test_self_check_generates_sources(tmp_path, monkeypatch, stale):
    monkeypatch.setenv("SIM", "icarus")
    if stale:
        for name in ("gpio_regs.v", "tb_gpio_regs.v"):
            (tmp_path / name).write_text("stale source")
    calls = []

    def simulate(top, dut, tb, build_dir):
        assert top == "gpio"
        assert dut.parent == tb.parent == build_dir == tmp_path
        assert "module gpio_regs" in dut.read_text()
        assert "module tb_gpio_regs" in tb.read_text()
        calls.append(top)
        return 0, "TEST PASSED"

    monkeypatch.setattr(simulation, "_run_icarus", simulate)
    simulation.test_self_check_tb("gpio", tmp_path)
    assert calls == ["gpio"]


@pytest.mark.parametrize("stale", [False, True])
def test_stress_generates_sources(tmp_path, monkeypatch, stale):
    monkeypatch.setenv("SIM", "icarus")
    monkeypatch.setattr(stress, "REPO_ROOT", tmp_path)
    build_dir = tmp_path / "sim_build/stress/gpio/icarus/stress_random_axi"
    dut = build_dir / "sources/gpio_regs.v"
    if stale:
        dut.parent.mkdir(parents=True)
        dut.write_text("stale source")
    calls = []

    def build(**kwargs):
        assert kwargs["sources"] == [str(dut)]
        assert "module gpio_regs" in dut.read_text()
        calls.append("build")

    def test(**kwargs):
        assert kwargs["testcase"] == "stress_random_axi"
        calls.append("test")

    monkeypatch.setattr(
        runner, "get_runner", lambda sim: SimpleNamespace(build=build, test=test)
    )
    stress._run_cocotb_test("gpio", "stress_random_axi")
    assert calls == ["build", "test"]


@pytest.mark.parametrize("source", ["bus_generator.py", "__init__.py"])
def test_make_rebuilds_artifacts_for_generator_changes(tmp_path, source):
    root = simulation.REPO_ROOT
    shutil.copy(root / "Makefile", tmp_path / "Makefile")
    prerequisites = [
        root / "samples/gpio.rdl",
        *(root / "src/bus_generator").glob("*.py"),
        *(root / "src/bus_generator/templates").glob("*.jinja2"),
    ]
    for path in prerequisites:
        dest = tmp_path / path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.touch()
        os.utime(dest, (100, 100))
    for artifact in ("axi4l/gpio_regs.v", "c_header/gpio.h", "tb_axi4l/tb_gpio_regs.v"):
        dest = tmp_path / "generated" / artifact
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.touch()
        os.utime(dest, (200, 200))

    command = ["make", "-n", "SAMPLES=gpio", "artifacts"]
    unchanged = subprocess.check_output(command, cwd=tmp_path, text=True)
    assert "uv run bus-generator" not in unchanged
    changed = subprocess.check_output(
        [*command, "-W", str(Path("src/bus_generator") / source)],
        cwd=tmp_path,
        text=True,
    )
    assert changed.count("uv run bus-generator") == 3
