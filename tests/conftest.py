import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="superterm_test_")      # never touch real settings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def spin(qapp):
    import time

    def _spin(seconds=0.2, until=None):
        end = time.time() + seconds
        while time.time() < end:
            qapp.processEvents()
            if until and until():
                return True
            time.sleep(0.005)
        return until() if until else True
    return _spin
