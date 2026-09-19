"""Project maintenance loop. No credentials, chat state or account data are copied."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def run(argv, cwd=None, timeout=30):
    result=subprocess.run(argv,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        # Do not persist raw stderr: remote URLs or credential-helper errors may include secrets.
        raise RuntimeError(f'{Path(argv[0]).name}: exit {result.returncode}')
    return result.stdout.strip()


def atomic_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


@contextmanager
def singleton(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    handle=path.open('a+b');handle.seek(0);handle.write(b'1');handle.flush();handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        handle.close();raise RuntimeError('maintenance instance already running')
    try:yield
    finally:handle.close()


def project_status(project):
    raw=project.get('win_path') if os.name=='nt' else project.get('linux_path')
    row={'key':project['key'],'path':raw,'state':'missing_path','write_access':'not_tested'}
    if not raw:return row
    path=Path(raw)
    if not path.is_dir():return row
    row['state']='local_only'
    if not (path/'.git').exists():return row
    try:
        prefix=['git','-c',f'safe.directory={path.as_posix()}','-C',str(path)]
        row['head']=run(prefix+['rev-parse','HEAD'])
        row['branch']=run(prefix+['branch','--show-current'])
        row['dirty']=bool(run(prefix+['status','--porcelain','--untracked-files=normal']))
        row['state']='dirty_preserved' if row['dirty'] else 'clean'
    except (OSError,RuntimeError,subprocess.TimeoutExpired) as exc:
        row['state']='git_unavailable';row['error']=type(exc).__name__
    return row


def validate_request(request, policy):
    if request.get('action')!='auto_merge':raise ValueError('unsupported action')
    repository=request.get('repository')
    rule=policy.get('repositories',{}).get(repository,{})
    if rule.get('auto_merge') is not True:raise ValueError('repository not approved')
    checks=rule.get('required_checks',[])
    if not checks or not all(isinstance(v,str) and v for v in checks):raise ValueError('required checks not configured')
    sha=request.get('head_sha','')
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('exact head SHA required')
    number=request.get('pr')
    if type(number) is not int or number<=0:raise ValueError('invalid PR')
    return rule


def validate_checks(pr, request, required):
    if pr.get('headRefOid')!=request['head_sha']:raise ValueError('PR changed; new validation required')
    if pr.get('state')!='OPEN' or pr.get('isDraft'):raise ValueError('PR not ready')
    checks=pr.get('statusCheckRollup') or []
    names={c.get('name') or c.get('context') for c in checks}
    if not set(required)<=names:raise ValueError('required checks missing')
    for check in checks:
        if check.get('__typename')=='StatusContext':
            ok=check.get('state')=='SUCCESS'
        else:
            ok=check.get('status')=='COMPLETED' and check.get('conclusion')=='SUCCESS'
        if not ok:raise ValueError('checks pending, failed or skipped')
    if pr.get('reviewDecision') in ('CHANGES_REQUESTED','REVIEW_REQUIRED'):raise ValueError('review pending')


def process_request(request,policy):
    rule=validate_request(request,policy)
    repo=request['repository'];number=str(request['pr'])
    data=json.loads(run(['gh','pr','view',number,'--repo',repo,'--json',
        'headRefOid,state,isDraft,statusCheckRollup,reviewDecision']))
    validate_checks(data,request,rule['required_checks'])
    # Native auto-merge also enforces remote branch rules. Never use --admin.
    run(['gh','pr','merge',number,'--repo',repo,'--auto','--squash','--match-head-commit',request['head_sha']])
    return 'auto_merge_requested'


def cycle(home):
    home=Path(home)
    policy=json.loads((home/'policy.json').read_text(encoding='utf-8-sig'))
    registry=json.loads((home/'projects.json').read_text(encoding='utf-8-sig'))
    projects=registry['projects'] if isinstance(registry,dict) else registry
    report={'time':datetime.now(timezone.utc).isoformat(),'pid':os.getpid(),
        'enabled':policy.get('enabled') is True,'github_auth':'not_checked','projects':[], 'jobs':[]}
    if not report['enabled']:
        atomic_json(home/'status.json',report);return report
    for project in projects:report['projects'].append(project_status(project))
    try:
        # Authenticate using the actual service account's gh configuration, not Codex MCP.
        run(['gh','api','user','--jq','.login'],timeout=15)
        report['github_auth']='ok'
    except (OSError,RuntimeError,subprocess.TimeoutExpired):
        report['github_auth']='blocked_auth_or_network'
    queue=home/'queue';queue.mkdir(exist_ok=True)
    results=home/'results';results.mkdir(exist_ok=True)
    for path in sorted(queue.glob('*.json'))[:10]:
        content=path.read_bytes();digest=hashlib.sha256(content).hexdigest()
        completed=results/(digest+'.json')
        if completed.exists():continue
        state={'job':path.name,'sha256':digest,'state':'blocked_github_auth'}
        if report['github_auth']=='ok':
            try:
                state['state']=process_request(json.loads(content),policy)
                atomic_json(completed,state)
            except (ValueError,KeyError,TypeError,OSError,RuntimeError,subprocess.TimeoutExpired) as exc:
                state['state']='blocked';state['reason']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
        report['jobs'].append(state)
    report['blocked_capabilities']=['deploy_requires_project_specific_release_manifest',
        'github_workflows_permission_not_confirmed','vps_connection_not_verified']
    atomic_json(home/'status.json',report)
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--home',required=True);parser.add_argument('--once',action='store_true')
    args=parser.parse_args();home=Path(args.home)
    with singleton(home/'maintenance.lock'):
        while True:
            try:
                report=cycle(home)
                if not report['enabled']:return
            except Exception as exc:
                atomic_json(home/'status.json',{'time':datetime.now(timezone.utc).isoformat(),'pid':os.getpid(),'error':type(exc).__name__})
            if args.once:return
            # Re-read stop policy at most 5 seconds after owner changes it.
            for _ in range(60):
                time.sleep(5)
                try:
                    if json.loads((home/'policy.json').read_text(encoding='utf-8-sig')).get('enabled') is not True:return
                except (OSError,ValueError):return


if __name__=='__main__':main()
