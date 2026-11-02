"""GRASPG 零阶划分：输入顺序、CSFG 计数及独立 shell 脚本的运行前检查。"""

import subprocess

import pytest

import grasp_core as core


def write_list(path, blocks):
    text = 'Core subshells:\n\nPeel subshells:\n 1s\nCSF(s):\n'
    text += ' *\n'.join(''.join(' 1s( 2)\n\n ' + sym + '\n' for _ in range(n))
                        for n, sym in blocks)
    path.write_text(text)


@pytest.mark.parametrize('group', ['odd', 'even'])
def test_partition_page(group):
    step = core.RcsfgZeroFirst()
    vals = core.group_defaults(group)[step.key]
    assert step.key in core.package_keys('GRASPG')
    assert step.stdin(vals) == f'{group}2.g\n{group}3.g\n'
    assert step.post(vals) == [('cp', 'rcsfg.out', f'{group}3.g'), ('cp', 'icut', f'{group}3.icut')]
    vals['saveas'] = 'partition.g'
    assert step.post(vals)[-1] == ('cp', f'{group}3.l', 'partition.l')
    vals['saveas'] = ''
    assert step.post(vals) == []


@pytest.mark.parametrize('step', [core.RAngularCsfg(), core.RCiCsfg()])
def test_input_order(step):
    vals = dict(step.defaults(), zf=True, zero='zero.g')
    stdin = step.stdin(vals)
    if step.key == 'rangular_csfg':
        assert stdin == 'n\nn\n@ICCUT zero.g rcsfg.inp csfg\n'
        assert step.stdin(dict(vals, zf=False)) == 'y\n'
    else:
        assert stdin == ('n\noddCI6\nn\nn\ny\nn\n@ICCUT zero.g oddCI6.g csfg\n'
                         'y\ny\n1.d-6\nn\n15\nn\n14\ny\nn\nn\ny\n2\n8\n1\n1\n')
        assert step.stdin(dict(vals, zf=False)) == 'y\noddCI6\n' + stdin.split('csfg\n')[1]


def test_block_ci_has_no_partition_fields():
    step = core.RCiBlockCsfg()
    assert 'zf' not in step.defaults() and 'zero' not in step.defaults()
    assert step.stdin(step.defaults()).startswith('y\n')


@pytest.mark.parametrize('zero,full,valid', [
    ([(1, '0+')], [(1, '0+')], True),
    ([(1, '0+'), (2, '1-')], [(3, '0+'), (2, '1-')], True),
    ([(2, '0+')], [(1, '0+')], False),
    ([(1, '0+')], [(2, '1-')], False),
    ([(1, '0+')], [(2, '0+'), (2, '1-')], False),
    ([(0, '0+')], [(2, '0+')], False),
])
def test_python_and_exported_script(tmp_path, zero, full, valid):
    write_list(tmp_path / 'zero list.g', zero)
    write_list(tmp_path / 'rcsfg.inp', full)
    step = core.RAngularCsfg()
    job = step.job(dict(step.defaults(), zf=True, zero='zero list.g', csf=''))
    # 用 cat 捕获传给 Fortran 的输入；无效时连替身程序也不得启动。
    job.update(prog='sh', args=['-c', 'touch started; cat'], mpi=False)
    result = subprocess.run(['sh', '-c', core.describe(job)], cwd=tmp_path, text=True, capture_output=True)
    if valid:
        expected = 'n\nn\n' + ''.join(f'{n}\n' for n, _ in zero)
        assert core.expand_iccut(job['stdin'], str(tmp_path)) == expected
        assert result.returncode == 0 and result.stdout == expected, result.stderr
    else:
        with pytest.raises(RuntimeError):
            core.expand_iccut(job['stdin'], str(tmp_path))
        assert result.returncode != 0 and 'Invalid CSFG ICCUT' in result.stderr
        assert not (tmp_path / 'started').exists()


def test_missing_list_stops_export(tmp_path):
    step = core.RAngularCsfg()
    job = step.job(dict(step.defaults(), zf=True, csf=''))
    job.update(prog='touch', args=['started'], mpi=False)
    with pytest.raises(RuntimeError):
        core.expand_iccut(job['stdin'], str(tmp_path))
    result = subprocess.run(['sh', '-c', core.describe(job)], cwd=tmp_path, capture_output=True)
    assert result.returncode != 0 and not (tmp_path / 'started').exists()
