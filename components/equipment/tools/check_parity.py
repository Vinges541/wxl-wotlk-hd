"""Independent CPU PyTorch / GPU MLX forward check on a fixed synthetic input."""
import argparse,json
from pathlib import Path
import numpy as np

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=['torch','mlx']);p.add_argument('--weights',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reference',type=Path);p.add_argument('--streamed',action='store_true',help='Check the full-frame streamed MLX forward');a=p.parse_args()
 x=np.random.default_rng(12340).uniform(0,1,(1,12,16,3)).astype(np.float32)
 if a.stage=='torch':
  import torch
  import torch.nn.functional as f
  state=torch.load(a.weights,map_location='cpu',weights_only=True);s=state.get('params_ema',state.get('params',state))
  def conv(v,name):return f.conv2d(v,s[name+'.weight'],s[name+'.bias'],padding=1)
  def dense(v,name):
   parts=[v]
   for i in range(1,5):parts.append(f.leaky_relu(conv(torch.cat(parts,1),name+f'.conv{i}'),.2))
   return conv(torch.cat(parts,1),name+'.conv5')*.2+v
  with torch.inference_mode():
   v=torch.from_numpy(x).permute(0,3,1,2);feat=conv(v,'conv_first');body=feat
   for i in range(23):
    y=body
    for j in range(1,4):y=dense(y,f'body.{i}.rdb{j}')
    body=y*.2+body
   v=feat+conv(body,'conv_body')
   for i in [1,2]:v=f.leaky_relu(conv(f.interpolate(v,scale_factor=2,mode='nearest'),f'conv_up{i}'),.2)
   v=conv(f.leaky_relu(conv(v,'conv_hr'),.2),'conv_last')
   output=v.permute(0,2,3,1).numpy()
  np.save(a.output,output)
 else:
  import mlx.core as mx
  from realesrgan_mlx.archs import RRDBNet
  if not mx.metal.is_available():raise RuntimeError('GPU required')
  mx.set_default_device(mx.gpu)
  if a.streamed:
   from wxl_equipment.mlx_inference import MLXUpscaler
   from wxl_equipment.assets import sha
   wrapper=MLXUpscaler(a.weights,sha(a.weights.read_bytes()),'RealESRNet_x4plus');m=wrapper.forward_streamed
  else:
   m=RRDBNet(3,3,scale=4,num_feat=64,num_block=23,num_grow_ch=32)
   m.load_weights(str(a.weights),strict=True);m.eval()
  out=m(mx.array(x));mx.eval(out)
  reference=np.load(a.reference,allow_pickle=False);diff=np.abs(np.asarray(out)-reference)
  report={'maxAbsoluteError':float(diff.max()),'meanAbsoluteError':float(diff.mean()),'tolerance':.0001,'passed':bool(diff.max()<.0001),'input':'synthetic-seed-12340-12x16','reference':'official-pth-PyTorch-CPU-fp32','device':str(mx.default_device()),'forward':'streamed-full-frame' if a.streamed else 'full-frame'}
  a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
  if not report['passed']:raise ValueError('Parity failed')
if __name__=='__main__':main()
