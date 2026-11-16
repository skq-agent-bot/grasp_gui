"""审核中发现的独立回归：保持既有输入和协议格式。"""

import shlex
import subprocess

import pytest

import grasp_core as core
import grasp_config as config
import grasp_remote as remote
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
