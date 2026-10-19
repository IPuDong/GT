"""Deterministic open formats, using the Python standard library only."""
import base64, html, json, math, struct, zlib, zipfile
from pathlib import Path
from xml.sax.saxutils import escape
import mesh

FIXED=(2020,1,1,0,0,0)
def zip_files(path, files):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,FIXED);info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,data.encode('utf-8') if isinstance(data,str) else data)

def triangles(p):
    v=p['world_vertices'];out=[]
    for f in p['world_faces']:
        if len(f)==3: out.append(f);continue
        normal=[0.,0.,0.]
        for a,b in zip(f,f[1:]+f[:1]):normal=mesh.add(normal,mesh.cross(v[a],v[b]))
        omit=max(range(3),key=lambda i:abs(normal[i]));axes=[i for i in range(3) if i!=omit]
        local=mesh.triangulate([[v[i][a] for a in axes] for i in f])
        # Preserve original winding rather than the triangulator's 2-D orientation.
        for t in local:
            ids=[f[i] for i in t]
            n=mesh.cross(mesh.sub(v[ids[1]],v[ids[0]]),mesh.sub(v[ids[2]],v[ids[0]]))
            if mesh.dot(n,normal)<0:ids.reverse()
            out.append(ids)
    return out

def color(p):return p['command'].get('color_rgb',[135,145,155])
def bounds(parts):
    verts=[v for p in parts for v in p['world_vertices']]
    return [min(v[i] for v in verts) for i in range(3)],[max(v[i] for v in verts) for i in range(3)]

def obj(scene,path):
    lines=['# CASE-001 design draft; coordinates in mm; material grades unconfirmed']
    offset=1
    for p in scene['parts']:
        lines.append('o '+p['id'])
        lines += ['v '+' '.join(format(x,'.12g') for x in v) for v in p['world_vertices']]
        lines += ['f '+' '.join(str(offset+i) for i in f) for f in p['_triangles']]
        offset+=len(p['world_vertices'])
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')

def gltf(scene,path):
    blob=bytearray();views=[];access=[];meshes=[];nodes=[];materials=[]
    def add(data,target,component,typ,count,limits=None):
        while len(blob)%4:blob.append(0)
        views.append({'buffer':0,'byteOffset':len(blob),'byteLength':len(data),'target':target});blob.extend(data)
        acc={'bufferView':len(views)-1,'componentType':component,'count':count,'type':typ}
        if limits:acc.update(min=limits[0],max=limits[1])
        access.append(acc);return len(access)-1
    for p in scene['parts']:
        # glTF convention: meters, Y up. Source X,Y,Z -> X,Z,-Y.
        vs=[[v[0]/1000,v[2]/1000,-v[1]/1000] for v in p['world_vertices']]
        inds=[i for f in p['_triangles'] for i in f]
        limits=([min(v[i] for v in vs) for i in range(3)],[max(v[i] for v in vs) for i in range(3)])
        a=add(struct.pack('<'+'f'*len(vs)*3,*[x for v in vs for x in v]),34962,5126,'VEC3',len(vs),limits)
        b=add(struct.pack('<'+'I'*len(inds),*inds),34963,5125,'SCALAR',len(inds))
        materials.append({'name':p['id']+'_appearance','doubleSided':True,'pbrMetallicRoughness':{'baseColorFactor':[x/255 for x in color(p)]+[1],'metallicFactor':.15,'roughnessFactor':.65}})
        meshes.append({'name':p['id'],'primitives':[{'attributes':{'POSITION':a},'indices':b,'material':len(materials)-1}]})
        nodes.append({'name':p['id'],'mesh':len(meshes)-1,'extras':{'label':p['name'],'nominal':p['nominal']}})
    data={'asset':{'version':'2.0','generator':'engineering-microinnovation 0.1.0'},'scene':0,'scenes':[{'nodes':list(range(len(nodes)))}],'nodes':nodes,'meshes':meshes,'materials':materials,'buffers':[{'byteLength':len(blob),'uri':'data:application/octet-stream;base64,'+base64.b64encode(blob).decode()}],'bufferViews':views,'accessors':access,'extras':{'source_units':'mm','units':'m','axis_transform':'x,z,-y','engineering_status':'pending'}}
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

