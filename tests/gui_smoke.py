"""Offline entry-window smoke test: python tests/gui_smoke.py."""
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication

QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
from servo_system_v2 import MainApplication

app = QApplication([])
window = MainApplication()
window.show()
QTimer.singleShot(700, app.quit)
app.exec_()
print("GUI startup smoke test passed")
