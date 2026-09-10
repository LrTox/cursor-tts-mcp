import os

# Keep unit tests on in-process orchestrator; avoid autostarting HTTP service.
os.environ.setdefault("CURSOR_TTS_MODE", "embedded")
