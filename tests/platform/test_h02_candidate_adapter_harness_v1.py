import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('candidate', ROOT / 'scripts/h02_candidate_adapter_harness_v1.py')
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(mod)


def make_repo(root: Path, profile_name: str):
    profile = mod.PROFILES[profile_name]
    path = root / profile['manifest']
    path.parent.mkdir(parents=True, exist_ok=True)
    package = {'tokio': 'tokio', 'rustls-ring': 'rustls', 'rustls-aws-lc': 'rustls', 'openraft': 'openraft'}[profile_name]
    features = {
        'tokio': ['io-util','macros','net','rt-multi-thread','signal','sync','time'],
        'rustls-ring': ['logging','ring','std','tls12'],
        'rustls-aws-lc': ['aws_lc_rs','logging','prefer-post-quantum','std','tls12'],
        'openraft': ['serde','tokio-rt'],
    }[profile_name]
    feature_text = ', '.join(json.dumps(v) for v in features)
    path.write_text(f'''[package]\nname="probe"\nversion="0.0.0"\nedition="2021"\n\n[dependencies]\n{package} = {{ version = "={profile['version']}", default-features = false, features = [{feature_text}] }}\n\n[workspace]\n''')


def output_rows(profile_name: str, seed: int, status='PASS'):
    p=mod.PROFILES[profile_name]
    rows=[{'kind':'meta','candidate_id':p['candidate_id'],'version':p['version'],'profile_id':p['profile_id'],'domain':p['domain'],'seed':f'0x{seed:016x}'}]
    rows += [{'kind':'case','case_id':case,'status':status,'assertion_count':1 if status=='PASS' else 0,'detail':'synthetic'} for case in p['cases']]
    return '\n'.join(json.dumps(r,sort_keys=True) for r in rows)+'\n'


