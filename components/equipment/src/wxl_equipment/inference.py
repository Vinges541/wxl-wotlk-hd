"""Offline-only SRVGG inference; architecture adapted from Real-ESRGAN (BSD-3-Clause)."""
import os
import time
import numpy as np
from PIL import Image, ImageFilter
from .assets import sha


def network():
    import torch
    from torch import nn
    class SRVGG(nn.Module):
        def __init__(self):
            super().__init__()
            self.body = nn.ModuleList([nn.Conv2d(3, 64, 3, 1, 1), nn.PReLU(64)])
            for _ in range(32):
                self.body.extend([nn.Conv2d(64, 64, 3, 1, 1), nn.PReLU(64)])
            self.body.append(nn.Conv2d(64, 48, 3, 1, 1))
            self.upsampler = nn.PixelShuffle(4)
        def forward(self, x):
            out = x
            for layer in self.body:
                out = layer(out)
            return self.upsampler(out) + torch.nn.functional.interpolate(x, scale_factor=4, mode='nearest')
    return SRVGG()


class Upscaler:
    def __init__(self, weights, expected_sha256, device='mps'):
        if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK') == '1':
            raise ValueError('Disable implicit CPU fallback for measurable device provenance')
        import torch
        if sha(weights.read_bytes()) != expected_sha256:
            raise ValueError('Weight hash mismatch')
        if device == 'mps' and not torch.backends.mps.is_available():
            raise RuntimeError('MPS unavailable; no automatic CPU fallback')
        if device not in ('mps', 'cpu'):
            raise ValueError('Device must be mps or explicitly cpu')
        self.device = device
        self.model = network().eval()
        state = torch.load(weights, map_location='cpu', weights_only=True)
        self.model.load_state_dict(state.get('params_ema', state.get('params', state)), strict=True)
        self.model.to(device)
        self.weights_hash = expected_sha256

    def run(self, image, scale=2, strength=0.35, tile=128):
        import torch
        if scale not in (1, 2, 4) or not 0 <= strength <= 1 or tile < 32:
            raise ValueError('Invalid inference settings')
        image = image.convert('RGBA')
        if max(image.size)*scale > 2048:
            raise ValueError('Output exceeds supported client texture budget')
        started = time.perf_counter()
        rgb = np.asarray(image.convert('RGB'), dtype=np.float32) / 255
        h, w, _ = rgb.shape
        output = np.empty((h*4, w*4, 3), dtype=np.float32)
        # 34 convolutions: 34 source-pixel receptive radius; 40 avoids tile seams.
        halo = 40
        with torch.inference_mode():
            for y in range(0, h, tile):
                for x in range(0, w, tile):
                    x0,y0,x1,y1=max(0,x-halo),max(0,y-halo),min(w,x+tile+halo),min(h,y+tile+halo)
                    tensor=torch.from_numpy(rgb[y0:y1,x0:x1].copy()).permute(2,0,1)[None].to(self.device)
                    pred=self.model(tensor).clamp(0,1)[0].permute(1,2,0).cpu().numpy()
                    tw,th=min(tile,w-x),min(tile,h-y)
                    output[y*4:(y+th)*4,x*4:(x+tw)*4]=pred[(y-y0)*4:(y-y0+th)*4,(x-x0)*4:(x-x0+tw)*4]
        size=(w*scale,h*scale)
        neural=Image.fromarray(np.rint(output*255).astype('uint8')).resize(size,Image.Resampling.LANCZOS)
        baseline=image.convert('RGB').resize(size,Image.Resampling.LANCZOS)
        # Keep original low-frequency colour; only blend a bounded neural detail residual.
        blur=max(1,scale)
        detail=np.asarray(neural,dtype=np.float32)-np.asarray(neural.filter(ImageFilter.GaussianBlur(blur)),dtype=np.float32)
        base=np.asarray(baseline,dtype=np.float32)
        base_detail=base-np.asarray(baseline.filter(ImageFilter.GaussianBlur(blur)),dtype=np.float32)
        correction=np.clip(detail-base_detail,-24,24)*strength
        result=Image.fromarray(np.rint(np.clip(base+correction,0,255)).astype('uint8')).convert('RGBA')
        # Preserve masks exactly at native size; nearest-neighbour replication at integer enlargement.
        alpha=image.getchannel('A').resize(size,Image.Resampling.NEAREST)
        result.putalpha(alpha)
        if self.device=='mps':
            torch.mps.synchronize()
        report={'device':self.device,'torch':torch.__version__,'weightsSha256':self.weights_hash,
                'seconds':time.perf_counter()-started,'scale':scale,'strength':strength,'tile':tile,'halo':halo,
                'inputSize':[w,h],'outputSize':list(size),'alphaPolicy':'nearest-exact',
                'maxRgbCorrection':float(np.abs(correction).max()),
                'mpsAllocatedBytes':torch.mps.current_allocated_memory() if self.device=='mps' else None,
                'mpsDriverBytes':torch.mps.driver_allocated_memory() if self.device=='mps' else None,
                'gameplayVerified':False}
        return result,report
