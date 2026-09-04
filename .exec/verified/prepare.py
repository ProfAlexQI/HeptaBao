#!/usr/bin/env python3
"""Reconstruct pinned source-stage inputs without publishing or granting authority."""
from pathlib import Path
import base64, gzip, hashlib, importlib.util, shutil, subprocess as sp, sys
repo=Path(sys.argv[1]).resolve(); out=Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
pins={'150':'f6c8512d368998a9b0f9998ceede9ff6e3ccd682','160':'f3165b3d1c4d4c4e8fd923162efd8535dfa09548','170':'56aea04b4a081c89dd6f5b5ea74da25a2a0d6a8a','180':'cb2ac86a6cf54d0e8a52f50c817dd7e5accca017','190':'9be8cb5da341f65d0332a45036daa1f2e5d5999f'}
for v,sha in pins.items():
 d=out/('input'+v);d.mkdir()
 archive=sp.check_output(['git','archive',sha,'.exec'],cwd=repo)
 sp.run(['tar','-xf','-','-C',str(d)],input=archive,check=True)
patch=out/'input190/.exec'
def run(*args):sp.run([sys.executable,*map(str,args)],check=True)
for version in ('150','160','180'):
 d=out/('v'+version);d.mkdir();fn={'150':'1_5_0','160':'1_6_0','180':'1_8_0'}[version]
 src=out/('input'+version)/'.exec'
 shutil.copy(src/f'materialize_v{fn}.py',d/'materialize.py');shutil.copy(src/f'patch_v{fn}.py',d/'patch.py')
 if version=='180':run(patch/'patch_v1_8_patch_script.py',d/'patch.py')
 run(d/'patch.py',d/'materialize.py')
 if version=='180':run(patch/'patch_v1_8_materializer.py',d/'materialize.py')
d=out/'v170';d.mkdir();src=out/'input170/.exec'
payload=''.join(p.read_text() for p in sorted((src/'v1_7_payload').glob('materializer-*')))
(d/'materialize.py').write_bytes(gzip.decompress(base64.b64decode(payload)))
shutil.copytree(src/'v1_7_assets',d/'assets')
for name in ('patch_v1_7_assets.py','patch_v1_7_assets_v2.py','patch_v1_7_assets_v3.py'):run(src/name,d/'assets')
run(patch/'patch_v1_7_materializer_for_convergence.py',d/'materialize.py')
for path in sorted((d/'assets').glob('*.rs')):sp.run(['rustfmt','+1.98.0','--edition','2024',str(path)],check=True)
raw=b''.join(base64.b64decode(p.read_bytes()) for p in sorted((patch/'v1_9_payload').glob('part-*')))
if hashlib.sha256(raw).hexdigest()!='ab838212f426b8f526e27a1e0e6981a97bfacbf7c9b48772594d4aee66faa838':raise SystemExit('V1.9 source digest mismatch')
(out/'converge.py').write_bytes(raw);run(patch/'patch_v1_9_generator.py',out/'converge.py')
spec=importlib.util.spec_from_file_location('payload_recovery',patch/'repair_external_v2_payload.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
raw=module.recover_source((patch/'augment_external_v2.py.gz.b64').read_bytes())
if hashlib.sha256(raw).hexdigest()!='c97528017a6b4cb22acd32cd191fb88f26f5697015fb75035176ccb5ec98716b':raise SystemExit('external source digest mismatch')
(out/'augment.py').write_bytes(raw)
parts=sorted((repo/'.exec/verified').glob('overlay-part-*'))
expected=['3afc60b3015c03c5a03e35bcb392797b36ebefae','00822d63669989cb0425d6819b509cb0a3e4a97a','1aa003f6af6697a5f8d2e36c24bfe88a475a36d3','b8c83fc5d76239f051423e29670176b3b05a081b','c8bde5a09c3014c22c557f4d97e5576ea2bc16e5','e6083784e41418a1e6905c6695ec08362b9f5fd4','5e107bd3b9a812628b87428d47162db1a2b0d423']
if len(parts)!=len(expected):raise SystemExit('incomplete overlay')
result=[]
for i,(path,wanted) in enumerate(zip(parts,expected)):
 raw=path.read_bytes()
 if i==0:
  for a,b in [(b'gnu5/H04',b'gnu5/G04'),(b'V7/6v0+wwJ0',b'V7/6v0+PXJ0'),(b'79Hr06uzw46',b'79Hr06Oz46')]:raw=raw.replace(a,b)
 if i==5:raw=raw.replace(b'cnbo78lvblug',b'cnbo78vblug')
 observed=hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()
 if observed!=wanted:raise SystemExit(f'overlay transport mismatch part {i}: {observed} != {wanted}')
 result.append(raw)
(out/'overlay.b64').write_bytes(b''.join(result))
print('PASS all pinned controllers and overlay transport identities')
