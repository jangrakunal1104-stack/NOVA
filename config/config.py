import os

# Repo root (this file lives in NOVA/config/, so go up one level).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))

# settings.json actually lives alongside this file (NOVA/config/settings.json),
# not at the repo root — this used to point at the wrong path, silently
# ignoring the real file and falling back to defaults every run.
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
