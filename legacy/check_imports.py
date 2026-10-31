#!/usr/bin/env python3
"""Check that the PySide6 stand-in provides every Qt name the GUI imports (run with a Python that has PySide2):

    python3 legacy/check_imports.py

Names are taken from the `from PySide6.X import ...` statements of the program files. This only catches missing
imports; methods that changed between Qt 5 and Qt 6 show up when the GUI tests run on the stand-in, e.g.
PYTHONPATH=legacy python3 <test>.
"""

import ast
import glob
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "legacy"))

missing = []
for path in sorted(glob.glob(os.path.join(ROOT, "*.py"))):
    for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "PySide6":
            module = importlib.import_module(node.module)
            missing += [f"{os.path.basename(path)}:{node.lineno}  {node.module}.{a.name}"
                        for a in node.names if not hasattr(module, a.name)]
print("\n".join(missing) or "all PySide6 imports available")
sys.exit(1 if missing else 0)
