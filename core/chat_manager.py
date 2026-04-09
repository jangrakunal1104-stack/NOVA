import sqlite3
from datetime import datetime
import time

DB_FILE = "chats.db"

class ChatManager:
    def __init__(self):
        self.db_path = DB_FILE
        self._ensure_tables()

    # ----------------------------------
    # Always open fresh SQLite connection
    # (thread-safe because check_same_thread=False)
    # ----------------------------------
    def _conn(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    # ----------------------------------
    # Create tables
    # ----------------------------------
    def _ensure_tables(self):
        conn = self._conn()
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            created_at TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp TEXT,
            FOREIGN KEY(chat_id) REFERENCES chats(id)
        )
        """)

        conn.commit()
        conn.close()

    # ----------------------------------
    # Create new chat
    # ----------------------------------
    def create_chat(self, first_message="New Chat"):
        title = first_message.strip()[:40]
        created_at = datetime.now().isoformat()

        conn = self._conn()
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO chats (title, created_at) VALUES (?, ?)",
            (title, created_at)
        )

        chat_id = cur.lastrowid
        conn.commit()
        conn.close()
        return chat_id
    # ----------------------------------
    # Auto-rename based on first user message
    # ----------------------------------
    def auto_rename_if_needed(self, chat_id, first_user_msg):
        conn = self._conn()
        cur = conn.cursor()

        cur.execute("SELECT title FROM chats WHERE id = ?", (chat_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return

        current_title = row[0]

        # Only rename if still default or blank
        if current_title.lower().startswith("new chat") or current_title.strip() == "":
            new_title = first_user_msg.strip()[:40]
            cur.execute(
                "UPDATE chats SET title = ? WHERE id = ?",
                (new_title, chat_id)
            )

        conn.commit()
        conn.close()
    # ----------------------------------
    # Load messages for LLM (OpenAI-style format)
    # ----------------------------------
    def get_messages_for_llm(self, chat_id):
        conn = self._conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,)
        )
        rows = cur.fetchall()
        conn.close()

        formatted = []
        for role, content in rows:
            formatted.append({
                "role": role,      # "user" or "assistant"
                "content": content
            })

        return formatted

    def delete_chat(self, chat_id):
        conn = self._conn()
        cur = conn.cursor()

        # Delete all messages belonging to this chat
        cur.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        # Delete chat entry
        cur.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

        conn.commit()
        conn.close()

    # ----------------------------------
    # Update chat title
    # ----------------------------------
    def rename_chat(self, chat_id, new_title):
        conn = self._conn()
        cur = conn.cursor()

        cur.execute(
            "UPDATE chats SET title = ? WHERE id = ?",
            (new_title, chat_id)
        )

        conn.commit()
        conn.close()

    # ----------------------------------
    # Add a message
    # ----------------------------------
    def add_message(self, chat_id, role, content):
        timestamp = datetime.now().isoformat()

        conn = self._conn()
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (chat_id, role, content, timestamp)
        )

        conn.commit()
        conn.close()

    # ----------------------------------
    # Load chat messages (UI friendly)
    # ----------------------------------
    def get_chat(self, chat_id):
        conn = self._conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,)
        )

        rows = cur.fetchall()
        conn.close()

        return [{"role": r[0], "content": r[1]} for r in rows]

    # ----------------------------------
    # For LLM worker (tuple format)
    # ----------------------------------
    def list_messages(self, chat_id):
        conn = self._conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,)
        )

        rows = cur.fetchall()
        conn.close()

        return [{"role": r[0], "content": r[1]} for r in rows]

    # ----------------------------------
    # List chats for sidebar
    # ----------------------------------
    def list_chats(self):
        conn = self._conn()
        cur = conn.cursor()

        cur.execute("SELECT id, title, created_at FROM chats ORDER BY id DESC")
        rows = cur.fetchall()

        conn.close()
        return rows

    # ----------------------------------
    # Get a chat’s title
    # ----------------------------------
    def get_chat_title(self, chat_id):
        conn = self._conn()
        cur = conn.cursor()

        cur.execute("SELECT title FROM chats WHERE id = ?", (chat_id,))
        row = cur.fetchone()

        conn.close()

        return row[0] if row else "Untitled"

    def get_all_chats(self):
        conn = self._conn()
        cur = conn.cursor()

        cur.execute("SELECT id, title FROM chats ORDER BY id DESC")
        rows = cur.fetchall()

        conn.close()

        return [{"id": r[0], "title": r[1]} for r in rows]
