"""CASE-001 software baseline generator. Never runs or modifies legacy scripts.

World geometry is a polygonal representation of the same commands sent to SU.
All sizes are software-test parameters, not approved engineering specifications.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
from pathlib import Path
import mesh

SOURCE_DIR = Path(__file__).resolve().parents[1] / 'assets' / 'case001' / 'stages'
RUN_ROOT = Path('outputs')  # Legacy writer is not the portable entry point.
PARAMETER_SCHEMA = json.loads(Path(__file__).with_name('parameter_schema.json').read_text(encoding='utf-8'))['parameters']
DEFAULTS = {p['key']:p['default'] for p in PARAMETER_SCHEMA}
CREATE_OPS = {"create_box", "create_cylinder", "create_prism"}
IGNORED_OPS = {"clear_generated", "add_label", "zoom_extents", "save_copy", "write_view", "export_model"}
DISCLAIMER = "可调设计草案；非采购型号、加工图或受力批准。截面与节点几何供评审，螺纹、焊缝、材料和安装工艺须深化。构件数和网格体积不得直接作为采购量。"


def validate_parameters(parameters):
    if set(parameters) != set(DEFAULTS):
        raise ValueError("parameters must contain exactly the declared baseline dimensions")
    for key, value in parameters.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be a finite positive millimeter value")
    if parameters["tube_wall"] * 2 >= parameters["tube_od"]:
        raise ValueError("tube_wall must be strictly less than tube_od/2")
    for rule in PARAMETER_SCHEMA:
        value=parameters[rule['key']]
        if not rule['min']<=value<=rule['max']:raise ValueError(f"{rule['key']} outside software draft range")
    if parameters['tube_od']/2-parameters['tube_wall']<=14:raise ValueError('tube bore leaves insufficient draft sleeve material around M24 rod')


def source_files(source_dir=SOURCE_DIR):
    paths = sorted(Path(source_dir).glob("[0-9][0-9]-recording_v5_*.json"))
    if len(paths) != 13:
        raise ValueError(f"expected 13 V5 stages, found {len(paths)}")
    return paths


def read_source(source_dir=SOURCE_DIR):
    commands, fingerprints = [], []
    for path in source_files(source_dir):
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"))
        fingerprints.append({"path": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        for index, command in enumerate(payload["commands"]):
            commands.append((copy.deepcopy(command), f"assets/case001/stages/{path.name}#commands/{index}"))
    return commands, fingerprints


def role_for(name):
    if "钢压板_" in name:
        return "pressure_plate"
    if "上销轴_" in name or "压头销轴_" in name:
        return "hinge_pin"
    if "Φ48钢管_" in name:
        return "steel_tube"
    return "other"


def corrected_command(original, parameters):
    command = copy.deepcopy(original)
    role = role_for(command["name"])
    nominal = {"role": role, "status": "software_test_baseline_not_engineering_approval"}
    if role == "pressure_plate":
        command["size_mm"][2] = parameters["plate_thickness"]
        command["material"] = f"PressurePlate{parameters['plate_thickness']:g}"
        nominal["thickness_mm"] = parameters["plate_thickness"]
    elif role == "hinge_pin":
        command["radius_mm"] = parameters["pin_diameter"] / 2
        command["material"] = f"Pin{parameters['pin_diameter']:g}"
        nominal["diameter_mm"] = parameters["pin_diameter"]
    elif role == "steel_tube":
        command["op"] = "create_tube"
        command["name"] = command["name"].replace("Φ48钢管", f"Φ{parameters['tube_od']:g}钢管")
        command["radius_mm"] = parameters["tube_od"] / 2
        command["inner_radius_mm"] = parameters["tube_od"] / 2 - parameters["tube_wall"]
        command["material"] = f"Phi{parameters['tube_od']:g}x{parameters['tube_wall']:g}Tube"
        nominal.update(outer_diameter_mm=parameters["tube_od"], wall_thickness_mm=parameters["tube_wall"],
                       inner_diameter_mm=parameters["tube_od"] - 2 * parameters["tube_wall"])
    if command["op"] == "create_box":
        nominal["size_mm"] = command["size_mm"][:]
    elif command["op"] in {"create_cylinder", "create_tube"}:
        nominal["length_mm"] = command["height_mm"]
        nominal.setdefault("diameter_mm", command["radius_mm"] * 2)
    return command, nominal


def base_wireframe(command):
    """Vertices in source world coordinates, before group transforms."""
    if command["op"] == "create_box":
        x, y, z = command["origin_mm"]
        a, b, c = command["size_mm"]
        vertices = [[x, y, z], [x+a, y, z], [x+a, y+b, z], [x, y+b, z],
                    [x, y, z+c], [x+a, y, z+c], [x+a, y+b, z+c], [x, y+b, z+c]]
        edges = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4],
                 [0, 4], [1, 5], [2, 6], [3, 7]]
        return vertices, edges
    if command["op"] in {"create_cylinder", "create_tube"}:
        x, y, z = command["center_mm"]  # legacy center_mm means BASE circle center
        segments = command.get("segments", 32)
        vertices, edges = [], []
        radii = [command["radius_mm"]]
        if command["op"] == "create_tube":
            radii.append(command["inner_radius_mm"])
        for radius in radii:
            start = len(vertices)
            for elevation in (z, z + command["height_mm"]):
                vertices.extend([[x + radius * math.cos(i * 2 * math.pi / segments),
                                  y + radius * math.sin(i * 2 * math.pi / segments), elevation]
                                 for i in range(segments)])
            for i in range(segments):
                j = (i + 1) % segments
                edges.extend([[start+i, start+j], [start+segments+i, start+segments+j],
                              [start+i, start+segments+i]])
        return vertices, edges
    raise ValueError(f"unsupported geometry in V5 baseline: {command['op']}")


def apply_transforms(vertices, transforms):
    points = copy.deepcopy(vertices)
    for transform in transforms:
        translation = transform.get("translation_mm", [0, 0, 0])
        points = [[p[i] + translation[i] for i in range(3)] for p in points]
        # Matches legacy Geometry.transform: translation, then current bounds center;
        # world X/Y/Z rotations use this same center within one transform command.
        center = [(min(p[i] for p in points) + max(p[i] for p in points)) / 2 for i in range(3)]
        for axis, degrees in enumerate(transform.get("rotation_deg", [0, 0, 0])):
            if not degrees:
                continue
            c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
            rotated = []
            for point in points:
                x, y, z = [point[i] - center[i] for i in range(3)]
                q = ([x, c*y-s*z, s*y+c*z] if axis == 0 else
                     [c*x+s*z, y, -s*x+c*z] if axis == 1 else
                     [c*x-s*y, s*x+c*y, z])
                rotated.append([q[i] + center[i] for i in range(3)])
            points = rotated
    return points


def build_legacy_scene(parameters=None, run_id="CASE-001-B1", source_dir=SOURCE_DIR):
    parameters = dict(DEFAULTS if parameters is None else parameters)
    validate_parameters(parameters)
    originals, fingerprints = read_source(source_dir)
    parts, by_original_name, commands = [], {}, []
    for original, reference in originals:
        operation = original["op"]
        if operation in CREATE_OPS:
            name = original["name"]
            if name in by_original_name:
                raise ValueError(f"duplicate source part: {name}")
            command, nominal = corrected_command(original, parameters)
            part_id = f"P{len(parts)+1:03d}"
            display_name = command["name"]
            command["name"] = f"{part_id}_{display_name}"
            part = {"id": part_id, "name": display_name, "source_name": name,
                    "kind": command["op"].removeprefix("create_"),
                    "command": command, "transforms": [], "material": command.get("material"),
                    "source_ref": reference, "nominal": nominal,
                    "limitations": ["软件验证基准；连接间隙、材料性能和加工公差未验算。"]}
            parts.append(part)
            by_original_name[name] = part
            commands.append(copy.deepcopy(command))
        elif operation == "transform":
            if original["target"] not in by_original_name:
                raise ValueError(f"transform before create: {original['target']}")
            part = by_original_name[original["target"]]
            transform = {key: copy.deepcopy(original[key]) for key in ("rotation_deg", "translation_mm") if key in original}
            part["transforms"].append(transform)
            commands.append({"op": "transform", "target": part["command"]["name"], **copy.deepcopy(transform)})
        elif operation not in IGNORED_OPS:
            raise ValueError(f"unhandled source operation: {operation}")
    for part in parts:
        vertices, edges = base_wireframe(part["command"])
        part["world_vertices"] = apply_transforms(vertices, part["transforms"])
        part["world_edges"] = edges
    scene = {"schema_version": "case001.scene.v1", "run_id": run_id, "parameters_mm": parameters,
             "baseline_status": "software_test_only_not_engineering_approval", "source_files": fingerprints,
             "transform_convention": "translation_then_current_bounds_center_world_xyz_rotations_in_original_order",
             "limitations": [DISCLAIMER, "按历史构件原点保留位置；改变截面后连接贴合仍须复核。"], "parts": parts}
    return scene, commands


def build_scene(parameters=None, run_id='CASE-001-v2', source_dir=SOURCE_DIR):
    supplied={} if parameters is None else dict(parameters)
    if set(supplied)-set(DEFAULTS):raise ValueError('unknown parameter keys')
    params={**DEFAULTS,**supplied};validate_parameters(params)
    legacy,_=build_legacy_scene(params,run_id,source_dir)
    parts=[];by_name={};source_parts=[];connections=[]
    def make(old, geometry, role=None, nominal=None, name=None, material=None):
        vertices,faces=geometry;mesh.validate(vertices,faces)
        p=copy.deepcopy(old)
        p['name']=name or old['name'];p['material']=material or old['material']
        p['kind']='mesh';p['transforms']=[]
        p['command']={'op':'create_mesh','name':p['id']+'_'+p['name'],'vertices_mm':vertices,'faces':faces,
                      'material':p['material'],'color_rgb':old['command'].get('color_rgb',[135,145,155])}
        p['world_vertices']=vertices;p['world_faces']=faces;p['world_edges']=mesh.edges(faces)
        prior=old.get('nominal',{}) if role is None else {'role':role,'status':'design_assumption_not_engineering_approved'}
        p['nominal']={**prior,**(nominal or {})}
        if role:p['nominal']['role']=role
        p['limitations']=[DISCLAIMER];return p
    for old in legacy['parts']:
        cmd=old['command'];op=cmd['op']
        if op=='create_box':v,f=mesh.box(cmd['origin_mm'],cmd['size_mm'])
        elif op=='create_tube':v,f=mesh.tube(cmd['center_mm'],[0,0,1],cmd['radius_mm'],cmd['inner_radius_mm'],cmd['height_mm'],cmd.get('segments',32))
        else:v,f=mesh.cylinder(cmd['center_mm'],[0,0,1],cmd['radius_mm'],cmd['height_mm'],cmd.get('segments',32))
        v=apply_transforms(v,old['transforms'])
        p=make(old,(v,f));p['source_command']=old['command'];p['source_transforms']=old['transforms']
        parts.append(p);by_name[old['source_name']]=p
        source_parts.append({'id':old['id'],'name':old['source_name'],'source_ref':old['source_ref'],'replaced_by':[old['id']]})
    def replace(name,geometry,role=None,nominal=None,display=None,material=None):
        old=by_name[name];p=make(old,geometry,role,nominal,display,material)
        parts[parts.index(old)]=p;by_name[name]=p;return p
    def remove(name,target):
        old=by_name.pop(name);parts.remove(old)
        next(s for s in source_parts if s['id']==old['id'])['replaced_by']=[target['id']]
    def fresh(name,geometry,role,nominal=None,material='DraftSteel',color=None):
        ident='N%03d'%(1+sum(p['id'].startswith('N') for p in parts))
        old={'id':ident,'name':name,'source_name':None,'source_ref':'design-draft:v2','material':material,
             'nominal':{'role':role,'status':'design_assumption_not_engineering_approved'},
             'command':{'color_rgb':color or [125,135,150]}}
        p=make(old,geometry,role,nominal);parts.append(p);return p
    def midpoint(p):return [(min(v[i] for v in p['world_vertices'])+max(v[i] for v in p['world_vertices']))/2 for i in range(3)]
    def record(kind,ids,center,checks,assumptions,pin_id=None):
        c={'id':f'C{len(connections)+1:03d}','kind':kind,'part_ids':ids,'center_mm':center,'axis':[1,0,0],
           'status':'draft_geometry_checked','checks':checks,'assumptions':assumptions}
        if pin_id:c['pin_id']=pin_id
        connections.append(c);return c
    frame_data={}
    # One-sided C section: same 50x100 outer envelope, no overlapping boxes.
    for frame in ('F2','F1','F3'):
        web=by_name[f'4_槽钢腹板_{frame}'];top=by_name[f'4_槽钢上翼缘_{frame}']
        cmd=top['source_command'];xmin,ymin,_=cmd['origin_mm'];length=cmd['size_mm'][1]
        zmin=web['source_command']['origin_mm'][2];cx=xmin+25
        tw,tf=params['channel_web'],params['channel_flange']
        profile=[[0,0],[50,0],[50,tf],[tw,tf],[tw,100-tf],[50,100-tf],[50,100],[0,100]]
        p=replace(f'4_槽钢腹板_{frame}',mesh.extrude(profile,[xmin,ymin,zmin],[1,0,0],[0,0,1],[0,1,0],length),
                  'channel_section',{'section_profile_mm':profile,'extrusion_axis':[0,1,0],'length_mm':length,'web_mm':tw,'flange_mm':tf,'width_mm':50,'height_mm':100},
                  f'单侧C形设计截面_{frame}',f'DraftC50x100_w{tw:g}_f{tf:g}')
        remove(f'4_槽钢上翼缘_{frame}',p);remove(f'4_槽钢下翼缘_{frame}',p)
        frame_data[frame]=(cx,xmin,ymin,zmin,length,p)
    # Complete 12 hinge nodes and centerline-aligned telescopic brace assemblies.
    for frame,(cx,xmin,ymin,zmin,length,channel) in frame_data.items():
        for side,sign in (('L',1),('R',-1)):
            plate=by_name[f'6{side}_钢压板_{frame}'];pc=midpoint(plate)
            normal=[0,-sign/math.sqrt(2),1/math.sqrt(2)];tangent=[0,1/math.sqrt(2),sign/math.sqrt(2)]
            plate_top=mesh.add(pc,mesh.mul(normal,params['plate_thickness']/2))
            lower=mesh.add(plate_top,mesh.mul(normal,55))
            upper_old=midpoint(by_name[f'5{side}_上销轴_{frame}']);upper=[cx,upper_old[1],zmin-60]
            axis=mesh.unit(mesh.sub(upper,lower));distance=mesh.norm(mesh.sub(upper,lower))
            tube_length=480;start=(distance-tube_length)/2;end=start+tube_length
            if start<=80:raise ValueError('brace geometry lacks room for the eye and adjustment stroke')
            # Rubber pad is now flush to the underside, not left at old displaced coordinates.
            rubber_center=mesh.sub(pc,mesh.mul(normal,params['plate_thickness']/2+4))
            origin=mesh.sub(mesh.sub(mesh.sub(rubber_center,[110,0,0]),mesh.mul(tangent,175)),mesh.mul(normal,4))
            replace(f'6{side}_橡胶垫_{frame}',mesh.extrude([[0,0],[220,0],[220,350],[0,350]],origin,[1,0,0],tangent,normal,8),'pressure_pad',{'thickness_mm':8})
            related=[]
            for label,center,outward,pin_name in (('upper',upper,mesh.mul(axis,-1),f'5{side}_上销轴_{frame}'),('lower',lower,axis,f'6{side}_压头销轴_{frame}')):
                ear=params['clevis_ear_thickness'];eye_thickness=24;gap=eye_thickness+2;outer=gap/2+ear
                hole=(params['pin_diameter']+params['pin_clearance'])/2;radius=params['pin_diameter']/2
                node_parts=[]
                if label=='upper':u,v=[0,1,0],[0,0,1];profile=[[-35,-35],[35,-35],[35,60],[-35,60]]
                else:u,v=tangent,normal;profile=[[-35,-55],[35,-55],[35,35],[-35,35]]
                for suffix,xoffset in (('A',-gap/2-ear),('B',gap/2)):
                    geo=mesh.annular_prism(profile,hole,mesh.add(center,[xoffset,0,0]),u,v,[1,0,0],ear)
                    info={'hole_diameter_mm':2*hole,'ear_thickness_mm':ear,'role':'clevis_ear'}
                    p=(replace(f'5{side}_上耳板{suffix}_{frame}',geo,'clevis_ear',info) if label=='upper' else
                       fresh(f'{frame}{side}_下铰耳板{suffix}',geo,'clevis_ear',info))
                    node_parts.append(p['id'])
                eye_u=mesh.unit(mesh.cross([1,0,0],outward))
                eye=fresh(f'{frame}{side}_{label}_带孔杆端眼板',mesh.annular_prism([[-30,-30],[30,-30],[20,55],[-20,55]],hole,mesh.add(center,[-12,0,0]),eye_u,outward,[1,0,0],24),
                          'hinge_eye',{'hole_diameter_mm':2*hole,'thickness_mm':24,'tail_length_mm':55})
                node_parts.append(eye['id'])
                shaft_start=-outer-4;groove_start=outer+3;shaft_end=groove_start+5
                profile_pin=[(shaft_start,radius),(groove_start,radius),(groove_start,radius-1),(groove_start+2,radius-1),(groove_start+2,radius),(shaft_end,radius)]
                pin=replace(pin_name,mesh.lathe(profile_pin,center,[1,0,0],[0,1,0]),'hinge_pin',
                            {'diameter_mm':2*radius,'length_mm':shaft_end-shaft_start,'groove_depth_mm':1,'measurement_axis':[1,0,0],'measurement_origin':center},material=f'Pin{2*radius:g}')
                node_parts.append(pin['id'])
                head=fresh(f'{frame}{side}_{label}_销头',mesh.cylinder(mesh.add(center,[shaft_start-6,0,0]),[1,0,0],radius+6,6),'pin_head',{'thickness_mm':6})
                node_parts.append(head['id'])
                for side_label,xoffset in (('左',-outer-3),('右',outer)):
                    washer=fresh(f'{frame}{side}_{label}_{side_label}垫片',mesh.tube(mesh.add(center,[xoffset,0,0]),[1,0,0],radius+7,hole,3),'pin_washer',{'hole_diameter_mm':2*hole,'thickness_mm':3})
                    node_parts.append(washer['id'])
                retainer=fresh(f'{frame}{side}_{label}_开口挡圈',mesh.split_ring(mesh.add(center,[groove_start+.25,0,0]),[1,0,0],radius+5,radius-.8,1.5),'pin_retainer',{'groove_width_mm':2,'ring_thickness_mm':1.5,'opening_angle_deg':60})
                node_parts.append(retainer['id']);related+=node_parts
                record('hinge',node_parts+[channel['id'] if label=='upper' else plate['id']],center,
                       {'coaxial_error_mm':0,'diametral_clearance_mm':params['pin_clearance'],'eye_side_clearance_mm':1,'ear_base_to_support_gap_mm':0,
                        'legacy_pin_center_shift_mm':mesh.norm(mesh.sub(center,upper_old)) if label=='upper' else None},
                       ['耳板与支承面按待设计焊接连接；眼板与丝杆端面贴合，焊缝/制造工艺未批准。','销槽、开口挡圈和垫片尺寸均为可审查的设计假设，非标准采购件。'],pin['id'])
            tube=replace(f'5{side}_Φ48钢管_{frame}',mesh.tube(mesh.add(lower,mesh.mul(axis,start)),axis,params['tube_od']/2,params['tube_od']/2-params['tube_wall'],tube_length),
                         'steel_tube',{'outer_diameter_mm':params['tube_od'],'inner_diameter_mm':params['tube_od']-2*params['tube_wall'],'wall_thickness_mm':params['tube_wall'],'length_mm':tube_length,'measurement_axis':axis,'measurement_origin':mesh.add(lower,mesh.mul(axis,start))},
                         f'5{side}_Φ{params["tube_od"]:g}×{params["tube_wall"]:g}钢管_{frame}',f'Phi{params["tube_od"]:g}x{params["tube_wall"]:g}Tube')
            related.append(tube['id'])
            for label,a,b in (('下',55,start+35),('上',end-35,distance-55)):
                rod=replace(f'5{side}_{label}M24丝杆_{frame}',mesh.cylinder(mesh.add(lower,mesh.mul(axis,a)),axis,12,b-a),'adjusting_rod',{'diameter_mm':24,'length_mm':b-a,'thread':'M24 schematic'})
                related.append(rod['id'])
            for label,pos in (('下',start),('上',end-35)):
                sleeve=fresh(f'{frame}{side}_{label}管端螺纹衬套',mesh.tube(mesh.add(lower,mesh.mul(axis,pos)),axis,params['tube_od']/2-params['tube_wall'],12,35),'threaded_bush',{'thread':'M24 schematic','length_mm':35,'bore_diameter_mm':24})
                related.append(sleeve['id'])
            for label,pos in (('下',start-16),('上',end)):
                nut=replace(f'5{side}_{label}调节螺母_{frame}',mesh.tube(mesh.add(lower,mesh.mul(axis,pos)),axis,24,12,16),'adjusting_nut',{'thread':'M24 schematic','length_mm':16},material='M24DraftNut')
                related.append(nut['id'])
            record('adjustable_brace',related,mesh.mul(mesh.add(lower,upper),.5),
                   {'centerline_error_mm':0,'rod_eye_face_gap_mm':0,'tube_bush_radial_gap_mm':0,'bush_engagement_mm':35},
                   ['螺纹用孔/杆名义接触面简化；有效啮合长度、防松与焊接强度仍需工程设计。'])
    # Rebuild existing tie-node end brackets: drilled anchor plate, seated shelf,
    # side gussets and two-sided washer/nut capture. Existing tie remains a boundary.
    for frame,(cx,xmin,ymin,zmin,length,channel) in frame_data.items():
        for side,direction in (('L',1),('R',-1)):
            plate_name=f'3{side}_夹座钢板_{frame}';old=by_name[plate_name];cmd=old['source_command'];px,py,pz=cmd['origin_mm'];sx,sy,sz=cmd['size_mm']
            tie=by_name[f'2{side}_M20既有对拉杆端_{frame}'];tc=midpoint(tie);hole=11
            plate=replace(plate_name,mesh.annular_prism([[px-cx,pz-tc[2]],[px+sx-cx,pz-tc[2]],[px+sx-cx,pz+sz-tc[2]],[px-cx,pz+sz-tc[2]]],hole,[cx,py,tc[2]],[1,0,0],[0,0,1],[0,1,0],sy),
                          'anchor_plate',{'hole_diameter_mm':22,'thickness_mm':sy})
            face=py+sy if direction==1 else py;beam_end=ymin if direction==1 else ymin+length
            ys=sorted((face,beam_end+direction*40));shelf=replace(f'3{side}_背楞卡板_{frame}',mesh.box([cx-100,ys[0],zmin-8],[200,ys[1]-ys[0],8]),'clamp_shelf',{'thickness_mm':8},f'{frame}{side}_梁端承托板')
            ids=[plate['id'],shelf['id'],channel['id'],tie['id']]
            for dx in (-65,65):
                x=xmin-8 if dx<0 else xmin+50
                profile=[[0,0],[direction*abs(beam_end-face),0],[0,150]]
                gusset=replace(f'3{side}_M16抱箍腿_{dx}_{frame}',mesh.extrude(profile,[x,face,zmin],[0,1,0],[0,0,1],[1,0,0],8),'clamp_gusset',{'thickness_mm':8},f'{frame}{side}_承托侧加劲板{dx}','DraftGussetPlate8')
                ids.append(gusset['id'])
            for label,is_inside in (('内',True),('外',False)):
                contact=face if is_inside else (py if direction==1 else py+sy)
                toward=direction if is_inside else -direction
                washer=fresh(f'{frame}{side}_{label}锚接垫片',mesh.tube([cx,contact,tc[2]],[0,toward,0],25,11,3),'anchor_washer',{'hole_diameter_mm':22,'thickness_mm':3})
                geo=mesh.tube([cx,contact+toward*3,tc[2]],[0,toward,0],25,10,30)
                nut=(replace(f'3{side}_对拉杆螺母_{frame}',geo,'anchor_nut',{'thread':'M20 schematic','length_mm':30}) if is_inside else
                     fresh(f'{frame}{side}_外锚接螺母',geo,'anchor_nut',{'thread':'M20 schematic','length_mm':30}))
                ids += [washer['id'],nut['id']]
            record('tie_anchor_bracket',ids,[cx,face,zmin],{'legacy_beam_end_to_plate_gap_mm':abs(beam_end-face),'shelf_to_beam_gap_mm':0,'anchor_hole_to_rod_axis_error_mm':0},
                   ['借用既有M20对拉杆及两侧可接近螺母的假设；现场背楞与拉杆剩余长度须复核。','承托板、加劲板、夹板为待设计焊接支架；非已批准替换既有节点。'])
    # Angle top lip is brought into exact contact with all three C undersides.
    for side in ('L','R'):
        horizontal=by_name[f'11{side}_L50角钢水平肢'];cmd=horizontal['source_command'];x,y,z=cmd['origin_mm'];length=cmd['size_mm'][0];t=params['angle_thickness']
        target_z=next(iter(frame_data.values()))[3]-50
        profile=([[0,0],[50,0],[50,50],[50-t,50],[50-t,t],[0,t]] if side=='L' else [[0,0],[50,0],[50,t],[t,t],[t,50],[0,50]])
        angle=replace(f'11{side}_L50角钢水平肢',mesh.extrude(profile,[x,y,target_z],[0,1,0],[0,0,1],[1,0,0],length),
                      'angle_section',{'section_profile_mm':profile,'extrusion_axis':[1,0,0],'length_mm':length,'thickness_mm':t,'leg_mm':50},f'{side}_L形设计纵梁',f'DraftL50x50x{t:g}')
        remove(f'11{side}_L50角钢竖直肢',angle)
        for frame,(cx,xmin,ymin,zmin,length,channel) in frame_data.items():
            record('angle_to_channel',[angle['id'],channel['id']],[cx,y+(50-t/2 if side=='L' else t/2),zmin],
                   {'legacy_vertical_gap_mm':zmin-(z+50),'contact_gap_mm':0,'nominal_contact_area_mm2':50*t},
                   ['角钢顶面与横梁底面贴合；连接按待设计焊接假设，焊脚、材质、拆装方案未批准。'])
    # Do not hide remaining secondary-module incompleteness behind the new joints.
    diagnostics=[{'id':'D-VIBRATION','status':'requires_engineering_detail','description':'传振模块原示意保留；其连杆端部与压持区域/振动底板的实际连接、隔振导向和限位间隙仍须专项深化，不计入已完成主静力连接。'}]
    for p in parts:mesh.validate(p['world_vertices'],p['world_faces'])
    scene={**legacy,'parts':parts,'parameters_mm':params,'parameter_sources':{r['key']:r['source'] for r in PARAMETER_SCHEMA},
           'baseline_status':'adjustable_design_draft_not_engineering_approval','limitations':[DISCLAIMER],
           'source_parts':source_parts,'connections':connections,'diagnostics':diagnostics,
           'geometry_contract':'All create_mesh vertices/faces are world coordinates; faces are ordered single-ring polygons; holes use closed annular patches.'}
    return scene,[p['command'] for p in parts]


def component_manifest(scene):
    return {"schema_version": "case001.components.v1", "run_id": scene["run_id"],
            "parameters_mm": scene["parameters_mm"], "limitations": scene["limitations"],
            "connections":scene.get('connections',[]),"source_parts":scene.get('source_parts',[]),"diagnostics":scene.get('diagnostics',[]),
            "parts": [{key: copy.deepcopy(part[key]) for key in
                       ("id", "name", "source_name", "kind", "material", "source_ref", "nominal", "limitations")}
                      for part in scene["parts"]]}


def batches(commands, run_id, limit=180):
    if not 1 <= limit <= 200:
        raise ValueError("batch limit must be within 1..200")
    return [{"protocol": "1.0", "id": f"{run_id}_geometry_{index//limit+1:02d}",
             "description": "CASE-001 B1 software verification geometry only; not engineering approved",
             "commands": copy.deepcopy(commands[index:index+limit])}
            for index in range(0, len(commands), limit)]


def write_run(run_dir, parameters, source_dir=SOURCE_DIR):
    run_dir = Path(run_dir).resolve()
    if run_dir.parent != RUN_ROOT.resolve():
        raise ValueError(f"run-dir must be a direct child of {RUN_ROOT}")
    scene, commands = build_scene(parameters, run_dir.name, source_dir)
    manifest = component_manifest(scene)
    payloads = {"scene.json": scene, "component_manifest.json": manifest}
    payloads.update({f"batch_{i:02d}.json": batch for i, batch in enumerate(batches(commands, run_dir.name), 1)})
    targets = [run_dir / name for name in [*payloads, "component_manifest.csv"]]
    if any(path.exists() for path in targets):
        raise FileExistsError("refusing to replace existing run artifacts; use a new run_id")
    run_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (run_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with (run_dir / "component_manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "name", "kind", "material", "role", "nominal", "limitations"])
        writer.writeheader()
        for part in manifest["parts"]:
            writer.writerow({**{key: part[key] for key in ("id", "name", "kind", "material")},
                             "role": part["nominal"]["role"], "nominal": json.dumps(part["nominal"], ensure_ascii=False),
                             "limitations": DISCLAIMER})
    return {"run_dir": str(run_dir), "parts": len(scene["parts"]), "commands": len(commands),
            "batch_count": len(payloads)-2, "status": "files_prepared_not_executed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument('--parameters',type=Path)
    for key, default in DEFAULTS.items():
        parser.add_argument("--" + key.replace("_", "-"), type=float, default=None)
    args = parser.parse_args()
    parameters=json.loads(args.parameters.read_text(encoding='utf-8-sig')) if args.parameters else {}
    parameters=parameters.get('parameters_mm',parameters)
    parameters.update({key:getattr(args,key) for key in DEFAULTS if getattr(args,key) is not None})
    print(json.dumps(write_run(args.run_dir, parameters), ensure_ascii=False))


if __name__ == "__main__":
    main()
