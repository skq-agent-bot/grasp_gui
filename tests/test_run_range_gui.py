"""连续多选的按钮、旧服务器能力回退，以及分段运行的结果提示。"""

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.gui
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QEvent, QObject, Signal  # noqa: E402

import calc_panel as panel  # noqa: E402
import grasp_bg as bg  # noqa: E402
import grasp_config as config  # noqa: E402
import grasp_core as core  # noqa: E402
from remote_panel import RemoteCalculation  # noqa: E402
from test_gui import no_dialogs, window  # noqa: E402, F401
from test_summary import job  # noqa: E402


def select(widget, rows, current=None):
    widget.setCurrentRow(rows[0] if current is None else current)
    widget.clearSelection()
    for row in rows:
        widget.item(row).setSelected(True)


def test_local_run_buttons_and_current_row_actions(qapp, tmp_path, monkeypatch, no_dialogs):
    w = window(tmp_path)
    calc = w.calc
    try:
        calc.pipeline = [job("rnucleus", z=str(i)) for i in range(1, 6)]
        calc.refresh_list()
        calls = []
        monkeypatch.setattr(calc, "start", lambda jobs, **kw: calls.append((jobs, kw)))
        select(calc.plist, [1, 2], current=2)
        for button, a, b in ((calc.run_to, 0, 3), (calc.run_selected, 1, 3), (calc.run_from, 1, 5)):
            button.click()
            assert calls[-1] == (calc.pipeline[a:b], dict(span=(a + 1, b, 5)))
        calc.run_all.click()
        assert calls[-1][0] == calc.pipeline
        assert calc.selected() == 2
        select(calc.plist, [1, 3])
        assert calc.run_all.isEnabled()
        for button in (calc.run_to, calc.run_selected, calc.run_from):
            assert not button.isEnabled() and "连续" in button.toolTip()
        select(calc.plist, [2])
        calc.run_from.click()
        assert calls[-1][0] == calc.pipeline[2:]
        select(calc.plist, [1, 2], current=2)
        before = list(calc.pipeline)
        calc.remove_job()
        assert calc.pipeline == before[:2] + before[3:]
    finally:
        assert w.close()


def test_local_preflight_only_checks_the_requested_slice(qapp, tmp_path, monkeypatch, no_dialogs):
    w = window(tmp_path)
    calls = []
    try:
        w.calc.pipeline = [job("rangular", csf="missing.c"), job("rnucleus"),
                           job("jj2lsj", state="valid")]
        w.calc.pipeline[2]["vals"]["state"] = "x" * 60
        w.calc.refresh_list()
        select(w.calc.plist, [1])
        def launch(directory, jobs, cfg):
            calls.append(jobs)
            raise RuntimeError("test launch reached")
        monkeypatch.setattr(bg, "launch", launch)
        w.calc.run_selected.click()
        assert [j["step"] for j in calls[0]] == ["rnucleus"]
        assert not any(kind == "question" for kind, _ in no_dialogs)
    finally:
        assert w.close()


@pytest.mark.parametrize("language", ["zh", "en"])
def test_partial_completion_and_reopened_caption(qapp, tmp_path, monkeypatch, no_dialogs, language):
    core.set_lang(language)
    jobs = [job("rnucleus"), job("rcsfgenerate"), job("rangular"), job("rwfnestimate")]
    config.install(config.export(jobs, dict(title="range")), str(tmp_path / "calc"))
    w = window(tmp_path / "calc")
    try:
        calc = w.calc
        titles = [j["title"] for j in jobs[1:3]]
        state = dict(status="ok", step=1, titles=titles, end="2026-01-01", seen=True)
        monkeypatch.setattr(bg, "status", lambda *a: dict(state))
        monkeypatch.setattr(bg, "mark_seen", lambda *a: None)
        calc.busy, calc.titles, calc.run_span = True, titles, (2, 3, 4)
        calc.finished("ok")
        calc.poll()
        expected = core.T("已运行第 {a}–{b} 步 (流程共 {n} 步)", a=2, b=3, n=4)
        assert expected in calc.last_run and expected in calc.out.toPlainText()
        calc.last_run = ""
        calc.show_background(calc.cur_workdir)
        assert expected in calc.last_run
        assert expected not in panel.run_summary(dict(state, status="failed"), titles, (2, 3, 4))
    finally:
        assert w.close()


