"""Decode real RadonEye Plus2 (RD200P2) replies captured over Bluetooth."""

from custom_components.rd200_ble.rd200_ble import (
    parse_plus2_measurement,
    parse_plus2_uptime_minutes,
)

# Reply to 0x50 from a real device (minute/second of its clock in the last two bytes).
MEASUREMENT = bytes.fromhex("5010540039004b0054006400610205000500132f")
# Reply to 0x51 from the same device, minutes before the app showed Meas. Time 260d 10:04.
STATUS = bytes.fromhex("51120200d7b805005a100800ab151a0b13122f28")


def test_measurement():
    assert parse_plus2_measurement(MEASUREMENT) == {
        "radon": 84,
        "radon_1day_level": 57,
        "radon_1month_level": 75,
        "radon_7day_level": 84,
        "radon_peak": 100,
        "radon_C_now": 5,
        "radon_C_last": 5,
    }


def test_uptime():
    minutes = parse_plus2_uptime_minutes(STATUS)
    assert minutes == 374_999
    assert (minutes // 1440, (minutes % 1440) // 60, minutes % 60) == (260, 9, 59)


def test_rejects_other_replies():
    assert parse_plus2_measurement(STATUS) is None
    assert parse_plus2_measurement(MEASUREMENT[:10]) is None
    assert parse_plus2_measurement(None) is None
    assert parse_plus2_uptime_minutes(MEASUREMENT) is None
    assert parse_plus2_uptime_minutes(None) is None
