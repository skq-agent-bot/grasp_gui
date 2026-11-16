"""审核中发现的独立回归：保持既有输入和协议格式。"""

import shlex
import subprocess

import pytest

import grasp_core as core
import grasp_config as config
import grasp_remote as remote
from test_large_files import make_files
from test_run_range import launches  # noqa: F401


@pytest.mark.parametrize("name", ["mpi", "MPI space's $HOME"])
def test_absolute_mpi_temporary_directory_is_not_prefixed_with_workdir(tmp_path, name):
    workdir = tmp_path / "work"
    workdir.mkdir()
    temporary = tmp_path / name
    script = core.shell_script([], "/opt/grasp/bin", str(workdir), "mpirun -np 2", str(temporary))
    result = subprocess.run(["sh", "-c", script + '\nprintf "%s" "$MPI_TMP"\n'],
                            capture_output=True, text=True, env=core.child_env(), timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(temporary)
    assert temporary.is_dir()


@pytest.mark.parametrize("temporary", ["tmp_mpi", "relative mpi", ""])
def test_relative_mpi_script_remains_byte_identical(temporary):
    expected = ("#!/bin/sh\nset -x\n\nexport PATH=/opt/grasp/bin:$PATH\ncd .\n\n"
                'export MPI_TMP="$PWD"/' + shlex.quote(temporary or "tmp_mpi") + '\nmkdir -p "$MPI_TMP"\n'
                "# hwloc's GL plugin makes mpirun hang under WSLg\n"
                'export HWLOC_COMPONENTS="${HWLOC_COMPONENTS:--gl}"\n')
    assert core.shell_script([], "/opt/grasp/bin", ".", "mpirun -np 2", temporary) == expected


@pytest.mark.parametrize("directory", ["calc", "work/../calc", "~/calc"])
def test_remote_workstation_run_resolves_paths_consistently(tmp_path, monkeypatch, launches, directory):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "work").mkdir()
    root = tmp_path / "calc"
    config.install(dict(format=config.FORMAT, version=config.VERSION,
                        jobs=[dict(step="rnucleus", vals=config.STEPS["rnucleus"].defaults())]), str(root))
    operation = remote.Operations()
    revision = operation.record(directory)[2]
    result = operation.run(directory, revision)
    assert result["started"] and result["directory"] == str(root)
    assert launches[0][1]["cwd"] == str(root)


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize("block,index", [(2, 1), (1, 2)])
def test_missing_composition_has_a_clear_error(tmp_path, language, block, index):
    core.set_lang(language)
    make_files(tmp_path, ncf=2, nev=1)
    message = "块或能级不存在" if language == "zh" else "Block or level does not exist"
    with pytest.raises(ValueError, match=message):
        remote.Operations().composition(str(tmp_path), "state.cm", block, index)


def test_remote_composition_error_does_not_break_later_requests(tmp_path):
    from test_remote import Peer
    make_files(tmp_path, ncf=2, nev=1)
    peer = Peer()
    try:
        result = peer.call("composition", directory=str(tmp_path), file="state.cm", block=2, index=1)
        assert result.get("error") and "块或能级不存在" in result["error"]
        result = peer.call("composition", directory=str(tmp_path), file="state.cm", block=1, index=1)
        assert result["result"]["components"]
    finally:
        peer.close()
