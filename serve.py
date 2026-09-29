"""Start the API and event worker together; manages only its own child process."""
import argparse
import subprocess
import sys
from pathlib import Path

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8004)
    args=parser.parse_args();root=Path(__file__).resolve().parent
    worker=subprocess.Popen([sys.executable,str(root/'worker.py')],cwd=root)
    try:
        subprocess.run([sys.executable,'-m','uvicorn','app.main:create_app','--factory','--host',args.host,'--port',str(args.port)],cwd=root,check=True)
    except KeyboardInterrupt:
        pass
    finally:
        worker.terminate()
        try:worker.wait(timeout=5)
        except subprocess.TimeoutExpired:worker.kill();worker.wait()
