"""Supervise one API and worker. Child failure stops service for host restart."""
import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

def supervise(api_command,worker_command,cwd):
    children=[]
    stopping=False
    def stop(signum,frame):
        nonlocal stopping
        stopping=True
    previous={s:signal.signal(s,stop) for s in (signal.SIGINT,signal.SIGTERM)}
    try:
        for command in (worker_command,api_command):
            children.append(subprocess.Popen(command,cwd=cwd))
        while not stopping:
            for child in children:
                if child.poll() is not None:
                    print('A child process exited; stopping the service for restart.',flush=True)
                    return child.returncode or 1
            time.sleep(0.2)
        return 0
    finally:
        for child in children:
            if child.poll() is None: child.terminate()
        for child in children:
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: child.kill();child.wait()
        for sig,handler in previous.items():signal.signal(sig,handler)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8004')))
    args=parser.parse_args();root=Path(__file__).resolve().parent
    api=[sys.executable,'-m','uvicorn','app.main:create_app','--factory','--host',args.host,'--port',str(args.port),'--limit-concurrency','32','--timeout-keep-alive','5']
    worker=[sys.executable,str(root/'worker.py')]
    sys.exit(supervise(api,worker,root))