def xlsx(path,sheets):
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    files={'_rels/.rels':f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>'}
    overrides=['<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>']
    work=[];rels=[]
    for si,(name,rows) in enumerate(sheets,1):
        work.append(f'<sheet name="{escape(name)}" sheetId="{si}" r:id="rId{si}"/>')
        rels.append(f'<Relationship Id="rId{si}" Type="{rel}/worksheet" Target="worksheets/sheet{si}.xml"/>')
        overrides.append(f'<Override PartName="/xl/worksheets/sheet{si}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        data=[]
        for ri,row in enumerate(rows,1):
            cells=[]
            for ci,val in enumerate(row,1):
                n=ci;col=''
                while n:n,a=divmod(n-1,26);col=chr(65+a)+col
                ref=f'{col}{ri}'
                if isinstance(val,(int,float)):cells.append(f'<c r="{ref}"><v>{val}</v></c>')
                else:cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(val))}</t></is></c>')
            data.append(f'<row r="{ri}">'+''.join(cells)+'</row>')
        files[f'xl/worksheets/sheet{si}.xml']=f'<worksheet xmlns="{ns}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="18" customWidth="1"/><col min="2" max="8" width="35" customWidth="1"/></cols><sheetData>'+''.join(data)+'</sheetData></worksheet>'
    files['xl/workbook.xml']=f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'+''.join(work)+'</sheets></workbook>'
    files['xl/_rels/workbook.xml.rels']='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(rels)+'</Relationships>'
    files['[Content_Types].xml']='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'+''.join(overrides)+'</Types>'
    zip_files(path,files)

def docx(path,paragraphs):
    body=[]
    for i,text in enumerate(paragraphs):
        sz=32 if i==0 else 21
        body.append(f'<w:p><w:pPr><w:spacing w:after="140"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Calibri" w:eastAsia="等线"/><w:sz w:val="{sz}"/></w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')
    doc='<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+''.join(body)+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr></w:body></w:document>'
    zip_files(path,{'word/document.xml':doc,'_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>','[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'})

class DXF:
    """Minimal deterministic UTF-8 DXF AC1021, no binary CAD dependency."""
    def __init__(self):self.entities=[]
    def entity(self,kind,values,layer='GEOMETRY'):
        self.entities.extend([(0,kind),(8,layer)]+values)
    def line(self,a,b,layer='GEOMETRY'):
        if math.dist(a,b)>1e-8:self.entity('LINE',[(10,a[0]),(20,a[1]),(30,0),(11,b[0]),(21,b[1]),(31,0)],layer)
    def text(self,s,x,y,size=2.4,layer='NOTE'):
        txt=str(s).replace('\n',' ')
        self.entity('TEXT',[(10,x),(20,y),(30,0),(40,size),(1,txt),(7,'STANDARD')],layer)
    def dim(self,a,b,y,label):
        self.line((a,y),(b,y),'DIM');self.line((a,y-2),(a,y+2),'DIM');self.line((b,y-2),(b,y+2),'DIM')
        self.text(label,(a+b)/2-8,y+2,2.2,'DIM')
    def save(self,path):
        p=[(0,'SECTION'),(2,'HEADER'),(9,'$ACADVER'),(1,'AC1021'),(9,'$INSUNITS'),(70,4),(0,'ENDSEC'),(0,'SECTION'),(2,'TABLES'),(0,'TABLE'),(2,'LTYPE'),(70,1),(0,'LTYPE'),(2,'CONTINUOUS'),(70,0),(3,'Solid'),(72,65),(73,0),(40,0),(0,'ENDTAB'),(0,'TABLE'),(2,'LAYER'),(70,4)]
        for name,col in [('GEOMETRY',7),('DIM',3),('NOTE',7),('FRAME',8)]:p.extend([(0,'LAYER'),(2,name),(70,0),(62,col),(6,'CONTINUOUS')])
        p.extend([(0,'ENDTAB'),(0,'TABLE'),(2,'STYLE'),(70,1),(0,'STYLE'),(2,'STANDARD'),(70,0),(40,0),(41,1),(50,0),(71,0),(42,2.5),(3,'simhei.ttf'),(4,''),(0,'ENDTAB'),(0,'ENDSEC'),(0,'SECTION'),(2,'ENTITIES')])
        p+=self.entities+[(0,'ENDSEC'),(0,'EOF')]
        # Valid table head handles avoid reader repair of otherwise parseable DXF.
        with_handles=[]
        for i,pair in enumerate(p):
            with_handles.append(pair)
            if pair[0]==2 and i and p[i-1]==(0,'TABLE'):
                with_handles.append((5,{'LTYPE':'F0','LAYER':'F1','STYLE':'F2'}[pair[1]]))
        p=with_handles
        path.write_text('\n'.join(str(v) if isinstance(v,str) else format(v,'.12g') for pair in p for v in pair)+'\n',encoding='utf-8')

