"""Compare rendered primary-skin surfaces, ignoring storage order and unused LOD vertices."""
import itertools,math,struct
from .creatures import array
from .model.chunks import read_chunks


def primary_mesh(model,skin,geosets=None):
    chunks=read_chunks(model) if model[:4]==b'MD21' else []
    b=chunks[0].payload if chunks else model
    if b[:4]!=b'MD20' or skin[:4]!=b'SKIN':raise ValueError('Expected M2 and SKIN')
    n,o=array(b,60,48);vertices=[struct.unpack_from('<3f',b,o+i*48) for i in range(n)]
    n,o=array(skin,4,2);indices=list(struct.unpack_from('<'+'H'*n,skin,o))
    base=struct.unpack_from('<I',skin,44)[0] if any(c.tag=='LDV1' for c in chunks) else 0
    n,o=array(skin,12,2);triangles=list(struct.unpack_from('<'+'H'*n,skin,o))
    ns,so=array(skin,28,48);nb,bo=array(skin,36,24)
    drawn={struct.unpack_from('<H',skin,bo+i*24+4)[0] for i in range(nb)}
    if any(i>=ns for i in drawn):raise ValueError('Invalid draw section')
    selected=[]
    for i in sorted(drawn):
        at=so+i*48;gid,level=struct.unpack_from('<HH',skin,at)
        keep=(not 0<gid<900 or gid in geosets) if geosets is not None else (gid%10==0 or gid%100==1)
        if not keep:continue
        start,count=struct.unpack_from('<HH',skin,at+8);start+=level<<16
        if count%3 or start+count>len(triangles):raise ValueError('Invalid section triangles')
        for j in range(start,start+count,3):
            ids=[base+indices[k] for k in triangles[j:j+3]]
            if any(k>=len(vertices) for k in ids):raise ValueError('Invalid vertex reference')
            selected.append(tuple(vertices[k] for k in ids))
    if not selected:raise ValueError('No rendered primary geometry')
    return selected


class PointIndex:
    def __init__(self,tolerance):self.tolerance=tolerance;self.cells={};self.points=[]
    def cell(self,p):return tuple(math.floor(x/self.tolerance) for x in p)
    def find(self,p):
        cell=self.cell(p)
        for delta in itertools.product((-1,0,1),repeat=3):
            for i in self.cells.get(tuple(a+b for a,b in zip(cell,delta)),[]):
                if math.dist(self.points[i],p)<=self.tolerance:return i
        return None
    def add(self,p):
        i=self.find(p)
        if i is not None:return i
        i=len(self.points);self.points.append(p);self.cells.setdefault(self.cell(p),[]).append(i);return i


def surfaces(mesh,index,transform=lambda p:p):
    result=set()
    for tri in mesh:
        t=[transform(p) for p in tri];a,b,c=t
        ab=[b[i]-a[i] for i in range(3)];ac=[c[i]-a[i] for i in range(3)]
        cross=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]]
        if sum(x*x for x in cross)<1e-16:continue
        ids=tuple(sorted(index.add(p) for p in t))
        if len(set(ids))==3:result.add(ids)
    return result


def compare_meshes(old,new,tolerance=.001):
    old_points={p for t in old for p in t};new_points={p for t in new for p in t}
    bounds=lambda points:([min(p[i] for p in points) for i in range(3)],[max(p[i] for p in points) for i in range(3)])
    lo,hi=bounds(old_points);ln,hn=bounds(new_points)
    extent=[hi[i]-lo[i] for i in range(3)];new_extent=[hn[i]-ln[i] for i in range(3)]
    ratio=[extent[i]/new_extent[i] for i in range(3) if new_extent[i]>tolerance]
    variants=[('original-coordinates',lambda p:p)]
    # A uniform coordinate normalization alone is not a new surface model.
    if ratio and max(ratio)-min(ratio)<.001:
        scale=sum(ratio)/len(ratio)
        shift=[(hi[i]+lo[i]-scale*(hn[i]+ln[i]))/2 for i in range(3)]
        variants.append(('uniform-scale-and-translation',lambda p:tuple(p[i]*scale+shift[i] for i in range(3))))
    choices=[]
    for method,transform in variants:
        index=PointIndex(tolerance);a=surfaces(old,index);nv=len(index.points);b=surfaces(new,index,transform)
        shared=len(a&b)
        choices.append({'oldSurfaces':len(a),'newSurfaces':len(b),'sharedSurfaces':shared,
                        'removedSurfaces':len(a-b),'addedSurfaces':len(b-a),'newUnmatchedPoints':len(index.points)-nv,
                        'oldPoints':nv,'normalization':method,'tolerance':tolerance})
    result=max(choices,key=lambda r:r['sharedSurfaces']/(r['oldSurfaces']+r['newSurfaces']-r['sharedSurfaces']))
    result['changed']=bool(result['removedSurfaces'] or result['addedSurfaces'])
    result['oldExtent']=extent;result['newExtent']=new_extent
    return result
