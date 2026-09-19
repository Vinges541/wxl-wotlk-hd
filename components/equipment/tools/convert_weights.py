"""Two-stage local conversion of official RRDB .pth to MLX FP32 safetensors."""
import argparse
from pathlib import Path
import hashlib
import json


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['numpy','mlx']);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--sha256',required=True);a=p.parse_args()
    if hashlib.sha256(a.input.read_bytes()).hexdigest()!=a.sha256:raise ValueError('Input hash mismatch')
    if a.output.exists():raise FileExistsError(a.output)
    if a.stage=='numpy':
        import torch,numpy as np
        checkpoint=torch.load(a.input,map_location='cpu',weights_only=True)
        state=checkpoint.get('params_ema',checkpoint.get('params',checkpoint))
        arrays={k:v.detach().cpu().numpy() for k,v in state.items()}
        np.savez(a.output,**arrays)
    else:
        import numpy as np
        import mlx.core as mx
        mx.set_default_device(mx.cpu)
        with np.load(a.input,allow_pickle=False) as arrays:
            weights={k:mx.array(v.transpose(0,2,3,1) if v.ndim==4 else v) for k,v in arrays.items()}
        mx.eval(weights);mx.save_safetensors(str(a.output),weights,metadata={'format':'mlx','precision':'fp32'})
    print(json.dumps({'inputSha256':a.sha256,'outputSha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'bytes':a.output.stat().st_size}))

if __name__=='__main__':main()
