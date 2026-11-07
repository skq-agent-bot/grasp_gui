"""rhfszeeman95 默认分支的四问，以及与已有自定义输入的对照。"""

from pathlib import Path

import pytest

import grasp_config as config
import grasp_core as core


@pytest.mark.parametrize("ci", [False, True])
@pytest.mark.parametrize("offdiag", [False, True])
def test_hfszeeman_input(ci, offdiag):
    step = core.RHfsZeeman95()
    v = dict(step.defaults(), state=" state ", ci=ci, offdiag=offdiag)
    assert step.stdin(v) == f"y\nstate\n{'y' if ci else 'n'}\n{'y' if offdiag else 'n'}\n"
    assert step.post(v) == []
    v["saveas"] = " constants.txt "
    assert step.post(v) == [("cp", "state.ch" if ci else "state.h", "constants.txt")]


@pytest.mark.parametrize("state", ["", " ", "a b", "../state", "/state", "-state", "态", "a;echo", "a\nb", "x" * 24])
def test_hfszeeman_invalid_state(state):
    step = core.RHfsZeeman95()
    v = dict(step.defaults(), state=state)
    with pytest.raises(ValueError):
        step.validate(v)
    with pytest.raises(ValueError):
        step.stdin(v)


def test_hfszeeman_registration_and_fields():
    step = core.RHfsZeeman95()
    assert step.stdin(dict(step.defaults(), state="x" * 23)).splitlines()[1] == "x" * 23
    assert step.defaults()["ci"] is True
    assert step.defaults()["offdiag"] is True
    assert step.key in core.GROUP_STEPS
    keys = next(keys for _, keys in core.STEP_GROUPS if "rhfs" in keys)
    assert keys[keys.index("rhfs") + 1] == step.key
    assert all(f.added == "2.5.0" for f in step.fields if isinstance(f, core.Field))
    cfg, warnings = config.check(dict(format=config.FORMAT, version=config.VERSION,
                                      jobs=[dict(step=step.key, vals={})]))
    assert not warnings
    assert config.session(cfg)["pipeline"][0]["stdin"] == step.stdin(step.defaults())


def test_example9_hfszeeman_inputs_unchanged():
    cfg, _ = config.load(str(Path(__file__).resolve().parents[1] / "demos/example9.json"))
    states = []
    step = core.RHfsZeeman95()
    for job in cfg["jobs"]:
        v = job["vals"]
        if job["step"] == "custom" and v["prog"] == "rhfszeeman95":
            default, state, ci, offdiag = v["stdin"].splitlines()
            assert default == "y"
            actual = step.stdin(dict(step.defaults(), state=state, ci=ci == "y", offdiag=offdiag == "y"))
            assert actual == v["stdin"]
            states.append(state)
    assert states == ["even_n3", "odd_n3"]
