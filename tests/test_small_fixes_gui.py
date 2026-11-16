"""审核修复的本机提示与不丢失其他文件的显示行为。"""

import pytest

pytestmark = pytest.mark.gui
pytest.importorskip("PySide6.QtWidgets")

import grasp_config as config  # noqa: E402
import grasp_core as core  # noqa: E402
import grasp_workdir as work  # noqa: E402
from test_gui import no_dialogs, window  # noqa: E402, F401
from test_summary import job  # noqa: E402


@pytest.mark.parametrize("language", ["zh", "en"])
def test_clear_refused_before_deletion_only_reports_the_reason(qapp, tmp_path, monkeypatch, no_dialogs, language):
    monkeypatch.setattr(core, "CONFIG_FILE", str(tmp_path / "preferences.json"))
    core.set_lang(language)
    root = tmp_path / "calc"
    config.install(config.export([job("rnucleus")], {}), str(root))
    (root / "result.cm").write_bytes(b"untouched result")
    w = window(root)
    try:
        original = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
        monkeypatch.setattr(work.bg, "status", lambda *args: dict(status="running"))
        w.calc.clear_workdir()
        assert len(no_dialogs) == 1
        assert no_dialogs[0][1][1] == core.T("已有任务在运行，请等待或先停止。")
        assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == original
    finally:
        assert w.close()
