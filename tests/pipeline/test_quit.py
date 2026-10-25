import subprocess
import sys
import time

CODE = """
import threading, time
threading.Thread(target=time.sleep, args=(30,)).start()  # a stuck non-daemon Spark thread
from magic_box.main import hard_exit
hard_exit(0)
"""


def test_hard_exit_does_not_wait_for_in_flight_threads():
    start = time.monotonic()
    done = subprocess.run([sys.executable, "-c", CODE], timeout=10)
    assert done.returncode == 0 and time.monotonic() - start < 5


def test_module_entry_exits_fast_with_run_code():
    start = time.monotonic()
    done = subprocess.run(
        [sys.executable, "-m", "magic_box", "--fake", "--headless", "--max-ticks", "3"],
        timeout=30,
        capture_output=True,
    )
    assert done.returncode == 0 and time.monotonic() - start < 15
