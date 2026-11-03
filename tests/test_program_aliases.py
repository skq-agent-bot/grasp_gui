"""同源程序不同安装名：运行、缺失提示和可独立执行的导出脚本。"""

import os
import subprocess

import pytest

import grasp_core as core
import grasp_config as config


def executable(directory, name):
    p = directory / name
    p.write_text('#!/bin/sh\nprintf "' + name + ':%s\\n" "$1"\n/bin/cat\n')
    p.chmod(0o755)
    return str(p)


def job():
    return dict(prog='jj2lsj', args=['a b'], stdin='input\n', pre=[], post=[],
                log='', title='jj2lsj', mpi=False)


@pytest.mark.parametrize('original', [False, True])
def test_runner_runs_preferred_name(tmp_path, monkeypatch, original):
    monkeypatch.setenv('PATH', str(tmp_path))
    executable(tmp_path, 'jj2lsj_2025')
    if original:
        executable(tmp_path, 'jj2lsj')
    output = []
    runner = core.Runner(lambda text, tag: output.append(text))
    cfg = dict(bindir=str(tmp_path), cwd=str(tmp_path), np=1, nice=False)
    assert runner.exec_cmd(['jj2lsj', 'a b'], cfg, 'input\n') == 0
    assert ''.join(output).endswith(('jj2lsj' if original else 'jj2lsj_2025') + ':a b\ninput\n')


def test_missing_and_unrelated_names(tmp_path, monkeypatch):
    monkeypatch.setenv('PATH', str(tmp_path))
    executable(tmp_path, 'jj2lsj_2024')
    runner = core.Runner(lambda *args: None)
    with pytest.raises(FileNotFoundError, match='找不到程序 jj2lsj'):
        runner.resolve(str(tmp_path), 'jj2lsj')
    executable(tmp_path, 'jj2lsj_2025')
    with pytest.raises(FileNotFoundError, match='jj2lsj_csfg'):
        runner.resolve(str(tmp_path), 'jj2lsj_csfg')
    (tmp_path / 'jj2lsj_2025').chmod(0o644)
    with pytest.raises(FileNotFoundError):
        runner.resolve(str(tmp_path), 'jj2lsj')


@pytest.mark.parametrize('kind', ['shell', 'slurm', 'preview'])
@pytest.mark.parametrize('original', [False, True])
def test_exports_select_at_runtime(tmp_path, kind, original):
    bindir = tmp_path / 'bin'; bindir.mkdir()
    # 先导出再安装程序，确认选择发生在脚本运行时。
    if kind == 'shell':
        script = core.shell_script([job(), job()], str(bindir), str(tmp_path))
    elif kind == 'slurm':
        script = core.slurm_script([job(), job()], dict(bindir=str(bindir), mpirun=''))
    else:
        script = core.describe(job())
    assert script.count('command -v jj2lsj') == 1
    executable(bindir, 'jj2lsj_2025')
    for name in ('mkdir', 'date'):
        (bindir / name).symlink_to('/bin/' + name)
    if original:
        executable(bindir, 'jj2lsj')
    env = dict(os.environ, PATH=str(bindir), SLURM_SUBMIT_DIR=str(tmp_path))
    result = subprocess.run(['/bin/sh', '-c', script], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    expected = ('jj2lsj' if original else 'jj2lsj_2025') + ':a b\ninput\n'
    assert result.stdout.count(expected) == (1 if kind == 'preview' else 2)


def test_missing_programs_and_path_priority(tmp_path, monkeypatch):
    bindir=tmp_path/'bin'; bindir.mkdir()
    pathdir=tmp_path/'path'; pathdir.mkdir()
    monkeypatch.setenv('PATH', str(pathdir))
    cfg=dict(format=config.FORMAT,version=2,jobs=[dict(step='jj2lsj',vals=config.STEPS['jj2lsj'].defaults())])
    assert config.missing_programs(cfg,str(bindir)) == ['jj2lsj']
    executable(bindir,'jj2lsj_2025')
    assert config.missing_programs(cfg,str(bindir)) == []
    original=executable(pathdir,'jj2lsj')
    assert core.Runner(lambda *a:None).resolve(str(bindir),'jj2lsj') == original


def test_no_fallback_for_unrelated_jobs():
    j=job(); j['prog']='jj2lsj_csfg'
    assert core.program_fallbacks([j]) == []
    assert 'jj2lsj_2025' not in core.describe(j)
    j['post']=[('run',['jj2lsj','state'])]
    assert len(core.program_fallbacks([j])) == 1
