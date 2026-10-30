"""
GRASP 图形界面的核心逻辑（与界面库无关）：

  * 各 GRASP 程序的参数字段描述，以及由参数生成交互输入 (stdin) 的规则；
    提问顺序与 grasptest/case1/script 中各 sh_* 脚本的 here-document 一致
  * 在工作目录中依次运行任务 (可选 MPI)、导出 shell / Slurm 脚本
  * 界面文字的中英文翻译
"""

import codecs
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".config", "grasp_gui.json")

# 输出窗口只保留最后这么多行（完整输出可写入日志文件），避免大量输出拖慢界面
MAX_OUT_LINES = 5000

# Slurm 作业脚本的默认设置
SLURM_DEFAULTS = dict(job="grasp", partition="", nodes="1", ntasks="32", time="2-00:00:00", mem="",
                      bindir="$HOME/grasp/bin", modules="", mpirun="mpirun -np $SLURM_NTASKS",
                      mpitmp="$SLURM_SUBMIT_DIR/tmp_mpi", mail="", extra="")

# ---------------------------------------------------------------------------
#  界面语言
# ---------------------------------------------------------------------------

LANG = "zh"

EN = {
    # 主窗口
    "GRASP 图形界面": "GRASP GUI",
    "文件": "File",
    "保存参数…": "Save parameters…",
    "载入参数…": "Load parameters…",
    "导出流程为 shell 脚本…": "Export pipeline as shell script…",
    "退出": "Quit",
    "语言": "Language",
    "工作目录": "Working directory",
    "GRASP bin 目录": "GRASP bin directory",
    "浏览…": "Browse…",
    "查看文件": "List files",
    "预览输入": "Preview input",
    "▶ 运行当前程序": "▶ Run this program",
    "加入流程 ↓": "Add to pipeline ↓",
    "■ 停止": "■ Stop",
    "流程": "Pipeline",
    "▶ 运行全部": "▶ Run all",
    "▶ 从选中开始": "▶ Run from selected",
    "查看": "Show",
    "上移": "Move up",
    "下移": "Move down",
    "删除": "Remove",
    "清空": "Clear",
    "导出脚本…": "Export script…",
    "输入预览": "Input preview",
    "程序输出": "Program output",
    "清屏": "Clear",
    "就绪": "Ready",
    "完成": "Finished",
    "失败 / 已停止 — 详见输出": "Failed / stopped — see output",
    "运行中：{n} 个步骤 …": "Running: {n} step(s) …",
    "运行中": "Busy",
    "已有任务在运行，请等待或先停止。": "A job is already running. Wait for it or stop it first.",
    "有程序正在运行，退出将终止它。确定退出吗？": "A program is still running and will be terminated. Quit anyway?",
    "参数错误": "Invalid parameters",
    "参数格式有误：{e}": "Invalid parameter format: {e}",
    "错误": "Error",
    "工作目录不存在：{d}": "Working directory does not exist: {d}",
    "导出": "Export",
    "流程为空：先在各标签页点击“加入流程”。": "The pipeline is empty: click “Add to pipeline” on a tab first.",
    "导出 shell 脚本": "Export shell script",
    "已导出 {p}": "Exported {p}",
    "保存参数": "Save parameters",
    "载入参数": "Load parameters",
    "参数已保存到 {p}": "Parameters saved to {p}",
    "已载入 {p}": "Loaded {p}",
    "----- {d} ({n} 个文件) -----": "----- {d} ({n} files) -----",
    # 运行
    "找不到程序 {p} (bin 目录: {d})": "Program {p} not found (bin directory: {d})",
    "[输出已写入 {f}]": "[output written to {f}]",
    "{p} 退出码 {rc}": "{p} exited with code {rc}",
    "\n*** 错误: {e}\n": "\n*** Error: {e}\n",
    "\n*** 已停止\n": "\n*** Stopped\n",
    # 通用
    "输出日志文件": "Output log file",
    "空 = 只显示在窗口": "empty = show in window only",
    "态名称": "State name",
    "每块一行": "one line per block",
    "混合系数来自 CI 计算": "Mixing coefficients from CI calculation",
    "初态名称": "Initial state name",
    "末态名称": "Final state name",
    "留空则不复制": "leave empty to skip copy",
    # rnucleus
    "生成核数据文件 isodata。": "Generate the nuclear data file isodata.",
    "原子序数 Z": "Atomic number Z",
    "质量数 A": "Mass number A",
    "0 = 点核模型": "0 = point nucleus",
    "修改默认的核半径 / 表面厚度": "Revise default nuclear radius / skin thickness",
    "  均方根半径 (fm)": "  RMS radius (fm)",
    "  表面厚度 (fm)": "  Skin thickness (fm)",
    "中性原子质量 (amu)": "Mass of neutral atom (amu)",
    "0 = 静止核": "0 = static nucleus",
    "核自旋 I": "Nuclear spin I",
    "磁偶极矩 (核磁子)": "Dipole moment (nuclear magnetons)",
    "电四极矩 (barn)": "Quadrupole moment (barns)",
    # rcsfgenerate
    "生成 CSF 列表 rcsf.out。组态写法如 1s(2,i)2s(2,*)2p(1,*)：c=闭壳, i=不激发, *=活跃, "
    "数字=最小占据。可添加多个列表 (Generate more lists)。":
        "Generate the CSF list rcsf.out. Configurations are written like 1s(2,i)2s(2,*)2p(1,*): "
        "c = closed, i = inactive, * = active, number = minimal occupation. "
        "Several lists can be added (Generate more lists).",
    "轨道排序": "Orbital ordering",
    "默认": "default",
    "反序": "reverse",
    "按对称性": "symmetry",
    "闭壳芯": "Core",
    "无芯": "no core",
    "CSF 列表:": "CSF lists:",
    "+ 添加列表": "+ Add list",
    "− 删除当前列表": "− Remove current list",
    "列表 {n}": "List {n}",
    "参考组态 (每行一个)": "Reference configurations\n(one per line)",
    "活跃轨道集": "Active set",
    "各 l 的最高 n，如 5s,4p,3d": "highest n per l, e.g. 5s,4p,3d",
    "2J 最小值": "2J min",
    "2J 最大值": "2J max",
    "激发数": "Number of excitations",
    "负数: 关联轨道总是双占据": "negative: correlation orbitals doubly occupied",
    "保存 rcsf.out 为": "Save rcsf.out as",
    # rcsfsplit
    "按轨道集把 name.c 拆分为 name<标签>.c 等多个文件。":
        "Split name.c by orbital set into name<label>.c files.",
    "CSF 文件名 (不含 .c)": "CSF file name (without .c)",
    "拆分 (每行: 轨道集  标签)": "Splits (per line: orbital set  label)",
    # rangular
    "计算角系数 (mcp.*)。读取 rcsf.inp。": "Compute angular coefficients (mcp.*). Reads rcsf.inp.",
    "复制此 CSF 文件为 rcsf.inp": "Copy this CSF file to rcsf.inp",
    "留空则直接用现有 rcsf.inp": "leave empty to use existing rcsf.inp",
    # rwfnestimate
    "生成初始径向波函数 rwfn.inp。可先从已有 .w 文件读取部分轨道，其余用 Thomas-Fermi 或屏蔽类氢估计。":
        "Generate initial radial wave functions rwfn.inp. Orbitals can first be read from an "
        "existing .w file; the rest are estimated with Thomas-Fermi or screened hydrogenic functions.",
    "先从已有波函数文件读取 (GRASP92 File)": "First read from an existing wave function file (GRASP92 File)",
    "  波函数文件": "  Wave function file",
    "如 odd2.w，空则为 rwfn.out": "e.g. odd2.w; empty = rwfn.out",
    "  读取的轨道": "  Orbitals to read",
    "* = 全部": "* = all",
    "其余轨道的估计方法": "Method for remaining orbitals",
    "屏蔽类氢 (Screened Hydrogenic)": "Screened Hydrogenic",
    "  轨道": "  Orbitals",
    # rmcdhf
    "自洽场计算 (读取 rcsf.inp, rwfn.inp, mcp.*；输出 rwfn.out, rmix.out)。"
    "每个 J 对称块一行能级号，例如 1,2,3 或 1-3。":
        "Self-consistent field calculation (reads rcsf.inp, rwfn.inp, mcp.*; writes rwfn.out, rmix.out). "
        "One line of level numbers per J block, e.g. 1,2,3 or 1-3.",
    "各块要优化的能级": "Levels to optimise\nper block",
    "使用内存版本 rmcdhf_mem": "Use the in-memory version rmcdhf_mem",
    "角系数一次读入内存：更快，但更占内存": "angular coefficients kept in memory: faster, but uses more memory",
    "能级权重": "Level weights",
    "标准 (EOL)": "standard (EOL)",
    "等权重": "equal",
    "用户指定": "user",
    "  用户权重": "  User weights",
    "选 9 时填写, 如 1,1,2": "for option 9, e.g. 1,1,2",
    "变分轨道": "Orbitals to vary",
    "如 *  或 3*  或 2s,2p*": "e.g. *  or 3*  or 2s,2p*",
    "谱学轨道 (非关联轨道)": "Spectroscopic orbitals",
    "空 = 无": "empty = none",
    "最大 SCF 迭代次数": "Max SCF cycles",
    "结束后 rsave 保存为": "rsave afterwards as",
    "空 = 不保存": "empty = do not save",
    # rsave
    "把 rcsf.inp / rwfn.out / rmix.out 等保存为 name.c / name.w / name.m ...":
        "Save rcsf.inp / rwfn.out / rmix.out etc. as name.c / name.w / name.m ...",
    # rci
    "组态相互作用计算 (可含 Breit 与 QED)。读取 name.c, name.w，输出 name.cm 等。":
        "Configuration interaction (optionally with Breit and QED). Reads name.c, name.w; writes name.cm etc.",
    "先从此态复制 .c/.w": "First copy .c/.w from state",
    "空 = 不复制": "empty = no copy",
    "包含横向 (Breit) 相互作用": "Include transverse (Breit) interaction",
    "修改横向光子频率": "Modify transverse photon frequencies",
    "  频率缩放因子": "  Frequency scale factor",
    "真空极化 (Vacuum Polarisation)": "Vacuum polarisation",
    "正常质量移动 (NMS)": "Normal mass shift (NMS)",
    "特殊质量移动 (SMS)": "Specific mass shift (SMS)",
    "估计自能 (Self-energy)": "Estimate self-energy",
    "  自能计算的最大 n (≤8)": "  Max n for self-energy (≤8)",
    "各块计算的能级": "Levels per block",
    # jj2lsj
    "把 jj 耦合的混合系数变换到 LSJ 耦合，给出 LSJ 标记。":
        "Transform jj-coupled mixing coefficients to LSJ coupling and produce LSJ labels.",
    "混合系数来自 CI 计算 (.cm)": "Mixing coefficients from CI calculation (.cm)",
    "否则读 .m": "otherwise .m is read",
    "需要唯一标记 (unique labeling)": "Unique labeling",
    # rlevels
    "列出能级。可给多个 .m / .cm 文件。": "List energy levels. Several .m / .cm files may be given.",
    "混合系数文件": "Mixing coefficient files",
    "空格分隔": "space separated",
    # rbiotransform / rtransition
    "跃迁计算前的双正交变换。": "Biorthogonal transformation before transition calculations.",
    "计算跃迁参数 (需先运行 rbiotransform)。": "Compute transition parameters (run rbiotransform first).",
    "跃迁类型": "Transition type",
    "M1 跃迁只计算不同 J 的能级之间": "M1 transitions only between levels with different J",
    "E2 跃迁只计算不同 J 的能级之间": "E2 transitions only between levels with different J",
    "跃迁类型含 M1 时询问": "asked when the types include M1",
    "跃迁类型含 E2 时询问": "asked when the types include E2",
    "屏蔽类氢，关联轨道增加 Z (custom Z)": "Screened Hydrogenic, increased Z for correlation orbitals (custom Z)",
    "  关联轨道的 Z 增加量": "  Increase in Z for correlation orbitals",
    "仅方法 4": "method 4 only",
    "如 E1  或 E1,M2": "e.g. E1  or E1,M2",
    # 自定义
    "自定义": "Custom",
    "运行任意 GRASP 程序，手动填写交互输入（每行回答一个提问）。":
        "Run any GRASP program with hand-written interactive input (one answer per line).",
    "程序": "Program",
    "命令行参数": "Arguments",
    "输入 (stdin)": "Input (stdin)",
    # MPI / 性能
    "MPI 进程数": "MPI processes",
    "mpirun 命令": "mpirun command",
    "降低计算进程优先级 (nice)": "Lower priority of calculations (nice)",
    "进程数 > 1 时 rangular / rmcdhf / rci / rbiotransform / rtransition 改用 *_mpi 版本；"
    "rangular 与 rmcdhf 须使用相同的进程数和 MPI_TMP。":
        "With more than 1 process, rangular / rmcdhf / rci / rbiotransform / rtransition use their *_mpi "
        "versions; rangular and rmcdhf must use the same number of processes and MPI_TMP.",
    "（只显示最后 {n} 行，完整输出请设置日志文件）": "(last {n} lines only; set a log file for the full output)",
    "找不到 rangular 生成的角系数文件 (mcp.*)：请先运行 rangular。":
        "No angular coefficient files (mcp.*) from rangular were found: run rangular first.",
    "角系数文件是串行 rangular 生成的 (工作目录中的 mcp.*)，rmcdhf 不能用 {np} 个 MPI 进程运行："
    "请把 MPI 进程数设为 1，或用 {np} 个进程重新运行 rangular。":
        "The angular coefficients were generated by serial rangular (mcp.* in the working directory), so "
        "rmcdhf cannot run on {np} MPI processes: set the number of MPI processes to 1, or rerun rangular "
        "on {np} processes.",
    "角系数文件是 rangular 用 {k} 个 MPI 进程生成的 (在 {d} 中)，rmcdhf 必须使用相同的进程数："
    "请把 MPI 进程数设为 {k}，或用 {np} 个进程重新运行 rangular。":
        "The angular coefficients were generated by rangular on {k} MPI processes (in {d}); rmcdhf must use "
        "the same number of processes: set the number of MPI processes to {k}, or rerun rangular on {np} "
        "process(es).",
    "rcsf.inp 比角系数文件新：请先对当前的 rcsf.inp 运行 rangular。":
        "rcsf.inp is newer than the angular coefficient files: run rangular on the current rcsf.inp first.",
    # Slurm
    "导出 Slurm 作业脚本…": "Export Slurm job script…",
    "Slurm 作业脚本": "Slurm job script",
    "把当前流程导出为可直接 sbatch 提交的作业脚本。把脚本和工作目录中的输入文件 (isodata, *.c, *.w …) "
    "一起上传到服务器的同一目录，然后运行 sbatch 脚本名。":
        "Export the current pipeline as a job script for sbatch. Upload the script together with the input "
        "files of the working directory (isodata, *.c, *.w …) to one directory on the server, then run "
        "sbatch <script>.",
    "作业名": "Job name",
    "分区 (partition)": "Partition",
    "空 = 默认分区": "empty = default partition",
    "节点数": "Nodes",
    "每节点 MPI 进程数": "MPI tasks per node",
    "时间限制": "Time limit",
    "如 2-00:00:00 (2 天)": "e.g. 2-00:00:00 (2 days)",
    "内存": "Memory",
    "如 64G；空 = 不指定": "e.g. 64G; empty = not set",
    "服务器上的 GRASP bin 目录": "GRASP bin directory on server",
    "加载模块等命令": "Environment setup\n(module load …)",
    "每行一条，如 module load openmpi": "one per line, e.g. module load openmpi",
    "MPI 启动命令": "MPI launch command",
    "MPI 临时目录 (MPI_TMP)": "MPI scratch dir (MPI_TMP)",
    "邮件通知地址": "Notification e-mail",
    "空 = 不通知": "empty = no e-mail",
    "其他 #SBATCH 选项": "Other #SBATCH options",
    "每行一条，如 --account=xxx": "one per line, e.g. --account=xxx",
    "导出…": "Export…",
    "取消": "Cancel",
    # 程序列表分组
    "核与组态": "Nucleus & CSFs",
    "自洽场与 CI": "SCF & CI",
    "性质与跃迁": "Properties & transitions",
    "结果与工具": "Results & tools",
    # 态组 / 工作目录记录
    "态组": "State group",
    "复制到 {g}（替换名称）": "Copy to {g} (rename files)",
    "标签上带组名的程序页按态组分别保存参数，其余程序页两组共用。":
        "Tabs labelled with the group keep separate parameters per group; the other tabs are shared.",
    # rhfs / ris4
    "计算超精细结构常数 A、B 和朗德 g 因子。读取 isodata (核自旋 I、磁偶极矩、电四极矩在 rnucleus 中设置)、"
    "name.c、name.w、name.(c)m；输出 name.(c)h、name.(c)hoffd。":
        "Compute hyperfine constants A, B and Landé g factors. Reads isodata (nuclear spin I, dipole and "
        "quadrupole moments are set in rnucleus), name.c, name.w, name.(c)m; writes name.(c)h, name.(c)hoffd.",
    "结束后运行 rhfs_lsj，用 LSJ 标记输出结果": "Then run rhfs_lsj to print the results with LSJ labels",
    "需先运行 jj2lsj；输出 name.(c)hlsj": "needs jj2lsj first; writes name.(c)hlsj",
    "  按能量排序": "  Sort by energy",
    "计算同位素移位：正常 / 特殊质量移位参数和场移电子因子。读取 isodata、name.c、name.w、name.(c)m；"
    "输出 name.(c)i。":
        "Compute isotope shifts: normal / specific mass shift parameters and field shift electronic factors. "
        "Reads isodata, name.c, name.w, name.(c)m; writes name.(c)i.",
    "计算高阶场移电子因子": "Compute higher-order field shift electronic factors",
    "保存角系数 (name.IOB / name.ITB)，以后重复计算时直接读取":
        "Save angular coefficients (name.IOB / name.ITB) for later runs",
    "这两个文件已存在时程序不询问": "not asked when these files already exist",
    # rcsfinteract / rtablevels
    "从完整 CSF 列表中只保留与多参考组态有相互作用的 CSF。读取 rcsfmr.inp (多参考) 和 rcsf.inp (完整列表)，"
    "输出 rcsf.out。":
        "Keep only the CSFs of the full list that interact with the multireference. Reads rcsfmr.inp "
        "(multireference) and rcsf.inp (full list); writes rcsf.out.",
    "多参考 CSF 文件 → rcsfmr.inp": "Multireference CSF file → rcsfmr.inp",
    "留空则直接用现有 rcsfmr.inp": "leave empty to use existing rcsfmr.inp",
    "完整 CSF 文件 → rcsf.inp": "Full CSF file → rcsf.inp",
    "按哪种哈密顿量判断相互作用": "Interaction through",
    "结果 rcsf.out 保存为": "Save the result rcsf.out as",
    "如 odd.c；与完整列表同名时覆盖原列表；留空则不复制":
        "e.g. odd.c; the same name as the full list overwrites it; empty = no copy",
    "把 rlevels 生成的能级文件整理成 LaTeX 和 ASCII 能级表 (energytablelatex.tex、energytableascii.txt)。"
    "每个文件占表中一列，能级标记和顺序以最后一个文件为准。":
        "Make LaTeX and ASCII energy tables (energytablelatex.tex, energytableascii.txt) from energy files "
        "written by rlevels. Each file fills one column; labels and order follow the last file.",
    "标签开头跳过的字符数": "Characters to skip at the start of labels",
    "如标签以闭壳芯 1s(2). 开头，跳过 6 个字符": "e.g. skip 6 when labels start with the core 1s(2).",
    "能级文件": "Energy files",
    "每行一个，按活跃集从小到大；在 rlevels 页用“输出日志文件”生成":
        "one per line, smallest active set first; write them with the output log file of the rlevels tab",
    # rtabtrans1 / rtabtrans2
    "为 rtabtrans2 生成能级标记文件 energylabel.latex / energylabel.ascii。读取各混合系数文件及其 jj2lsj 标记 "
    "(name.lsj.lbl)。":
        "Write the energy label file energylabel.latex / energylabel.ascii for rtabtrans2. Reads the mixing "
        "coefficient files and their jj2lsj labels (name.lsj.lbl).",
    "混合系数文件 (.m / .cm)": "Mixing coefficient files (.m / .cm)",
    "每行一个，与计算跃迁的波函数对应；需先运行 jj2lsj": "one per line, the wave functions of the transitions; run jj2lsj first",
    "输出格式": "Output format",
    "能级标记文件格式": "Energy label file format",
    "与 rtabtrans1 的输出格式一致": "the format written by rtabtrans1",
    "由 rtransition 的跃迁数据和 rtabtrans1 的能级标记生成跃迁表、寿命表 (transitiontable、lifetimetable 的 .tex / .txt) "
    "和 scatterplot.m。":
        "Make transition and lifetime tables (transitiontable, lifetimetable as .tex / .txt) and scatterplot.m from "
        "the transition data of rtransition and the energy labels of rtabtrans1.",
    "注意：跃迁文件里每种跃迁类型都要至少有一条跃迁，否则 rtabtrans2 会报 End of file 错误 "
    "(例如 odd–even 之间没有 M1 / E2 跃迁时，rtransition 只算 E1)。":
        "Note: every transition type in the file needs at least one transition, otherwise rtabtrans2 stops with "
        "End of file (e.g. compute only E1 in rtransition when there are no M1 / E2 transitions between odd and "
        "even).",
    "跃迁数据文件": "Transition data file",
    "rtransition 的 .t / .ct，可把多个文件合并成一个": "a .t / .ct file from rtransition; several may be concatenated",
    "  离子名称 (表格左列)": "  Ion name (left column)",
    "仅 ASCII 格式，如 Fe X": "ASCII format only, e.g. Fe X",
    "A 值打印下限": "Cut-off for printing A values",
    "跃迁 A 值占上能级总 A 值的最小比例": "Minimum fraction of the upper level's total A value",
    "跃迁数据已按波长排序": "Transition data sorted by wavelength",
    "波长小数位数 (1–6)": "Decimals for wavelengths (1–6)",
    "当前态组：{g}": "Current group: {g}",
    "已把 {a} 组的参数复制到 {b} 组 (名称中的 {a} 已替换为 {b})；请检查 {b} 的参考组态、2J 范围和能级。":
        "Copied the {a} parameters to {b} ({a} replaced by {b} in names); check the reference configurations, "
        "2J range and levels of {b}.",
    "确定用 {a} 组的参数覆盖 {b} 组吗？": "Overwrite the {b} parameters with those of {a}?",
    "已载入此目录上次的记录": "Loaded the last session of this directory",
    "此目录还没有记录，沿用当前参数": "No session in this directory yet; keeping the current parameters",
}


