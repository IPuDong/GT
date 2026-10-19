"""Portable CASE-001 generation. Python >=3.10; no pip, CAD, server or network."""
from __future__ import annotations
import argparse, collections, hashlib, json, math, os, platform, struct, sys, tempfile, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import base64
import case_generator as engine
import formats, mesh

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.1.0'
STAGES=['00_input','01_parameters','02_model','03_drawings','04_bom','05_documents','06_checks','07_review']
def canonical(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(data):return hashlib.sha256(data).hexdigest()
def write_json(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def read_json(path):return json.loads(Path(path).read_text('utf-8-sig'),parse_constant=lambda x:(_ for _ in ()).throw(ValueError('non-finite JSON')))

def schema_check(value,schema,where='$'):
    """Implements all keywords used by the shipped input schema (not a full validator)."""
    kind=schema.get('type')
    valid={'object':lambda:isinstance(value,dict),'array':lambda:isinstance(value,list),'string':lambda:isinstance(value,str),'number':lambda:isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)}
    if kind and not valid[kind]():raise ValueError(f'{where}: expected {kind}')
    if 'const' in schema and value!=schema['const']:raise ValueError(f'{where}: unsupported value')
    if 'enum' in schema and value not in schema['enum']:raise ValueError(f'{where}: unsupported choice')
    if kind=='number' and not schema.get('minimum',-math.inf)<=value<=schema.get('maximum',math.inf):raise ValueError(f'{where}: outside software draft range')
    if kind=='string' and any(ord(c)<32 and c not in '\n\t\r' for c in value):raise ValueError(f'{where}: control character not allowed')
    if kind=='object':
        props=schema.get('properties',{})
        if set(schema.get('required',[]))-set(value):raise ValueError(f'{where}: missing required fields')
        if schema.get('additionalProperties') is False and set(value)-set(props):raise ValueError(f'{where}: unknown fields {sorted(set(value)-set(props))}')
        for key,val in value.items():
            if key in props:schema_check(val,props[key],where+'.'+key)
    if kind=='array':
        if len(value)<schema.get('minItems',0):raise ValueError(f'{where}: empty array')
        if schema.get('uniqueItems') and len({canonical(v) for v in value})!=len(value):raise ValueError(f'{where}: duplicate items')
        for i,val in enumerate(value):schema_check(val,schema.get('items',{}),f'{where}[{i}]')

def input_data(path):
    data=read_json(path);schema_check(data,read_json(ROOT/'schemas/input.schema.json'))
    data['parameters_mm']={k:float(data['parameters_mm'][k]) for k in sorted(data['parameters_mm'])}
    engine.validate_parameters(data['parameters_mm'])
    return data

def geometry_checks(scene):
    rows=[];ids=[p['id'] for p in scene['parts']]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate part IDs')
    for p in scene['parts']:
        mesh.validate(p['world_vertices'],p['world_faces']);n=p['nominal'];role=n['role'];vs=p['world_vertices']
        # Independent vertex measurements, not trusting stored nominal values.
        if role=='pressure_plate':
            # Rotated plate: find its shortest perpendicular face-to-face dimension.
            spans=[]
            for f in p['world_faces']:
                normal=mesh.unit(mesh.cross(mesh.sub(vs[f[1]],vs[f[0]]),mesh.sub(vs[f[2]],vs[f[0]])))
                dots=[mesh.dot(v,normal) for v in vs];spans.append(max(dots)-min(dots))
            actual=min(spans);expected=scene['parameters_mm']['plate_thickness']
            if abs(actual-expected)>1e-6:raise ValueError(p['id']+' plate thickness mismatch')
            rows.append({'id':p['id'],'check':'plate_thickness','measured_mm':round(actual,6),'expected_mm':expected})
        if role=='steel_tube':
            axis=n['measurement_axis'];origin=n['measurement_origin'];rad=[]
            for v in vs:
                d=mesh.sub(v,origin);rad.append(mesh.norm(mesh.sub(d,mesh.mul(axis,mesh.dot(d,axis)))))
            od=max(rad)*2;wall=max(rad)-min(rad)
            if abs(od-scene['parameters_mm']['tube_od'])>1e-6 or abs(wall-scene['parameters_mm']['tube_wall'])>1e-6:raise ValueError(p['id']+' tube mismatch')
            rows.append({'id':p['id'],'check':'tube_od_wall','measured_mm':[round(od,6),round(wall,6)]})
        if role=='hinge_pin':
            # Pins run along X; mesh includes smaller retention grooves.
            lo,hi=formats.bounds([p]);diam=max(hi[1]-lo[1],hi[2]-lo[2])
            if abs(diam-scene['parameters_mm']['pin_diameter'])>1e-6:raise ValueError(p['id']+' pin diameter mismatch')
            rows.append({'id':p['id'],'check':'pin_diameter','measured_mm':round(diam,6)})
    for c in scene['connections']:
        if set(c['part_ids'])-set(ids):raise ValueError(c['id']+' dangling connection')
    return rows

def quantities(scene):
    groups=collections.defaultdict(list)
    for p in scene['parts']:
        n={k:v for k,v in p['nominal'].items() if k not in ['measurement_origin','measurement_axis','status','section_profile_mm','extrusion_axis']}
        groups[canonical({'role':n['role'],'appearance_label':p['material'],'spec':n})].append(p['id'])
    return [{'group':f'G{i:03d}',**json.loads(key),'instance_ids':ids,'quantity':len(ids),'quantity_basis':'model_instances_not_procurement'} for i,(key,ids) in enumerate(sorted(groups.items()),1)]

def generate(data,out):
    if out.exists():raise FileExistsError('Output path already exists; choose a new directory. No overwrite.')
    lock=read_json(ROOT/'assets/vendor/lock.json')['three.js']
    if sha((ROOT/'assets/vendor/three.r160.min.js').read_bytes())!=lock['sha256']:raise ValueError('three.js vendor checksum mismatch')
    engine_digest=sha(b''.join(p.name.encode()+p.read_bytes() for p in sorted((ROOT/'scripts').glob('*.py'))))
    run_id='CASE-001-'+sha((canonical(data)+engine_digest).encode())[:12]
    scene,_=engine.build_scene(data['parameters_mm'],run_id)
    measured=geometry_checks(scene)
    for p in scene['parts']:p['_triangles']=formats.triangles(p)
    out.mkdir(parents=True)
    for s in STAGES:(out/s).mkdir()
    write_json(out/'00_input/requirements.json',data['requirements'])
    write_json(out/'01_parameters/input.canonical.json',data)
    write_json(out/'01_parameters/parameter_provenance.json',{'sources':scene['parameter_sources'],'unknown_loads':True,'scope':'fixed CASE-001 layout; nine dimensions only','quantity_authority':'scripts derive quantities'})
    write_json(out/'01_parameters/components.derived.json',{'schema_version':'microinnovation.components.v1','quantity_authority':'script_derived_instances','components':[{'id':p['id'],'name':p['name'],'section_and_dimensions':p['nominal'],'material_grade_status':'pending','connection_ids':[c['id'] for c in scene['connections'] if p['id'] in c['part_ids']],'quantity':1} for p in scene['parts']]})
    write_json(out/'01_parameters/connections.derived.json',scene['connections'])
    write_json(out/'02_model/scene.json',scene)
    formats.obj(scene,out/'02_model/model.obj');formats.gltf(scene,out/'02_model/model.gltf')
    formats.viewer(scene,out/'02_model/viewer.html',ROOT)
    formats.render_png(scene,out/'02_model/render.png')
    drawings=formats.drawings(scene,out/'03_drawings');write_json(out/'03_drawings/drawing_index.json',drawings)
    groups=quantities(scene);write_json(out/'04_bom/quantities.json',groups)
    instance_rows=[['构件编号','名称','角色','实例数','设计/外观标签（非材质牌号）','名义参数','材料牌号状态']]
    instance_rows += [[p['id'],p['name'],p['nominal']['role'],1,p['material'],canonical(p['nominal']),'待确认'] for p in scene['parts']]
    group_rows=[['分组编号','角色','实例数量（非采购量）','构件编号','名义参数','外观标签']]+[[g['group'],g['role'],g['quantity'],','.join(g['instance_ids']),canonical(g['spec']),g['appearance_label']] for g in groups]
    param_rows=[['参数','值','单位','依据']]+[[r['label'],data['parameters_mm'][r['key']],'mm',r['source']] for r in engine.PARAMETER_SCHEMA]
    review_rows=[['待复核项','状态'],['荷载/强度/稳定/疲劳','未验算'],['材料/焊缝/螺纹/制造公差','待工程确认'],['传振模块连接','待深化'],['正式申报','待专业复核']]
    formats.xlsx(out/'04_bom/components.xlsx',[('构件实例',instance_rows),('同规格汇总',group_rows),('参数表',param_rows),('人工复核',review_rows)])
    types=read_json(ROOT/'templates/document_types.json')
    for name in data['document_types']:
        t=types[name];paras=[t['title'],'工程微创新孵化平台 | '+run_id,'设计草案；非正式申报文件。以下叙述为输入文本，程序不认证其事实与工程结论。',data['requirements']['problem'],'现场部位：'+data['requirements']['location'],'约束：'+data['requirements']['constraints'],'荷载：'+data['requirements']['loads']]
        for title,key in t['sections']:paras.extend([title,data['narrative'].get(key) or '待补充：需 AI 结合资料形成草案，并由专业人员确认。'])
        paras += ['同源参数（脚本填充）']+[r['label']+f"：{data['parameters_mm'][r['key']]:g} mm" for r in engine.PARAMETER_SCHEMA]
        paras += [f"模型实例数量（非采购量）：{len(scene['parts'])}",'关联成果：02_model/viewer.html；03_drawings/*.dxf；04_bom/components.xlsx','人工复核：荷载与承载、连接强度、焊缝、螺纹、加工公差、传振连接、规范适用性。','程序校核通过仅指软件范围，不能替代工程审定。']
        (out/f'05_documents/{name}.md').write_text('\n\n'.join(paras)+'\n',encoding='utf-8');formats.docx(out/f'05_documents/{name}.docx',paras)
    standards=[]
    for s in data['requirements']['standards']:
        missing=[k for k in ['standard_id','edition','clause','evidence_text','evidence_source'] if not s[k].strip()]
        standards.append({'standard_id':s['standard_id'],'clause':s['clause'],'evidence_completeness':'missing' if missing else 'provided_not_verified','missing':missing,'applicability':'requires_engineer','compliance':'not_evaluated','currency':'not_verified'})
    write_json(out/'06_checks/standards.json',{'status':'engineering_review_required','clauses':standards,'note':'仅核对证据字段是否齐全；无标准原文/计算依据时不得宣称符合规范。'})
    write_json(out/'06_checks/geometry.json',{'status':'passed_with_engineering_hold','closed_meshes':len(scene['parts']),'vertex_measurements':measured,'remaining_diagnostics':scene['diagnostics']})
    write_json(out/'07_review/confirmation.template.json',{'status':'pending','engineer':'','date':'','model_hash':'','drawing_hashes':{},'load_and_strength':'pending','materials_and_welds':'pending','vibration_detail':'pending','standards':'pending','manufacturing_or_filing_release':'not_authorized','note':'单独填写留档；生成脚本不会批准或覆盖工程结论。'})
    (out/'07_review/README.md').write_text('# 人工确认关\n\n日常评审可打开 HTML。加工制作、正式申报、受力关键构件必须由工程师在适用的 SketchUp/CAD 工具中复核；OBJ/glTF 导入支持依实际软件版本/插件核验，不保证所有版本原生支持。DXF 为线框设计草案，尚未进行隐藏线消除、制造公差与正式图审。\n',encoding='utf-8')
    manifest={'version':VERSION,'run_id':run_id,'input_sha256':sha(canonical(data).encode()),'engine_sha256':engine_digest,'status':'generated_pending_independent_readback','engineering_gate':'pending','parts':len(scene['parts']),'quantities':sum(g['quantity'] for g in groups),'files':{}}
    write_json(out/'manifest.json',manifest)
    result=verify(out,check_hashes=False)
    write_json(out/'06_checks/readback.json',result)
    manifest['status']='software_checks_passed_engineering_pending'
    manifest['files']={p.relative_to(out).as_posix():sha(p.read_bytes()) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json'}
    write_json(out/'manifest.json',manifest)
    return {'output':str(out),'run_id':run_id,'parts':len(scene['parts']),'status':manifest['status']}

def verify(out,check_hashes=True):
    manifest=read_json(out/'manifest.json')
    if check_hashes:
        actual={p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'}
        if actual!=set(manifest['files']):raise ValueError('artifact set mismatch')
        for rel,digest in manifest['files'].items():
            path=out/rel
            if not path.resolve().is_relative_to(out.resolve()):raise ValueError('unsafe manifest path')
            if sha(path.read_bytes())!=digest:raise ValueError('artifact hash mismatch: '+rel)
    scene=read_json(out/'02_model/scene.json');parts=scene['parts'];ids=[p['id'] for p in parts]
    data=input_data(out/'01_parameters/input.canonical.json')
    if scene['parameters_mm']!=data['parameters_mm']:raise ValueError('parameter-scene mismatch')
    geometry_checks(scene)
    derived=read_json(out/'01_parameters/components.derived.json')['components']
    if [p['id'] for p in derived]!=ids or any(p['quantity']!=1 for p in derived):raise ValueError('derived component table mismatch')
    for d,p in zip(derived,parts):
        if d['section_and_dimensions']!=p['nominal']:raise ValueError('derived section/dimension mismatch')
    # OBJ readback: identity and actual vertices, independent of report metadata.
    objects={};current=None
    for line in (out/'02_model/model.obj').read_text('utf-8').splitlines():
        if line.startswith('o '):current=line[2:];objects[current]=[]
        elif line.startswith('v '):objects[current].append([float(x) for x in line.split()[1:]])
    if list(objects)!=ids:raise ValueError('OBJ ID mismatch')
    for p in parts:
        if len(objects[p['id']])!=len(p['world_vertices']):raise ValueError('OBJ vertex count mismatch')
        for a,b in zip(objects[p['id']],p['world_vertices']):
            if max(abs(x-y) for x,y in zip(a,b))>1e-6:raise ValueError('OBJ coordinates mismatch')
    g=read_json(out/'02_model/model.gltf')
    if [n['name'] for n in g['nodes']]!=ids:raise ValueError('glTF ID mismatch')
    blob=base64.b64decode(g['buffers'][0]['uri'].split(',')[1])
    for p,node in zip(parts,g['nodes']):
        prim=g['meshes'][node['mesh']]['primitives'][0];acc=g['accessors'][prim['attributes']['POSITION']];view=g['bufferViews'][acc['bufferView']]
        verts=list(struct.iter_unpack('<fff',blob[view['byteOffset']:view['byteOffset']+view['byteLength']]))
        if len(verts)!=len(p['world_vertices']):raise ValueError('glTF vertices mismatch')
        for xyz,v in zip(verts,p['world_vertices']):
            if max(abs(a-b) for a,b in zip(xyz,[v[0]/1000,v[2]/1000,-v[1]/1000]))>1e-6:raise ValueError('glTF coordinates mismatch')
    groups=read_json(out/'04_bom/quantities.json')
    if groups!=quantities(scene):raise ValueError('BOM groups mismatch')
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(out/'04_bom/components.xlsx') as z:
        tree=ET.fromstring(z.read('xl/worksheets/sheet1.xml'));rows=tree.findall('s:sheetData/s:row',ns)[1:]
        xids=[r.find('s:c/s:is/s:t',ns).text for r in rows]
        counts=[float(r.findall('s:c',ns)[3].find('s:v',ns).text) for r in rows]
        if xids!=ids or any(c!=1 for c in counts):raise ValueError('Excel instance mismatch')
        tr=ET.fromstring(z.read('xl/worksheets/sheet2.xml'));rr=tr.findall('s:sheetData/s:row',ns)[1:]
        q=[int(r.findall('s:c',ns)[2].find('s:v',ns).text) for r in rr]
        if q!=[g['quantity'] for g in groups]:raise ValueError('Excel summary mismatch')
    dxf=(out/'03_drawings/D04_part_index.dxf').read_text('utf-8').splitlines();texts=[dxf[i+1] for i in range(0,len(dxf)-1,2) if dxf[i]=='1'];listed=[s.split()[0] for s in texts if s.split() and s.split()[0] in set(ids)]
    if listed!=ids:raise ValueError('DXF index mismatch')
    # Recompute drawing coordinates and annotations independently from saved scene.
    with tempfile.TemporaryDirectory(prefix='microinnovation-verify-') as temp:
        formats.drawings(scene,Path(temp))
        for p in Path(temp).glob('*.dxf'):
            if p.read_bytes()!=(out/'03_drawings'/p.name).read_bytes():raise ValueError('DXF geometry/annotation mismatch: '+p.name)
    text=(out/'02_model/viewer.html').read_text('utf-8');model=json.loads(text.split('<script id="model-data" type="application/json">')[1].split('</script>')[0].replace('<\\/','</'))
    if [p['id'] for p in model['parts']]!=ids:raise ValueError('HTML instance mismatch')
    for hp,p in zip(model['parts'],parts):
        if hp['vertices']!=p['world_vertices'] or hp['triangles']!=p['_triangles']:raise ValueError('HTML geometry mismatch')
    # three.js contains unused loader functions; only the application code is checked.
    app=text.rsplit('<script>',1)[1]
    if 'src="http' in text or 'fetch(' in app:raise ValueError('viewer external dependency detected')
    return {'status':'passed','readback':['OBJ vertices','glTF meter coordinates','HTML geometry','Excel instances + grouped quantities','DXF recomputed geometry + IDs'],'parts':len(ids),'engineering_review':'pending','limitations':['drawing readback is not independent CAD application approval','standards applicability not evaluated','render is deterministic mesh illustration, not photoreal engineering evidence']}

def probe(out):
    if out.exists():raise FileExistsError('Choose a new output directory')
    out.mkdir(parents=True)
    report={'python':platform.python_version(),'platform':platform.system(),'script_execution':'passed','file_creation':'passed','file_download':'not_verified','skill_installation':'not_verified','network_used':False,'external_packages':[]}
    write_json(out/'probe.json',report)
    (out/'download-test.txt').write_text('工程微创新 Skill 文件下载测试\n请从平台附件下载并确认能打开。\n',encoding='utf-8')
    formats.zip_files(out/'probe-download.zip',{'probe.json':canonical(report),'download-test.txt':(out/'download-test.txt').read_bytes()})
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='cmd',required=True)
    g=sub.add_parser('generate');g.add_argument('--input',type=Path,required=True);g.add_argument('--out',type=Path,required=True)
    v=sub.add_parser('verify');v.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('probe');p.add_argument('--out',type=Path,required=True)
    a=parser.parse_args()
    try:
        result=generate(input_data(a.input),a.out) if a.cmd=='generate' else verify(a.out) if a.cmd=='verify' else probe(a.out)
        print(json.dumps(result,ensure_ascii=False));return 0
    except Exception as e:
        print(json.dumps({'status':'failed','error_type':type(e).__name__,'message':str(e),'action':'修正输入或执行环境后使用新的输出目录重试；不得宣称成果已完成。'},ensure_ascii=False),file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
