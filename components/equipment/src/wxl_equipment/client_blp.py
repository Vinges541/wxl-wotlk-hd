"""WotLK deployment encoding, separate from lossless inference-cache storage.

BLP preferredFormat is a GPU format, not merely a DXT alpha selector. The client
selects it before locking mip data. Raw BGRA must request PIXEL_ARGB8888 (2).
Body layers retain the palettized layout used by the legacy body compositor.
"""
import math
import struct
import numpy as np
from PIL import Image
from .assets import decode_blp

HEADER_SIZE=1172
PALETTE_MODES=('maxcoverage', 'median-dither')


def raw_levels(data):
    if data[:4]!=b'BLP2' or len(data)<148 or data[8:10]!=bytes([3,8]):raise ValueError('Expected lossless BGRA cache')
    width,height=struct.unpack_from('<2I',data,12)
    if min(width,height)<1 or max(width,height)>2048 or width&(width-1) or height&(height-1):raise ValueError('Invalid dimensions')
    offsets=struct.unpack_from('<16I',data,20);sizes=struct.unpack_from('<16I',data,84);images=[];cursor=offsets[0]
    if cursor not in (148,HEADER_SIZE):raise ValueError('Unexpected cache header')
    for level in range(16):
        if level>int(math.log2(max(width,height))):
            if offsets[level] or sizes[level]:raise ValueError('Unexpected mip')
            continue
        w,h=max(1,width>>level),max(1,height>>level)
        if offsets[level]!=cursor or sizes[level]!=w*h*4 or cursor+sizes[level]>len(data):raise ValueError('Invalid raw mip')
        images.append(Image.frombytes('RGBA',(w,h),data[cursor:cursor+sizes[level]],'raw','BGRA'));cursor+=sizes[level]
    if cursor!=len(data):raise ValueError('Trailing cache payload')
    return images


def assemble(size,encoding,alpha,preferred,payloads,palette=bytes(1024)):
    offsets=[0]*16;sizes=[0]*16;cursor=HEADER_SIZE
    for i,payload in enumerate(payloads):offsets[i]=cursor;sizes[i]=len(payload);cursor+=len(payload)
    return struct.pack('<4sI4B2I16I16I',b'BLP2',1,encoding,alpha,preferred,1,*size,*offsets,*sizes)+palette+b''.join(payloads)


def validate(data,component=False):
    if len(data)<HEADER_SIZE or data[:4]!=b'BLP2' or struct.unpack_from('<I',data,4)[0]!=1:raise ValueError('Incomplete client BLP header')
    encoding,alpha,preferred,mips=data[8:12];w,h=struct.unpack_from('<2I',data,12)
    if min(w,h)<1 or max(w,h)>2048 or w&(w-1) or h&(h-1) or mips!=1:raise ValueError('Invalid client dimensions or mips')
    if component and encoding!=1:raise ValueError('Body components require palettized deployment')
    if encoding==3:
        if preferred!=2 or alpha!=8:raise ValueError('BGRA pixels require ARGB8888 preferredFormat=2')
    elif encoding==1:
        if preferred!=8 or alpha not in (0,8):raise ValueError('Unexpected component format')
    else:raise ValueError('Unsupported deployment encoding')
    offsets=struct.unpack_from('<16I',data,20);sizes=struct.unpack_from('<16I',data,84);cursor=HEADER_SIZE
    for level in range(16):
        if level>int(math.log2(max(w,h))):
            if offsets[level] or sizes[level]:raise ValueError('Unexpected client mip')
            continue
        count=max(1,w>>level)*max(1,h>>level)
        expected=count*4 if encoding==3 else count*(2 if alpha else 1)
        if offsets[level]!=cursor or sizes[level]!=expected:raise ValueError('Client mip layout mismatch')
        cursor+=expected
    if cursor!=len(data):raise ValueError('Client payload size mismatch')
    return {'encoding':encoding,'alphaDepth':alpha,'preferredFormat':preferred,'width':w,'height':h}


def to_runtime(data,component=False,*,palette_mode='maxcoverage'):
    """Reuse every neural mip; only body RGB palette quantization may be lossy."""
    if palette_mode not in PALETTE_MODES:raise ValueError('Unknown palette mode')
    images=raw_levels(data)
    if not component:
        result=assemble(images[0].size,3,8,2,[image.tobytes('raw','BGRA') for image in images])
        maximum=0;error_sum=0;channels=0
    else:
        # Train one palette across every mip. The historical max-coverage mode
        # prioritizes rare accents; median/dither trades that for smoother ramps.
        rgb=b''.join(image.convert('RGB').tobytes() for image in images)
        method=Image.Quantize.MEDIANCUT if palette_mode=='median-dither' else Image.Quantize.MAXCOVERAGE
        colors=Image.frombytes('RGB',(len(rgb)//3,1),rgb).quantize(colors=256,method=method,dither=Image.Dither.NONE)
        values=colors.getpalette()[:768];values+= [0]*(768-len(values))
        palette=bytes(v for i in range(256) for v in (values[3*i+2],values[3*i+1],values[3*i],0))
        alpha=0 if all(image.getchannel('A').getextrema()==(255,255) for image in images) else 8
        payloads=[];maximum=0;error_sum=0;channels=0;cursor=0
        if palette_mode=='median-dither':
            # Diffuse error over the real 2D mip, never over the concatenated
            # palette-training strip or across mip boundaries. Alpha stays exact.
            quantized=[image.convert('RGB').quantize(palette=colors,dither=Image.Dither.FLOYDSTEINBERG) for image in images]
            indices=b''.join(image.tobytes() for image in quantized)
            mapped=b''.join(image.convert('RGB').tobytes() for image in quantized)
        else:
            indices=colors.tobytes();mapped=colors.convert('RGB').tobytes()
        for image in images:
            count=image.width*image.height
            payloads.append(indices[cursor:cursor+count]+(image.getchannel('A').tobytes() if alpha else b''))
            restored=Image.frombytes('RGB',image.size,mapped[cursor*3:(cursor+count)*3]);cursor+=count
            difference=np.asarray(restored,dtype=np.int16)-np.asarray(image.convert('RGB'),dtype=np.int16)
            visible=np.asarray(image.getchannel('A'))>0;delta=difference[visible]
            if delta.size:maximum=max(maximum,int(np.abs(delta).max()));error_sum+=int(np.square(delta.astype(np.int64)).sum());channels+=delta.size
        result=assemble(images[0].size,1,alpha,8,payloads,palette)
    info=validate(result,component)
    # Independent decoder checks the palette/alpha layout of each mip.
    for level,before in enumerate(images):
        if not component:continue
        offset,size=struct.unpack_from('<I',result,20+level*4)[0],struct.unpack_from('<I',result,84+level*4)[0]
        single=assemble(before.size,1,info['alphaDepth'],8,[result[offset:offset+size]],result[148:1172])
        after=decode_blp(single)
        if before.getchannel('A').tobytes()!=after.getchannel('A').tobytes():raise ValueError('Alpha changed during deployment encoding')
    return result,{**info,'paletteMode':palette_mode if component else None,'allMipAlphaExact':True,'allMipRgbaExact':not component,'visibleRgbQuantizationMax':maximum,'visibleRgbQuantizationSquaredError':error_sum,'visibleRgbChannels':channels}