class Source(QObject):
    push = Signal(object)
    client = SimpleNamespace(host="cluster")

    def __init__(self, modern=True, slurm=False):
        super().__init__()
        self.server_type = "slurm" if slurm else "workstation"
        self.server = dict(server_types=["workstation", "slurm"],
                           capabilities=["run_range_v1"] if modern else [])
        self.jobs = [job("rnucleus"), job("rcsfgenerate"), job("rangular"), job("rwfnestimate")]
        self.calls = []

    def submit(self, method, args, callback):
        self.calls.append((method, args))
        if method == "pipeline":
            callback(dict(jobs=self.jobs, revision="rev"), None)
        elif method == "watch":
            callback(dict(text="", state=None), None)
        elif method == "run_plan":
            callback(dict(revision="rev", custom_commands=[], logout_kills=False, lingering=False,
                          slurm=dict(core.SLURM_DEFAULTS)), None)


@pytest.mark.parametrize("modern", [True, False])
def test_remote_range_and_old_server_request_shapes(qapp, modern):
    source = Source(modern)
    calc = RemoteCalculation(source, "/server/calc")
    source.setParent(calc)
    try:
        select(calc.steps, [1, 2], current=2)
        assert calc.run_to.isEnabled() is modern and calc.run_range.isEnabled() is modern
        if modern:
            for button, start, end in ((calc.run_to, 1, 3), (calc.run_range, 2, 3)):
                button.click()
                assert source.calls[-2] == ("run_plan", dict(directory="/server/calc", start=start, end=end))
                assert source.calls[-1][1]["start"] == start and source.calls[-1][1]["end"] == end
        else:
            assert "更新" in calc.run_to.toolTip()
        calc.run_selected.click()
        assert source.calls[-1][1]["start"] == 2
        calc.run_button.click()
        assert source.calls[-1][1]["start"] == 1
        if not modern:
            for method, args in source.calls:
                assert "end" not in args
                if method == "run_plan":
                    assert "start" not in args
        select(calc.steps, [0, 2])
        assert calc.run_button.isEnabled() and not calc.run_selected.isEnabled()
        calc.show_state(dict(status="running", titles=["nucleus"], step=0))
        assert not calc.run_button.isEnabled() and not calc.run_to.isEnabled()
    finally:
        calc.close()
        calc.deleteLater()
        qapp.sendPostedEvents(None, QEvent.DeferredDelete)


def test_slurm_resource_dialog_and_final_confirmation_show_range(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(core, "CONFIG_FILE", str(tmp_path / "settings.json"))
    source = Source(slurm=True)
    calc = RemoteCalculation(source, "/server/calc")
    source.setParent(calc)
    try:
        select(calc.steps, [1, 2])
        expected = core.T("第 {a}–{b} 步 (流程共 {n} 步)", a=2, b=3, n=4)
        def accept(dialog):
            assert expected in [label.text() for label in dialog.findChildren(QtWidgets.QLabel)]
            return QtWidgets.QDialog.Accepted
        questions = []
        def confirm(*args):
            questions.append(args[2])
            assert args[-1] == QtWidgets.QMessageBox.No
            return QtWidgets.QMessageBox.Yes
        monkeypatch.setattr(panel.SlurmDialog, "exec", accept)
        monkeypatch.setattr(QtWidgets.QMessageBox, "question", confirm)
        calc.run_range.click()
        assert expected in questions[0]
        method, args = source.calls[-1]
        assert method == "run" and args["server_type"] == "slurm" and args["start"] == 2 and args["end"] == 3
        assert not calc.run_range.isEnabled() and not calc.run_button.isEnabled()
    finally:
        calc.close()
        calc.deleteLater()
        qapp.sendPostedEvents(None, QEvent.DeferredDelete)
