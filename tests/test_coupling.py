"""Coupling 及 jj2lsj 非默认输入，对照当前 Fortran 源码。"""

import pytest

import grasp_core as core


def test_jj2lsj_default_and_coupling_inputs():
    step = core.Jj2lsj()
    v = dict(step.defaults(), state="state", ci=False, unique=False)
    assert step.stdin(v) == "state\nn\nn\ny\n"
    v.update(coupling_files=True, coupling_threshold="0.01")
    assert step.stdin(v) == "state\nn\nn\nn\ny\n0\n0.01\nn\nn\n1\n"
    v["coupling_levels"] = "1: 1\n2: 1-3\n3: 1"
    assert step.stdin(v) == "state\nn\nn\nn\nn\n1\n1\ny\n2\n1-3\ny\n3\n1\nn\n0\n0.01\nn\nn\n1\n"
    v["coupling_backup"] = True
    assert step.pre(v) == [("cp", "state.lsj.lbl", "state.lsj.lbl_SAVE")]


@pytest.mark.parametrize("shells", ["1", "2", "3"])
@pytest.mark.parametrize("verbose", [False, True])
def test_coupling_input(shells, verbose):
    step = core.Coupling()
    v = dict(step.defaults(), state="state", shells=shells, verbose=verbose)
    assert step.stdin(v) == f"state\n{'n' if verbose else 'y'}\n{shells}\n0\n1s,2s,2p\n"
    assert step.post(v) == []
    for scheme in step.SCHEMES[shells]:
        v.update(use_label=True, scheme=scheme, backup=True)
        assert step.post(v) == [("cp", "state.lsj.lbl", "state.lsj.lbl_SAVE"),
                                ("cp", f"state.coup{shells}.{scheme}.lbl", "state.lsj.lbl")]
        v["backup"] = False
        assert len(step.post(v)) == 1


@pytest.mark.parametrize("step, changes", [
    (core.Jj2lsj(), dict(coupling_files=True, coupling_levels="1: 3-1")),
    (core.Jj2lsj(), dict(coupling_files=True, coupling_levels="x: 1")),
    (core.Jj2lsj(), dict(coupling_files=True, coupling_threshold="nan")),
    (core.Coupling(), dict(shells="0")), (core.Coupling(), dict(threshold="nan")),
    (core.Coupling(), dict(threshold="2")), (core.Coupling(), dict(state="a b")),
    (core.Coupling(), dict(orbitals="invalid")),
    (core.Coupling(), dict(shells="1", use_label=True, scheme="LK3")),
])
def test_invalid_coupling(step, changes):
    with pytest.raises(ValueError):
        step.stdin(dict(step.defaults(), **changes))
