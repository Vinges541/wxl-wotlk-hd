"""Preserve the final DIP StartIndex with the pinned core's native-index hook.

Core v1.1.245 widens the section index before native GxDeviceDraw adds the bound
index-buffer offset. Repeating that widening in modern-M2's DIP hook can discard
the offset. This opt-in candidate removes only the second expansion, retaining
the bone budget and all DIP interceptors/events. Gameplay verification is separate.
"""
import hashlib

from patch_shadow_bone_budget import RESULT as EXPECTED
from patch_wow import Pe32, PatchError

RESULT = 'ca9bc64edc5852e06ce4c36308341864b8f85576b85cde0f1c2e686e5d71d55d'
RVA = 0xB321
BEFORE = bytes.fromhex('ff751c')  # push [ebp+1c]: incoming StartIndex
CALL = bytes.fromhex('e89afdffff')  # call ExpandM2StartIndex
AFTER = bytes.fromhex('8b5d2083c404')  # mov ebx,[ebp+20]; add esp,4
REPLACEMENT = bytes.fromhex('8b04249090')  # mov eax,[esp]; nop; nop


def patch(source):
    if hashlib.sha256(source).hexdigest() != EXPECTED:
        raise PatchError('Expected exact bone-budget modern-M2 runtime; unknown or already patched input')
    result = _patch_verified_image(source)
    if hashlib.sha256(result).hexdigest() != RESULT:
        raise PatchError('DIP candidate output differs from the verified byte profile')
    return result


def _patch_verified_image(source):
    """Structural helper for synthetic tests; public build uses full hash guards."""
    result = bytearray(source)
    pe = Pe32(result)
    if pe.image_base != 0x10000000:
        raise PatchError('Unexpected modern-M2 image base')
    offset = pe.va_to_offset(pe.image_base + RVA)
    context = BEFORE + CALL + AFTER
    if result[offset-len(BEFORE):offset+len(CALL)+len(AFTER)] != context:
        raise PatchError('DIP StartIndex call/stack context mismatch')
    result[offset:offset+len(CALL)] = REPLACEMENT
    return bytes(result)
