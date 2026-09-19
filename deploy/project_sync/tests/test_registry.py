import json,sys,tempfile,unittest
from dataclasses import dataclass
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'registry'))
from registry_overlay import load_shared_projects,RegistryError,default_registry_path
@dataclass
class Project:
 key:str
 name:str
 win_path:str
 description:str
 linux_path:str|None=None
 repo_url:str|None=None
class RegistryPortableTests(unittest.TestCase):
 def fixture(self,rows):
  td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);p=Path(td.name)/'projects.json';p.write_text(json.dumps({'schema_version':1,'projects':rows}));return p
 def row(self):return dict(key='app',name='App',win_path='C:/Projects/app',description='Test',linux_path='/srv/app',repo_url=None)
 def test_load(self):self.assertEqual(load_shared_projects([],Project,__file__,self.fixture([self.row()]))[0].key,'app')
 def test_duplicate(self):
  with self.assertRaises(RegistryError):load_shared_projects([],Project,__file__,self.fixture([self.row(),self.row()]))
 def test_local_change_not_silently_lost(self):
  old=Project(**{**self.row(),'win_path':'C:/Projects/other'})
  with self.assertRaises(RegistryError):load_shared_projects([old],Project,__file__,self.fixture([self.row()]))
 def test_missing_record_not_silently_lost(self):
  with self.assertRaises(RegistryError):load_shared_projects([Project(**self.row())],Project,__file__,self.fixture([]))
 def test_relative_linux_path_rejected(self):
  with self.assertRaises(RegistryError):load_shared_projects([],Project,__file__,self.fixture([{**self.row(),'linux_path':'../other'}]))
