#!/usr/bin/env python3
"""Make the README screenshots (docs/images/{en,zh}_*.png).

    tools/make_screenshots.py GRASP_BIN [--lang en|zh] [--out DIR]

Imports example 4 of the GRASP2018 manual through the GUI and runs it (about 2 minutes with one process), computes
an E1 transition in the level diagram and grabs the calculation tab, the level diagram, the radial wave functions
and the import dialog. Without --lang both languages are made, each in its own process. Runs without a display
(offscreen) in a temporary home directory, so the user's settings are not touched; paths in the pictures are shown
as /home/user/... and /opt/grasp/bin. Needs PySide6 >= 6.8.3 and a compiled GRASP2018 (GRASP_BIN).
"""
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = "example4"
WINDOW = (1280, 820)
SCALE = "1.5"                  # device pixel ratio of the pictures: sharp on high-resolution screens


def shoot(bindir, lang, out):
    home = tempfile.mkdtemp(prefix="grasp_shots_")
    os.environ.update(QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR=SCALE, HOME=home)
    sys.path.insert(0, ROOT)
    import grasp_core as core
    core.set_lang(lang)
    core.save_config(lang=lang)
    import calc_panel as cp
    import grasp_config
    import grasp_gui as g
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit

    app = QApplication([])
    app.setApplicationName("GRASP GUI")
    g.load_fonts()
    app.window_style = g.WindowStyle(app, frames=False)
    os.makedirs(out, exist_ok=True)

    def wait(busy, limit=1800):
        t = time.time()
        while busy() and time.time() - t < limit:
            app.processEvents()
            time.sleep(0.05)
        for _ in range(5):
            app.processEvents()

    def grab(w, name):
        """Neutral paths instead of the temporary home and the GRASP directory; the texts are restored afterwards."""
        app.processEvents()
        changed = []
        for c in [w] + w.findChildren(QLineEdit) + w.findChildren(QLabel):
            if isinstance(c, (QLineEdit, QLabel)) and (home in c.text() or bindir in c.text()):
                changed.append((c, c.text()))
                c.blockSignals(True)
                c.setText(c.text().replace(home, "/home/user").replace(bindir, "/opt/grasp/bin"))
        app.processEvents()
        path = os.path.join(out, f"{lang}_{name}.png")
        w.grab().save(path)
        print("written", path)
        for c, text in changed:
            c.setText(text)
            c.blockSignals(False)

    win = g.MainWindow(home)
    win.resize(*WINDOW)
    win.show()
    win.run.bindir_edit.setText(bindir)
    win.run.np_spin.setValue(1)

    # import dialog, then import the example
    ids = [d["id"] for d in grasp_config.list_demos()]

    def show_dialog(dlg):
        dlg.list.setCurrentRow(ids.index(DEMO))
        dlg.resize(1100, 700)
        dlg.show()
        grab(dlg, "examples")
        return QDialog.Accepted
    cp.ConfigDialog.exec = show_dialog
    win.calc.import_demo()
    wd = win.cur_workdir

    t = time.time()
    win.calc.run_pipeline()
    wait(lambda: win.calc.busy or time.time() - t < 0.5)
    print(f"{DEMO}: {time.time() - t:.0f} s, {win.statusBar().currentMessage()}")

    # calculation: rmcdhf of the odd group, with the input of its last use in the pipeline
    calc = win.calc
    win.show_tab("calc")
    calc.switch_group("odd")
    calc.nav.setCurrentWidget(next(f for f in calc.forms if f.step.key == "rmcdhf"))
    calc.plist.setCurrentRow(max(i for i, j in enumerate(calc.pipeline)
                                 if j.get("step") == "rmcdhf" and j.get("group") == "odd"))
    calc.show_job()
    calc.split.setSizes([480, 520])
    grab(win, "calculation")

    # levels: drag from the ground state to odd4 1- #2 and compute the transition
    win.show_tab("levels")
    v = win.panels["levels"]
    wait(lambda: False)
    v.diagram.grab()                            # paint once, so that the level positions are known
    lo = v.key_by_id[(os.path.join(wd, "even4.cm"), 0, 1, 1)]
    up = v.key_by_id[(os.path.join(wd, "odd4.cm"), 2, -1, 2)]
    a, b = (QPoint(*map(int, v.diagram.centers[k])) for k in (lo, up))
    QTest.mousePress(v.diagram, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 6):
        p = QPointF(a + (b - a) * i / 5)
        QApplication.sendEvent(v.diagram, QMouseEvent(QEvent.MouseMove, p, v.diagram.mapToGlobal(p),
                                                      Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    QTest.mouseRelease(v.diagram, Qt.LeftButton, Qt.NoModifier, b)
    QTest.mouseClick(v.tr_run, Qt.LeftButton)
    wait(lambda: v.running is not None)
    if not v.diagram.arrows:
        sys.exit("the transition was not computed")
    grab(win, "levels_transition")

    # radial wave functions of the even and odd states
    win.show_tab("wfn")
    win.panels["wfn"].set_checked_paths([os.path.join(wd, "even4.w"), os.path.join(wd, "odd4.w")])
    wait(lambda: False)
    grab(win, "wavefunctions")


def main():
    args = sys.argv[1:]
    opts = {}
    for name in ("--lang", "--out"):
        if name in args:
            i = args.index(name)
            opts[name] = args[i + 1]
            del args[i:i + 2]
    if len(args) != 1 or not os.path.isfile(os.path.join(args[0], "rmcdhf")):
        sys.exit(__doc__.strip() + "\n\nGRASP_BIN must contain rmcdhf.")
    bindir = os.path.abspath(args[0])
    out = os.path.abspath(opts.get("--out", os.path.join(ROOT, "docs", "images")))
    if "--lang" in opts:
        shoot(bindir, opts["--lang"], out)
        sys.stdout.flush()
        os._exit(0)                             # skip Qt's teardown
    procs = [subprocess.Popen([sys.executable, "-u", __file__, bindir, "--lang", lang, "--out", out])
             for lang in ("en", "zh")]
    sys.exit(max(p.wait() for p in procs))


if __name__ == "__main__":
    main()
