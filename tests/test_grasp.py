"""用真实的 GRASP2018 运行算例：用 `grasp_gui script` 生成的脚本从头计算，能级能量与配置中的参考能量一致。
需要 GRASP_BINDIR；默认只跑几秒钟的算例，GRASP_SLOW=1 时跑全部算例 (case1 单进程约 50 分钟)。"""

import os
import subprocess

import pytest

import grasp_config as config
import grasp_core as core
from conftest import DEMOS

pytestmark = pytest.mark.grasp
FAST = ["example1", "example2", "example8", "example9"]
SLOW = ["case4", "example3", "example4", "example5", "case1"]
TOLERANCE = 1e-7          # Hartree：不同编译器 / BLAS 的舍入差别


@pytest.mark.parametrize("name", FAST + SLOW)
def test_demo_reproduces_reference(name, grasp_bindir, tmp_path):
    if name in SLOW and not os.environ.get("GRASP_SLOW"):
        pytest.skip("slow demo: set GRASP_SLOW=1")
    cfg, _ = config.load(os.path.join(DEMOS, name + ".json"))
    wd = tmp_path / name
    config.install(cfg, str(wd))
    script = core.shell_script(config.session(cfg)["pipeline"], grasp_bindir, ".")
    (wd / "run.sh").write_text(script)
    r = subprocess.run(["sh", "run.sh"], cwd=wd, capture_output=True, text=True,
                       env=core.child_env(), timeout=6 * 3600)
    assert r.returncode == 0, r.stderr[-3000:]
    for ref in cfg["reference"]:
        path = wd / ref["file"]
        assert path.exists(), f"{ref['file']} not produced; see {wd}"
        got = config.reference_energies(str(path))
        assert len(got) == len(ref["energies"])
        assert max(abs(a - b) for a, b in zip(got, ref["energies"])) < TOLERANCE, (got, ref["energies"])
