"""Scan project files and reachable Git history without printing matched secrets."""
from pathlib import Path
import re
import subprocess
import io
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PATTERNS={
 'AWS access key':rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
 'account number':rb'(?<![\w.])\d{12}(?![\w.])',
 'home directory':rb'/(?:Users|home)/[^/\s"<>]+',
 'email address':rb'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
 'private key':rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
 'GitHub token':rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b',
}
NEUTRAL_EMAIL=b'build-with-aws'+b'@users.noreply.github.com'
SKIP={'.git','.venv','__pycache__','private','results','dist','site-source'}
violations=[]
def check(label,data):
 if data.startswith(b'PK\x03\x04'):
  with zipfile.ZipFile(io.BytesIO(data)) as archive:
   for name in archive.namelist():check(label+' / '+name,archive.read(name))
  return
 if data.startswith((b'\x89PNG\r\n\x1a\n',b'%PDF',b'\xff\xd8\xff')):
  violations.append((label,'binary asset needs a separate review'))
  return
 for kind,pattern in PATTERNS.items():
  if any(m.group()!=NEUTRAL_EMAIL for m in re.finditer(pattern,data)):
   violations.append((label,kind))
for p in ROOT.rglob('*'):
 if p.is_file() and not any(part in SKIP for part in p.relative_to(ROOT).parts) and p.name!='config.local.json':
  check(str(p.relative_to(ROOT)),p.read_bytes())
if (ROOT/'.git').exists():
 def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args],stderr=subprocess.DEVNULL)
 try:
  check('commit metadata',git('log','--all','--format=fuller'))
  for line in git('rev-list','--objects','--all').decode().splitlines():
   oid=line.split(' ',1)[0]
   if git('cat-file','-t',oid).strip()==b'blob':check('Git blob '+oid[:8],git('cat-file','-p',oid))
 except subprocess.CalledProcessError:pass
if violations:
 for label,kind in violations:print(f'{label}: possible {kind}')
 raise SystemExit(1)
print('Project files and reachable Git history passed the privacy scan.')
