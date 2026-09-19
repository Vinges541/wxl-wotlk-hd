"""Explicit local MLX execution. No auto-download or silent CPU device."""
import time
import numpy as np
from PIL import Image, ImageFilter
from .assets import sha


class MLXUpscaler:
    def __init__(self, weights, expected_sha256, variant):
        import mlx.core as mx
        from realesrgan_mlx.utils.weights import build_model
        if not mx.metal.is_available():raise RuntimeError('Metal unavailable; no CPU fallback')
        mx.set_default_device(mx.gpu)
        if sha(weights.read_bytes())!=expected_sha256:raise ValueError('Weight hash mismatch')
        # An explicit directory prevents the third-party resolver from using HF auto-download.
        if variant=='RealESRNet_x4plus':
            from realesrgan_mlx.archs import RRDBNet
            self.model=RRDBNet(3,3,scale=4,num_feat=64,num_block=23,num_grow_ch=32)
            self.model.load_weights(str(weights),strict=True)
            self.model.eval()
        else:
            self.model=build_model(variant,weights_dir=str(weights.parent),denoise_strength=1.0)
        self.weights_hash=expected_sha256
        self.variant=variant
        self.device='mlx-gpu'
        if variant=='RealESRNet_x4plus':
            from mlx.utils import tree_flatten
            if any(value.dtype!=mx.float32 for _,value in tree_flatten(self.model.parameters())):
                raise ValueError('RealESRNet weights must remain FP32')
        # Avoid keeping several texture sizes worth of temporary Metal buffers.
        mx.set_cache_limit(512*1024*1024)
        mx.eval(self.model.parameters())

    def forward_streamed(self, x):
        """Exact full-frame RRDB evaluation with bounded graph lifetime; no spatial tiles."""
        import mlx.core as mx
        import mlx.nn as nn
        from realesrgan_mlx.utils.spatial import interpolate_nearest_nhwc
        if self.variant!='RealESRNet_x4plus':raise ValueError('Streamed path requires the FP32 RRDB model')
        first=self.model.conv_first(x);mx.eval(first)
        body=first
        for block in self.model.body:
            # The residual-dense blocks retain the full image receptive field.
            inner=body
            for dense in (block.rdb1,block.rdb2,block.rdb3):
                inner=dense(inner);mx.eval(inner)
            body=inner*.2+body;mx.eval(body)
        feat=self.model.conv_body(body)+first;mx.eval(feat)
        del body,first,inner
        for convolution in (self.model.conv_up1,self.model.conv_up2):
            feat=nn.leaky_relu(convolution(interpolate_nearest_nhwc(feat,2)),.2);mx.eval(feat)
        feat=nn.leaky_relu(self.model.conv_hr(feat),.2);mx.eval(feat)
        out=self.model.conv_last(feat);mx.eval(out)
        return out

    def run(self, image, scale=2, strength=.35, tile=0):
        import mlx.core as mx
        if scale not in (1,2,4) or not 0 <= strength <= 1:raise ValueError('Invalid settings')
        image=image.convert('RGBA');w,h=image.size
        if tile:raise ValueError('Spatial input tiling is not enabled')
        if max(w,h)>1024 or w*h>1048576 or max(w,h)*scale>2048:raise ValueError('Full-frame budget exceeded')
        mx.reset_peak_memory();started=time.perf_counter()
        x=mx.array(np.asarray(image.convert('RGB'),dtype=np.float32)[None]/255)
        streamed=w*h>131072
        y=mx.clip(self.forward_streamed(x) if streamed else self.model(x),0,1);mx.eval(y)
        raw=Image.fromarray(np.rint(np.asarray(y[0])*255).astype('uint8'))
        size=(w*scale,h*scale)
        neural=raw.resize(size,Image.Resampling.LANCZOS)
        baseline=image.convert('RGB').resize(size,Image.Resampling.LANCZOS)
        base=np.asarray(baseline,dtype=np.float32)
        detail=np.asarray(neural,dtype=np.float32)-np.asarray(neural.filter(ImageFilter.GaussianBlur(max(1,scale))),dtype=np.float32)
        base_detail=base-np.asarray(baseline.filter(ImageFilter.GaussianBlur(max(1,scale))),dtype=np.float32)
        correction=np.clip(detail-base_detail,-24,24)*strength
        after=Image.fromarray(np.rint(np.clip(base+correction,0,255)).astype('uint8')).convert('RGBA')
        after.putalpha(image.getchannel('A').resize(size,Image.Resampling.NEAREST))
        self.raw=raw
        self.neural=neural
        report={'device':'mlx-gpu','variant':self.variant,'precision':('fp32' if self.variant=='RealESRNet_x4plus' else 'fp32-input-fp16-weights'),
                'weightsSha256':self.weights_hash,'seconds':time.perf_counter()-started,
                'scale':scale,'strength':strength,'tile':0,'forward':'streamed-full-frame' if streamed else 'full-frame','inputSize':[w,h],'outputSize':list(size),
                'alphaPolicy':'nearest-exact','maxRgbCorrection':float(abs(correction).max()),
                'peakMemoryBytes':mx.get_peak_memory(),'activeMemoryBytes':mx.get_active_memory(),
                'cacheMemoryBytes':mx.get_cache_memory(),'gameplayVerified':False}
        return after,report
