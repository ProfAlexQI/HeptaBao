#!/usr/bin/env python3
"""Align every staged product workflow with the current executed profile."""
import json, sys, subprocess
from pathlib import Path
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root/'scripts'))
from repository_integrity_v1_9 import load_yaml
current=root/'.github/workflows/plan-v1.9.0-full-repository-convergence.yml'
s=current.read_text();old='${{ runner.temp }}/heptabao-v190-target';new='/tmp/heptabao-v190-${{ github.run_id }}-${{ github.run_attempt }}-${{ matrix.source_kind }}'
if s.count(old)!=1:raise SystemExit('unexpected current CI input')
s=s.replace(old,new);current.write_text(s)
paths={'1.5.0':'control-plane-vertical-slice','1.6.0':'runtime-recovery-operations','1.7.0':'service-ha-plugin-compatibility','1.8.0':'operational-service'}
for version,suffix in paths.items():
 target=root/f'.github/workflows/plan-v{version}-{suffix}.yml'
 target.write_text(s.replace('name: HeptaBao V1.9.0 full repository convergence',f'name: HeptaBao V{version} inherited profile on V1.9.0').replace('v1.9.0-pr-',f'v{version}-pr-').replace('name: v1.9.0 /',f'name: v{version} /'))
contract=root/'planning/HEPTABAO_WORKFLOW_CONTRACT_V1_9.json';v=json.loads(contract.read_text());v['job']=load_yaml(current,strings=True)['jobs']['validate'];contract.write_text(json.dumps(v,indent=2)+'\n')
p=root/'scripts/workflow_contract_v1_9.py';s=p.read_text();needle="    steps = job['steps']\n"
if s.count(needle)!=1:raise SystemExit('workflow validator anchor drift')
s=s.replace(needle,"    if any('runner.' in str(item) for item in job.get('env', {}).values()):\n        raise ValueError('runner context is unavailable in job-level env')\n"+needle)
s+='''
    # The staged V1.5-V1.8 workflows explicitly execute the current profile,
    # including every current and version-bound historical regression lane.
    current = (root/'.github/workflows/plan-v1.9.0-full-repository-convergence.yml').read_text()
    inherited = {'1.5.0':'control-plane-vertical-slice','1.6.0':'runtime-recovery-operations','1.7.0':'service-ha-plugin-compatibility','1.8.0':'operational-service'}
    for version, suffix in inherited.items():
        path = root/f'.github/workflows/plan-v{version}-{suffix}.yml'
        expected = current.replace('name: HeptaBao V1.9.0 full repository convergence',f'name: HeptaBao V{version} inherited profile on V1.9.0').replace('v1.9.0-pr-',f'v{version}-pr-').replace('name: v1.9.0 /',f'name: v{version} /')
        if not path.is_file() or path.read_text() != expected:
            raise ValueError('inherited workflow lost current full-regression profile: '+str(path))
'''
p.write_text(s)
p=root/'tests/plan/test_repository_integrity_v1_9.py';s=p.read_text();needle='        return root\n    def reject_change';replacement='''        for path in (ROOT/'.github/workflows').glob('plan-v1.[5678].0-*.yml'):
            shutil.copyfile(path,root/'.github/workflows'/path.name)
        return root
    def reject_change'''
if s.count(needle)!=1:raise SystemExit('test fixture anchor drift')
s=s.replace(needle,replacement)
needle="if __name__=='__main__': unittest.main()"
s=s.replace(needle,'''    def test_unavailable_runner_context_fails_even_with_matching_contract(self):
        root=self.candidate();p=root/'.github/workflows/plan-v1.9.0-full-repository-convergence.yml'
        value=load_yaml(p,strings=True);value['jobs']['validate']['env']['CARGO_TARGET_DIR']='${{ runner.temp }}/bad'
        p.write_text(yaml.safe_dump(value));contract=root/'planning/HEPTABAO_WORKFLOW_CONTRACT_V1_9.json'
        expected=json.loads(contract.read_text());expected['job']=value['jobs']['validate'];contract.write_text(json.dumps(expected))
        with self.assertRaises(ValueError):validate_workflow(root)
    def test_inherited_wildcard_replay_fails(self):
        root=self.candidate();p=root/'.github/workflows/plan-v1.6.0-runtime-recovery-operations.yml'
        p.write_text(p.read_text().replace('python scripts/run_repository_regressions_v1_9.py','python -m unittest discover'))
        with self.assertRaises(ValueError):validate_workflow(root)
    def test_inherited_profile_may_not_disappear(self):
        root=self.candidate();(root/'.github/workflows/plan-v1.5.0-control-plane-vertical-slice.yml').unlink()
        with self.assertRaises(ValueError):validate_workflow(root)
    def test_inherited_profile_may_not_skip_checks(self):
        root=self.candidate();p=root/'.github/workflows/plan-v1.8.0-operational-service.yml'
        p.write_text(p.read_text().replace('  validate:\\n','  validate:\\n    if: false\\n'))
        with self.assertRaises(ValueError):validate_workflow(root)
'''+needle)
p.write_text(s)
p=root/'docs/plan/HEPTABAO_PLAN_V1_9_0_FULL_REPOSITORY_CONVERGENCE.md'
if not p.is_file():raise SystemExit('missing current plan')
p.write_text(p.read_text()+'''
## Current workflow execution profile

The V1.5-V1.8 source stages were not independently merged or qualified.
Their retained pull-request workflow names now explicitly execute the V1.9
current profile: complete source-manifest and module checks, every assigned
current and immutable historical regression lane, platform/Oracle tests,
deterministic source packaging, and strict Rust tests/Clippy. No historical
closure receipt is created by this routing. Each workflow still executes
both the exact head and prospective merge with read-only permissions.
Job-level environment expressions must not reference runner context; runtime
temporary paths use step environment or GitHub/matrix-bound job identifiers.
''')
subprocess.run([sys.executable,'scripts/render_repository_state_v1_9.py','--write'],cwd=root,check=True)
print('PASS current and inherited workflow execution profiles synchronized')
