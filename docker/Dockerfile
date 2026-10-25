# magic-box on the Jetson with the ZED X, without installing the ZED SDK on the host.
# Build and run through compose.yaml at the repo root (README: "Jetson with Docker").
#
# The base image carries ZED SDK 5.5 and pyzed for JetPack 6.2.2 (L4T 36.5), matching the host's
# ZED Link driver. The venv follows the README's Jetson quickstart: --system-site-packages so
# pyzed and JetPack's cv2 are visible, then `uv sync` from uv.lock (no laptop extra).
# Owner: Daniel + Enoch
ARG BASE_IMAGE=stereolabs/zed:5.5-py-devel-jetson-jp6.2.2
FROM ${BASE_IMAGE}

# PortAudio for sounddevice (README step 2); uv as in README step 0, pinned.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libportaudio2 \
 && rm -rf /var/lib/apt/lists/* \
 && curl -LsSf https://astral.sh/uv/0.13.4/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_FROZEN=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN uv venv --system-site-packages --python /usr/bin/python3 /opt/venv
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
# The project is installed editable from /app/src; compose mounts the repo over /app at run time,
# so code edits need no rebuild. Rebuild after pyproject.toml or uv.lock change.
RUN uv sync --frozen \
 && python -c "import numpy, pygame, rapidfuzz, sounddevice, websockets, yaml; print('numpy', numpy.__version__)"

# Files the container writes into the mounted repo (recordings/) stay deletable by the host user.
ENTRYPOINT ["sh", "-c", "umask 000 && exec \"$@\"", "--"]
CMD ["scripts/run_demo.sh"]
