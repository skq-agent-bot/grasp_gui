"""后台运行进程 (grasp_bg)：启动、接上后收到全部输出、停止、目录锁。用 sh 代替 GRASP 程序。"""

import json
import os
import socket
import time

import pytest

import grasp_bg as bg


def sh_job(command):
    return dict(title="sh", prog="sh", args=["-c", command], stdin="", log="", pre=[], post=[], mpi=False)


def run_cfg(workdir):
    return dict(bindir=str(workdir), cwd=str(workdir), np=1, mpirun="mpirun", mpitmp="tmp_mpi", nice=False)


def messages(sock, timeout=30):
    """读取运行进程发来的消息，直到 {"done": …} 或连接关闭。"""
    sock.settimeout(timeout)
    buf, out = b"", []
    while True:
        data = sock.recv(65536)
        if not data:
            return out
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            out.append(json.loads(line))
            if "done" in out[-1]:
                return out


def wait_status(workdir, statuses, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        st = bg.status(str(workdir))
        if st and st["status"] in statuses:
            return st
        time.sleep(0.05)
    pytest.fail(f"status did not become {statuses}: {bg.status(str(workdir))}")


def test_run_and_attach(tmp_path):
    jobs = [sh_job("echo first; sleep 0.5"), sh_job("echo second")]
    proc = bg.launch(str(tmp_path), jobs, run_cfg(tmp_path))
    sock = bg.connect(str(tmp_path), timeout=10)
    assert sock is not None
    msgs = messages(sock)
    sock.close()
    proc.wait(10)
    text = "".join(m.get("s", "") for m in msgs)
    assert text.index("first") < text.index("second")
    assert msgs[-1] == {"done": "ok"}
    assert {"step": 1} in msgs
    st = bg.status(str(tmp_path))
    assert st["status"] == "ok" and st["titles"] == ["sh", "sh"] and not st["remote"]
    assert "second" in bg.log_tail(str(tmp_path))
    assert not os.path.exists(tmp_path / bg.RUN_REQUEST)


def test_instant_run_waits_for_viewer(tmp_path):
    """几毫秒就结束的计算：运行进程等启动它的界面连上再开始，界面收到全部输出 (v2.3.0 中连不上)。"""
    proc = bg.launch(str(tmp_path), [sh_job("echo instant")], run_cfg(tmp_path))
    sock = bg.connect(str(tmp_path), timeout=10)
    assert sock is not None
    msgs = messages(sock)
    sock.close()
    proc.wait(10)
    assert "instant" in "".join(m.get("s", "") for m in msgs) and msgs[-1] == {"done": "ok"}


def test_late_attach_gets_history(tmp_path):
    """计算开始后才接上的界面 (如重新打开目录) 先收到已有的输出，不丢也不重复。"""
    proc = bg.launch(str(tmp_path), [sh_job("echo early; sleep 1; echo late")], run_cfg(tmp_path))
    first = bg.connect(str(tmp_path), timeout=10)
    time.sleep(0.5)
    sock = bg.connect(str(tmp_path), timeout=10)
    text = "".join(m.get("s", "") for m in messages(sock))
    sock.close()
    first.close()
    proc.wait(10)
    assert text.count("early") == 1 and text.count("late") == 1


def test_stop(tmp_path):
    proc = bg.launch(str(tmp_path), [sh_job("echo started; sleep 60"), sh_job("echo never")], run_cfg(tmp_path))
    sock = bg.connect(str(tmp_path), timeout=10)
    wait_status(tmp_path, ("running",))
    time.sleep(0.3)
    sock.sendall(b"stop\n")
    msgs = messages(sock)
    sock.close()
    proc.wait(15)
    assert msgs[-1] == {"done": "stopped"}
    assert "never" not in "".join(m.get("s", "") for m in msgs)


def test_failed_step(tmp_path):
    proc = bg.launch(str(tmp_path), [sh_job("exit 3"), sh_job("echo never")], run_cfg(tmp_path))
    msgs = messages(bg.connect(str(tmp_path), timeout=10))
    proc.wait(15)
    assert msgs[-1] == {"done": "failed"}
    assert bg.status(str(tmp_path))["status"] == "failed"


def test_one_runner_per_directory(tmp_path):
    proc = bg.launch(str(tmp_path), [sh_job("sleep 60")], run_cfg(tmp_path))
    try:
        assert bg.connect(str(tmp_path), timeout=10)
        with pytest.raises(RuntimeError):
            bg.launch(str(tmp_path), [sh_job("true")], run_cfg(tmp_path))
    finally:
        os.kill(proc.pid, 15)            # SIGTERM：按“停止”处理
        proc.wait(15)
    assert bg.status(str(tmp_path))["status"] == "stopped"


def test_killed_runner_is_lost(tmp_path):
    proc = bg.launch(str(tmp_path), [sh_job("sleep 3")], run_cfg(tmp_path))
    sock = bg.connect(str(tmp_path), timeout=10)
    wait_status(tmp_path, ("running",))
    os.killpg(proc.pid, 9)
    proc.wait(15)
    sock.close()
    assert bg.status(str(tmp_path))["status"] == "lost"


def test_remote_state(tmp_path):
    """另一台机器上运行的计算：不能判断进程是否还在，只标记 remote。"""
    bg.write_state(str(tmp_path), dict(pid=1, host=socket.gethostname() + "-other", status="running"))
    st = bg.status(str(tmp_path))
    assert st["remote"] and st["status"] == "running"


def test_stop_before_start(tmp_path):
    """还在等界面连上时被停止 (SIGTERM)：立即结束，一步也不执行。"""
    proc = bg.launch(str(tmp_path), [sh_job("touch ran")], run_cfg(tmp_path))
    wait_status(tmp_path, ("running",))
    t0 = time.monotonic()
    os.kill(proc.pid, 15)
    proc.wait(15)
    assert time.monotonic() - t0 < bg.ATTACH_WAIT / 2
    assert bg.status(str(tmp_path))["status"] == "stopped"
    assert not os.path.exists(tmp_path / "ran")
