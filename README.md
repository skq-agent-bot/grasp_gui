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
- **Wave function viewer** (*Tools → Wave function viewer…* or the *Wave functions…* button): reads the `.w`
  files of the working directory and plots P(r), Q(r) and P² + Q² on an r, log r or √r axis; several files can
  be overlaid (e.g. `odd2.w` … `odd6.w`), each orbital in one colour and each file in one line style. A table
  lists orbital energies, ⟨r⟩, peak position, nodes (vs. n − l − 1) and norms. Export as PNG or CSV.
  Files are recognised by their content, not their name, so `rwfn.inp`, `rwfn.out` and renamed files are found too.
- **Levels and compositions** (*Tools → Levels and compositions…* or the *Levels…* button): reads the mixing
  coefficient files (`.m`, `.cm`) and draws an energy level diagram, one column per J^π (odd parity red, even
  blue). Hover a level for details, click it (or a row of the level list) to see the composition of the ASF:
  the jj-coupled CSF mixing coefficients with configurations from the `.c` file, and the LSJ composition from
  `jj2lsj` (`.lsj.lbl`). Energies relative to the lowest level in eV (default), cm⁻¹ or atomic units; the choice is remembered.
  The matching `.c` and `.lsj.lbl` files are found by content (number of orbitals, CSFs and J^π of each block;
  energies of the levels), so they need not share the name of the mixing file.

**态组 odd / even**：上述 11 个程序页按态组分别保存参数，文件名自动对应，其余程序页两组共用；
“复制到 …”把当前组的参数复制到另一组并替换名称。
**工作目录记录**：参数、态组和流程自动保存在 `工作目录/.grasp_gui.json`，再次打开该目录时自动恢复；
启动时打开上次使用的目录。
**波函数查看器**（“工具 → 波函数查看器…”或“波函数…”按钮）：读取工作目录中的 `.w` 文件，绘制 P(r)、Q(r)
和径向密度 P² + Q²，可叠加多个文件比较；表格列出轨道能量、⟨r⟩、峰值位置、节点数和归一化；可导出 PNG 或 CSV。按文件内容识别波函数文件，与文件名无关 (`rwfn.inp`、`rwfn.out` 或改过名的文件也能找到)。
**能级与组成查看器**（“工具 → 能级与组成查看器…”或“能级…”按钮）：读取混合系数文件 (`.m`、`.cm`) 画出能级图，
每个 J^π 一列；鼠标停在能级上显示信息，点击能级 (或能级列表中的一行) 显示该原子态的组成：jj 耦合下的 CSF
混合系数 (组态来自 `.c` 文件) 以及 jj2lsj 给出的 LSJ 组成 (`.lsj.lbl`)。能量相对于最低能级，默认用 eV，可切换为 cm⁻¹ 或原子单位，并记住选择。对应的 `.c` 和 `.lsj.lbl` 文件按内容匹配 (轨道数、各块的 CSF 数与 J^π，以及能级能量)，不要求与混合系数文件同名。

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
modules on first use. The executable (about 90 MB) needs a glibc at least as new as the build machine's
(e.g. built on Ubuntu 22.04: glibc ≥ 2.35); to use it on an older system, run `build.sh` there. GRASP
itself is not included: point the GUI at a GRASP `bin` directory as usual.

Fonts are bundled, so the GUI also works on machines without (Chinese) fonts: Noto Sans CJK
(SIL Open Font License) and DejaVu Sans / DejaVu Sans Mono (free licence), with their licence files.
`build.sh` takes them from the build machine via fontconfig (Debian/Ubuntu:
`apt install fonts-noto-cjk fonts-dejavu-core`); missing fonts are reported and left out.

`build.sh` 首次运行时自动建立打包环境。生成的可执行文件约 90 MB，不需要 Python 或 PySide6；
要求系统的 glibc 不低于打包机器的版本（在 Ubuntu 22.04 上打包则需 glibc ≥ 2.35），
在更老的系统上使用时，在那台机器上重新运行 `build.sh` 即可。GRASP 本身不包含在内。
可执行文件内置了字体 (Noto Sans CJK、DejaVu Sans / Sans Mono 及其许可证)，没有安装中文字体的机器也能正常显示；
打包时从本机取这些字体 (Ubuntu：`apt install fonts-noto-cjk fonts-dejavu-core`)。

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
| `grasp_wfn.py` | Reads GRASP radial wave function files (`.w`) and computes orbital properties (standard library only) |
| `wfn_viewer.py` | Wave function viewer window (plots drawn with QPainter) |
| `grasp_mix.py` | Reads mixing coefficient files (`.m`, `.cm`), CSF lists (`.c`) and `jj2lsj` labels (`.lsj.lbl`) (standard library only) |
| `level_viewer.py` | Energy level diagram and ASF composition window |
| `build.sh` | Builds a standalone executable with PyInstaller |

## License / 许可证

[MIT](LICENSE)
