"""Binary stream framing survives arbitrary pipe chunks and exposes key frames."""

import struct

from embernet.video_stream import AccessUnits, nals, packet


def test_access_units_survive_split_start_codes():
    first = b"\x00\x00\x00\x01\x09\x10\x00\x00\x01\x65abc"
    second = b"\x00\x00\x01\x09\x10\x00\x00\x01\x41def"
    parser = AccessUnits()
    result = []
    for byte in first + second:
        result.extend(parser.feed(bytes([byte])))
    assert result == [first]
    encoded = packet(7, result[0])
    assert struct.unpack(">BBQ", encoded[:10]) == (2, 1, 7 * 33333)
    assert encoded[10:] == first
    assert [kind for _, kind in nals(first)] == [9, 5]
