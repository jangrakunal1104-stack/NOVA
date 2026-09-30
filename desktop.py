#!/usr/bin/env python3

import sys

# Load environment variables (e.g. TAVILY_API_KEY) from a local .env file,
# if present, before any component that reads them is constructed.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is optional: if it's not installed, env vars can still
    # be set the normal way (exported in the shell, systemd unit, etc).
    pass

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
