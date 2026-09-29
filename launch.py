"""One-command local setup. Uses PyPI; never deploys publicly or deletes data."""
import os
import subprocess
import sys
import venv
from pathlib import Path
if __name__=='__main__':
    root=Path(__file__).resolve().parent
    environment=root/'.venv'
    python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.exists(): venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements.txt')],cwd=root,check=True)
    subprocess.run([str(python),'-m','app.bootstrap'],cwd=root,check=True)
    print('Open http://127.0.0.1:8004 — Ctrl+C to stop. Fictional demo only.',flush=True)
    try:
        subprocess.run([str(python),str(root/'serve.py')],cwd=root,check=True)
    except KeyboardInterrupt: pass
