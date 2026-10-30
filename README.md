# GRASP GUI

A graphical interface for [GRASP2018](https://github.com/compas/grasp): fill in the parameters of each
program, and the GUI generates the interactive input (stdin) and runs the program in a working directory.
The interface is available in Chinese and English.

GRASP2018 的图形界面：在表单中填写各程序的参数，界面自动生成交互输入 (stdin)，并在工作目录中运行。
界面支持中文和 English。

## Features / 功能

- One tab per program: `rnucleus`, `rcsfgenerate`, `rcsfinteract`, `rcsfsplit`, `rangular`, `rwfnestimate`,
  `rmcdhf`, `rsave`, `rci`, `jj2lsj`, `rhfs` (optionally followed by `rhfs_lsj`), `ris4`, `rlevels`,
  `rtablevels`, `rtabtrans1`, `rtabtrans2`, `rbiotransform`, `rtransition`, plus a *Custom* tab (grouped as *Nucleus & CSFs*, *SCF & CI*,
  *Properties & transitions*, *Results & tools*) for any other program with hand-written input. Inputs follow the
  default-settings question order of each program; they reproduce the inputs of the test cases in
  `grasptest/` (case1–4, example1–5, 8, 9) except non-default `jj2lsj` runs, which need the *Custom* tab.
- Common file steps are built in: save `rcsf.out` as `name.c`, copy a `.c` file to `rcsf.inp` before
  `rangular`, run `rsave` after `rmcdhf`, copy `.c/.w` before `rci`.
- **Pipeline**: add several steps, run them in order (stops at the first error), preview the input, and
  export as a shell script.
- **MPI**: with more than one process, `rangular`, `rmcdhf`, `rci`, `rbiotransform` and `rtransition` run as
  `mpirun -np N <prog>_mpi` (with `MPI_TMP`). `rmcdhf` can use the in-memory version
  `rmcdhf_mem` / `rmcdhf_mem_mpi`.
- **Slurm**: export the pipeline as a job script for `sbatch` (partition, nodes, tasks, time, memory,
  modules, e-mail, extra `#SBATCH` options).
- **State groups odd / even**: `rcsfgenerate`, `rcsfinteract`, `rcsfsplit`, `rangular`, `rwfnestimate`,
  `rmcdhf`, `rsave`, `rci`, `jj2lsj`, `rhfs` and `ris4` keep separate parameters for each group
  (file names such as `odd2.c` / `even2.c`,
  `outodd_rci` / `outeven_rci` correspond automatically); the other tabs are shared. *Copy to …* copies
  the current group to the other one and renames the files.
- **Per-directory session**: parameters, groups and the pipeline are saved automatically in
  `<working directory>/.grasp_gui.json` and restored when the directory is opened again. On start the GUI
  opens the directory used last time.
- Save / load all parameters and the pipeline as JSON.

**态组 odd / even**：上述 11 个程序页按态组分别保存参数，文件名自动对应，其余程序页两组共用；
“复制到 …”把当前组的参数复制到另一组并替换名称。
**工作目录记录**：参数、态组和流程自动保存在 `工作目录/.grasp_gui.json`，再次打开该目录时自动恢复；
启动时打开上次使用的目录。

## Requirements / 依赖

- Python ≥ 3.9 and PySide6: `pip install -r requirements.txt`
- A compiled GRASP2018 (`bin/` with `rmcdhf`, …; the `*_mpi` programs and an MPI library for parallel runs)

## Usage / 用法

```bash
python3 grasp_gui.py                  # 中文界面，打开上次的工作目录
python3 grasp_gui.py path/to/workdir  # 打开指定的工作目录 / open this working directory
python3 grasp_gui.py --lang en        # English interface
```

The language can also be switched in the *Language / 语言* menu; the choice is remembered in
`~/.config/grasp_gui.json`.

The GRASP `bin` directory is looked up in this order: `$GRASP_BINDIR`, the directory used last time,
the directory of `rmcdhf` on `PATH`, `../bin` relative to this program. It can be changed at the top of the
window.

GRASP `bin` 目录的查找顺序：`$GRASP_BINDIR` → 上次使用的目录 → `PATH` 中 `rmcdhf` 所在目录 →
本程序上一级目录的 `bin`。也可以在窗口顶部修改。

### Standalone executable / 独立可执行文件

```bash
./build.sh            # -> dist/grasp_gui   single file, runs without Python or PySide6
./build.sh --onedir   # -> dist/grasp_gui/  folder variant
```

`build.sh` creates its own build environment (`build/venv`) with PyInstaller and the essential PySide6
modules on first use. The executable (about 70 MB) needs a glibc at least as new as the build machine's
(e.g. built on Ubuntu 22.04: glibc ≥ 2.35); to use it on an older system, run `build.sh` there. GRASP
itself is not included: point the GUI at a GRASP `bin` directory as usual.

`build.sh` 首次运行时自动建立打包环境。生成的可执行文件约 70 MB，不需要 Python 或 PySide6；
要求系统的 glibc 不低于打包机器的版本（在 Ubuntu 22.04 上打包则需 glibc ≥ 2.35），
在更老的系统上使用时，在那台机器上重新运行 `build.sh` 即可。GRASP 本身不包含在内。

### Submitting to a cluster / 提交到服务器

1. Build the pipeline locally and test it on a small case.
2. *File → Export Slurm job script…*, fill in the cluster settings.
3. Upload the script together with the input files of the working directory (`isodata`, `*.c`, `*.w`, …)
   to one directory on the server and run `sbatch <script>` there.

## Notes for WSL2 / WSLg

- Qt uses Wayland directly. If `$XDG_RUNTIME_DIR` lacks the WSLg socket (common when systemd is enabled),
  the GUI points `WAYLAND_DISPLAY` at `/mnt/wslg/runtime-dir/wayland-0` automatically. For the X11
  fallback, install `libxcb-cursor0`.
- hwloc's GL plugin makes `mpirun` hang under WSLg; MPI runs therefore set `HWLOC_COMPONENTS=-gl`
  unless it is already set.
- Qt's teardown can hang on Wayland, so the GUI exits directly after the window is closed. If a program is
  still running, it asks for confirmation and terminates the whole process group first.

## Files / 文件

| File | Content |
|---|---|
| `grasp_core.py` | Toolkit-independent core: field definitions and input rules of each program, running (serial / MPI), shell and Slurm export, translations |
| `grasp_gui.py` | Qt (PySide6) interface; forms are generated from the field definitions in `grasp_core.py` |
| `build.sh` | Builds a standalone executable with PyInstaller |

## License / 许可证

[MIT](LICENSE)
