"""连接检查的程序目录、旧版本兼容性和重新检查。"""

from concurrent.futures import Future
import os
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

import pytest

import grasp_config as config
import grasp_core as core
import grasp_remote as remote
from test_remote_edit_ssh import call, energies, peer, target, wait_done  # noqa: F401
from test_remote_run_settings import install, job


def install_program(directory, name):
    directory.mkdir(exist_ok=True)
    program = directory / name
    program.write_text("#!/bin/sh\n")
    program.chmod(0o700)


@pytest.mark.parametrize("source", ["env", "saved", "path", None])
def test_hello_reports_same_directory_as_run_plan(tmp_path, monkeypatch, source):
    env_bin, saved_bin, path_bin = [tmp_path / name for name in ("env", "saved", "path")]
    monkeypatch.setattr(core, "CONFIG_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(core, "REPO_DIR", str(tmp_path))
    monkeypatch.delenv("GRASP_BINDIR", raising=False)
    monkeypatch.setenv("PATH", str(path_bin))
    if source:
        install_program(path_bin, "rmcdhf")
    if source in ("env", "saved"):
        install_program(saved_bin, "rmcdhf")
        core.save_config(bindir=str(saved_bin))
    if source == "env":
        install_program(env_bin, "rmcdhf")
        install_program(env_bin, "rci_mpi")
        monkeypatch.setenv("GRASP_BINDIR", str(env_bin))
    calc = tmp_path / "calc"
    install(calc, [job("rnucleus")])
    operations = remote.Operations()
    hello = operations.hello(remote.PROTOCOL)
    report = hello["grasp_check"]
    assert remote.GRASP_CHECK in hello["capabilities"]
    assert report["source"] == source
    assert report["directory"] == operations.run_plan(str(calc))["run_settings"]["bindir"]
    assert report["bindir_env"] == (str(env_bin) if source == "env" else "")
    assert report["path_env"] == str(path_bin)
    assert len(report["programs"]) == 12
    assert report["programs"]["rmcdhf"] is bool(source)
    assert report["programs"]["rci_mpi"] is (source == "env")


@pytest.mark.gui
def test_grasp_check_refreshes_from_settings_and_reconnects(qapp, tmp_path, monkeypatch):
    from remote_panel import Source, grasp_check_text

    monkeypatch.setattr(core, "CONFIG_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(core, "LANG", "en")
    requests = []

    def request(method, args, cached=False):
        future = Future()
        future.request_id = len(requests) + 1
        requests.append((method, args, future))
        return future

    client = SimpleNamespace(host="fixture", events=Queue(), request=request, close=lambda **kw: None)
    source = Source(client)
    report = dict(directory="", source=None, programs=dict(rmcdhf=False, rci_mpi=False), path_programs=[],
                  bindir_env="", path_env="/no-grasp")
    try:
        client.events.put(dict(event="connected", capabilities=[]))
        source.poll()
        assert "Update it" in grasp_check_text(source, "workstation")[0]
        client.events.put(dict(event="connected", capabilities=[remote.GRASP_CHECK], grasp_check=report))
        source.poll()
        text, settings = grasp_check_text(source, "slurm")
        assert settings and "PATH=/no-grasp" in text and "login node" in text
        assert "Non-interactive SSH" in text
        core.save_config(remote_hosts={"fixture": dict(run=dict(bindir="~/grasp/bin"))})
        source.refresh_grasp_check()
        method, args, future = requests[-1]
        assert (method, args) == ("list_dir", {"directory": "~/grasp/bin"})
        future.set_result(dict(directory="/home/research/grasp/bin",
                               files=[dict(name="rmcdhf", directory=False)]))
        source.poll()
        text, settings = grasp_check_text(source, "workstation")
        assert not settings and "/home/research/grasp/bin" in text and "settings saved" in text
        assert "Program files not found: rci_mpi" in text
        env = dict(report, source="env", directory="/from-env", programs=dict(rmcdhf=True))
        client.events.put(dict(event="connected", capabilities=[remote.GRASP_CHECK], grasp_check=env))
        source.poll()
        assert "/from-env (from GRASP_BINDIR)" in grasp_check_text(source, "workstation")[0]
        assert len(requests) == 1
    finally:
        source.close()


@pytest.mark.grasp
@pytest.mark.gui
@pytest.mark.skipif(os.environ.get("GRASP_REMOTE_EDIT_TEST") != "1" or not os.environ.get("GRASP_SSH_TEST_HOST"),
                    reason="dedicated GRASP check SSH fixture not configured")
def test_real_ssh_shows_default_grasp_and_runs_example1(peer, qapp, tmp_path, monkeypatch,
                                                       accept_server_run_dialog):
    from remote_panel import Source
    from test_gui import spin, window

    monkeypatch.setattr(core, "CONFIG_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(core, "LANG", "en")
    cfg, _ = config.load(Path(__file__).resolve().parents[1] / "demos/example1.json")
    directory = target()
    call(peer, "create_workdir", directory, configuration=cfg)
    plan = call(peer, "run_plan", directory)
    source = Source(peer)
    main = window(tmp_path)
    try:
        workspace = main.open_remote_workspace(source, directory)
        spin(qapp, lambda: source.grasp_check is not None and workspace.calc.run_button.isEnabled())
        assert source.grasp_check["source"] == "env"
        assert source.grasp_check["directory"] == plan["run_settings"]["bindir"]
        assert "from GRASP_BINDIR" in workspace.grasp_status.text()
        assert "remote_hosts" not in core.load_config()
        workspace.calc.run_button.click()
        spin(qapp, lambda: (workspace.calc.runtime_state or {}).get("status") == "ok", timeout=90)
        wait_done(peer, directory)
        assert accept_server_run_dialog
        for reference in cfg["reference"]:
            assert energies(peer, directory, reference["file"]) == pytest.approx(reference["energies"], abs=1e-7)
    finally:
        main.close()
