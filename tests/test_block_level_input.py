"""核对跳块回答、已有 CSF 的行数校验和旧记录输入重建。"""

from pathlib import Path
import shutil

import pytest

import grasp_config as config
import grasp_core as core
import grasp_service as service
import grasp_summary as summary

CSF = Path(__file__).parent / "data/skipped_blocks/skip1.c"


def job(key, **values):
    step = config.STEPS[key]
    return step.job(dict(step.defaults(), **values))


@pytest.mark.parametrize("text,expected", [
    ("\n1\n \n2\n\n", ["", "1", "", "2"]),
    ("\n-\n1\n-\n\n", ["", "", "1", ""]),
    (" 1\r\n2\r\n", ["1", "2"]),
])
def test_block_level_lines(text, expected):
    assert core.block_level_lines(text) == expected
    assert core.count_levels(["", "  ", " - ", "1,3-4"]) == 3


@pytest.mark.parametrize("level", ["1", ",1,", "1- 1", "1-,1"])
def test_stdin_keeps_skips_and_counts_only_selected_levels_for_weights(level):
    one = job("rmcdhf", levels=f"\n{level}\n-", weights="9", uweights="2")["stdin"].splitlines()
    assert one == ["y", "", level, "", "*", "*", "100"]
    two = job("rmcdhf", levels="1\n-\n1", weights="9", uweights="1,2")["stdin"].splitlines()
    assert two == ["y", "1", "", "1", "9", "1,2", "*", "*", "100"]
    ci = job("rci", levels="1\n\n-\n")
    assert ci["stdin"].endswith("\n1\n\n\n")
    assert ci["stdin"] + "EOF" in core.describe(ci)


@pytest.mark.parametrize("step", ["rmcdhf", "rci"])
@pytest.mark.parametrize("levels", ["\n-\n-", "\n, ,\n-"])
def test_rejects_all_skipped(step, levels):
    with pytest.raises(ValueError, match="至少有一个块"):
        job(step, levels=levels)


@pytest.mark.parametrize("levels,why", [("1\n1", "缺少块 3:3/2-"), ("1\n1\n1\n1", "多填了 1 行")])
def test_existing_csf_reports_order_and_missing_or_extra_answers(tmp_path, levels, why):
    shutil.copyfile(CSF, tmp_path / "rcsf.inp")
    checked = summary.check_files(tmp_path, [job("rmcdhf", levels=levels)])
    problem, = checked["invalid"]
    assert problem["kind"] == "block_levels"
    assert "1:1/2+, 2:1/2-, 3:3/2-" in problem["reason"] and why in problem["reason"]


def test_preflight_reads_copy_source_and_defers_file_from_earlier_job(tmp_path):
    shutil.copyfile(CSF, tmp_path / "source.c")
    (tmp_path / "result.c").write_text("stale")
    step = job("rci", state="result", copyfrom="source", levels="1\n-\n1")
    assert not summary.check_files(tmp_path, [step])["invalid"]
    invalid = job("rci", state="result", copyfrom="source", levels="1")
    assert "source.c" in summary.check_files(tmp_path, [invalid])["invalid"][0]["reason"]
    assert not summary.check_files(tmp_path, [job("rcsfgenerate", saveas="source.c"), invalid])["invalid"]


def test_export_updates_legacy_stdin_and_rejects_real_mismatch(tmp_path, monkeypatch, capsys):
    raw = job("rmcdhf", levels="\n1\n-")
    previous = dict(raw, stdin=job("rmcdhf", levels="1")["stdin"])
    assert summary.checked_script_jobs(tmp_path, [previous])[0]["stdin"] == raw["stdin"]
    rendered = core.describe(previous)
    assert raw["stdin"] + "EOF" in rendered
    assert previous["stdin"] + "EOF" not in rendered
    assert previous["stdin"] != raw["stdin"]
    shutil.copyfile(CSF, tmp_path / "rcsf.inp")
    bad = job("rmcdhf", levels="1\n1")
    cfg = config.export([bad], dict(title="mismatch"))
    path = tmp_path / "workflow.json"
    path.write_text(config.dumps(cfg))
    monkeypatch.chdir(tmp_path)
    assert config.cli(["script", str(path)]) == 1
    assert "3:3/2-" in capsys.readouterr().err
    with pytest.raises(ValueError, match="3:3/2-"):
        summary.checked_script_jobs(tmp_path, [bad])
    assert core.save_session(str(tmp_path), dict(pipeline=[bad]))
    with pytest.raises(ValueError, match="3:3/2-"):
        service.Service(str(tmp_path)).export_script(".", slurm={})
