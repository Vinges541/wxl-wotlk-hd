"""Named RGB recipes and the separately ordered runtime alpha treatment."""
from PIL import Image
from .assets import decode_blp
from .client_blp import to_runtime
from .smooth_alpha import resample_alpha

RECIPES = ('direct-smooth', 'conservative')


def direct_rgba(source, raw, scale):
    """Resize full x4 neural RGB while retaining the independent source mask."""
    if scale not in (1, 2, 4) or raw.size != (source.width * 4, source.height * 4):
        raise ValueError('Expected a matching full x4 neural output')
    size = (source.width * scale, source.height * scale)
    result = raw.convert('RGB').resize(size, Image.Resampling.LANCZOS).convert('RGBA')
    result.putalpha(source.convert('RGBA').getchannel('A').resize(size, Image.Resampling.NEAREST))
    return result


def restore(model, source, scale, strength, recipe):
    if recipe not in RECIPES:
        raise ValueError('Unknown restoration recipe')
    if recipe == 'direct-smooth' and scale != 2:
        raise ValueError('The direct-smooth recipe requires 2x output')
    image, report = model.run(source, scale, strength)
    if recipe == 'direct-smooth':
        image = direct_rgba(source, model.raw, 2)
        report = {k: v for k, v in report.items() if k != 'maxRgbCorrection'}
        report.update(strength=None, outputMode='direct-neural-rgb')
    report['recipe'] = recipe
    return image, report


def deployment(data, source, component, recipe, *, palette_mode='maxcoverage'):
    if recipe not in RECIPES:
        raise ValueError('Unknown restoration recipe')
    result, report = to_runtime(data, component, palette_mode=palette_mode)
    if recipe == 'direct-smooth':
        # Quantize RGB/mips with the original replicated mask first. Smoothing
        # before palette selection changes the reviewed recipe's RGB values.
        result = resample_alpha(result, decode_blp(source))
        report.update(alphaPolicy='source-bilinear-2x-recursive-box-mips',
                      allMipAlphaExact=False, allMipRgbaExact=False,
                      rgbUnchangedByAlphaStep=True)
    return result, report
