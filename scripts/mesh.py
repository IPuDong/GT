"""Small deterministic closed-mesh primitives; no CAD or network dependencies."""
import math

def add(a,b):return [a[i]+b[i] for i in range(3)]
def sub(a,b):return [a[i]-b[i] for i in range(3)]
def mul(a,s):return [x*s for x in a]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def norm(a):return math.sqrt(dot(a,a))
def unit(a):return mul(a,1/norm(a))

def signed_volume(vertices,faces):
    # Translation near the origin reduces cancellation for world-coordinate meshes.
    origin=vertices[0];v=[sub(p,origin) for p in vertices]
    return sum(dot(v[f[0]],cross(v[f[i]],v[f[i+1]]))/6 for f in faces for i in range(1,len(f)-1))

def finish(vertices,faces):
    if signed_volume(vertices,faces)<0:faces=[list(reversed(f)) for f in faces]
    return vertices,faces

def edges(faces):return [list(e) for e in sorted({tuple(sorted((f[i],f[(i+1)%len(f)]))) for f in faces for i in range(len(f))})]

def triangulate(poly):
    def area(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    indices=list(range(len(poly)))
    if sum(poly[i][0]*poly[(i+1)%len(poly)][1]-poly[(i+1)%len(poly)][0]*poly[i][1] for i in indices)<0:indices.reverse()
    result=[]
    while len(indices)>3:
        found=False
        for j in range(len(indices)):
            a,b,c=indices[j-1],indices[j],indices[(j+1)%len(indices)]
            if area(poly[a],poly[b],poly[c])<=1e-9:continue
            others=[k for k in indices if k not in (a,b,c)]
            if any(area(poly[a],poly[b],poly[k])>=-1e-9 and area(poly[b],poly[c],poly[k])>=-1e-9 and area(poly[c],poly[a],poly[k])>=-1e-9 for k in others):continue
            result.append([a,b,c]);indices.pop(j);found=True;break
        if not found:raise ValueError('cannot triangulate profile')
    result.append(indices)
    return result

def extrude(poly,origin,u,v,axis,length):
    if sum(poly[i][0]*poly[(i+1)%len(poly)][1]-poly[(i+1)%len(poly)][0]*poly[i][1] for i in range(len(poly)))<0:poly=list(reversed(poly))
    n=len(poly)
    vertices=[add(add(origin,mul(u,x)),add(mul(v,y),mul(axis,z))) for z in (0,length) for x,y in poly]
    triangles=triangulate(poly)
    faces=[list(reversed(t)) for t in triangles]+[[i+n for i in t] for t in triangles]
    faces += [[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)]
    return finish(vertices,faces)

def box(origin,size):return extrude([[0,0],[size[0],0],[size[0],size[1]],[0,size[1]]],origin,[1,0,0],[0,1,0],[0,0,1],size[2])

def annular_prism(poly,hole_radius,origin,u,v,axis,length,segments=24):
    # Hole center is local (0,0). Add angles through every outer corner so no
    # rectangular/hexagonal corner is accidentally cut off by radial meshing.
    angles=[2*math.pi*i/segments for i in range(segments)]
    angles += [math.atan2(y,x)%(2*math.pi) for x,y in poly]
    angles=sorted(set(round(a,12) for a in angles))
    outer=[];inner=[]
    for a in angles:
        dx,dy=math.cos(a),math.sin(a);hits=[]
        for i,p in enumerate(poly):
            q=poly[(i+1)%len(poly)];sx,sy=q[0]-p[0],q[1]-p[1]
            det=dx*sy-dy*sx
            if abs(det)<1e-10:continue
            t=(p[0]*sy-p[1]*sx)/det;f=(p[0]*dy-p[1]*dx)/det
            if t>0 and -1e-8<=f<=1+1e-8:hits.append(t)
        if not hits:raise ValueError('hole center is outside star-convex profile')
        radius=min(hits)
        if radius<=hole_radius+0.05:raise ValueError('hole breaks through plate edge')
        outer.append([radius*dx,radius*dy]);inner.append([hole_radius*dx,hole_radius*dy])
    n=len(angles);verts=[]
    for z,ring in ((0,outer),(0,inner),(length,outer),(length,inner)):
        verts += [add(add(origin,mul(u,x)),add(mul(v,y),mul(axis,z))) for x,y in ring]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        faces += [[i,j,n+j,n+i],[2*n+i,3*n+i,3*n+j,2*n+j],
                  [i,2*n+i,2*n+j,j],[n+i,n+j,3*n+j,3*n+i]]
    return finish(verts,faces)

def lathe(profile,origin,axis,u,segments=24):
    axis=unit(axis);u=unit(u);v=cross(axis,u)
    vertices=[]
    for along,radius in profile:
        vertices += [add(add(origin,mul(axis,along)),add(mul(u,radius*math.cos(i*2*math.pi/segments)),mul(v,radius*math.sin(i*2*math.pi/segments)))) for i in range(segments)]
    faces=[list(reversed(list(range(segments))))]
    for j in range(len(profile)-1):
        for i in range(segments):faces.append([j*segments+i,j*segments+(i+1)%segments,(j+1)*segments+(i+1)%segments,(j+1)*segments+i])
    faces.append(list(range((len(profile)-1)*segments,len(profile)*segments)))
    return finish(vertices,faces)

def cylinder(origin,axis,radius,length,segments=24):
    u=[1,0,0] if abs(unit(axis)[0])<0.9 else [0,1,0]
    return lathe([(0,radius),(length,radius)],origin,axis,u,segments)

def tube(origin,axis,outer,inner,length,segments=24):
    axis=unit(axis);u=[1,0,0] if abs(axis[0])<0.9 else [0,1,0];v=cross(axis,u)
    vertices=[]
    for z,r in ((0,outer),(0,inner),(length,outer),(length,inner)):
        vertices += [add(add(origin,mul(axis,z)),add(mul(u,r*math.cos(i*2*math.pi/segments)),mul(v,r*math.sin(i*2*math.pi/segments)))) for i in range(segments)]
    n=segments;faces=[]
    for i in range(n):
        j=(i+1)%n
        faces += [[i,j,n+j,n+i],[2*n+i,3*n+i,3*n+j,2*n+j],[i,2*n+i,2*n+j,j],[n+i,n+j,3*n+j,3*n+i]]
    return finish(vertices,faces)

def split_ring(origin,axis,outer,inner,length,segments=24):
    axis=unit(axis);u=[0,1,0];v=cross(axis,u);angles=[math.radians(30+300*i/segments) for i in range(segments+1)]
    poly=[[outer*math.cos(a),outer*math.sin(a)] for a in angles]+[[inner*math.cos(a),inner*math.sin(a)] for a in reversed(angles)]
    return extrude(poly,origin,u,v,axis,length)

def validate(vertices,faces):
    if len(vertices)>20000 or len(faces)>30000:raise ValueError('mesh exceeds bound')
    if not vertices or not faces:raise ValueError('empty mesh')
    if any(len(p)!=3 or any(not isinstance(x,(int,float)) or not math.isfinite(x) or abs(x)>1e6 for x in p) for p in vertices):raise ValueError('invalid mesh vertices')
    directed={}
    for f in faces:
        if len(f)<3 or len(set(f))!=len(f) or any(type(i)!=int or not 0<=i<len(vertices) for i in f):raise ValueError('invalid face indices')
        for a,b in zip(f,f[1:]+f[:1]):
            key=tuple(sorted((a,b)));directed.setdefault(key,[]).append((a,b))
    if any(len(e)!=2 or e[0]!=tuple(reversed(e[1])) for e in directed.values()):raise ValueError('mesh is not a consistently oriented closed manifold')
    if signed_volume(vertices,faces)<=1e-6:raise ValueError('non-positive mesh volume')
    return True
