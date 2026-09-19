import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
import maintainer as m

SHA='a'*40
POLICY={'repositories':{'Oleg5603/gavrik':{'auto_merge':True,'required_checks':['gavrik-tests']}}}
REQUEST={'action':'auto_merge','repository':'Oleg5603/gavrik','pr':1,'head_sha':SHA}

def passing():
 return {'headRefOid':SHA,'state':'OPEN','isDraft':False,'statusCheckRollup':[{'name':'gavrik-tests','status':'COMPLETED','conclusion':'SUCCESS'}]}

class Tests(unittest.TestCase):
 def test_explicit_repo_and_exact_sha_required(self):
  m.validate_request(REQUEST,POLICY)
  for request in ({**REQUEST,'repository':'other/repo'},{**REQUEST,'head_sha':'main'},{**REQUEST,'pr':True},{**REQUEST,'action':'exec'}):
   with self.assertRaises(ValueError):m.validate_request(request,POLICY)
 def test_empty_gate_is_not_permission_to_merge(self):
  with self.assertRaises(ValueError):m.validate_request(REQUEST,{'repositories':{'Oleg5603/gavrik':{'auto_merge':True}}})
 def test_success_same_head(self):m.validate_checks(passing(),REQUEST,['gavrik-tests'])
 def test_new_commit_cancels_permission(self):
  pr=passing();pr['headRefOid']='b'*40
  with self.assertRaises(ValueError):m.validate_checks(pr,REQUEST,['gavrik-tests'])
 def test_missing_pending_skipped_failed_checks_block(self):
  for conclusion in ('SKIPPED','FAILURE','NEUTRAL',None):
   pr=passing();pr['statusCheckRollup'][0]['conclusion']=conclusion
   with self.assertRaises(ValueError):m.validate_checks(pr,REQUEST,['gavrik-tests'])
  with self.assertRaises(ValueError):m.validate_checks(passing(),REQUEST,['other'])
 def test_requested_review_blocks(self):
  pr=passing();pr['reviewDecision']='REVIEW_REQUIRED'
  with self.assertRaises(ValueError):m.validate_checks(pr,REQUEST,['gavrik-tests'])
 def test_native_merge_never_bypasses_admin(self):
  with patch.object(m,'run',side_effect=[json.dumps(passing()),'']) as run:
   m.process_request(REQUEST,POLICY)
  argv=run.call_args.args[0]
  self.assertIn('--match-head-commit',argv);self.assertIn('--auto',argv);self.assertNotIn('--admin',argv)
 def test_auth_failure_does_not_execute_jobs(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td);(home/'policy.json').write_text(json.dumps({**POLICY,'enabled':True}))
   (home/'projects.json').write_text('[]');(home/'queue').mkdir()
   (home/'queue'/'request.json').write_text(json.dumps(REQUEST))
   with patch.object(m,'run',side_effect=RuntimeError('gh: exit 1')),patch.object(m,'process_request') as action:
    report=m.cycle(home)
   action.assert_not_called();self.assertEqual(report['github_auth'],'blocked_auth_or_network')
 def test_disabled_policy_does_not_use_network(self):
  with tempfile.TemporaryDirectory() as td:
   home=Path(td);(home/'policy.json').write_text('{"enabled":false}');(home/'projects.json').write_text('[]')
   with patch.object(m,'run') as action:m.cycle(home)
   action.assert_not_called()
 def test_missing_path_not_marked_synced(self):
  report=m.project_status({'key':'missing','win_path':'Z:/not-existing-gavrik','linux_path':'/nonexistent-gavrik'})
  self.assertEqual(report['state'],'missing_path')
 def test_dirty_tree_is_read_only(self):
  with tempfile.TemporaryDirectory() as td:
   (Path(td)/'.git').mkdir()
   with patch.object(m,'run',side_effect=[SHA,'master',' M edited.py']) as action:
    report=m.project_status({'key':'test','win_path':td,'linux_path':td})
   self.assertEqual(report['state'],'dirty_preserved')
   self.assertEqual(action.call_count,3)
 def test_single_instance(self):
  with tempfile.TemporaryDirectory() as td:
   with m.singleton(Path(td)/'lock'):
    with self.assertRaises(RuntimeError):
     with m.singleton(Path(td)/'lock'):pass

if __name__=='__main__':unittest.main()
