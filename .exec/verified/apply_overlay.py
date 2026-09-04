#!/usr/bin/env python3
from pathlib import Path, PurePosixPath
import base64, hashlib, json, os, re, subprocess, sys, tempfile, zlib
root=Path(sys.argv[1]).resolve(); payload=Path(sys.argv[2]); expected=sys.argv[3]
raw=zlib.decompress(base64.b64decode(payload.read_bytes(),validate=True))
if hashlib.sha256(raw).hexdigest()!=expected:raise SystemExit('overlay digest mismatch')
v=json.loads(raw)
if subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()!=v['base']:raise SystemExit('overlay base mismatch')
def path(name):
 p=PurePosixPath(name)
 if p.is_absolute() or any(c in ('','.','..','.git')for c in name.split('/')) or '\\'in name:raise SystemExit('unsafe overlay path')
 q=root
 for c in p.parts:
  q=q/c
  if q.is_symlink():raise SystemExit('symlink overlay path')
 return q
pattern=re.compile(r'<!-- BEGIN GENERATED V1.4.7 (?:PUBLIC API TRUTH|MODULE FACTS); DO NOT EDIT -->.*?<!-- END GENERATED V1.4.7 (?:PUBLIC API TRUTH|MODULE FACTS) -->',re.S)
for name in v['strip_generated']:
 p=path(name);p.write_text(pattern.sub('',p.read_text()))
for entry in v['digests']:
 p=path(entry['path'])
 digest=hashlib.sha256(p.read_bytes()).hexdigest()if p.exists()else None
 if digest!=entry['before']:raise SystemExit('overlay input drift: '+entry['path'])
with tempfile.NamedTemporaryFile(suffix='.patch')as temporary:
 temporary.write(v['patch'].encode());temporary.flush()
 subprocess.run(['git','apply','--check',temporary.name],cwd=root,check=True)
 subprocess.run(['git','apply',temporary.name],cwd=root,check=True)
for entry in v['digests']:
 p=path(entry['path'])
 if hashlib.sha256(p.read_bytes()).hexdigest()!=entry['after']:raise SystemExit('overlay output drift: '+entry['path'])
 os.chmod(p,entry['mode'])
for name in v['strip_generated']:
 p=path(name);s=p.read_text();heading='## Machine-verified source truth\n\n'
 if s.count(heading)!=1:raise SystemExit('facts heading ambiguity')
 p.write_text(s.replace(heading,heading+'<!-- BEGIN GENERATED V1.4.7 MODULE FACTS; DO NOT EDIT -->\n<!-- END GENERATED V1.4.7 MODULE FACTS -->',1))
for name in v['delete']:
 if not name.startswith('.github/workflows/exec-v1.9.0-pr-relay'):raise SystemExit('unexpected removal')
 path(name).unlink()
print('PASS exact overlay before/after digest binding')
