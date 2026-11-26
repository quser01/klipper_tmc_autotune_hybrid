"""Tests for the hybrid chopper sources (computed / manual / measured).

Klipper is not installed here: a stub package provides the `tmc` module the
plugin imports, and small fakes stand in for the config and the driver."""

import importlib.util
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ConfigError(Exception):
    pass


class CommandError(Exception):
    pass


def load_plugin():
    pkg = types.ModuleType("extras")
    pkg.__path__ = [str(ROOT)]
    tmc = types.ModuleType("extras.tmc")

    def TMCtstepHelper(mcu_tmc, velocity, pstepper=None):
        return int(velocity)

    tmc.TMCtstepHelper = TMCtstepHelper
    sys.modules["extras"] = pkg
    sys.modules["extras.tmc"] = tmc
    for name in ("motor_constants", "autotune_tmc"):
        spec = importlib.util.spec_from_file_location(
            f"extras.{name}", ROOT / f"{name}.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"extras.{name}"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["extras.autotune_tmc"], sys.modules["extras.motor_constants"]


at, mc = load_plugin()


class FakeSection:
    def __init__(self, opts):
        self.opts = {k.lower(): v for k, v in opts.items()}
        self.error = ConfigError

    def get(self, key, default=None):
        return self.opts.get(key, default)

    def getint(self, key, default=None, minval=None, maxval=None):
        v = self.opts.get(key)
        return default if v is None else int(v)


class FakeFields:
    def __init__(self, names):
        self.names = set(names)
        self.written = {}

    def lookup_register(self, field, default=None):
        return "REG" if field in self.names else default

    def set_field(self, field, val, *a):
        self.written[field] = val
        return 0


def plugin(driver="tmc5160", measured=None, hstrt=None, hend=None, fields=None):
    obj = at.AutotuneTMC.__new__(at.AutotuneTMC)
    obj.name = "stepper_x"
    obj.driver_type = driver
    obj.driver_name = f"{driver} stepper_x"
    obj.fclk = 12.5e6
    obj.pwm_freq_target = at.PWM_FREQ_TARGETS[driver]
    obj.voltage = 48.0
    obj.tbl, obj.toff, obj.tpfd = at.TBL, at.TOFF, None
    obj.extra_hysteresis = 0
    obj.hstrt, obj.hend = hstrt, hend
    obj.measured = measured
    obj.measured_chopper = measured is not None
    obj.chopper = None
    obj.printer = types.SimpleNamespace(command_error=CommandError)
    obj.motor_object = types.SimpleNamespace(
        hysteresis=lambda **kw: (3, 5)
    )  # stand-in for the analytic model
    obj.tmc_object = types.SimpleNamespace(
        fields=FakeFields(fields or ["tbl", "toff", "hstrt", "hend", "tpfd"]),
        mcu_tmc=types.SimpleNamespace(set_register=lambda *a: None),
    )
    return obj


# --- check_chopper ---------------------------------------------------------


def test_valid_set():
    assert at.check_chopper("tmc5160", 2, 3, 5, 0) is None


@pytest.mark.parametrize(
    "args, word",
    [
        ((0, 1, 0, 0), "toff=1"),  # TOFF=1 with TBL<2
        ((1, 1, 0, 0), "toff=1"),  # the upstream guard let TBL=1 through
        ((2, 0, 0, 0), "toff=0"),
        ((2, 3, 7, 12), "effective"),  # 7+12 = 19 > 18
        ((2, 3, 8, 0), "hstrt"),
    ],
)
def test_invalid_sets(args, word):
    assert word in at.check_chopper("tmc5160", *args)


def test_tmc2660_raw_sum():
    assert at.check_chopper("tmc5160", 2, 3, 7, 9) is None
    assert "TMC2660" in at.check_chopper("tmc2660", 2, 3, 7, 9)


# --- resolve ----------------------------------------------------------------


def test_computed_is_default():
    c = plugin()._resolve_chopper(2.0)
    assert c["source"] == "computed"
    assert (c["hstrt"], c["hend"]) == (3, 5)
    assert c["toff"] >= 1 and c["tpfd"] is not None


def test_computed_toff1_bumps_tbl_to_2():
    p = plugin()
    p.toff, p.tbl = 1, 1
    c = p._resolve_chopper(2.0)
    assert (c["toff"], c["tbl"]) == (1, 2)


def test_manual_hysteresis_overrides_model():
    c = plugin(hstrt=1, hend=2)._resolve_chopper(2.0)
    assert (c["source"], c["hstrt"], c["hend"]) == ("manual", 1, 2)


def test_measured_wins_over_manual():
    m = {"tbl": 1, "toff": 4, "hstrt": 0, "hend": 6, "tpfd": 0}
    c = plugin(measured=m, hstrt=1, hend=2)._resolve_chopper(2.0)
    assert c == dict(m, source="measured")


def test_measured_switched_off_falls_back():
    m = {"tbl": 1, "toff": 4, "hstrt": 0, "hend": 6, "tpfd": 0}
    p = plugin(measured=m)
    p.measured_chopper = False
    assert p._resolve_chopper(2.0)["source"] == "computed"


def test_measured_without_tpfd_uses_computed_tpfd():
    m = {"tbl": 1, "toff": 4, "hstrt": 0, "hend": 6, "tpfd": None}
    c = plugin(measured=m)._resolve_chopper(2.0)
    assert c["tpfd"] is not None and c["toff"] == 4


def test_invalid_manual_raises_before_any_write():
    p = plugin(hstrt=7, hend=15)
    with pytest.raises(CommandError, match="effective"):
        p._resolve_chopper(2.0)
    assert p.tmc_object.fields.written == {}


def test_setup_writes_all_and_records():
    p = plugin(fields=["tbl", "toff", "hstrt", "hend"])  # no tpfd: e.g. TMC2209
    c = p._resolve_chopper(2.0)
    p._setup_spreadcycle(c)
    assert set(p.tmc_object.fields.written) == {"tbl", "toff", "hstrt", "hend"}
    assert p.get_status()["source"] == "computed"


# --- reading what chopper-autotune saved ----------------------------------


def reader(tmc_opts, autotune_opts=None):
    p = plugin()
    p.tmc_section = FakeSection(tmc_opts)
    return p, FakeSection(autotune_opts or {})


def test_reads_chopper_autotune_save():
    # chopper-autotune writes upper case names; Klipper's parser lowercases them
    p, cfg = reader(
        {
            "driver_TBL": 1,
            "driver_TOFF": 3,
            "driver_HSTRT": 2,
            "driver_HEND": 4,
            "driver_TPFD": 0,
        }
    )
    assert p._read_measured(cfg) == {
        "tbl": 1,
        "toff": 3,
        "hstrt": 2,
        "hend": 4,
        "tpfd": 0,
    }


def test_missing_measured_values_explain_the_fix():
    p, cfg = reader({"driver_TBL": 1})
    with pytest.raises(ConfigError, match="CHOPPER_TUNE SAVE=1"):
        p._read_measured(cfg)


def test_measured_clashes_with_manual_options():
    p, cfg = reader(
        {"driver_TBL": 1, "driver_TOFF": 3, "driver_HSTRT": 2, "driver_HEND": 4},
        {"hend": 3},
    )
    with pytest.raises(ConfigError, match="remove hend"):
        p._read_measured(cfg)


def test_invalid_measured_rejected_at_config():
    p, cfg = reader(
        {"driver_TBL": 0, "driver_TOFF": 1, "driver_HSTRT": 2, "driver_HEND": 4}
    )
    with pytest.raises(ConfigError, match="toff=1"):
        p._read_measured(cfg)
