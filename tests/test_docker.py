"""The Jetson Docker setup mounts what the ZED X needs and builds the venv like the README's
Jetson quickstart (system site-packages for pyzed and JetPack's cv2, uv sync from the lock).

Owner: Daniel + Enoch
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_mounts_what_the_zed_x_needs():
    service = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]["magic-box"]
    assert service["runtime"] == "nvidia" and service["privileged"]
    assert service["pid"] == "host", "check_env.py finds ZEDX_Daemon through the host pids"
    targets = {volume.split(":")[1] for volume in service["volumes"]}
    assert {
        "/app",
        "/dev",
        "/tmp",
        "/var/nvidia/nvcam/settings",
        "/etc/systemd/system/zed_x_daemon.service",
        "/usr/local/zed/resources",
    } <= targets
    assert "restart" not in service, "run_demo.sh restarts the game; boot must not race the camera"


def test_dockerfile_builds_the_venv_like_the_jetson_quickstart():
    text = (ROOT / "docker" / "Dockerfile").read_text()
    assert "--system-site-packages" in text
    assert "uv sync --frozen" in text
    assert "--extra laptop" not in text, "opencv-python would shadow JetPack's cv2"
    assert "libportaudio2" in text
