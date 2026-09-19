"""Local contact sheets and fidelity diagnostics; metrics are not ground-truth quality scores."""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);a=p.parse_args();r=a.workspace
 sources={name:json.loads((r/(name+'-inference.json')).read_text())['records'] for name in ['general','x4plus','realesrnet']}
 out=r/'comparisons';out.mkdir(exist_ok=True);metrics=[]
 for item,token in [(6098,'Chest_TU_M'),(16865,'Chest_TU_M'),(19364,'Sword_2H')]:
  picks={name:next(x for x in rows if x['itemId']==item and token in x['path']) for name,rows in sources.items()}
  original=Image.open(r/'cache'/picks['x4plus']['cacheKey']/'before.png').convert('RGBA')
  box=(64,0,192,64) if item==19364 else (0,0,128,64)
  size=(512,256);alpha=original.crop(box).getchannel('A').resize(size,Image.Resampling.NEAREST)
  images=[original.crop(box).resize(size,Image.Resampling.NEAREST),original.crop(box).resize(size,Image.Resampling.LANCZOS)]
  labels=['Original 4x nearest','Lanczos 4x']
  for name,entry in picks.items():
   raw=Image.open(r/'cache'/entry['cacheKey']/'raw-neural-4x.png').convert('RGB')
   images.append(raw.crop(tuple(v*4 for v in box)).convert('RGBA'));labels.append(name+' / raw MLX')
   native=raw.resize(original.size,Image.Resampling.LANCZOS)
   delta=np.abs(np.asarray(native,dtype=np.int16)-np.asarray(original.convert('RGB'),dtype=np.int16))
   visible=np.asarray(original.getchannel('A'))>0
   after=Image.open(r/'cache'/entry['cacheKey']/'after.png')
   expected=original.getchannel('A').resize(after.size,Image.Resampling.NEAREST)
   metrics.append({'itemId':item,'model':name,'rawCycleRgbMAE':float(delta[visible].mean()),'alphaExact':expected.tobytes()==after.getchannel('A').tobytes(),'seconds':entry['seconds'],'peakMemoryBytes':entry['peakMemoryBytes'],'notGroundTruthQuality':True})
  panel=Image.new('RGB',(512*len(images),290),(40,40,40));draw=ImageDraw.Draw(panel)
  for i,(image,label) in enumerate(zip(images,labels)):
   draw.text((i*512+8,9),label,fill='white');panel.paste(image.convert('RGB'),(i*512,30),alpha)
  panel.save(out/f'item-{item}-raw-models.png')
 (out/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
 print(json.dumps(metrics,indent=2))
if __name__=='__main__':main()
