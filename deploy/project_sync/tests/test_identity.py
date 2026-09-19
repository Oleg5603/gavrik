import ctypes,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
import maintenance_bootstrap as b
class IdentityTests(unittest.TestCase):
 def identity(self,name):
  def get(buffer,size):buffer.value=name;return 1
  return get
 @unittest.skipUnless(sys.platform=='win32','Windows account guard')
 def test_sandbox_identity_cannot_start_bot_helpers(self):
  with patch.object(ctypes.windll.advapi32,'GetUserNameW',side_effect=self.identity('CodexSandboxOnline')):
   with self.assertRaises(RuntimeError):b.ensure_runtime_identity()
 @unittest.skipUnless(sys.platform=='win32','Windows account guard')
 def test_owner_identity_is_accepted(self):
  with patch.object(ctypes.windll.advapi32,'GetUserNameW',side_effect=self.identity('HP')):b.ensure_runtime_identity()
 @unittest.skipUnless(sys.platform=='win32','Windows account guard')
 def test_identity_error_fails_closed(self):
  with patch.object(ctypes.windll.advapi32,'GetUserNameW',return_value=0):
   with self.assertRaises(RuntimeError):b.ensure_runtime_identity()
