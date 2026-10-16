import base64
import json

import pytest

from maika_direct_testpkg.api import (
    WRITABLE_FIELDS,
    extract_frames,
    find_device_payload,
    normalize_device,
    normalize_login,
    unwrap_directive,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0912345678", "+84912345678"),
        ("+84 912 345 678", "+84912345678"),
        ("84912345678", "+84912345678"),
        ("0084912345678", "+84912345678"),
        ("+840912345678", "+84912345678"),
        ("Ban@Example.com", "Ban@Example.com"),
    ],
)
def test_normalize_login(raw, expected):
    assert normalize_login(raw) == expected


def test_extract_frames_keeps_partial_tail():
    buf = (
        'noise$START_JSON\n{"session_id":"s"}\n$END_JSON'
        '$START_JSON{"directive":{"header":{"name":"DeviceInfo"}}}$END_JSON'
        '$START_JSON{"half":'
    )
    frames, rest = extract_frames(buf)
    assert frames[0] == {"session_id": "s"}
    assert unwrap_directive(frames[1])["header"]["name"] == "DeviceInfo"
    assert rest == '$START_JSON{"half":'


def test_extract_frames_vietnamese_and_bad_json():
    frames, _ = extract_frames('$START_JSON{"t":"bật đèn"}$END_JSON$START_JSON{oops$END_JSON')
    assert frames == [{"t": "bật đèn"}]


def test_normalize_device_aliases_and_bools():
    dev = normalize_device({"deviceId": " A1 ", "currentPlayback": {}, "mute": "false", "isOnline": 1})
    assert dev["device_id"] == "A1"
    assert dev["mute"] is False
    assert dev["online"] is True
    assert "current_playback" in dev
    assert normalize_device({"name": "no serial"}) is None


def test_find_device_payload_nested():
    payload = {"data": {"device": {"deviceId": "X", "volume": 5}}}
    assert find_device_payload(payload)["volume"] == 5


def test_meta_roundtrip_is_base64_json():
    meta = {"event": {"header": {"name": "Recognize", "rawSpeech": "mấy giờ rồi"}}}
    encoded = base64.b64encode(json.dumps(meta, ensure_ascii=False).encode()).decode()
    assert json.loads(base64.b64decode(encoded)) == meta


def test_writable_fields_exclude_dangerous():
    assert "status" not in WRITABLE_FIELDS
    assert {"name", "tts_voice"} <= WRITABLE_FIELDS
