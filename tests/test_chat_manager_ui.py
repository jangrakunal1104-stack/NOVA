"""
ui.chat_manager_ui.ChatManagerUI.delete_chat() drives a real QMessageBox
confirmation dialog and several live Qt widgets, which needs a running
QApplication + display to instantiate properly -- not worth pulling in a
Qt-testing harness (pytest-qt) just for this one regression check. The
underlying database behavior it depends on (ChatManager.delete_chat) is
already covered behaviorally in test_chat_manager.py.

What we verify here is the actual regression: delete_chat() used to
reference `self.main_window.chat_list_widgets`, an attribute that is
never defined anywhere on MainWindow, so clicking "Delete Chat" crashed
with AttributeError. This is a static source check for that dead
reference rather than a live UI test.
"""
from pathlib import Path


def test_delete_chat_no_longer_references_undefined_attribute():
    src = Path(__file__).parent.parent.joinpath("ui", "chat_manager_ui.py").read_text()
    assert "chat_list_widgets" not in src, (
        "chat_manager_ui.py references chat_list_widgets again, which is "
        "never defined on MainWindow -- this crashed 'Delete Chat' before."
    )


def test_clear_and_delete_chat_use_item_data_not_baked_in_id():
    # Same regression as ui/main_window.py: clear_chat() used to add rows
    # as f"{c['id']}::{c['title']}" (an id number visibly prefixing every
    # chat title), and delete_chat() matched/parsed rows by string-slicing
    # that same text. Both must now go through Qt.UserRole item data so no
    # number is displayed unless the user actually renamed a chat to one.
    src = Path(__file__).parent.parent.joinpath("ui", "chat_manager_ui.py").read_text()
    assert 'f"{c[\'id\']}::{c[\'title\']}"' not in src
    assert 'item.text().split("::")' not in src
    assert 'str(chat_id) in item.text()' not in src
    assert src.count("item.data(Qt.UserRole)") >= 2
