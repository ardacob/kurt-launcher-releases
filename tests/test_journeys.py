import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import Store,Launcher,Task,LauncherError,atomic_json,Cancelled
from journeys import server_endpoint,server_status,packet,varint,Sessions,gpu_tier
from deep_links import invite_link,link_code,argument_link
from invites import encode_invite
from snapshots import digest
from test_worlds_management import level_bytes


class JourneysTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(self.root/'data');self.launcher=Launcher(self.store)
        self.addCleanup(self.launcher.api.session.close)
        self.p=self.store.create('Oyunum','1.20.1','fabric');self.store.settings.update(login_mode='offline',offline_username='Player',auto_backup=False)
        self.world=self.store.directory(self.p)/'saves/World';self.world.mkdir(parents=True)
        (self.world/'level.dat').write_bytes(level_bytes());(self.world/'region.mca').write_bytes(b'unchanged-region')

    def test_world_history_reuses_unchanged_files_and_restores_deleted_files(self):
        history=self.launcher.world_history
        first=history.create(self.p,'World',Task());second=history.create(self.p,'World',Task())
        self.assertGreater(first['new_bytes'],0);self.assertEqual(second['new_bytes'],0)
        (self.world/'region.mca').write_bytes(b'changed-region')
        third=history.create(self.p,'World',Task());self.assertEqual(third['new_bytes'],len(b'changed-region'))
        (self.world/'extra.txt').write_text('new file');(self.world/'region.mca').unlink()
        point=next(p for p in history.points(self.p,'World') if p['created']==first['created'])
        history.restore(self.p,'World',point['path'],Task())
        self.assertEqual((self.world/'region.mca').read_bytes(),b'unchanged-region');self.assertFalse((self.world/'extra.txt').exists())
        self.assertTrue(self.launcher.worlds.backups(self.p,'World'))

    def test_corrupt_history_object_does_not_replace_world(self):
        history=self.launcher.world_history;meta=history.create(self.p,'World',Task())
        history.object(meta['files']['level.dat']).write_bytes(b'corrupt')
        before=digest(self.world/'level.dat');point=history.points(self.p,'World')[0]
        with self.assertRaises(LauncherError):history.restore(self.p,'World',point['path'],Task())
        self.assertEqual(digest(self.world/'level.dat'),before)

    def test_history_manifest_traversal_is_rejected(self):
        history=self.launcher.world_history;history.create(self.p,'World',Task());point=history.points(self.p,'World')[0]
        meta=json.loads(Path(point['path']).read_text());meta['files']['../escape']=meta['files']['level.dat'];atomic_json(Path(point['path']),meta)
        with self.assertRaises(LauncherError):history.restore(self.p,'World',point['path'],Task())
        self.assertFalse((self.world.parent/'escape').exists())

    def test_canceled_history_does_not_publish_restore_point(self):
        task=Task();task.cancel.set()
        with self.assertRaises(Cancelled):self.launcher.world_history.create(self.p,'World',task)
        self.assertEqual(self.launcher.world_history.points(self.p,'World'),[])

    def test_running_game_blocks_history_and_import(self):
        self.launcher.process=Mock();self.launcher.process.poll.return_value=None
        with self.assertRaises(LauncherError):self.launcher.world_history.create(self.p,'World',Task())
        with self.assertRaises(LauncherError):self.launcher.external_imports.install({},'x','1.20.1','vanilla',True,Task())

    def external(self):
        folder=self.root/'Prism/instances/Test/.minecraft';folder.mkdir(parents=True)
        (folder/'saves/MyWorld').mkdir(parents=True);(folder/'saves/MyWorld/level.dat').write_bytes(level_bytes())
        (folder/'mods').mkdir();(folder/'mods/test.jar').write_bytes(b'jar')
        (folder/'options.txt').write_text('music:0.3\n');(folder/'accounts.json').write_text('secret')
        (folder/'config').mkdir();(folder/'config/mod.json').write_text('{"enabled":true}')
        atomic_json(folder.parent/'mmc-pack.json',{'components':[{'uid':'net.minecraft','version':'1.20.1'},{'uid':'net.fabricmc.fabric-loader','version':'0.16.14'}]})
        return folder

    def test_prism_import_detects_loader_keeps_source_and_excludes_accounts(self):
        source=self.external();before={str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file()}
        rows=self.launcher.external_imports.discover(self.root/'Prism',Task());self.assertEqual(len(rows),1)
        info=rows[0];self.assertEqual((info['version'],info['loader'],info['loader_version']),('1.20.1','fabric','0.16.14'))
        imported=self.launcher.external_imports.install(info,'Imported','1.20.1','fabric',True,Task());target=self.store.directory(imported)
        self.assertEqual((target/'mods/test.jar').read_bytes(),b'jar');self.assertTrue((target/'saves/MyWorld/level.dat').is_file())
        self.assertFalse((target/'accounts.json').exists());self.assertIsNone(imported['installed'])
        self.assertEqual(before,{str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file()})

    def test_import_without_worlds_and_cancel_preserve_profile_list(self):
        source=self.external();info=self.launcher.external_imports.discover(source,Task())[0]
        imported=self.launcher.external_imports.install(info,'Without worlds','1.20.1','fabric',False,Task())
        self.assertFalse((self.store.directory(imported)/'saves').exists());count=len(self.store.profiles)
        task=Task();task.cancel.set()
        with self.assertRaises(Cancelled):self.launcher.external_imports.install(info,'Canceled','1.20.1','fabric',True,task)
        self.assertEqual(len(self.store.profiles),count)

    def test_official_import_resolves_fabric_inherits_from(self):
        game=self.root/'.minecraft';metadata=game/'versions/fabric-loader-test';metadata.mkdir(parents=True)
        atomic_json(game/'launcher_profiles.json',{'profiles':{'x':{'lastVersionId':'fabric-loader-test'}}})
        atomic_json(metadata/'fabric-loader-test.json',{'inheritsFrom':'1.20.1','libraries':[{'name':'net.fabricmc:fabric-loader:0.16.14'}]})
        rows=self.launcher.external_imports.discover(game,Task())
        self.assertEqual((rows[0]['version'],rows[0]['loader']),('1.20.1','fabric'))

    def test_invite_link_round_trip_and_hostile_links_rejected(self):
        code=encode_invite('demo.ply.gg:12345',{'version':'1.20.1','loader':'vanilla','loader_version':None})
        link=invite_link(code);self.assertEqual(link_code(link),code);self.assertEqual(argument_link(['app',link]),link)
        for bad in ('https://join/'+code,'kurt://evil/'+code,link+'?x=1',link+'#x','kurt://join/%20'+code,link+' '):
            with self.subTest(bad=bad),self.assertRaises(LauncherError):link_code(bad)
        with self.assertRaises(LauncherError):argument_link(['app',link,link])

    def test_endpoint_supports_dns_ipv4_ipv6_and_rejects_commands(self):
        self.assertEqual(server_endpoint('example.org'),('example.org',25565))
        self.assertEqual(server_endpoint('[::1]:12345'),('::1',12345))
        for bad in ('http://example.org','x:0','x:65536','x;whoami','example.org --token','x\nnext'):
            with self.subTest(bad=bad),self.assertRaises(LauncherError):server_endpoint(bad)

    def test_real_java_status_and_ping_with_fragmented_network_packets(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);self.addCleanup(listener.close)
        errors=[]
        def serve():
            try:
                conn,_=listener.accept()
                with conn:
                    conn.settimeout(3);request=conn.recv(4096)
                    self.assertIn(b'127.0.0.1',request)
                    raw=json.dumps({'version':{'name':'1.20.1','protocol':763},'players':{'online':3,'max':20},'description':{'text':'Hello','extra':[{'text':' world'}]}}).encode()
                    response=packet(b'\0'+varint(len(raw))+raw)
                    for b in response:conn.sendall(bytes([b]))
                    ping=conn.recv(10)
                    while len(ping)<10:ping+=conn.recv(10-len(ping))
                    conn.sendall(ping)
            except Exception as exc:errors.append(exc)
        worker=threading.Thread(target=serve,daemon=True);worker.start()
        result=server_status('127.0.0.1:'+str(listener.getsockname()[1]));worker.join(4)
        self.assertEqual(errors,[]);self.assertEqual((result['version'],result['online'],result['description']),('1.20.1',3,'Hello world'));self.assertIsInstance(result['ping'],int)

    def test_oversized_status_packet_rejected_before_allocation(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);self.addCleanup(listener.close)
        def serve():
            conn,_=listener.accept()
            with conn:conn.recv(4096);conn.sendall(varint(16*1024**2))
        worker=threading.Thread(target=serve,daemon=True);worker.start()
        with self.assertRaises(ValueError):server_status('127.0.0.1:'+str(listener.getsockname()[1]))
        worker.join(3)

    def test_favorites_persist_and_bind_to_selected_profile(self):
        row=self.launcher.favorites.add('Local server','localhost:25565',self.p['id'])
        self.assertEqual(self.launcher.favorites.list()[0]['profile'],self.p['id'])
        self.launcher.favorites.remove(row['id']);self.assertEqual(self.launcher.favorites.list(),[])

    def test_session_duration_uses_monotonic_time_and_survives_restart(self):
        stats=self.launcher.sessions;clock=[100];stats.clock=lambda:clock[0];stats.start(self.p)
        clock[0]=165;process=Mock();process.poll.return_value=None;stats.update(process)
        self.assertEqual(stats.summary()[0]['seconds'],65)
        process.poll.return_value=0;process.returncode=0;clock[0]=170;stats.update(process)
        loaded=Sessions(self.store);self.assertEqual(loaded.summary()[0]['seconds'],70);self.assertEqual(loaded.rows[-1]['state'],'completed')
        loaded.start(self.p);self.assertEqual(Sessions(self.store).rows[-1]['state'],'interrupted')

    def test_gpu_presets_are_conservative_and_unknown_hardware_is_light(self):
        self.assertEqual(gpu_tier([],16000),'low');self.assertEqual(gpu_tier(['RTX 5070'],16000),'high')
        self.assertEqual(gpu_tier(['GeForce GTX 1660'],16000),'medium');self.assertEqual(gpu_tier(['RTX 5070'],4000),'low')

    def prepare_game(self,quick=True):
        self.p['installed']='fabric-test'
        folder=self.store.minecraft/'versions/1.20.1';folder.mkdir(parents=True)
        (folder/'1.20.1.jar').write_bytes(b'jar')
        atomic_json(folder/'1.20.1.json',{'arguments':{'game':['--quickPlaySingleplayer'] if quick else []}})
        installed=self.store.minecraft/'versions/fabric-test';installed.mkdir()
        atomic_json(installed/'fabric-test.json',{})

    def test_quick_play_uses_world_argument_and_creates_safety_point(self):
        self.prepare_game();process=Mock();process.poll.return_value=None
        with patch.object(self.launcher,'java',return_value='java'),patch('core.mc.command.get_minecraft_command',return_value=['java']) as command,patch('core.subprocess.Popen',return_value=process):
            self.launcher.play(self.p,Task(),world_name='World')
            options=command.call_args[0][2];self.assertEqual(options['quickPlaySingleplayer'],'World')
            self.assertEqual(len(self.launcher.world_history.points(self.p,'World')),1)

    def test_unsupported_or_mismatched_world_cannot_start(self):
        self.prepare_game(quick=False)
        with patch.object(self.launcher,'java',return_value='java'),patch('core.subprocess.Popen') as process:
            with self.assertRaises(LauncherError):self.launcher.play(self.p,Task(),world_name='World')
            process.assert_not_called()
        self.p['version']='1.21.1'
        with self.assertRaises(LauncherError):self.launcher.play(self.p,Task(),world_name='World')


if __name__=='__main__':unittest.main()
