"""Bounds-checked modern model arrays."""
import struct
def array(data, at, stride):
    if at < 0 or stride <= 0 or at + 8 > len(data): raise ValueError("Array header out of bounds")
    n, off = struct.unpack_from("<II", data, at)
    if n and (off < 8 or off + n * stride > len(data)): raise ValueError("Array out of bounds")
    return n, off