def drawings(scene,folder):
    metadata=[]
    def sheet(name,title):
        d=DXF()
        for a,b in [((10,10),(410,10)),((410,10),(410,287)),((410,287),(10,287)),((10,287),(10,10)),((10,28),(410,28))]:d.line(a,b,'FRAME')
        d.text('工程微创新孵化平台 / '+title,16,277,4)
        d.text('CASE-001 | '+name+' | A3 | mm | 设计草案·未经工程审定',16,17,2.5)
        d.text('线框投影：包含遮挡边，不代表加工图。材料、焊缝、公差及受力待复核。',16,263,2.5)
        return d
    def view(d,parts,axes,box,label,scale):
        lo,hi=bounds(parts);x,y,w,h=box;cx=(lo[axes[0]]+hi[axes[0]])/2;cy=(lo[axes[1]]+hi[axes[1]])/2
        def project(v):return (x+w/2+(v[axes[0]]-cx)*scale,y+h/2+(v[axes[1]]-cy)*scale)
        for p in parts:
            v=p['world_vertices'];seen=set()
            for a,b in p['world_edges']:
                aa,bb=project(v[a]),project(v[b]);key=tuple(sorted((tuple(round(t,5) for t in aa),tuple(round(t,5) for t in bb))))
                if key in seen:continue
                seen.add(key);d.line(aa,bb)
        d.text(label+f'  1:{1/scale:g}',x,y+h+3,3)
        d.dim(x+w/2-(hi[axes[0]]-lo[axes[0]])*scale/2,x+w/2+(hi[axes[0]]-lo[axes[0]])*scale/2,y-5,f'{hi[axes[0]]-lo[axes[0]]:.2f}')
        return project
    # Three views on one sheet; fixed engineering scale, no stretched geometry.
    d=sheet('D01','总装三视图')
    for ax,box,name in [((0,1),(20,140,180,110),'俯视 X-Y'),((0,2),(20,45,180,70),'正视 X-Z'),((1,2),(215,45,180,70),'侧视 Y-Z')]:view(d,scene['parts'],ax,box,name,.04)
    d.text('完整构件 ID 与数量见 D04 / Excel 实例表；编号沿用同源场景。',215,200,2.5)
    roles=['channel_section','steel_tube','pressure_plate','hinge_pin']
    for i,r in enumerate(roles):
        p=next(p for p in scene['parts'] if p['nominal']['role']==r);d.text(p['id']+' '+p['name'],215,185-i*10,2.3)
    d.save(folder/'D01_assembly.dxf')
    d=sheet('D02','真实截面与尺寸')
    for i,role in enumerate(['channel_section','angle_section','steel_tube']):
        p=next(p for p in scene['parts'] if p['nominal']['role']==role);n=p['nominal'];x=24+i*128
        if role=='steel_tube':
            # Circle section generated from actual nominal radius checked against geometry.
            for diameter in [n['outer_diameter_mm'],n['inner_diameter_mm']]:
                d.entity('CIRCLE',[(10,x+50),(20,185),(30,0),(40,diameter/2)])
            details=[('外径',n['outer_diameter_mm']),('内径',n['inner_diameter_mm']),('壁厚',n['wall_thickness_mm'])]
        else:
            poly=n['section_profile_mm']
            for a,b in zip(poly,poly[1:]+poly[:1]):d.line((x+a[0],135+a[1]),(x+b[0],135+b[1]))
            details=[(k,n[k]) for k in (['width_mm','height_mm','web_mm','flange_mm'] if role=='channel_section' else ['leg_mm','thickness_mm'])]
        d.text(p['id']+' / '+role,x,248,2.7);d.text('截面 1:1；设计外形，非采购规格',x,118,2.2)
        for j,(label,val) in enumerate(details):d.text(f'{label} = {val:g} mm',x,104-j*9,2.5)
    d.save(folder/'D02_sections.dxf')
    d=sheet('D03','铰接节点与编号引线')
    conn=next(c for c in scene['connections'] if c['kind']=='hinge');ids=set(conn['part_ids'])
    parts=[p for p in scene['parts'] if p['id'] in ids and p['nominal']['role'] not in ['channel_section','pressure_plate']]
    pr=view(d,parts,(0,2),(25,110,210,120),'节点轴向投影',1)
    for i,p in enumerate(parts):
        lo,hi=bounds([p]);pt=pr([(a+b)/2 for a,b in zip(lo,hi)]);end=(270,238-i*14)
        d.line(pt,(255,end[1]),'DIM');d.line((255,end[1]),end,'DIM');d.text(p['id']+' '+p['name'],273,end[1]+1,2.1)
    d.text(f"销径 {scene['parameters_mm']['pin_diameter']:g}；孔销直径差 {scene['parameters_mm']['pin_clearance']:g}（草案）",25,73,3)
    d.text('孔、销、垫片及防脱件同源；螺纹简化，焊缝与配合公差未批准。',25,58,2.5)
    d.save(folder/'D03_joint.dxf')
    d=sheet('D04','完整构件编号索引')
    for i,p in enumerate(scene['parts']):
        col,row=divmod(i,60);d.text(p['id']+' '+p['nominal']['role'],17+col*97,253-row*3.55,1.7)
    d.save(folder/'D04_part_index.dxf')
    for p in sorted(folder.glob('*.dxf')):metadata.append({'file':p.name,'units':'mm','sheet_mm':[420,297],'status':'wireframe_design_draft'})
    return metadata