class CandidateTests(unittest.TestCase):
    def collect(self, profile_name='tokio', status='PASS', replay_same=True):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); root=Path(td.name)
        make_repo(root, profile_name)
        seed=0x5eed20260828cafe
        out=root/'out.jsonl'; out.write_text(output_rows(profile_name,seed,status))
        replay=root/'replay.jsonl'; replay.write_text(output_rows(profile_name,seed,status if replay_same else 'FAIL'))
        ev=root/'evidence.json'; bind=root/'binding.json'
        args=Namespace(profile=profile_name,adapter_output=str(out),replay_output=str(replay),execution_exit_code=0,seed=hex(seed),toolchain='1.98.0',target='x86_64-unknown-linux-gnu',source_commit='1'*40,source_tree='2'*40,branch='test',clean_tree=True,environment_id='environment-123',executor_kind='local-container',runner_id=None,runner_name='test',root=str(root),output=str(ev),binding_output=str(bind))
        value=mod.collect(args)
        return td,root,value,ev

    def test_collect_pass_is_candidate_bound_and_authority_free(self):
        td,root,value,ev=self.collect()
        self.assertEqual(value['status'],'EXECUTED_PASS')
        self.assertTrue(value['candidate']['bound'])
        self.assertFalse(value['qualification'])
        self.assertEqual(value['authority_effect'],'NONE')
        td.cleanup()

    def test_blocked_case_blocks_evidence(self):
        td,root,value,ev=self.collect(status='BLOCKED')
        self.assertEqual(value['status'],'BLOCKED')
        self.assertEqual(value['summary']['blocked'],6)
        td.cleanup()

    def test_replay_mismatch_rejected(self):
        try:
            with self.assertRaises(mod.Failure):
                self.collect(replay_same=False)
        finally:
            pass

    def test_feature_digest_changes_with_toolchain(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); make_repo(root,'tokio')
            a=mod.manifest_binding(root,mod.PROFILES['tokio'],'1.71.0','x86_64-unknown-linux-gnu')
            b=mod.manifest_binding(root,mod.PROFILES['tokio'],'1.98.0','x86_64-unknown-linux-gnu')
            self.assertNotEqual(a['feature_profile_sha256'],b['feature_profile_sha256'])

    def test_meta_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); make_repo(root,'tokio'); seed=1
            rows=json.loads(output_rows('tokio',seed).splitlines()[0]); rows['candidate_id']='wrong'
            lines=[json.dumps(rows)]+output_rows('tokio',seed).splitlines()[1:]
            path=root/'bad'; path.write_text('\n'.join(lines)+'\n')
            with self.assertRaises(mod.Failure):
                mod.validate_rows(mod.parse_jsonl(path),mod.PROFILES['tokio'],seed)

    def test_secret_marker_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); make_repo(root,'tokio'); seed=1
            rows=[json.loads(x) for x in output_rows('tokio',seed).splitlines()]
            rows[1]['detail']='BEGIN PRIVATE KEY'
            path=root/'bad'; path.write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
            with self.assertRaises(mod.Failure):
                mod.validate_rows(mod.parse_jsonl(path),mod.PROFILES['tokio'],seed)

    def test_compare_full_scope_equivalent(self):
        td,root,candidate,cand_path=self.collect()
        ref=json.loads(cand_path.read_text()); ref['execution_kind']='REFERENCE_MODEL'; ref['candidate']={'bound':False,'candidate_id':None,'version':None,'feature_profile_sha256':None}; ref['profile_id']='HB-H02-BEHAVIOR-RUNTIME-REFERENCE'
        ref_path=root/'ref.json'; ref_path.write_text(json.dumps(ref))
        out=root/'comparison.json'
        args=Namespace(reference=str(ref_path),candidate=str(cand_path),adapter_scope='FULL_REFERENCE_CASE_SET',output=str(out))
        value=mod.compare(args)
        self.assertEqual(value['result'],'INVARIANT_EQUIVALENT_UNREVIEWED')
        self.assertEqual(value['authority_effect'],'NONE')
        td.cleanup()

    def test_compare_partial_scope_blocks_promotion(self):
        td,root,candidate,cand_path=self.collect(profile_name='openraft')
        ref=json.loads(cand_path.read_text()); ref['execution_kind']='REFERENCE_MODEL'; ref['candidate']={'bound':False,'candidate_id':None,'version':None,'feature_profile_sha256':None}; ref['profile_id']='HB-H02-BEHAVIOR-RAFT-REFERENCE'
        ref_path=root/'ref.json'; ref_path.write_text(json.dumps(ref))
        out=root/'comparison.json'
        value=mod.compare(Namespace(reference=str(ref_path),candidate=str(cand_path),adapter_scope='API_SEAM_AND_FAILURE_MODEL_PARTIAL',output=str(out)))
        self.assertEqual(value['result'],'PARTIAL_ADAPTER_SCOPE_BLOCKS_PROMOTION')
        td.cleanup()

    def test_compare_detects_failure(self):
        td,root,candidate,cand_path=self.collect(status='FAIL')
        ref=json.loads(cand_path.read_text());
        for row in ref['cases']: row['status']='PASS'
        ref['execution_kind']='REFERENCE_MODEL'; ref['candidate']={'bound':False,'candidate_id':None,'version':None,'feature_profile_sha256':None}; ref['profile_id']='HB-H02-BEHAVIOR-RUNTIME-REFERENCE'
        ref_path=root/'ref.json'; ref_path.write_text(json.dumps(ref))
        value=mod.compare(Namespace(reference=str(ref_path),candidate=str(cand_path),adapter_scope='FULL_REFERENCE_CASE_SET',output=str(root/'c.json')))
        self.assertEqual(value['result'],'DEVIATION_OR_DEFECT_REVIEW_REQUIRED')
        td.cleanup()

    def test_process_failure_preserved_as_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); make_repo(root,'tokio'); out=root/'out'; out.write_text('')
            ev=root/'e.json'
            args=Namespace(profile='tokio',adapter_output=str(out),replay_output=None,execution_exit_code=101,seed='1',toolchain='1.98.0',target='x86_64-unknown-linux-gnu',source_commit='1'*40,source_tree='2'*40,branch='test',clean_tree=True,environment_id='environment-123',executor_kind='local-container',runner_id=None,runner_name='test',root=str(root),output=str(ev),binding_output=None)
            value=mod.collect(args)
            self.assertEqual(value['status'],'BLOCKED')
            self.assertEqual(value['summary']['blocked'],6)

if __name__=='__main__': unittest.main()
