import fcntl
import os
import subprocess
import sys

from astheral import manage


def test_manager_distinguishes_live_lock_from_stale_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(manage, "RUN", tmp_path)
    path = tmp_path / "train.lock"
    path.write_text("12345")
    assert manage.running_pid() is None
    with path.open("r+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert manage.running_pid() == 12345
    assert manage.running_pid() is None


def test_duplicate_trainer_does_not_destroy_owner_pid(tmp_path):
    path = tmp_path / "train.lock"
    path.write_text(str(os.getpid()))
    with path.open("r+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run([sys.executable, "-m", "astheral.train", "--output", str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "trainer already owns" in result.stderr
    assert path.read_text() == str(os.getpid())
