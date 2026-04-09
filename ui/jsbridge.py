from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
import os


class JSBridge(QObject):

    def __init__(self, window):
        super().__init__()
        self.window = window

    def _open(self, path: str):
        path = path.strip('"').strip("'")
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            print("[JSBridge] File not found:", path)

    @Slot(str)
    def open_image(self, path: str):
        self._open(path)

    @Slot(str)
    def openImage(self, path: str):
        self._open(path)
