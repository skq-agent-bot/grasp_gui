"""Slurm 提交记录、限频状态查询与取消；不依赖 Qt，不在登录节点执行计算。"""

import datetime
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import threading
import time
import uuid

import grasp_core as core
import grasp_session as sessions
from grasp_core import T

RECORD = ".grasp_gui_slurm.json"
TERMINAL = {"COMPLETED", "CANCELLED", "FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "BOOT_FAIL",
            "DEADLINE", "PREEMPTED", "REVOKED"}
_cache = {}
_lock = threading.Lock()


class CommandFailed(ValueError):
    """命令明确返回失败；与超时、丢失回答导致的不确定结果分开。"""


def identity(state):
    return [(state or {}).get(k) for k in ("host", "pid", "start")]


def read(workdir):
    path = Path(workdir) / RECORD
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ValueError(T("Slurm 作业记录无效")) from error
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError(T("Slurm 作业记录无效"))
        raw = stream.read(65537)
    try:
        value = json.loads(raw) if len(raw) <= 65536 else None
        valid = (isinstance(value, dict) and value.get("version") == 1
                 and re.fullmatch(r"[0-9a-f]{32}", value.get("token", ""))
                 and value.get("directory") == str(Path(workdir).resolve())
                 and isinstance(value.get("job_id"), str)
                 and re.fullmatch(r"[1-9][0-9]*", value["job_id"] or "1")
                 and re.fullmatch(r"[A-Za-z0-9_.-]*", value.get("cluster", ""))
                 and isinstance(value.get("submitted"), str))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise ValueError(T("Slurm 作业记录无效"))
    return value


def command(args, workdir, text=None):
    try:
        result = subprocess.run(args, cwd=workdir, input=text, capture_output=True, text=True,
                                timeout=10, env=core.child_env(LC_ALL="C", TZ="UTC",
                                                               SLURM_TIME_FORMAT="%Y-%m-%dT%H:%M:%S"))
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(T("Slurm 命令失败：{e}", e=str(error))) from error
    if result.returncode:
        raise CommandFailed(T("Slurm 命令失败：{e}", e=(result.stderr or result.stdout).strip()[-2000:]))
    return result.stdout.strip()


def cluster_args(record):
    return ["--clusters=" + record["cluster"]] if record.get("cluster") else []


def log_file(workdir, record):
    return Path(workdir) / (".grasp_gui_slurm_" + record["token"] + ".log")


def path_expression(value):
    """路径只展开环境变量；空格和命令替换符按普通文件名处理。"""
    if value.startswith("~/"):
        value = "$HOME/" + value[2:]
    parts = re.split(r"(\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*)", value)
    return "".join('"${' + part.lstrip("$").strip("{}") + '}"' if part.startswith("$") and
                   re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*", part)
                   else shlex.quote(part)
                   for part in parts if part) or "''"


def batch_script(jobs, settings):
    values = dict(settings, bindir=path_expression(settings["bindir"]),
                  mpitmp=path_expression(settings["mpitmp"] or "$SLURM_SUBMIT_DIR/tmp_mpi"))
    return core.slurm_script(jobs, values)


def submit(workdir, script, background=None):
    """调用方已持有目录锁并检查空闲；先持久化意图，避免丢失回答后重复提交。"""
    root = Path(workdir).resolve()
    missing = [name for name in ("sbatch", "squeue", "scancel") if not shutil.which(name)]
    if missing:
        raise ValueError(T("服务器缺少 Slurm 命令：{names}", names=", ".join(missing)))
    token = uuid.uuid4().hex
    record = dict(version=1, directory=str(root), token=token, job_id="", cluster="",
                  submitted=datetime.datetime.now(datetime.timezone.utc).isoformat(), background=identity(background),
                  script_sha256=hashlib.sha256(script.encode()).hexdigest())
    path = root / (".grasp_gui_slurm_" + token + ".sh")
    sessions.atomic(path, script.encode())
    sessions.atomic(root / RECORD, json.dumps(record).encode())
    # CLI 选项覆盖脚本中的同名指令，确保日志和所有权标记可以找回。
    try:
        output = str(log_file(root, record)).replace("%", "%%")
        raw = command(["sbatch", "--parsable", "--comment=grasp-gui:" + token,
                       "--chdir=" + str(root), "--output=" + output, "--error=" + output, str(path)], root)
    except CommandFailed as error:
        record.update(rejected=True, error=str(error))
        sessions.atomic(root / RECORD, json.dumps(record).encode())
        raise
    match = re.fullmatch(r"([1-9][0-9]*)(?:;([A-Za-z0-9_.-]+))?", raw)
    if not match:
        raise ValueError(T("Slurm 提交结果不明确，请核对队列，勿重复提交"))
    record.update(job_id=match[1], cluster=match[2] or "")
    sessions.atomic(root / RECORD, json.dumps(record).encode())
    return dict(started=True, backend="slurm", job_id=record["job_id"], cluster=record["cluster"])


