"""OpenSSH 调用的短生命周期输入框；回答仅交给 ssh，不保存或写日志。"""

import os
import sys
from grasp_core import T


def main():
    from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox
    import grasp_core as core

    app = QApplication.instance() or QApplication([])
    core.set_lang(core.load_config().get("lang", core.LANG))
    prompt = sys.argv[2] if len(sys.argv) > 2 else T("SSH 登录")
    if os.environ.get("SSH_ASKPASS_PROMPT") == "confirm":
        answer = QMessageBox.question(None, T("SSH 主机确认"), prompt,
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        print("yes" if answer == QMessageBox.Yes else "no")
        return 0 if answer == QMessageBox.Yes else 1
    value, accepted = QInputDialog.getText(None, T("SSH 登录"), prompt, QLineEdit.Password)
    if accepted:
        sys.stdout.write(value + "\n")
        sys.stdout.flush()
    return 0 if accepted else 1
