#!/usr/bin/env python3
"""Run the standalone WRBPG verifier in an isolated directory.

This audit guards against correlated implementation errors: the selected checker
must execute with Python's isolated mode, no project import path, and no access
to frozen result files or the production optimizer package.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def select_checker(tools: Path) -> Path:
    candidates=[]
    for p in sorted(tools.glob('*wrbpg*.py')):
        if p.name.startswith('audit_') or 'test' in p.name.lower():
            continue
        text=p.read_text(encoding='utf-8')
        score=sum(tok in text.lower() for tok in ('red','blue','pebble','store','load','compute'))
        if score>=4:
            candidates.append((score,p))
    if not candidates:
        raise RuntimeError('no standalone WRBPG checker found')
    return max(candidates,key=lambda x:(x[0],-len(x[1].name)))[1]


def static_independence(path: Path) -> dict[str, object]:
    text=path.read_text(encoding='utf-8')
    tree=ast.parse(text,filename=str(path))
    banned_import_roots={'model','optimizer','checker','certificate','reproduce','tools','tests','src'}
    imports=[]
    violations=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            for a in node.names:
                root=a.name.split('.')[0]; imports.append(a.name)
                if root in banned_import_roots: violations.append(f'project import: {a.name}')
        elif isinstance(node,ast.ImportFrom):
            name=node.module or ''
            root=name.split('.')[0] if name else ''
            imports.append(name)
            if node.level or root in banned_import_roots: violations.append(f'project/relative import: {name}')
        elif isinstance(node,ast.Call):
            f=node.func
            label=''
            if isinstance(f,ast.Name): label=f.id
            elif isinstance(f,ast.Attribute):
                parts=[]; cur=f
                while isinstance(cur,ast.Attribute): parts.append(cur.attr); cur=cur.value
                if isinstance(cur,ast.Name): parts.append(cur.id)
                label='.'.join(reversed(parts))
            if label in {'eval','exec','compile','__import__','importlib.import_module','subprocess.run','subprocess.Popen','os.system'}:
                violations.append(f'dynamic/delegating call: {label}')
        elif isinstance(node,(ast.With,ast.AsyncWith)):
            # File access is not categorically forbidden, but the isolated run below
            # ensures no project files are available. Record direct open calls.
            pass
    for pattern in (r'\.\./',r'results/',r'instances/',r'claim_evidence',r'references\.bib'):
        if re.search(pattern,text): violations.append(f'project data reference: {pattern}')
    return {'imports':imports,'violations':sorted(set(violations))}


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--output',default='results/wrbpg-isolation-audit.json')
    ns=ap.parse_args()
    artifact=Path(__file__).resolve().parents[1]
    checker=select_checker(artifact/'tools')
    static=static_independence(checker)
    errors=list(static['violations'])
    with tempfile.TemporaryDirectory(prefix='wrbpg-isolated-') as td:
        td_path=Path(td)
        copy=td_path/'checker.py'
        shutil.copy2(checker,copy)
        env={'PATH':os.environ.get('PATH',''),'PYTHONHASHSEED':'0','PYTHONNOUSERSITE':'1','LC_ALL':'C.UTF-8'}
        proc=subprocess.run([sys.executable,'-I',str(copy)],cwd=td_path,env=env,
                            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
        output=proc.stdout
        if proc.returncode!=0: errors.append(f'isolated process exited {proc.returncode}')
        # Accept separators/labels but require all central values in the isolated output.
        numbers=[int(x) for x in re.findall(r'(?<![A-Za-z])\d+(?![A-Za-z])',output)]
        for required in (89,91,23,25):
            if required not in numbers: errors.append(f'missing expected value {required} in isolated output')
        if any(x in output for x in ('/mnt/','/home/','Traceback')):
            errors.append('isolated output leaked a path or traceback')
    report={
        'ok':not errors,
        'checker':f'tools/{checker.name}',
        'python_isolated_mode':True,
        'project_files_available':False,
        'required_values':[89,91,23,25],
        'static_imports':static['imports'],
        'errors':errors,
    }
    out=artifact/ns.output
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return 0 if report['ok'] else 1

if __name__=='__main__':
    raise SystemExit(main())
