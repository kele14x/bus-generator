"""Prove the generated merge checker rejects broken DUT software masks."""

import os
import re

import pytest
from test_simulation import REPO_ROOT, _run_icarus, _run_questa, _run_verilator

from bus_generator import main

pytestmark = pytest.mark.sim


@pytest.mark.parametrize("mutation", [None, "zero", "ones", "wrong_lane"])
@pytest.mark.parametrize("layout", ["gpio", "cross_byte", "msb0", "single_bit"])
def test_generated_merge_checker(tmp_path, layout, mutation):
    sim = os.environ["SIM"]
    if layout == "gpio":
        rdl = REPO_ROOT / "samples" / "gpio.rdl"
        top, field, width, bus_lsb = "gpio", "data_data", 32, 0
    else:
        top, field = "merge_check", "control_value"
        if layout == "single_bit":
            numbering, regwidth, bits, address = "lsb0", 32, "29:29", 0
            width, bus_lsb = 1, 29
        else:
            # A 16-bit register at byte 1 puts this field at AXI bits [19:12].
            numbering = "msb0" if layout == "msb0" else "lsb0"
            regwidth, bits, address = (
                16,
                "11:4" if layout == "cross_byte" else "4:11",
                1,
            )
            width, bus_lsb = 8, 12
        rdl = tmp_path / f"{top}.rdl"
        rdl.write_text(f"""addrmap {top} {{
            {numbering};
            reg {{
                regwidth = {regwidth}; accesswidth = {regwidth};
                field {{ sw = rw; hw = rw; }} value[{bits}];
            }} control @ {address};
        }};
        """)

    main([str(rdl), "-o", str(tmp_path), "-t", "axi4l", "tb_axi4l"])
    dut = tmp_path / f"{top}_regs.v"
    # .sv also enables SystemVerilog for Questa.
    tb = tmp_path / f"tb_{top}_regs.sv"
    tb.write_text((tmp_path / f"tb_{top}_regs.v").read_text())

    if mutation is not None:
        if mutation == "wrong_lane":
            mask = (
                "{"
                + ", ".join(
                    f"int_wr_strb[{((bus_lsb + bit) // 8 + 1) % 4}]"
                    for bit in reversed(range(width))
                )
                + "}"
            )
        else:
            mask = f"{width}'h{0 if mutation == 'zero' else (1 << width) - 1:x}"
        source, count = re.subn(
            rf"(assign {field}_sw_mask\s*=)[^;]+;",
            rf"\g<1> {mask};",
            dut.read_text(),
        )
        assert count == 1, "Mutation must replace exactly one DUT mask"
        dut.write_text(source)

    returncode, output = {
        "icarus": _run_icarus,
        "verilator": _run_verilator,
        "questa": _run_questa,
    }[sim](top, dut, tb, tmp_path)
    if mutation is None:
        assert returncode == 0, output
        assert "TEST PASSED" in output, output
        assert "TEST FAILED" not in output, output
    else:
        assert "software/hardware merge mismatch" in output, output
        assert "TEST FAILED" in output, output
        assert "TEST PASSED" not in output, output
