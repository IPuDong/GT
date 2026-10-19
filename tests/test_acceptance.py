"""Local acceptance; NOT evidence of aily/WorkBuddy installation or AI consistency."""
import copy, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run

def main():
    out=Path(sys.argv[1]).resolve()
    if out.exists():raise FileExistsError('Use a new test directory')
    out.mkdir(parents=True)
    results=[]
    def call(args,seed='1'):
        return subprocess.run([sys.executable,'-S',str(ROOT/'scripts/run.py'),*map(str,args)],capture_output=True,text=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONHASHSEED':seed})
    def hashes(p):return {x.relative_to(p).as_posix():run.sha(x.read_bytes()) for x in sorted(p.rglob('*')) if x.is_file()}
    for i in range(1,4):
        r=call(['generate','--input',ROOT/'assets/case001/input.example.json','--out',out/f'run{i}'],str(i))
        assert r.returncode==0,r.stderr
        results.append({'test':f'generate_{i}_python_no_site_packages','status':'passed'})
    hs=[hashes(out/f'run{i}') for i in range(1,4)]
    assert hs[0]==hs[1]==hs[2]
    results.append({'test':'same_canonical_input_three_processes_all_file_hashes','status':'passed','files':len(hs[0])})
    data=run.read_json(ROOT/'assets/case001/input.example.json');changed=copy.deepcopy(data);changed['parameters_mm']['plate_thickness']=12;changed['parameters_mm']['pin_diameter']=22;changed['parameters_mm']['tube_wall']=4
    run.write_json(out/'changed-input.json',changed)
    r=call(['generate','--input',out/'changed-input.json','--out',out/'changed']);assert r.returncode==0,r.stderr
    for file in ['02_model/model.obj','02_model/model.gltf','02_model/render.png','03_drawings/D01_assembly.dxf','03_drawings/D02_sections.dxf','03_drawings/D03_joint.dxf','04_bom/components.xlsx']:
        assert run.sha((out/'run1'/file).read_bytes())!=run.sha((out/'changed'/file).read_bytes()),file
    results.append({'test':'changed_plate_pin_tube_propagates_with_geometry_readback','status':'passed'})
    for label,mut in [('AI_quantity',lambda d:d.update(quantity=234)),('bool_parameter',lambda d:d['parameters_mm'].update(pin_diameter=True)),('out_of_range',lambda d:d['parameters_mm'].update(tube_wall=25)),('missing_load_field',lambda d:d['requirements'].pop('loads')),('unsupported_case',lambda d:d.update(case_id='CASE-002'))]:
        bad=copy.deepcopy(data);mut(bad);p=out/(label+'.json');run.write_json(p,bad);target=out/(label+'_output')
        r=call(['generate','--input',p,'--out',target]);assert r.returncode!=0 and not target.exists(),label
        results.append({'test':'reject_'+label,'status':'passed'})
    r=call(['generate','--input',ROOT/'assets/case001/input.example.json','--out',out/'run1']);assert r.returncode!=0 and hs[0]==hashes(out/'run1')
    results.append({'test':'no_overwrite_existing_output','status':'passed'})
    r=call(['verify','--out',out/'run1']);assert r.returncode==0,r.stderr
    results.append({'test':'artifact_independent_format_readback','status':'passed'})
    # Deliberate corruption is restricted to this newly created test copy.
    obj=out/'run3/02_model/model.obj';raw=obj.read_bytes();obj.write_bytes(raw+b'# tamper\n')
    r=call(['verify','--out',out/'run3']);assert r.returncode!=0
    obj.write_bytes(raw)
    results.append({'test':'tampered_file_rejected','status':'passed'})
    standards=run.read_json(out/'run1/06_checks/standards.json');review=run.read_json(out/'run1/07_review/confirmation.template.json')
    assert standards['status']=='engineering_review_required' and review['status']=='pending'
    results.append({'test':'missing_standard_evidence_never_marked_compliant','status':'passed'})
    r=call(['probe','--out',out/'probe']);assert r.returncode==0,r.stderr
    results.append({'test':'stdlib_environment_probe_and_zip_creation','status':'passed'})
    report={'status':'passed','tests':results,'reproducibility_scope':'same structured input + same script version; local CPython only','AI_same_request_three_runs':'not_tested','platforms':{'WorkBuddy/evolution':'user_trial_pending','aily':'not_tested'},'file_hashes':hs[0]}
    run.write_json(out/'local-acceptance.json',report)
    print(json.dumps({'status':'passed','tests':len(results),'files_per_run':len(hs[0]),'report':str(out/'local-acceptance.json')},ensure_ascii=False))
if __name__=='__main__':main()