def queued(workdir, record):
    rows = command(["squeue", *cluster_args(record), "--noheader", "--jobs=" + record["job_id"],
                    "--user=" + pwd.getpwuid(os.getuid()).pw_name, "--format=%i|%T|%k"], workdir)
    if not rows:
        return None
    fields = rows.split("|", 2)
    if len(fields) != 3 or fields[0].strip() != record["job_id"] or fields[2].strip() != "grasp-gui:" + record["token"]:
        raise ValueError(T("Slurm 队列中的任务与保存记录不匹配"))
    return fields[1].strip()


def query(workdir, record):
    state = queued(workdir, record)
    if state:
        pending = {"PENDING", "CONFIGURING", "REQUEUED", "REQUEUE_FED", "REQUEUE_HOLD", "RESV_DEL_HOLD", "SPECIAL_EXIT"}
        running = {"RUNNING", "COMPLETING", "SUSPENDED", "SIGNALING", "STAGE_OUT", "STOPPED", "RESIZING"}
        result = "queued" if state in pending else "running" if state in running else "unknown"
        return dict(scheduler_state=state, status=result, active=True, can_cancel=True)
    # squeue 消失不代表成功；只采用分配本身的记录，忽略 .batch/.extern 等步骤。
    raw = command(["sacct", *cluster_args(record), "--noheader", "--parsable2", "--allocations",
                   "--jobs=" + record["job_id"], "--starttime=" + record["submitted"][:10],
                   "--format=JobIDRaw,State%40,ExitCode,WorkDir%4096,Submit"], workdir)
    for line in raw.splitlines():
        parts = line.split("|")
        if len(parts) != 5 or parts[0] != record["job_id"]:
            continue
        job, state, exit_code, directory, submitted = parts
        if directory != str(Path(workdir).resolve()):
            continue
        try:
            before = datetime.datetime.fromisoformat(record["submitted"]).astimezone(datetime.timezone.utc)
            after = datetime.datetime.fromisoformat(submitted).replace(tzinfo=datetime.timezone.utc)
            if abs((after - before).total_seconds()) > 300:
                continue
        except ValueError:
            continue
        state = state.split()[0].rstrip("+")
        if state not in TERMINAL:
            return dict(scheduler_state=state, status="unknown", active=True, can_cancel=False)
        result = "ok" if state == "COMPLETED" and exit_code == "0:0" else (
            "stopped" if state == "CANCELLED" else "failed")
        return dict(scheduler_state=state, status=result, active=False, can_cancel=False, exit_code=exit_code)
    return dict(scheduler_state="UNKNOWN", status="unknown", active=True, can_cancel=False,
                error=T("Slurm 暂无作业记录，不能判定任务已结束"))


def status(workdir, background=None, refresh=False):
    record = read(workdir)
    if record is None:
        return None
    # 新的后台直跑有自己的状态；旧 Slurm 记录不应覆盖它。
    if background and identity(background) != record.get("background"):
        return None
    base = dict(backend="slurm", job_id=record["job_id"], cluster=record["cluster"],
                start=record["submitted"], token=record["token"], status="unknown", active=True, can_cancel=False)
    if not record["job_id"]:
        if record.get("rejected"):
            return dict(base, status="failed", active=False, error=record.get("error", ""))
        return dict(base, error=T("Slurm 提交结果不明确，请核对队列，勿重复提交"))
    key = (str(Path(workdir).resolve()), record["token"])
    with _lock:
        cached = _cache.get(key)
        if cached and not refresh and cached[0] > time.monotonic():
            return dict(base, **cached[1])
        try:
            value = query(workdir, record)
        except ValueError as error:
            value = dict(scheduler_state="UNKNOWN", status="unknown", active=True, can_cancel=False, error=str(error))
        interval = 60 if value.get("error") or not value["active"] else 15
        _cache[key] = (time.monotonic() + interval, value)
        # 仅缓存当前浏览的少量任务，避免长期服务随访问目录数增长。
        while len(_cache) > 128:
            _cache.pop(next(iter(_cache)))
        return dict(base, **value)


def cancel(workdir):
    record = read(workdir)
    if record is None or not record["job_id"] or queued(workdir, record) is None:
        raise ValueError(T("无法确认 Slurm 作业，请先刷新并核对队列"))
    try:
        command(["scancel", *cluster_args(record), record["job_id"]], workdir)
    finally:
        with _lock:
            _cache.pop((str(Path(workdir).resolve()), record["token"]), None)
    return dict(stop_requested=True, confirmed=False, backend="slurm", job_id=record["job_id"])
