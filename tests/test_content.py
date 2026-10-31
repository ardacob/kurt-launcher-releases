import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import Api,Launcher,LauncherError,Store,Task,atomic_json
from content import ModpackCatalog,ResourcePacks,validate_resourcepack
from shaders import ShaderManager
from test_downloads import Response
from test_shaders import shader_bytes,version


def resource_bytes():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        archive.writestr('pack.mcmeta',json.dumps({'pack':{'pack_format':15,'description':'Test pack'}}))
        archive.writestr('assets/minecraft/lang/en_us.json','{}')
    return stream.getvalue()


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'data');self.p=self.store.create('Test','1.20.1','vanilla')
        self.api=Api();self.addCleanup(self.api.session.close)
        self.api.download_cache=self.store.root/'cache/downloads'
        self.manager=ResourcePacks(self.store,self.api)

    def test_resource_catalog_filters_game_without_mod_loader(self):
        self.api.get=Mock(return_value={'hits':[],'total_hits':0})
        self.manager.search(self.p,'grass',40,'updated')
        facets=json.loads(self.api.get.call_args.kwargs['facets'])
        self.assertEqual(facets,[['project_type:resourcepack'],['versions:1.20.1']])
        self.assertEqual(self.api.get.call_args.kwargs['offset'],40)

    def test_resource_pack_import_order_preserves_other_options_and_builtin_packs(self):
        paths=[]
        for name in ('one.zip','two.zip'):
            path=Path(self.temp.name)/name;path.write_bytes(resource_bytes());paths.append(path)
        self.manager.import_local(self.p,paths,Task())
        options=self.store.directory(self.p)/'options.txt'
        options.write_text('music:0.4\nresourcePacks:["vanilla","programmer_art"]\nfov:0.7\n')
        self.manager.apply_order(self.p,['two.zip','one.zip'],Task())
        self.assertEqual(self.manager.order(self.p),['two.zip','one.zip'])
        text=options.read_text();self.assertIn('music:0.4',text);self.assertIn('programmer_art',text)
        self.assertFalse(list(self.store.mods(self.p).iterdir()))

    def test_invalid_pack_or_duplicate_order_does_not_change_options(self):
        bad=Path(self.temp.name)/'bad.zip';bad.write_bytes(shader_bytes())
        with self.assertRaises(LauncherError):self.manager.import_local(self.p,[bad],Task())
        with self.assertRaises(LauncherError):self.manager.apply_order(self.p,['bad.zip','bad.zip'],Task())
        self.assertFalse((self.store.directory(self.p)/'options.txt').exists())

    def test_resource_zip_with_traversal_is_rejected(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('pack.mcmeta','{"pack":{"pack_format":15}}')
            archive.writestr('../escape','bad')
        path=Path(self.temp.name)/'evil.zip';path.write_bytes(stream.getvalue())
        with self.assertRaises(LauncherError):validate_resourcepack(path)

    def test_shader_favorites_persist_without_stale_local_paths(self):
        manager=ShaderManager(self.store,self.api)
        hit={'project_id':'pack','title':'Good shader','description':'Shader','downloads':42,'icon_path':'private/path'}
        self.assertTrue(manager.favorite(hit))
        another=ShaderManager(self.store,self.api)
        self.assertEqual(another.favorites()['pack']['title'],'Good shader')
        self.assertNotIn('icon_path',another.favorites()['pack'])
        self.assertFalse(another.favorite(hit));self.assertEqual(manager.favorites(),{})

    def shader_fixture(self):
        manager=ShaderManager(self.store,self.api);v=version();project={'id':'pack','title':'Shader','project_type':'shader'}
        versions={'v1':v}
        def get(url,**params):
            if url.endswith('/project/pack/version'):return [copy.deepcopy(value) for value in versions.values()]
            if '/version/' in url:return copy.deepcopy(versions[url.rsplit('/',1)[-1]])
            return project
        self.api.get=Mock(side_effect=get);self.api.session.get=Mock(return_value=Response([shader_bytes()]))
        manager.install('pack',self.p,Task(),'v1')
        newer=version('v2');newer.update(version_number='3.0',date_published='2026-10-31',changelog='Improved water')
        newer['files'][0]['filename']='shader-new.zip';versions['v2']=newer
        return manager,versions

    def test_shader_updates_show_versions_and_commit_verified_replacement(self):
        manager,_=self.shader_fixture();rows=manager.updates(self.p,Task())
        self.assertEqual(rows[0]['new']['changelog'],'Improved water')
        manager.update('pack',self.p,'v2',Task())
        self.assertEqual(manager.records(self.p)['pack']['version_id'],'v2')
        self.assertFalse((manager.folder(self.p)/'shader.zip').exists())
        self.assertEqual((manager.folder(self.p)/'shader-new.zip').read_bytes(),shader_bytes())

    def test_shader_update_metadata_failure_restores_old_zip_and_record(self):
        manager,_=self.shader_fixture()
        with patch('shaders.atomic_json',side_effect=OSError('full')):
            with self.assertRaises(OSError):manager.update('pack',self.p,'v2',Task())
        self.assertEqual(manager.records(self.p)['pack']['version_id'],'v1')
        self.assertTrue((manager.folder(self.p)/'shader.zip').is_file())
        self.assertFalse((manager.folder(self.p)/'shader-new.zip').exists())

    def test_changed_local_shader_is_not_overwritten_by_update(self):
        manager,_=self.shader_fixture();path=manager.folder(self.p)/'shader.zip';path.write_bytes(b'user edited')
        with self.assertRaises(LauncherError):manager.update('pack',self.p,'v2',Task())
        self.assertEqual(path.read_bytes(),b'user edited')

    def test_modpack_download_is_inspected_before_any_profile_is_created(self):
        launcher=Launcher(self.store);self.addCleanup(launcher.api.session.close)
        catalog=ModpackCatalog(launcher);raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as archive:
            archive.writestr('modrinth.index.json',json.dumps({'formatVersion':1,'game':'minecraft','name':'Ready pack',
                'dependencies':{'minecraft':'1.20.1','fabric-loader':'0.16.0'},'files':[]}))
        payload=raw.getvalue()
        file={'filename':'test.mrpack','url':'https://cdn.modrinth.com/test.mrpack','size':len(payload),
              'primary':True,'hashes':{'sha512':hashlib.sha512(payload).hexdigest()}}
        def get(url,**params):
            return {'id':'pack','project_type':'modpack'} if '/project/' in url else {'id':'v1','project_id':'pack','files':[file]}
        catalog.api.get=Mock(side_effect=get);catalog.api.session.get=Mock(return_value=Response([payload]))
        before=len(self.store.profiles);result=catalog.download('pack','v1',Task())
        self.assertEqual(result['info']['name'],'Ready pack');self.assertEqual(len(self.store.profiles),before)
        self.assertTrue(Path(result['source']).is_file())

    def test_modpack_versions_filter_actual_file_and_loader(self):
        launcher=Launcher(self.store);self.addCleanup(launcher.api.session.close);catalog=ModpackCatalog(launcher)
        catalog.api.get=Mock(return_value=[{'id':'good','game_versions':['1.20.1'],'loaders':['fabric'],'files':[{'filename':'a.mrpack'}]},
            {'id':'wrong','game_versions':['1.21'],'loaders':['forge'],'files':[{'filename':'b.mrpack'}]}])
        self.assertEqual([v['id'] for v in catalog.versions('pack','1.20.1','fabric')],['good'])


if __name__=='__main__':unittest.main()
