"""Resample independent alpha without changing deployment RGB or its mip chain."""
import struct
from PIL import Image
from .client_blp import validate


def resample_alpha(data, source):
    info = validate(data)
    size = (info['width'], info['height'])
    if size != (source.width * 2, source.height * 2):
        raise ValueError('Smooth-alpha profile requires exact 2x dimensions')
    alpha = source.convert('RGBA').getchannel('A').resize(size, Image.Resampling.BILINEAR)
    if info['alphaDepth'] == 0:
        if alpha.getextrema() != (255, 255):
            raise ValueError('Missing alpha plane for a nonopaque source')
        return data
    result = bytearray(data)
    offsets = struct.unpack_from('<16I', data, 20)
    sizes = struct.unpack_from('<16I', data, 84)
    for offset, length in zip(offsets, sizes):
        if not offset:
            continue
        count = alpha.width * alpha.height
        if info['encoding'] == 1:
            result[offset + count:offset + length] = alpha.tobytes()
        else:
            result[offset + 3:offset + length:4] = alpha.tobytes()
        if alpha.size != (1, 1):
            alpha = alpha.resize((max(1, alpha.width // 2), max(1, alpha.height // 2)), Image.Resampling.BOX)
    output = bytes(result)
    validate(output)
    if output[:1172] != data[:1172] or len(output) != len(data):
        raise ValueError('Unexpected header or payload change')
    # Check all non-alpha bytes independently from the replacement operation.
    for offset, length in zip(offsets, sizes):
        if not offset:
            continue
        if info['encoding'] == 1:
            if output[offset:offset + length // 2] != data[offset:offset + length // 2]:
                raise ValueError('Palette indices changed')
        else:
            for channel in range(3):
                if output[offset + channel:offset + length:4] != data[offset + channel:offset + length:4]:
                    raise ValueError('RGB changed')
    return output
