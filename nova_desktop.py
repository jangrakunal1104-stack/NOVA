#!/usr/bin/env python3

import sys
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    # -------------------------------
    # 1️⃣ Start UI (NO MODEL LOADED)
    # -------------------------------
    app = QApplication(sys.argv)
    win = MainWindow()   # 🔥 no model_loader
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()