# Arena on the Jetson: ZED X tracker plus the browser game, served together on one port (8765).
# Build and run through compose.yaml at the repo root; see the README's Docker section.
#
# The base image carries ZED SDK 5.5, pyzed and numpy 2 for JetPack 6.2.2 (L4T 36.5), matching the
# host's ZED Link driver. Override BASE_IMAGE for another JetPack.
ARG BASE_IMAGE=stereolabs/zed:5.5-py-devel-jetson-jp6.2.2
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1

# pip's OpenCV, not the image's JetPack cv2: that one is built for numpy 1 and fails to import next
# to numpy 2. jetson/requirements.txt is for host installs; its numpy<2 pin would downgrade the
# numpy that pyzed 5.5 is built against, so the two pins are repeated here instead.
RUN pip3 install --no-cache-dir websockets==13.1 opencv-python-headless==4.10.0.84 \
 && python3 -c "import cv2, numpy, websockets; print('cv2', cv2.__version__, 'numpy', numpy.__version__)"

WORKDIR /app
COPY jetson/ jetson/
COPY game/ game/

EXPOSE 8765
CMD ["python3", "jetson/tracker.py"]
