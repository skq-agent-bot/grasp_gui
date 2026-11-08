"""捆绑包、shell 路径、安装校验及界面显式确认。"""

import io
import os
from pathlib import Path
import shlex
import tarfile

import pytest

import grasp_core as core
import grasp_install as install


@pytest.fixture
def package(tmp_path):
    import hashlib
    root = tmp_path / "bundle"
    root.mkdir()
    version = "GRASP GUI " + core.VERSION + " (server; remote protocol 1)"
    script = '#!/bin/sh\ncase "$1" in --version) echo ' + shlex.quote(version) + (
        ';; remote) echo "GRASP_GUI_REMOTE 1";; esac\n')
    archive = root / install.ARCHIVE
    with tarfile.open(archive, "w:gz") as stream:
        for name, value, mode in (("grasp_gui-server", script, 0o755), ("SERVER_VERSION", version, 0o644)):
            item = tarfile.TarInfo("grasp_gui-server/" + name)
            data = value.encode()
            item.size, item.mode = len(data), mode
            stream.addfile(item, io.BytesIO(data))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (root / (install.ARCHIVE + ".sha256")).write_text(digest + "  " + install.ARCHIVE + "\n")
    return install.bundle(root)


class LocalClient:
    def argv(self):
        return ["sh", "-c", "unused"]

    def environment(self):
        return os.environ.copy()


def test_bundle_checksum_and_unsafe_members(package):
    path = Path(package["path"])
    assert package["expanded"] > 0 and package["version"] == core.VERSION
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="校验"):
        install.bundle(path.parent)


def test_bundle_refuses_links_and_traversal(tmp_path):
    import hashlib
    for name, kind in (("../outside", tarfile.REGTYPE), ("grasp_gui-server/link", tarfile.SYMTYPE)):
        archive = tmp_path / install.ARCHIVE
        with tarfile.open(archive, "w:gz") as stream:
            item = tarfile.TarInfo(name)
            item.type, item.linkname = kind, "/outside"
            stream.addfile(item)
        (tmp_path / (install.ARCHIVE + ".sha256")).write_text(hashlib.sha256(archive.read_bytes()).hexdigest())
        with pytest.raises(ValueError, match="不安全"):
            install.bundle(tmp_path)


def test_probe_parsing_and_requirements():
    raw = b"\0".join([b"x86_64", b"glibc 2.17", b"100000", b"/home/user/install", b"/home/user/bin/grasp_gui", b""])
    assert install.probe_result(raw, 1024)["free"] == 100000 * 1024
    for changed in (raw.replace(b"x86_64", b"aarch64"), raw.replace(b"2.17", b"2.16"), b"invalid"):
        with pytest.raises(ValueError):
            install.probe_result(changed, 0)
    with pytest.raises(ValueError, match="空间不足"):
        install.probe_result(raw, 200000 * 1024)


def test_special_paths_are_arguments():
    root = "/home/space 'quote/$(touch forbidden)"
    parts = shlex.split(install.command(install.PROBE, root))
    assert parts == ["sh", "-c", install.PROBE, "sh", root]
    for invalid in ("relative", "/root\nmore", "\0"):
        with pytest.raises(ValueError):
            install.command(install.PROBE, invalid)


def test_install_checksum_failure_never_switches_and_cleans(package, tmp_path):
    peer = install.Installer(LocalClient())
    root = str(tmp_path / "install 'quoted $directory")
    checked = peer.probe(package, root)
    link = Path(checked["link"])
    if link.is_symlink():
        link.unlink()
    changed = dict(package, sha256="0" * 64)
    with pytest.raises(RuntimeError, match="sha256 mismatch"):
        peer.install(changed, root)
    assert not link.exists() and not list(Path(root).glob(".install.*"))
    progress = []
    path = peer.install(package, root, lambda n, total: progress.append((n, total)))
    assert Path(path).is_symlink() and progress[-1] == (package["size"], package["size"])
    assert Path(path).resolve().parent.name == core.VERSION
    marker = Path(root) / "unmanaged" / "result"
    marker.parent.mkdir()
    marker.write_text("keep")
    peer.remove(root)
    assert not link.is_symlink() and marker.read_text() == "keep"


@pytest.mark.gui
def test_install_dialog_requires_check_and_confirmation(qapp, monkeypatch, package):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QMessageBox
    from install_panel import InstallDialog
    monkeypatch.setattr(install, "bundle", lambda: package)
    client = SimpleNamespace(host="test.example")
    dialog = InstallDialog(client)
    try:
        assert not dialog.action.isEnabled()
        dialog.checked_server(dict(root="/remote/root", link="/remote/bin/grasp_gui", versions=[],
                                   architecture="x86_64", glibc="glibc 2.17", free=1 << 30))
        assert dialog.action.isEnabled() and "/remote/root" in dialog.details.toPlainText()
        seen = []
        monkeypatch.setattr(dialog, "start", lambda *args: seen.append(args))
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No)
        dialog.apply()
        assert seen == []
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
        dialog.apply()
        assert len(seen) == 1
        dialog.root.setText("/changed")
        assert not dialog.action.isEnabled()
    finally:
        dialog.reject()


@pytest.mark.gui
def test_missing_bundle_and_cancel_do_not_install(qapp, monkeypatch):
    from types import SimpleNamespace
    from install_panel import InstallDialog
    def missing():
        raise ValueError("本构建不含服务器版")
    monkeypatch.setattr(install, "bundle", missing)
    dialog = InstallDialog(SimpleNamespace(host="host"))
    assert not dialog.action.isEnabled() and not dialog.check_button.isEnabled()
    assert "不含服务器版" in dialog.details.toPlainText()
    dialog.busy = True
    dialog.reject()
    assert dialog.installer.cancelled.is_set()


def test_bundle_accepts_selected_archive_path(package):
    assert install.bundle(package["path"])["sha256"] == package["sha256"]


def test_same_version_keeps_previous_owned_version(package, tmp_path):
    root = tmp_path / "versions"
    old = root / "2.7.9"
    old.mkdir(parents=True)
    (old / ".grasp-gui-version").write_text("2.7.9\nold hash\n")
    (old / "grasp_gui-server").write_text("previous version")
    link = Path.home() / ".local/bin/grasp_gui"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(old / "grasp_gui-server")
    peer = install.Installer(LocalClient())
    try:
        peer.install(package, str(root))
        peer.install(package, str(root))
        assert old.is_dir() and Path(link).resolve().parent.name == core.VERSION
        unused = root / "2.7.8"
        unused.mkdir()
        (unused / ".grasp-gui-version").write_text("2.7.8\nold hash\n")
        peer.install(package, str(root))
        assert not unused.exists() and old.is_dir()
    finally:
        peer.remove(str(root))


def test_unmanaged_executable_is_never_replaced(package, tmp_path):
    link = Path.home() / ".local/bin/grasp_gui"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.write_text("administrator installation")
    peer = install.Installer(LocalClient())
    try:
        with pytest.raises(RuntimeError, match="unmanaged executable"):
            peer.install(package, str(tmp_path / "install"))
        assert link.read_text() == "administrator installation"
    finally:
        link.unlink()
