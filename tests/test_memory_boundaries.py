"""Generated memory-boundary checks must honor neighboring address mappings."""

import os

import pytest
from test_simulation import _run_icarus, _run_questa, _run_verilator

from bus_generator import main

pytestmark = pytest.mark.sim


@pytest.mark.parametrize(
    "neighbor",
    [
        "mem_rw",
        "mem_r",
        "mem_w",
        "mem_na",
        "reg_rw",
        "reg_r",
        "reg_w",
        "packed",
        "hole",
        "bus_end",
    ],
)
def test_memory_boundary_testbench(tmp_path, neighbor):
    top = "boundary"
    first_address, entries = (0, 2) if neighbor == "bus_end" else (0x100, 16)
    if neighbor.startswith("mem_"):
        following = f"""external mem {{
            memwidth = 32; mementries = 2; sw = {neighbor[4:]};
        }} second @ 0x140;"""
    elif neighbor.startswith("reg_"):
        following = f"""regfile {{
            reg {{ field {{ sw = {neighbor[4:]}; hw = r; }} value[31:0]; }}
                words[2] @ 0 += 4;
        }} bank @ 0x140;"""
    elif neighbor == "packed":
        following = """reg {
            regwidth = 16;
            field { sw = r; hw = r; } value[15:0];
        } low @ 0x140;
        reg {
            regwidth = 16;
            field { sw = w; hw = r; } value[15:0];
        } high @ 0x142;"""
    else:
        following = ""
    rdl = tmp_path / f"{top}.rdl"
    rdl.write_text(f"""addrmap {top} {{
        external mem {{ memwidth = 32; mementries = {entries}; sw = rw; }}
            first @ {first_address};
        {following}
    }};
    """)
    main([str(rdl), "-o", str(tmp_path), "-t", "axi4l", "tb_axi4l"])
    dut = tmp_path / f"{top}_regs.v"
    tb = tmp_path / f"tb_{top}_regs.sv"
    tb.write_text((tmp_path / f"tb_{top}_regs.v").read_text())
    sim = os.environ["SIM"]
    returncode, output = {
        "icarus": _run_icarus,
        "verilator": _run_verilator,
        "questa": _run_questa,
    }[sim](top, dut, tb, tmp_path)
    assert returncode == 0, output
    assert "TEST PASSED" in output, output
    assert "TEST FAILED" not in output, output
