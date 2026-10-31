import gzip
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import Launcher,LauncherError,Store,Task,atomic_json
from worlds import level_metadata


def string(value):
    data=value.encode();return struct.pack('>H',len(data))+data


def level_bytes():
    def named(kind,name,value):return bytes([kind])+string(name)+value
    version=named(8,'Name',string('1.20.1'))+named(3,'Id',struct.pack('>i',3465))+b'\0'
    data=(named(8,'LevelName',string('Benim Dünyam'))+named(4,'LastPlayed',struct.pack('>q',1700000000000))+
          named(4,'RandomSeed',struct.pack('>q',-12345))+named(10,'Version',version)+b'\0')
    return gzip.compress(b'\x0a\0\0'+named(10,'Data',data)+b'\0',mtime=0)


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(self.root/'data');self.launcher=Launcher(self.store)
        self.addCleanup(self.launcher.api.session.close)
        self.p=self.store.create('Asıl profil','1.20.1','fabric');self.p['installed']='fabric-1.20.1'
        self.world=self.store.directory(self.p)/'saves/Dunyam';self.world.mkdir(parents=True)
        (self.world/'level.dat').write_bytes(level_bytes());(self.world/'region.mca').write_bytes(b'original-region')
        self.store.settings['auto_backup']=False;self.store.save()

    def test_reads_real_gzip_nbt_world_name_version_seed_and_date(self):
        meta=level_metadata(self.world/'level.dat')
        self.assertEqual((meta['title'],meta['version'],meta['seed']),('Benim Dünyam','1.20.1',-12345))
        rows=self.launcher.worlds.list(self.p,Task())
        self.assertEqual(rows[0]['name'],'Dunyam');self.assertGreater(rows[0]['size'],0)

    def test_bad_nbt_is_reported_without_modifying_world(self):
        (self.world/'level.dat').write_bytes(b'invalid')
        self.assertEqual(level_metadata(self.world/'level.dat')['version'],'Okunamadı')
        self.assertEqual((self.world/'region.mca').read_bytes(),b'original-region')

    def test_world_backup_restore_preserves_pre_restore_state(self):
        original=(self.world/'level.dat').read_bytes()
        backup=self.launcher.worlds.backup(self.p,'Dunyam',Task())
        (self.world/'region.mca').write_bytes(b'new-progress')
        self.launcher.worlds.restore(self.p,'Dunyam',backup,Task())
        self.assertEqual((self.world/'region.mca').read_bytes(),b'original-region')
        self.assertEqual((self.world/'level.dat').read_bytes(),original)
        backups=self.launcher.worlds.backups(self.p,'Dunyam');self.assertEqual(len(backups),2)
        with zipfile.ZipFile(backups[0]['path']) as archive:
            self.assertEqual(archive.read('Dunyam/region.mca'),b'new-progress')

    def test_world_copy_and_export_do_not_change_source(self):
        self.launcher.worlds.copy(self.p,'Dunyam','Kopya',Task())
        copied=self.world.parent/'Kopya';self.assertEqual((copied/'region.mca').read_bytes(),b'original-region')
        target=self.root/'shared.zip';self.launcher.worlds.export(self.p,'Dunyam',target,Task())
        with zipfile.ZipFile(target) as archive:self.assertIn('Dunyam/level.dat',archive.namelist())
        self.assertTrue((self.world/'level.dat').exists())

    def test_corrupt_backup_cannot_replace_world(self):
        folder=self.store.root/'world-backups'/self.p['id'];folder.mkdir(parents=True)
        path=folder/'bad.zip'
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('kurt-world.json',json.dumps({'format':1,'profile':self.p['id'],'world':'Dunyam','files':{'level.dat':'0'*128}}))
            archive.writestr('Dunyam/level.dat',b'corrupt')
        with self.assertRaises(LauncherError):self.launcher.worlds.restore(self.p,'Dunyam',path,Task())
        self.assertEqual((self.world/'region.mca').read_bytes(),b'original-region')
        self.assertEqual((self.world/'level.dat').read_bytes(),level_bytes())

    def test_world_copy_collision_and_traversal_are_rejected(self):
        for name in ('Dunyam','../escape'):
            with self.assertRaises(LauncherError):self.launcher.worlds.copy(self.p,'Dunyam',name,Task())

    def test_profile_clone_keeps_mods_settings_and_optional_worlds(self):
        mod=self.store.mods(self.p)/'mod.jar';mod.write_bytes(b'mod')
        options=self.store.directory(self.p)/'options.txt';options.write_text('music:0.3\n')
        first=self.launcher.copies.clone(self.p,'Dünyasız',False,Task())
        self.assertEqual((self.store.directory(first)/'mods/mod.jar').read_bytes(),b'mod')
        self.assertFalse((self.store.directory(first)/'saves').exists())
        self.assertEqual(first['installed'],self.p['installed'])
        second=self.launcher.copies.clone(self.p,'Dünyalı',True,Task())
        self.assertEqual((self.store.directory(second)/'saves/Dunyam/region.mca').read_bytes(),b'original-region')
        self.assertEqual(options.read_text(),'music:0.3\n')

    def test_clone_metadata_failure_does_not_publish_incomplete_profile(self):
        before=list(self.store.profiles)
        with patch('profile_data.atomic_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.launcher.copies.clone(self.p,'Broken',True,Task())
        self.assertEqual(self.store.profiles,before)
        self.assertEqual([p.name for p in (self.store.root/'instances').iterdir()],[self.p['id']])

    def test_world_free_profile_copy_excludes_case_variant_saves_folder(self):
        self.world.parent.rename(self.world.parent.with_name('SAVES'))
        clone=self.launcher.copies.clone(self.p,'No worlds',False,Task())
        self.assertFalse(any(p.name.casefold()=='saves' for p in self.store.directory(clone).iterdir()))

    def test_running_game_blocks_copy_backup_and_restore(self):
        self.launcher.process=Mock();self.launcher.process.poll.return_value=None
        with self.assertRaises(LauncherError):self.launcher.worlds.backup(self.p,'Dunyam',Task())
        with self.assertRaises(LauncherError):self.launcher.copies.clone(self.p,'copy',True,Task())

    @unittest.skipUnless(os.name=='nt','Windows file-lock scenario')
    def test_world_session_lock_blocks_copy_without_touching_source(self):
        import msvcrt
        path=self.world/'session.lock';path.write_bytes(b'abc')
        with path.open('r+b') as stream:
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            with self.assertRaises(LauncherError):self.launcher.copies.clone(self.p,'copy',True,Task())
        self.assertEqual(len(self.store.profiles),1)

    def test_storage_cleanup_cannot_remove_worlds_or_backups(self):
        cache=self.store.root/'cache/downloads/item.part';cache.parent.mkdir(parents=True);cache.write_bytes(b'cache')
        report=self.launcher.storage.scan(Task());self.assertGreater(report['groups']['Dünyalar'],0)
        self.launcher.storage.clean(report['cleanup'],Task())
        self.assertFalse(cache.exists());self.assertTrue((self.world/'level.dat').exists())
        stat=(self.world/'level.dat').stat()
        unsafe={'path':f'instances/{self.p["id"]}/saves/Dunyam/level.dat','size':stat.st_size,'mtime_ns':stat.st_mtime_ns}
        with self.assertRaises(LauncherError):self.launcher.storage.clean([unsafe],Task())
        self.assertTrue((self.world/'level.dat').exists())

    def test_storage_keeps_cache_files_changed_since_scan(self):
        path=self.store.root/'cache/mod-icons/icon.img';path.parent.mkdir(parents=True);path.write_bytes(b'old')
        report=self.launcher.storage.scan(Task());path.write_bytes(b'new and larger')
        self.launcher.storage.clean(report['cleanup'],Task());self.assertTrue(path.exists())

    def test_mod_diagnostics_uses_world_free_copy_and_preserves_dependencies(self):
        def mod(name,requires=()):
            path=self.store.mods(self.p)/(name+'.jar')
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr('fabric.mod.json',json.dumps({'id':name,'version':'1','depends':{d:'*' for d in requires}}))
            return {'name':name,'file':path.name,'version_id':name+'1','requires':[{'project_id':d} for d in requires]}
        records={'a':mod('a',('dep',)),'b':mod('b'),'dep':mod('dep')}
        atomic_json(self.store.directory(self.p)/'mods.lock.json',records)
        session=self.launcher.diagnostics.start(self.p,Task());_,test=self.launcher.diagnostics.get(session['id'])
        self.assertFalse((self.store.directory(test)/'saves').exists())
        self.launcher.mods.validate_enabled(test)
        session=self.launcher.diagnostics.result(session['id'],False,Task())
        self.launcher.mods.validate_enabled(test)
        session=self.launcher.diagnostics.result(session['id'],True,Task())
        self.assertTrue(session['complete']);self.assertEqual(session['candidates'],['a.jar'])
        self.assertTrue(all((self.store.mods(self.p)/(name+'.jar')).is_file() for name in records))
        self.assertEqual((self.world/'region.mca').read_bytes(),b'original-region')


if __name__=='__main__':unittest.main()
