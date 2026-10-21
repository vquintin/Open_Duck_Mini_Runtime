"""The Pi's own view of its supply, as vcgencmd get_throttled reports it.

The firmware keeps the state now and since boot: a dip shorter than the
hwmon driver's 2 s poll (rpi_volt's in0_lcrit_alarm) still shows in the
"since boot" bits. Read through the VideoCore mailbox (/dev/vcio, which the
NixOS module opens to the walk's group). canard's servos saw their supply dip
to 4.9 V walking, a loose battery contact, and the Pi rebooted (2026-10-21).
"""

import array
import fcntl
import struct

VCIO = "/dev/vcio"
GET_THROTTLED_TAG = 0x00030046
# _IOWR(100, 0, char *) on a 64-bit kernel: the argument is a pointer.
IOCTL_MBOX_PROPERTY = 0xC0086400
MBOX_SUCCESS = 0x80000000  # the request code word, once the firmware answered
CPU_TEMP = "/sys/class/thermal/thermal_zone0/temp"  # millidegrees C

UNDERVOLTAGE, THROTTLED = 1 << 0, 1 << 2
UNDERVOLTAGE_SINCE_BOOT, THROTTLED_SINCE_BOOT = 1 << 16, 1 << 18


def throttled_request() -> bytes:
    """A property request for the throttled state: size, request code, the tag
    (its value buffer's size, request/response, value), end tag."""
    return struct.pack("<7I", 7 * 4, 0, GET_THROTTLED_TAG, 4, 0, 0, 0)


def decode_throttled(bits: int) -> dict[str, bool]:
    return {
        "undervoltage": bool(bits & UNDERVOLTAGE),
        "undervoltage_since_boot": bool(bits & UNDERVOLTAGE_SINCE_BOOT),
        "throttled": bool(bits & THROTTLED),
        "throttled_since_boot": bool(bits & THROTTLED_SINCE_BOOT),
    }


class PiPower:
    """get_throttled's bits and the SoC's temperature; None where unreadable
    (no /dev/vcio access, not a Pi)."""

    def __init__(self) -> None:
        try:
            self._vcio = open(VCIO, "rb", buffering=0)
        except OSError as e:
            print(f"[pi power]: {VCIO} unreadable ({e}); no throttled state")
            self._vcio = None

    def throttled(self) -> int | None:
        if self._vcio is None:
            return None
        buf = array.array("I", struct.unpack("<7I", throttled_request()))
        try:
            fcntl.ioctl(self._vcio, IOCTL_MBOX_PROPERTY, buf, True)
        except OSError:
            return None
        if buf[1] != MBOX_SUCCESS:
            return None
        return int(buf[5])

    @staticmethod
    def temperature() -> float | None:
        try:
            with open(CPU_TEMP) as f:
                return int(f.read()) / 1000
        except (OSError, ValueError):
            return None
