from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QListWidgetItem
from ui.renderer import Renderer


class ChatManagerUI:
    def __init__(self, main_window):
        self.main_window = main_window

    def new_chat(self):
        chat_id = self.main_window.chat_db.create_chat()
        self.main_window._load_chats_from_db()
        self.main_window._load_chat_from_db(chat_id)
        self.main_window.log(f"[CHAT] New chat created ({chat_id})")

    def clear_chat(self):
        if not self.main_window.current_chat_id:
            return

        old_id = self.main_window.current_chat_id
        self.main_window.chat_db.delete_chat(old_id)
        self.main_window.log(f"[CHAT] Deleted chat {old_id}")

        new_id = self.main_window.chat_db.create_chat()
        self.main_window.log(f"[CHAT] Created new chat {new_id}")

        self.main_window.chat_list.clear()
        chats = self.main_window.chat_db.get_all_chats()
        for c in chats:
            # See _load_chats_from_db in main_window.py -- only the title
            # is shown; the id lives in item data so a plain number never
            # appears unless the user actually renamed the chat to one.
            item = QListWidgetItem(c["title"])
            item.setData(Qt.UserRole, c["id"])
            self.main_window.chat_list.addItem(item)

        self.main_window.current_chat_id = new_id

        self.main_window.run_js("document.getElementById('chat').innerHTML = '';")
        self.main_window.run_js(Renderer.js_clear_stream())

    def delete_chat(self):
        if not self.main_window.current_chat_id:
            return

        chat_id = self.main_window.current_chat_id

        reply = QMessageBox.question(
            self.main_window, "Confirm Delete",
            f"Delete chat #{chat_id} permanently?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # 1. Delete from database
        self.main_window.chat_db.delete_chat(chat_id)

        # 2. Remove from left panel (QListWidget)
        for i in range(self.main_window.chat_list.count()):
            item = self.main_window.chat_list.item(i)
            if item and item.data(Qt.UserRole) == chat_id:
                self.main_window.chat_list.takeItem(i)
                break

        # 3. Clear current view
        self.main_window.run_js("document.getElementById('chat').innerHTML = '';")

        # 4. Switch to next chat or create new
        remaining = []
        for i in range(self.main_window.chat_list.count()):
            item = self.main_window.chat_list.item(i)
            if item:
                cid = item.data(Qt.UserRole)
                if cid is not None:
                    remaining.append(cid)

        if remaining:
            self.main_window.switch_chat(remaining[0])
        else:
            self.main_window.on_new_chat()

        self.main_window.log(f"✅ Chat {chat_id} deleted")
    def load_chat(self, chat_id):
        self.main_window._load_chat_from_db(chat_id)