def T(s, **kw):
    """翻译界面文字；kw 用于格式化占位符。"""
    if LANG == "en":
        s = EN.get(s, s)
    return s.format(**kw) if kw else s


def set_lang(lang):
    global LANG
    LANG = lang if lang in ("zh", "en") else "zh"


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(**kw):
    cfg = load_config()
    cfg.update(kw)
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f)
    except OSError:
        pass


def default_bindir():
    """GRASP 程序目录：$GRASP_BINDIR → 上次使用的目录 → PATH 中 rmcdhf 所在目录
    → 本程序上一级目录的 bin (放在 GRASP 源码树中时)。"""
    candidates = [os.environ.get("GRASP_BINDIR", ""), load_config().get("bindir", "")]
    p = shutil.which("rmcdhf")
    if p:
        candidates.append(os.path.dirname(p))
    candidates.append(os.path.join(REPO_DIR, "bin"))
    for d in candidates:
        if d and os.path.isfile(os.path.join(d, "rmcdhf")):
            return d
    return os.environ.get("GRASP_BINDIR") or os.path.join(REPO_DIR, "bin")


def yn(flag):
    return "y" if flag else "n"


def nonblank_lines(s):
    return [ln.strip() for ln in s.splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
#  参数字段
#
#  界面根据 Step.fields 生成表单。各字段：
#    Note(text)                      说明文字
#    Entry(key, label, default, hint)
#    Check(key, label, default, hint)
#    Choice(key, label, options, hint)   options: [(值, 说明)], 值是传给程序的回答
#    Text(key, label, default, hint, lines)
#    Program(key, label, default)        可编辑的程序名下拉框 (bin 目录中的程序)
#    CsfLists(key)                       rcsfgenerate 的多个 CSF 列表
#
#  参数值 (vals) 是 {key: 值} 的 dict：Entry/Text/Choice/Program 为字符串，
#  Check 为 bool，CsfLists 为 [dict(configs, active, jmin, jmax, nexc)]。
# ---------------------------------------------------------------------------

class Note:
    def __init__(self, text):
        self.text = text


class Field:
    def __init__(self, key, label, default="", hint="", **kw):
        self.key, self.label, self.default, self.hint = key, label, default, hint
        self.__dict__.update(kw)


class Entry(Field):
    pass


class Check(Field):
    pass


class Text(Field):
    def __init__(self, key, label, default="", hint="", lines=4):
        super().__init__(key, label, default, hint, lines=lines)


class Choice(Field):
    def __init__(self, key, label, options, hint=""):
        super().__init__(key, label, options[0][0], hint, options=options)


class Program(Field):
    pass


class CsfLists(Field):
    LIST_FIELDS = [("active", "活跃轨道集", "各 l 的最高 n，如 5s,4p,3d"),
                   ("jmin", "2J 最小值", ""),
                   ("jmax", "2J 最大值", ""),
                   ("nexc", "激发数", "负数: 关联轨道总是双占据")]
    EMPTY = dict(configs="", active="", jmin="", jmax="", nexc="2")

    def __init__(self, key, default):
        super().__init__(key, "", default)


def normalize(field, value):
    """把保存的参数值转换为字段需要的类型（兼容旧版本保存的 "5 标准 (EOL)" 这类下拉框值）。"""
    if isinstance(field, Check):
        return bool(value)
    if isinstance(field, Choice):
        code = str(value).split()[0] if str(value).split() else ""
        return code if code in [o[0] for o in field.options] else field.default
    if isinstance(field, CsfLists):
        return [dict(CsfLists.EMPTY, **d) for d in value] or [dict(CsfLists.EMPTY)]
    return str(value)


# ---------------------------------------------------------------------------
#  各程序
#
#  一个"任务" (job) 是一个 dict:
#    title, prog, args, stdin, log, mpi,
#    pre / post: 动作列表, ("cp", src, dst) 或 ("run", [prog, args...])
# ---------------------------------------------------------------------------

class Step:
    key = ""         # 保存参数时使用的名称 (与语言无关)
    name = ""        # 标签页标题
    prog = ""        # 程序名
    mpi = False      # 是否有 <prog>_mpi 并行版本
    fields = []

    @classmethod
    def defaults(cls):
        return {f.key: f.default for f in cls.fields if isinstance(f, Field)}

    def stdin(self, v):
        return ""

    def args(self, v):
        return []

    def pre(self, v):
        return []

    def post(self, v):
        return []

    def log(self, v):
        return v.get("log", "").strip()

    def title(self, v):
        return self.prog

    def program(self, v):
        return self.prog

    def job(self, v):
        return dict(title=self.title(v), prog=self.program(v), args=self.args(v), stdin=self.stdin(v),
                    log=self.log(v), pre=self.pre(v), post=self.post(v), mpi=self.mpi)


def fortran_zero(s):
    """Fortran 表控读入的数是否为 0 (支持 9.6D1 这类写法；无法解析时视为非零)。"""
    try:
        return float(s.strip().lower().replace("d", "e") or "0") == 0
    except ValueError:
        return False


def answers(lines):
    return "\n".join(lines) + "\n"


class RNucleus(Step):
    key = name = prog = "rnucleus"
    fields = [
        Note("生成核数据文件 isodata。"),
        Entry("z", "原子序数 Z", "42"),
        Entry("a", "质量数 A", "96", "0 = 点核模型"),
        Check("revise", "修改默认的核半径 / 表面厚度", False),
        Entry("rms", "  均方根半径 (fm)", ""),
        Entry("skin", "  表面厚度 (fm)", "2.3"),
        Entry("mass", "中性原子质量 (amu)", "96", "0 = 静止核"),
        Entry("spin", "核自旋 I", "1"),
        Entry("mu", "磁偶极矩 (核磁子)", "1"),
        Entry("q", "电四极矩 (barn)", "1"),
    ]

    def stdin(self, v):
        lines = [v["z"], v["a"]]
        if not fortran_zero(v["a"]):        # 点核 (A = 0) 时不询问核半径
            lines.append(yn(v["revise"]))
            if v["revise"]:
                lines += [v["rms"], v["skin"]]
        return answers(lines + [v["mass"], v["spin"], v["mu"], v["q"]])


class RcsfGenerate(Step):
    key = name = prog = "rcsfgenerate"
    fields = [
        Note("生成 CSF 列表 rcsf.out。组态写法如 1s(2,i)2s(2,*)2p(1,*)：c=闭壳, i=不激发, *=活跃, "
             "数字=最小占据。可添加多个列表 (Generate more lists)。"),
        Choice("order", "轨道排序", [("*", "默认"), ("r", "反序"), ("s", "按对称性")]),
        Choice("core", "闭壳芯", [("0", "无芯"), ("1", "He"), ("2", "Ne"), ("3", "Ar"),
                                  ("4", "Kr"), ("5", "Xe"), ("6", "Rn")]),
        CsfLists("lists", [dict(configs="1s(2,i)2s(2,i)2p(1,i)\n1s(2,i)2p(3,i)",
                                active="2s,2p", jmin="1", jmax="3", nexc="0")]),
        Entry("saveas", "保存 rcsf.out 为", "odd2.c", "留空则不复制"),
    ]

    def stdin(self, v):
        lines = [v["order"], v["core"]]
        for k, lst in enumerate(v["lists"]):
            lines += nonblank_lines(lst["configs"])
            lines += ["", lst["active"].strip(), f'{lst["jmin"].strip()},{lst["jmax"].strip()}',
                      lst["nexc"].strip(), "y" if k < len(v["lists"]) - 1 else "n"]
        return answers(lines)

    def post(self, v):
        s = v["saveas"].strip()
        return [("cp", "rcsf.out", s)] if s else []

    def title(self, v):
        s = v["saveas"].strip()
        return f"rcsfgenerate -> {s}" if s else "rcsfgenerate"


class RcsfInteract(Step):
    key = name = prog = "rcsfinteract"
    fields = [
        Note("从完整 CSF 列表中只保留与多参考组态有相互作用的 CSF。读取 rcsfmr.inp (多参考) 和 rcsf.inp (完整列表)，"
             "输出 rcsf.out。"),
        Entry("mr", "多参考 CSF 文件 → rcsfmr.inp", "odd2.c", "留空则直接用现有 rcsfmr.inp"),
        Entry("full", "完整 CSF 文件 → rcsf.inp", "odd.c", "留空则直接用现有 rcsf.inp"),
        Choice("ham", "按哪种哈密顿量判断相互作用", [("1", "Dirac-Coulomb"), ("2", "Dirac-Coulomb-Breit")]),
        Entry("saveas", "结果 rcsf.out 保存为", "", "如 odd.c；与完整列表同名时覆盖原列表；留空则不复制"),
    ]

    def stdin(self, v):
        return answers([v["ham"]])

    def pre(self, v):
        acts = []
        if v["mr"].strip():
            acts.append(("cp", v["mr"].strip(), "rcsfmr.inp"))
        if v["full"].strip():
            acts.append(("cp", v["full"].strip(), "rcsf.inp"))
        return acts

    def post(self, v):
        s = v["saveas"].strip()
        return [("cp", "rcsf.out", s)] if s else []

    def title(self, v):
        s = v["saveas"].strip()
        return f"rcsfinteract -> {s}" if s else "rcsfinteract"


class RcsfSplit(Step):
    key = name = prog = "rcsfsplit"
    fields = [
        Note("按轨道集把 name.c 拆分为 name<标签>.c 等多个文件。"),
        Entry("state", "CSF 文件名 (不含 .c)", "odd"),
        Text("splits", "拆分 (每行: 轨道集  标签)",
             "3s,3p,3d 3\n4s,4p,4d,4f 4\n5s,5p,5d,5f,5g 5\n6s,6p,6d,6f,6g,6h 6", lines=6),
    ]

    def stdin(self, v):
        rows = [ln.rsplit(None, 1) for ln in nonblank_lines(v["splits"])]
        lines = [v["state"], str(len(rows))]
        for orbs, label in rows:
            lines += [orbs, label]
        return answers(lines)

    def title(self, v):
        return f"rcsfsplit {v['state']}"


class RAngular(Step):
    key = name = prog = "rangular"
    mpi = True
    fields = [
        Note("计算角系数 (mcp.*)。读取 rcsf.inp。"),
        Entry("csf", "复制此 CSF 文件为 rcsf.inp", "odd2.c", "留空则直接用现有 rcsf.inp"),
    ]

    def stdin(self, v):
        return "y\n"

    def pre(self, v):
        s = v["csf"].strip()
        return [("cp", s, "rcsf.inp")] if s else []

    def title(self, v):
        s = v["csf"].strip()
        return f"rangular ({s})" if s else "rangular"


class RWfnEstimate(Step):
    key = name = prog = "rwfnestimate"
    fields = [
        Note("生成初始径向波函数 rwfn.inp。可先从已有 .w 文件读取部分轨道，其余用 Thomas-Fermi 或屏蔽类氢估计。"),
        Check("use_file", "先从已有波函数文件读取 (GRASP92 File)", False),
        Entry("wfile", "  波函数文件", "odd2.w", "如 odd2.w，空则为 rwfn.out"),
        Entry("forbs", "  读取的轨道", "*", "* = 全部"),
        Choice("method", "其余轨道的估计方法", [("3", "屏蔽类氢 (Screened Hydrogenic)"), ("2", "Thomas-Fermi"),
                                               ("4", "屏蔽类氢，关联轨道增加 Z (custom Z)")]),
        Entry("orbs", "  轨道", "*"),
        Entry("delz", "  关联轨道的 Z 增加量", "0", "仅方法 4"),
    ]

    def stdin(self, v):
        lines = ["y"]
        if v["use_file"]:
            lines += ["1", v["wfile"].strip(), v["forbs"]]
        lines += [v["method"], v["orbs"]]
        if v["method"] == "4":              # 方法 4 在轨道列表之后询问 Z 的增加量
            lines.append(v["delz"])
        return answers(lines)


class RMcdhf(Step):
    key = name = prog = "rmcdhf"
    mpi = True
    fields = [
        Note("自洽场计算 (读取 rcsf.inp, rwfn.inp, mcp.*；输出 rwfn.out, rmix.out)。"
             "每个 J 对称块一行能级号，例如 1,2,3 或 1-3。"),
        Check("mem", "使用内存版本 rmcdhf_mem", False, "角系数一次读入内存：更快，但更占内存"),
        Text("levels", "各块要优化的能级", "1\n1", "每块一行", lines=3),
        Choice("weights", "能级权重", [("5", "标准 (EOL)"), ("1", "等权重"), ("9", "用户指定")]),
        Entry("uweights", "  用户权重", "", "选 9 时填写, 如 1,1,2"),
        Entry("vary", "变分轨道", "*", "如 *  或 3*  或 2s,2p*"),
        Entry("spec", "谱学轨道 (非关联轨道)", "*", "空 = 无"),
        Entry("nscf", "最大 SCF 迭代次数", "100"),
        Entry("log", "输出日志文件", "outodd_rmcdhf_initial", "空 = 只显示在窗口"),
        Entry("save", "结束后 rsave 保存为", "odd2", "空 = 不保存"),
    ]

    def stdin(self, v):
        lines = ["y"] + nonblank_lines(v["levels"]) + [v["weights"]]
        if v["weights"] == "9":
            lines.append(v["uweights"])
        return answers(lines + [v["vary"], v["spec"], v["nscf"]])

    def program(self, v):
        # MPI 时在此基础上加 _mpi：rmcdhf_mpi / rmcdhf_mem_mpi
        return "rmcdhf_mem" if v["mem"] else "rmcdhf"

    def post(self, v):
        s = v["save"].strip()
        return [("run", ["rsave", s])] if s else []

    def title(self, v):
        s = v["save"].strip()
        return f"{self.program(v)} -> {s}" if s else self.program(v)


class RSave(Step):
    key = name = prog = "rsave"
    fields = [
        Note("把 rcsf.inp / rwfn.out / rmix.out 等保存为 name.c / name.w / name.m ..."),
        Entry("state", "态名称", "odd2"),
    ]

    def args(self, v):
        return [v["state"].strip()]

    def title(self, v):
        return f"rsave {v['state']}"


class RCi(Step):
    key = name = prog = "rci"
    mpi = True
    fields = [
        Note("组态相互作用计算 (可含 Breit 与 QED)。读取 name.c, name.w，输出 name.cm 等。"),
        Entry("state", "态名称", "oddCI6"),
        Entry("copyfrom", "先从此态复制 .c/.w", "odd6", "空 = 不复制"),
        Check("trans", "包含横向 (Breit) 相互作用", True),
        Check("modfreq", "修改横向光子频率", True),
        Entry("factor", "  频率缩放因子", "1.d-6"),
        Check("vp", "真空极化 (Vacuum Polarisation)", True),
        Check("nms", "正常质量移动 (NMS)", False),
        Check("sms", "特殊质量移动 (SMS)", False),
        Check("se", "估计自能 (Self-energy)", True),
        Entry("nqed", "  自能计算的最大 n (≤8)", "4"),
        Text("levels", "各块计算的能级", "1\n1", "每块一行", lines=3),
        Entry("log", "输出日志文件", "outodd_rci"),
    ]

    def stdin(self, v):
        lines = ["y", v["state"].strip(), yn(v["trans"]), yn(v["modfreq"])]
        if v["modfreq"]:
            lines.append(v["factor"])
        lines += [yn(v["vp"]), yn(v["nms"]), yn(v["sms"]), yn(v["se"])]
        if v["se"]:
            lines.append(v["nqed"])
        return answers(lines + nonblank_lines(v["levels"]))

    def pre(self, v):
        src, dst = v["copyfrom"].strip(), v["state"].strip()
        if not src:
            return []
        return [("cp", f"{src}.c", f"{dst}.c"), ("cp", f"{src}.w", f"{dst}.w")]

    def title(self, v):
        return f"rci {v['state']}"


class Jj2lsj(Step):
    key = name = prog = "jj2lsj"
    fields = [
        Note("把 jj 耦合的混合系数变换到 LSJ 耦合，给出 LSJ 标记。"),
        Entry("state", "态名称", "odd2"),
        Check("ci", "混合系数来自 CI 计算 (.cm)", False, "否则读 .m"),
        Check("unique", "需要唯一标记 (unique labeling)", True),
        Entry("log", "输出日志文件", ""),
    ]

    def stdin(self, v):
        return answers([v["state"].strip(), yn(v["ci"]), yn(v["unique"]), "y"])

    def title(self, v):
        return f"jj2lsj {v['state']}"


class RHfs(Step):
    key = name = prog = "rhfs"
    fields = [
        Note("计算超精细结构常数 A、B 和朗德 g 因子。读取 isodata (核自旋 I、磁偶极矩、电四极矩在 rnucleus 中设置)、"
             "name.c、name.w、name.(c)m；输出 name.(c)h、name.(c)hoffd。"),
        Entry("state", "态名称", "oddCI6"),
        Check("ci", "混合系数来自 CI 计算", True, "否则读 .m"),
        Check("lsj", "结束后运行 rhfs_lsj，用 LSJ 标记输出结果", False, "需先运行 jj2lsj；输出 name.(c)hlsj"),
        Check("sort", "  按能量排序", True),
        Entry("log", "输出日志文件", ""),
    ]

    def stdin(self, v):
        return answers(["y", v["state"].strip(), yn(v["ci"])])

    def post(self, v):
        if not v["lsj"]:
            return []
        return [("run", ["rhfs_lsj"], answers([v["state"].strip(), yn(v["ci"]), yn(v["sort"])]))]

    def title(self, v):
        return f"rhfs {v['state']}"


class RIs4(Step):
    key = name = prog = "ris4"
    fields = [
        Note("计算同位素移位：正常 / 特殊质量移位参数和场移电子因子。读取 isodata、name.c、name.w、name.(c)m；"
             "输出 name.(c)i。"),
        Entry("state", "态名称", "oddCI6"),
        Check("ci", "混合系数来自 CI 计算", True, "否则读 .m"),
        Check("higher", "计算高阶场移电子因子", True),
        Check("save", "保存角系数 (name.IOB / name.ITB)，以后重复计算时直接读取", True,
              "这两个文件已存在时程序不询问"),
        Entry("log", "输出日志文件", ""),
    ]

    def stdin(self, v):
        # 最后一问只在角系数文件不存在时出现；多给的一行不会被读取
        return answers(["y", v["state"].strip(), yn(v["ci"]), yn(v["higher"]), yn(v["save"])])

    def title(self, v):
        return f"ris4 {v['state']}"


class RLevels(Step):
    key = name = prog = "rlevels"
    fields = [
        Note("列出能级。可给多个 .m / .cm 文件。"),
        Entry("files", "混合系数文件", "odd2.m even2.m", "空格分隔"),
        Entry("log", "输出日志文件", ""),
    ]

    def args(self, v):
        return shlex.split(v["files"])


class RTableLevels(Step):
    key = name = prog = "rtablevels"
    fields = [
        Note("把 rlevels 生成的能级文件整理成 LaTeX 和 ASCII 能级表 (energytablelatex.tex、energytableascii.txt)。"
             "每个文件占表中一列，能级标记和顺序以最后一个文件为准。"),
        Entry("nskip", "标签开头跳过的字符数", "0", "如标签以闭壳芯 1s(2). 开头，跳过 6 个字符"),
        Text("files", "能级文件", "energy3", "每行一个，按活跃集从小到大；在 rlevels 页用“输出日志文件”生成", lines=4),
    ]

    def stdin(self, v):
        files = nonblank_lines(v["files"])
        return answers([v["nskip"], str(len(files))] + files)


class RTabTrans1(Step):
    key = name = prog = "rtabtrans1"
    fields = [
        Note("为 rtabtrans2 生成能级标记文件 energylabel.latex / energylabel.ascii。读取各混合系数文件及其 jj2lsj 标记 "
             "(name.lsj.lbl)。"),
        Text("files", "混合系数文件 (.m / .cm)", "oddCI6.cm\nevenCI6.cm", "每行一个，与计算跃迁的波函数对应；需先运行 jj2lsj",
             lines=3),
        Entry("nskip", "标签开头跳过的字符数", "0", "如标签以闭壳芯 1s(2). 开头，跳过 6 个字符"),
        Choice("fmt", "输出格式", [("0", "LaTeX"), ("1", "ASCII")]),
    ]

    def stdin(self, v):
        # 文件名逐行给出，空行结束
        return answers(nonblank_lines(v["files"]) + ["", v["nskip"], v["fmt"]])


class RTabTrans2(Step):
    key = name = prog = "rtabtrans2"
    fields = [
        Note("由 rtransition 的跃迁数据和 rtabtrans1 的能级标记生成跃迁表、寿命表 (transitiontable、lifetimetable 的 .tex / .txt) "
             "和 scatterplot.m。"),
        Note("注意：跃迁文件里每种跃迁类型都要至少有一条跃迁，否则 rtabtrans2 会报 End of file 错误 "
             "(例如 odd–even 之间没有 M1 / E2 跃迁时，rtransition 只算 E1)。"),
        Entry("tfile", "跃迁数据文件", "oddCI6.evenCI6.ct", "rtransition 的 .t / .ct，可把多个文件合并成一个"),
        Choice("fmt", "能级标记文件格式", [("0", "LaTeX"), ("1", "ASCII")], "与 rtabtrans1 的输出格式一致"),
        Entry("ion", "  离子名称 (表格左列)", "", "仅 ASCII 格式，如 Fe X"),
        Entry("cutoff", "A 值打印下限", "0"),
        Entry("frac", "跃迁 A 值占上能级总 A 值的最小比例", "0"),
        Check("sorted", "跃迁数据已按波长排序", True),
        Entry("digits", "波长小数位数 (1–6)", "3"),
    ]

    def stdin(self, v):
        lines = [v["tfile"].strip(), v["fmt"]]
        if v["fmt"] == "1":                 # ASCII 时询问表格左列的离子名称
            lines.append(v["ion"])
        return answers(lines + [v["cutoff"], v["frac"], yn(v["sorted"]), v["digits"]])


class RBioTransform(Step):
    key = name = prog = "rbiotransform"
    mpi = True
    fields = [
        Note("跃迁计算前的双正交变换。"),
        Check("ci", "混合系数来自 CI 计算", True),
        Entry("init", "初态名称", "oddCI6"),
        Entry("final", "末态名称", "evenCI6"),
        Entry("log", "输出日志文件", "out_rbiotransform"),
    ]

    def stdin(self, v):
        return answers(["y", yn(v["ci"]), v["init"], v["final"], "y"])


class RTransition(Step):
    key = name = prog = "rtransition"
    mpi = True
    fields = [
        Note("计算跃迁参数 (需先运行 rbiotransform)。"),
        Check("ci", "混合系数来自 CI 计算", True),
        Entry("init", "初态名称", "oddCI6"),
        Entry("final", "末态名称", "evenCI6"),
        Entry("kind", "跃迁类型", "E1", "如 E1  或 E1,M2"),
        Check("m1_diffj", "M1 跃迁只计算不同 J 的能级之间", False, "跃迁类型含 M1 时询问"),
        Check("e2_diffj", "E2 跃迁只计算不同 J 的能级之间", False, "跃迁类型含 E2 时询问"),
        Entry("log", "输出日志文件", "out_transition"),
    ]

    def stdin(self, v):
        kind = v["kind"].strip().upper()        # rtransition 只认大写的 E / M
        kinds = [k for k in re.split(r"[\s,;]+", kind) if k]
        lines = ["y", yn(v["ci"]), v["init"], v["final"], kind]
        # 按书写顺序，每个 M1 / E2 各追问一次 (rtransition 的 getrmp)
        for k in kinds:
            if k == "M1":
                lines.append(yn(v["m1_diffj"]))
            elif k == "E2":
                lines.append(yn(v["e2_diffj"]))
        return answers(lines)


class Custom(Step):
    key = "custom"
    name = "自定义"
    fields = [
        Note("运行任意 GRASP 程序，手动填写交互输入（每行回答一个提问）。"),
        Program("prog", "程序", "rhfs"),
        Entry("args", "命令行参数", ""),
        Text("stdin", "输入 (stdin)", "", lines=10),
        Entry("log", "输出日志文件", ""),
    ]

    def program(self, v):
        return v["prog"].strip()

    def title(self, v):
        return v["prog"].strip()

    def args(self, v):
        return shlex.split(v["args"])

    def stdin(self, v):
        s = v["stdin"]
        return s if s.endswith("\n") or not s else s + "\n"


STEPS = [RNucleus(), RcsfGenerate(), RcsfInteract(), RcsfSplit(), RAngular(), RWfnEstimate(), RMcdhf(), RSave(),
         RCi(), Jj2lsj(), RHfs(), RIs4(), RLevels(), RTableLevels(), RTabTrans1(), RTabTrans2(),
         RBioTransform(), RTransition(), Custom()]

# 界面左侧程序列表的功能分组 (每个程序恰好出现一次)
STEP_GROUPS = [
    ("核与组态", ["rnucleus", "rcsfgenerate", "rcsfinteract", "rcsfsplit"]),
    ("自洽场与 CI", ["rangular", "rwfnestimate", "rmcdhf", "rsave", "rci"]),
    ("性质与跃迁", ["rhfs", "ris4", "rbiotransform", "rtransition"]),
    ("结果与工具", ["jj2lsj", "rlevels", "rtablevels", "rtabtrans1", "rtabtrans2", "custom"]),
]
assert sorted(k for _, keys in STEP_GROUPS for k in keys) == sorted(s.key for s in STEPS)


# ---------------------------------------------------------------------------
#  态组 (宇称)
#
#  odd 与 even 各有一套参数的程序页；其余程序页 (rnucleus, rlevels, rtablevels,
#  rbiotransform, rtransition, 自定义) 两组共用。文件名中的组名 (odd2.c, outodd_rci,
#  oddCI6 …) 在两组之间按名称替换对应。
# ---------------------------------------------------------------------------

GROUPS = ("odd", "even")
GROUP_STEPS = ("rcsfgenerate", "rcsfinteract", "rcsfsplit", "rangular", "rwfnestimate", "rmcdhf", "rsave", "rci",
               "jj2lsj", "rhfs", "ris4")

# even 组与 odd 组默认值中物理内容不同的部分 (grasptest/case1 的 2s2p(2))
EVEN_DEFAULTS = {
    "rcsfgenerate": dict(lists=[dict(configs="1s(2,i)2s(1,i)2p(2,i)", active="2s,2p",
                                     jmin="1", jmax="5", nexc="0")]),
    "rmcdhf": dict(levels="1,2,3\n1,2,3\n1,2"),
    "rci": dict(levels="1,2,3\n1,2,3\n1,2"),
}


def rename_group(value, src, dst):
    """把参数值 (字符串 / dict / list) 中的组名 src 替换为 dst，如 odd2.c -> even2.c。"""
    if isinstance(value, str):
        return value.replace(src, dst)
    if isinstance(value, dict):
        return {k: rename_group(v, src, dst) for k, v in value.items()}
    if isinstance(value, list):
        return [rename_group(v, src, dst) for v in value]
    return value


def group_defaults(group):
    """某个态组各程序页的默认参数 {step key: vals}。"""
    steps = {s.key: s for s in STEPS}
    out = {}
    for key in GROUP_STEPS:
        vals = rename_group(steps[key].defaults(), GROUPS[0], group)
        if group == "even":
            vals.update(EVEN_DEFAULTS.get(key, {}))
        out[key] = vals
    return out


# ---------------------------------------------------------------------------
#  工作目录中的记录：打开目录时恢复上次的参数和流程
# ---------------------------------------------------------------------------

SESSION_FILE = ".grasp_gui.json"


def load_session(workdir):
    try:
        with open(os.path.join(workdir, SESSION_FILE)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_session(workdir, data):
    if not os.path.isdir(workdir):
        return False
    path = os.path.join(workdir, SESSION_FILE)
    try:
        with open(path + ".tmp", "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(path + ".tmp", path)     # 先写临时文件，避免中断时留下不完整的记录
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
#  脚本
# ---------------------------------------------------------------------------

def action_sh(a):
    """动作的 shell 写法：("cp", src, dst) 或 ("run", argv[, stdin])。"""
    if a[0] == "cp":
        return f"cp {shlex.quote(a[1])} {shlex.quote(a[2])}"
    cmd = " ".join(shlex.quote(x) for x in a[1])
    if len(a) > 2 and a[2]:
        return f"{cmd} <<'EOF'\n{a[2]}EOF"
    return cmd


def describe(job, mpi_prefix=""):
    """任务的 shell 等价写法，用于预览和导出脚本。

    mpi_prefix 非空 (如 "mpirun -np 4") 时，有并行版本的程序写成 "<mpi_prefix> <prog>_mpi"。
    """
    out = [action_sh(a) for a in job["pre"]]
    args = " ".join(shlex.quote(x) for x in job["args"])
    if mpi_prefix and job.get("mpi"):
        cmd = f"{mpi_prefix} {job['prog']}_mpi {args}".rstrip()
    else:
        cmd = f"{shlex.quote(job['prog'])} {args}".rstrip()
    if job["log"]:
        cmd += f" > {shlex.quote(job['log'])}"
    if job["stdin"].strip():
        out.append(f"{cmd} <<'EOF'\n{job['stdin']}EOF")
    else:
        out.append(cmd + " < /dev/null")
    out += [action_sh(a) for a in job["post"]]
    return "\n".join(out)


def shell_script(pipeline, bindir, workdir, mpi_prefix="", mpitmp="tmp_mpi"):
    body = ["#!/bin/sh", "set -x", "",
            f"export PATH={shlex.quote(bindir)}:$PATH",
            f"cd {shlex.quote(workdir)}", ""]
    if mpi_prefix:
        body += [f"export MPI_TMP=\"$PWD\"/{shlex.quote(mpitmp or 'tmp_mpi')}", 'mkdir -p "$MPI_TMP"',
                 "# hwloc's GL plugin makes mpirun hang under WSLg",
                 'export HWLOC_COMPONENTS="${HWLOC_COMPONENTS:--gl}"', ""]
    for i, job in enumerate(pipeline, 1):
        body += [f"# {i}. {job['title']}", describe(job, mpi_prefix), ""]
    return "\n".join(body)


def slurm_script(pipeline, s):
    """s: SLURM_DEFAULTS 中各项的取值。"""
    s = {k: str(s.get(k, d)).strip() for k, d in SLURM_DEFAULTS.items()}
    lines = ["#!/bin/bash", f"#SBATCH --job-name={s['job'] or 'grasp'}"]
    if s["partition"]:
        lines.append(f"#SBATCH --partition={s['partition']}")
    lines += [f"#SBATCH --nodes={s['nodes'] or 1}", f"#SBATCH --ntasks-per-node={s['ntasks'] or 1}"]
    if s["time"]:
        lines.append(f"#SBATCH --time={s['time']}")
    if s["mem"]:
        lines.append(f"#SBATCH --mem={s['mem']}")
    lines.append("#SBATCH --output=%x-%j.out")
    if s["mail"]:
        lines += [f"#SBATCH --mail-user={s['mail']}", "#SBATCH --mail-type=END,FAIL"]
    lines += [f"#SBATCH {x if x.startswith('-') else '--' + x}" for x in nonblank_lines(s["extra"])]
    lines += ["", "# Generated by the GRASP GUI (gui/grasp_gui.py).",
              "# Upload this script together with the input files (isodata, *.c, *.w ...)",
              "# to one directory on the server and submit it there with: sbatch <this script>",
              "", "set -e", ""]
    lines += nonblank_lines(s["modules"])
    lines += [f"export PATH={s['bindir']}:$PATH",
              'cd "$SLURM_SUBMIT_DIR"',
              f"export MPI_TMP={s['mpitmp'] or '$SLURM_SUBMIT_DIR/tmp_mpi'}",
              'mkdir -p "$MPI_TMP"',
              "",
              'echo "Job $SLURM_JOB_ID on $SLURM_JOB_NODELIST, $SLURM_NTASKS tasks, started $(date)"',
              "set -x", ""]
    for i, job in enumerate(pipeline, 1):
        lines += [f"# {i}. {job['title']}", describe(job, s["mpirun"]), ""]
    lines += ["set +x", 'echo "Finished $(date)"', ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  运行
# ---------------------------------------------------------------------------

def check_mcp(cwd, np, mpitmp):
    """检查 rmcdhf 所需的 rangular 角系数文件，返回错误信息；没有问题时返回 None。

    串行 rangular 写 <cwd>/mcp.30 …；rangular_mpi 写 <MPI_TMP>/<rank>/mcp<rank>.30 …，
    rmcdhf(_mpi) 只认与自己相同的方式和进程数，否则会读不到角系数而异常退出。
    """
    serial = os.path.join(cwd, "mcp.30")
    tmp = os.path.join(cwd, mpitmp)

    def rank_file(i):
        return os.path.join(tmp, f"{i:03d}", f"mcp{i:03d}.30")

    k = 0                                   # rangular_mpi 用过的进程数
    while os.path.isfile(rank_file(k)):
        k += 1
    mismatch = T("角系数文件是 rangular 用 {k} 个 MPI 进程生成的 (在 {d} 中)，rmcdhf 必须使用相同的进程数："
                 "请把 MPI 进程数设为 {k}，或用 {np} 个进程重新运行 rangular。", k=k, d=tmp, np=np)
    missing = T("找不到 rangular 生成的角系数文件 (mcp.*)：请先运行 rangular。")
    if np <= 1:
        if not os.path.isfile(serial):
            return mismatch if k else missing
        mcp = serial
    else:
        if k != np:
            if k:
                return mismatch
            if os.path.isfile(serial):
                return T("角系数文件是串行 rangular 生成的 (工作目录中的 mcp.*)，rmcdhf 不能用 {np} 个 MPI 进程运行："
                         "请把 MPI 进程数设为 1，或用 {np} 个进程重新运行 rangular。", np=np)
            return missing
        mcp = rank_file(0)
    rcsf = os.path.join(cwd, "rcsf.inp")
    if os.path.isfile(rcsf) and os.path.getmtime(rcsf) > os.path.getmtime(mcp) + 1:
        return T("rcsf.inp 比角系数文件新：请先对当前的 rcsf.inp 运行 rangular。")
    return None


class Runner:
    """在后台线程中依次执行任务，输出通过 emit(text, tag) 送回界面（tag: "", head, info, err）。

    cfg: dict(bindir, cwd, np, mpirun, mpitmp, nice)
    """

    def __init__(self, emit):
        self.emit = emit
        self.proc = None
        self.stopped = False

    def resolve(self, bindir, prog):
        p = os.path.join(bindir, prog)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
        p = shutil.which(prog)
        if not p:
            raise FileNotFoundError(T("找不到程序 {p} (bin 目录: {d})", p=prog, d=bindir))
        return p

    def exec_cmd(self, argv, cfg, stdin="", log="", mpi=False):
        bindir, cwd = cfg["bindir"], cfg["cwd"]
        env = dict(os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", ""))
        if getattr(sys, "frozen", False):
            # PyInstaller 打包的程序把 LD_LIBRARY_PATH 指向自带的库；子进程 (GRASP、mpirun) 用回原来的值
            orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
            if orig is None:
                env.pop("LD_LIBRARY_PATH", None)
            else:
                env["LD_LIBRARY_PATH"] = orig
        if mpi and cfg["np"] > 1:
            mpitmp = os.path.join(cwd, cfg["mpitmp"])
            os.makedirs(mpitmp, exist_ok=True)
            env["MPI_TMP"] = mpitmp
            # hwloc 的 GL 插件会连接图形显示，在 WSLg 下使 mpirun 启动时卡住
            env.setdefault("HWLOC_COMPONENTS", "-gl")
            argv = (shlex.split(cfg["mpirun"]) + ["-np", str(cfg["np"]),
                    self.resolve(bindir, argv[0] + "_mpi")] + list(argv[1:]))
        else:
            argv = [self.resolve(bindir, argv[0])] + list(argv[1:])
        if cfg.get("nice") and shutil.which("nice"):
            argv = ["nice", "-n", "10"] + argv     # 计算占满 CPU 时界面仍保持流畅
        # 独立进程组：停止时连同 mpirun 启动的各个进程一起结束
        self.proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
                                     start_new_session=True)
        threading.Thread(target=self._feed, args=(self.proc, stdin.encode()), daemon=True).start()
        # 按块读取（而不是逐行），大量输出时显著减少界面刷新次数；
        # 也能显示不以换行结尾的提示
        fd = self.proc.stdout.fileno()
        dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        logf = open(os.path.join(cwd, log), "wb") if log else None
        try:
            while True:
                data = os.read(fd, 65536)
                if not data:
                    break
                if logf:
                    logf.write(data)
                self.emit(dec.decode(data), "")
            self.emit(dec.decode(b"", final=True), "")
        finally:
            if logf:
                logf.close()
        rc = self.proc.wait()
        self.proc = None
        return rc

    @staticmethod
    def _feed(proc, data):
        try:
            proc.stdin.write(data)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    def run_job(self, job, cfg):
        self.emit(f"\n===== {job['title']} =====\n", "head")
        for a in job["pre"]:
            self.do_action(a, cfg)
        if job["prog"] in ("rmcdhf", "rmcdhf_mem"):
            err = check_mcp(cfg["cwd"], cfg["np"], cfg["mpitmp"])
            if err:
                raise RuntimeError(err)
        rc = self.exec_cmd([job["prog"]] + job["args"], cfg, job["stdin"], job["log"], job.get("mpi"))
        if job["log"]:
            self.emit(T("[输出已写入 {f}]", f=job["log"]) + "\n", "info")
        if rc != 0 or self.stopped:
            raise RuntimeError(T("{p} 退出码 {rc}", p=job["prog"], rc=rc))
        for a in job["post"]:
            self.do_action(a, cfg)

    def do_action(self, a, cfg):
        self.emit(f"$ {action_sh(a)}\n", "info")
        if a[0] == "cp":
            src, dst = os.path.join(cfg["cwd"], a[1]), os.path.join(cfg["cwd"], a[2])
            if os.path.abspath(src) != os.path.abspath(dst):     # 如 CSF 文件直接填成 rcsf.inp
                shutil.copyfile(src, dst)
        else:
            rc = self.exec_cmd(a[1], cfg, a[2] if len(a) > 2 else "")
            if rc != 0:
                raise RuntimeError(T("{p} 退出码 {rc}", p=a[1][0], rc=rc))

    def run_all(self, jobs, cfg, done):
        # 绝对路径：MPI_TMP 由工作目录拼出，程序又在工作目录中启动，相对路径会被解析两次
        cfg = dict(cfg, cwd=os.path.abspath(cfg["cwd"]))
        self.stopped = False
        ok = True
        try:
            for job in jobs:
                if self.stopped:
                    break
                self.run_job(job, cfg)
        except Exception as e:  # noqa: BLE001 - 所有错误都报告给界面
            ok = False
            self.emit(T("\n*** 错误: {e}\n", e=e), "err")
        if self.stopped:
            ok = False
            self.emit(T("\n*** 已停止\n"), "err")
        done(ok)

    def stop(self):
        self.stopped = True
        proc = self.proc
        if proc:
            self._signal(proc, signal.SIGTERM)
            # mpirun 卡住时可能不响应 SIGTERM，5 秒后强制结束整个进程组
            threading.Timer(5, self._signal, args=(proc, signal.SIGKILL)).start()

    def kill(self, grace=2):
        """立即结束当前程序（退出界面时使用）：先 SIGTERM，grace 秒后 SIGKILL。"""
        self.stopped = True
        proc = self.proc
        if proc:
            self._signal(proc, signal.SIGTERM)
            try:
                proc.wait(grace)
            except subprocess.TimeoutExpired:
                self._signal(proc, signal.SIGKILL)

    @staticmethod
    def _signal(proc, sig):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
