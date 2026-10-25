import copy
import sys
from enum import Enum, IntEnum
from pathlib import Path

import numpy as np
import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import KEYPOINT_NAMES
from magic_box.perception.keypoints import PART_NAMES
from magic_box.perception.raw import CameraInfo
from magic_box.perception.zed_source import (
    CameraError,
    ZedSource,
    bbox_from_corners,
    check_part_indices,
    grab_succeeded,
)
from tests.perception.fake_sl import fake_body, install_fake_sl
from tests.perception.fakes import body_points

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


@pytest.fixture
def sl(monkeypatch):
    return install_fake_sl(monkeypatch)


def test_grab_succeeded_orders_or_falls_back():
    E = IntEnum("E", {"WARN": -1, "SUCCESS": 0, "FAIL": 1})
    assert grab_succeeded(E.WARN, E.SUCCESS) and grab_succeeded(E.SUCCESS, E.SUCCESS)
    assert not grab_succeeded(E.FAIL, E.SUCCESS)
    ok, bad = object(), object()  # SDK 4 enums: no ordering
    assert grab_succeeded(ok, ok) and not grab_succeeded(bad, ok)


def test_bbox_from_corners():
    assert bbox_from_corners([[10, 20], [110, 20], [110, 220], [10, 220]]) == (10, 20, 100, 200)
    corners = np.array([[110.6, 220.2], [10.0, 20.9], [110, 20], [10, 220]])
    assert bbox_from_corners(corners) == (10, 20, 100, 200)


def test_check_part_indices():
    names = list(PART_NAMES["BODY_34"])
    check_part_indices("BODY_34", Enum("BODY_34_PARTS", {n: i for i, n in enumerate(names)}))
    names[3], names[5] = names[5], names[3]
    with pytest.raises(RuntimeError, match="BODY_34"):
        check_part_indices("BODY_34", Enum("BODY_34_PARTS", {n: i for i, n in enumerate(names)}))


def test_open_configures_the_zed_x(sl):
    src = ZedSource(CFG)
    src.open()
    cam = sl.Camera.last
    assert (cam.init.camera_resolution, cam.init.camera_fps) == (sl.RESOLUTION.SVGA, 30)
    assert cam.init.coordinate_units == sl.UNIT.METER
    assert cam.init.coordinate_system == sl.COORDINATE_SYSTEM.IMAGE
    assert cam.init.depth_maximum_distance == CFG["camera"]["max_range_m"]
    assert cam.positional.set_as_static is True
    bp = cam.body_params
    assert (bp.body_format, bp.detection_model, bp.enable_tracking, bp.enable_body_fitting) == (
        sl.BODY_FORMAT.BODY_34,
        sl.BODY_TRACKING_MODEL.HUMAN_BODY_FAST,
        True,
        True,
    )
    assert bp.max_range == CFG["camera"]["max_range_m"]
    assert src.is_open and src.info == CameraInfo("ZED_X", 4242, 960, 600, 30.0, "5.0.0", "live")


def test_open_failure_raises_camera_error_with_the_daemon_hint(sl):
    sl.Camera.open_status = sl.ERROR_CODE.CAMERA_NOT_DETECTED
    with pytest.raises(CameraError, match="zed_x_daemon"):
        ZedSource(CFG).open()
    assert sl.Camera.last.closed


def test_open_failure_closes_the_sdk_camera(sl):
    sl.Camera.open_status = sl.ERROR_CODE.FAILURE
    with pytest.raises(CameraError):
        ZedSource(CFG).open()
    assert sl.Camera.last.closed


def test_resolution_mismatch_is_fatal(sl):
    sl.Camera.resolution = (1920, 1200)
    src = ZedSource(CFG)
    with pytest.raises(RuntimeError, match="960x600") as err:
        src.open()
    assert not isinstance(err.value, CameraError)
    assert sl.Camera.last.closed and not src.is_open


