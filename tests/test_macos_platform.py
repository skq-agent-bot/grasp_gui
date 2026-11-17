"""在 Linux CI 也能核对桌面平台分支；实际 Cocoa 和后台套接字由 macOS CI 验证。"""

import os
from pathlib import Path
import shutil

import pytest

import grasp_core as core


def test_native_mac_source_leaves_linux_environment_prefixes_alone(monkeypatch):
    monkeypatch.setattr(core.sys, "platform", "darwin")
    monkeypatch.setattr(core.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/current/lib")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/saved/lib")
    monkeypatch.setenv("DYLD_LIBRARY_PATH", "/native/lib")
    assert core.child_env()["LD_LIBRARY_PATH"] == "/current/lib"
    assert core.child_env()["DYLD_LIBRARY_PATH"] == "/native/lib"


def test_linux_frozen_launcher_preserves_original_library_prefixes(monkeypatch):
    monkeypatch.setattr(core.sys, "platform", "linux")
    monkeypatch.setattr(core.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/frozen/lib")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/original/lib")
    monkeypatch.setenv("FONTCONFIG_FILE", "/generated/fonts.conf")
    monkeypatch.setenv("GRASP_GUI_FONTCONFIG", "/generated/fonts.conf")
    env = core.child_env()
    assert env["LD_LIBRARY_PATH"] == "/original/lib"
    assert "FONTCONFIG_FILE" not in env


@pytest.mark.gui
def test_native_mac_skips_wsl_and_bundled_font_config(qapp, tmp_path, monkeypatch):
    import grasp_gui as gui

    monkeypatch.setattr(gui.sys, "platform", "darwin")
    monkeypatch.setattr(gui.sys, "frozen", True, raising=False)
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.delenv("FONTCONFIG_FILE", raising=False)
    monkeypatch.delenv("FONTCONFIG_PATH", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    wayland = tmp_path / "wayland-test"
    wayland.touch()
    monkeypatch.setenv("WAYLAND_DISPLAY", str(wayland))
    gui.fix_wsl_display()
    gui.fix_fontconfig()
    gui.load_fonts()
    assert "QT_QPA_PLATFORM" not in os.environ and "FONTCONFIG_FILE" not in os.environ
    assert not (tmp_path / "grasp_gui").exists()


@pytest.mark.gui
@pytest.mark.parametrize("language", ["zh", "en"])
def test_desktop_opens_example_wavefunctions_and_levels(qapp, tmp_path, monkeypatch, language):
    import grasp_config as config
    import grasp_gui as gui
    from test_gui import spin
    from test_mcp import wavefunction
    from test_skipped_blocks import DATA

    monkeypatch.setattr(core, "CONFIG_FILE", str(tmp_path / "settings.json"))
    core.set_lang(language)
    example = Path(__file__).resolve().parents[1] / "demos/example1.json"
    cfg, _ = config.load(example)
    directory = tmp_path / "calculation"
    config.install(cfg, directory)
    for name in ("skip1.m", "skip1.c"):
        shutil.copy2(DATA / name, directory / name)
    wavefunction(directory / "example.w")
    window = gui.MainWindow(str(directory), "calc")
    try:
        window.show()
        assert len(window.calc.pipeline) == len(cfg["jobs"])
        window.show_tab("wfn")
        assert window.panel("wfn").orbs.item(0).text() == "1s"
        window.show_tab("levels")
        panel = window.panel("levels")
        spin(qapp, lambda: not panel.loading)
        assert panel.level_table.rowCount() == 2
        window.show_tab("calc")
        assert window.current_tab() == "calc"
    finally:
        assert window.close()
