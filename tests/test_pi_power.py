import struct

from mini_bdx_runtime.pi_power import GET_THROTTLED_TAG, decode_throttled, throttled_request


def test_the_request_asks_the_firmware_for_its_throttled_state():
    words = struct.unpack("<7I", throttled_request())
    assert words == (7 * 4, 0, GET_THROTTLED_TAG, 4, 0, 0, 0)  # size, request, tag, value size, ..., end tag


def test_throttled_bits_now_and_since_boot():
    # vcgencmd get_throttled's bits: 0-3 now, 16-19 since boot
    assert decode_throttled(0) == {"undervoltage": False, "undervoltage_since_boot": False,
                                   "throttled": False, "throttled_since_boot": False}
    s = decode_throttled(0x50005)
    assert s["undervoltage"] and s["throttled"] and s["undervoltage_since_boot"] and s["throttled_since_boot"]
    assert decode_throttled(0x10000) == {"undervoltage": False, "undervoltage_since_boot": True,
                                         "throttled": False, "throttled_since_boot": False}