def test_missing_pyzed_is_a_clear_fatal_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyzed", None)
    with pytest.raises(RuntimeError, match="--fake") as err:
        ZedSource(CFG).open()
    assert "failed to import" in str(err.value) and "No module named" in str(err.value)


def test_grab_converts_bodies_and_frame(sl):
    sl.Camera.bodies = [fake_body(7, ok=True), fake_body(8, ok=False, x=-0.5)]
    src = ZedSource(CFG)
    src.open()
    cap = src.grab()
    assert cap.frame.image.shape == (600, 960, 4) and cap.frame.frame_idx == 0
    assert cap.frame.cam_t == pytest.approx(12.5)
    b = cap.bodies[0]
    assert (b.id, b.tracking_ok, b.position) == (7, True, pytest.approx((0.5, -0.3, 2.0)))
    assert set(b.kp3d) == set(KEYPOINT_NAMES)
    assert b.kp3d["neck"] == pytest.approx(body_points(0.5, 2.0)["neck"])
    assert [x.id for x in cap.bodies] == [7]  # the SEARCHING body is dropped
    assert sl.Camera.last.runtime.measure3D_reference_frame == sl.REFERENCE_FRAME.CAMERA
    assert sl.Camera.last.body_runtime.detection_confidence_threshold == 40
    assert src.grab().frame.frame_idx == 1


def test_empty_sdk_arrays_do_not_crash_grab(sl):
    all_empty = ("keypoint", "keypoint_2d", "bounding_box_2d")
    sl.Camera.bodies = [
        fake_body(1, empty=all_empty),
        fake_body(2, ok=False, empty=all_empty),
        fake_body(3, empty=("bounding_box_2d",)),
    ]
    src = ZedSource(CFG)
    src.open()
    cap = src.grab()
    assert [b.id for b in cap.bodies] == [1, 3]
    assert cap.bodies[0].kp3d == {} and cap.bodies[0].kp2d == {}
    assert cap.bodies[0].bbox_px == (0, 0, 0, 0) and cap.bodies[1].bbox_px == (0, 0, 0, 0)
    assert cap.bodies[1].kp3d  # real keypoints are kept when the arrays are fine


def test_warnings_pass_and_failures_return_none(sl):
    sl.Camera.grab_statuses = [sl.ERROR_CODE.CORRUPTED_FRAME, sl.ERROR_CODE.FAILURE]
    src = ZedSource(CFG)
    src.open()
    assert src.grab() is not None and src.grab() is None


def test_svo_end_rewinds(sl):
    sl.Camera.grab_statuses = [sl.ERROR_CODE.END_OF_SVOFILE_REACHED]
    src = ZedSource(CFG)
    src.open()
    assert src.grab() is None and sl.Camera.last.svo_positions == [0]


def test_svo_playback_and_recording(sl, tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["camera"]["svo_path"] = "in.svo2"
    cfg["camera"]["record_svo"] = str(tmp_path / "out.svo2")
    src = ZedSource(cfg)
    src.open()
    cam = sl.Camera.last
    assert cam.init.svo_file == "in.svo2" and cam.init.svo_real_time_mode is True
    assert src.info.source == "in.svo2"
    assert cam.recording.video_filename == str(tmp_path / "out.svo2")


def test_close_is_idempotent_and_reopen_keeps_counting(sl):
    src = ZedSource(CFG)
    src.open()
    src.grab()
    src.close()
    src.close()
    assert not src.is_open
    src.open()
    assert src.grab().frame.frame_idx == 1


def test_grab_reuses_one_image_buffer(sl):
    src = ZedSource(CFG)
    src.open()
    src.grab()
    src.grab()
    mats = sl.Camera.last.image_mats
    assert len(mats) == 2 and mats[0] is mats[1]


def test_open_accepts_sdk_warning_codes(sl):
    sl.Camera.open_status = sl.ERROR_CODE.CORRUPTED_FRAME
    src = ZedSource(CFG)
    src.open()
    assert src.is_open