def render_png(scene,path,width=1100,height=780):
    """Orthographic triangle rasterization with a real z-buffer, no AI images."""
    lo,hi=bounds(scene['parts']);center=[(a+b)/2 for a,b in zip(lo,hi)]
    right=mesh.unit([1,1,0]);up=mesh.unit([-.55,.55,1]);depth=mesh.unit(mesh.cross(right,up))
    projected=[]
    for p in scene['parts']:
        vs=[mesh.sub(v,center) for v in p['world_vertices']]
        projected.append([(mesh.dot(v,right),mesh.dot(v,up),mesh.dot(v,depth)) for v in vs])
    allv=[v for vs in projected for v in vs];dx=max(v[0] for v in allv)-min(v[0] for v in allv);dy=max(v[1] for v in allv)-min(v[1] for v in allv)
    scale=min((width-90)/dx,(height-90)/dy);mx=(max(v[0] for v in allv)+min(v[0] for v in allv))/2;my=(max(v[1] for v in allv)+min(v[1] for v in allv))/2
    pixels=bytearray([248,250,253])*(width*height);zbuf=[-float('inf')]*(width*height)
    light=mesh.unit([.4,-.6,1])
    for p,vs in zip(scene['parts'],projected):
        screen=[((v[0]-mx)*scale+width/2,height/2-(v[1]-my)*scale,v[2]) for v in vs]
        for f in p['_triangles']:
            a,b,c=[screen[i] for i in f];den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(den)<1e-8:continue
            n=mesh.unit(mesh.cross(mesh.sub(p['world_vertices'][f[1]],p['world_vertices'][f[0]]),mesh.sub(p['world_vertices'][f[2]],p['world_vertices'][f[0]])))
            shade=.38+.62*abs(mesh.dot(n,light));rgb=bytes(max(0,min(255,int(ch*shade))) for ch in color(p))
            xmin=max(0,int(min(a[0],b[0],c[0])));xmax=min(width-1,math.ceil(max(a[0],b[0],c[0])))
            ymin=max(0,int(min(a[1],b[1],c[1])));ymax=min(height-1,math.ceil(max(a[1],b[1],c[1])))
            for y in range(ymin,ymax+1):
                for x in range(xmin,xmax+1):
                    u=((b[1]-c[1])*(x+.5-c[0])+(c[0]-b[0])*(y+.5-c[1]))/den
                    v=((c[1]-a[1])*(x+.5-c[0])+(a[0]-c[0])*(y+.5-c[1]))/den
                    if u>=-1e-8 and v>=-1e-8 and u+v<=1+1e-8:
                        z=u*a[2]+v*b[2]+(1-u-v)*c[2];idx=y*width+x
                        if z>zbuf[idx]:zbuf[idx]=z;pixels[idx*3:idx*3+3]=rgb
    raw=b''.join(b'\x00'+pixels[y*width*3:(y+1)*width*3] for y in range(height))
    def chunk(name,data):return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b''))

def viewer(scene,path,root):
    library=(root/'assets/vendor/three.r160.min.js').read_text('utf-8')
    model={'run_id':scene['run_id'],'parts':[{'id':p['id'],'name':p['name'],'vertices':p['world_vertices'],'triangles':p['_triangles'],'color':color(p)} for p in scene['parts']]}
    template=(root/'templates/viewer.html').read_text('utf-8')
    path.write_text(template.replace('__THREE_LIBRARY__',library).replace('__MODEL_JSON__',json.dumps(model,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')),encoding='utf-8')
