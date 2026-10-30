import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core import Api, Cancelled, Launcher, LauncherError, Store, Task
from shaders import ShaderManager, validate_shaderpack


def shader_bytes(entries=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, value in (entries or {'shaders/composite.fsh': '#version 150\nvoid main() {}'}).items():
            archive.writestr(name, value)
    return stream.getvalue()


def version(vid='v1', game='1.20.1', loaders=None):
    body = shader_bytes()
    return {'id': vid, 'project_id': 'pack', 'version_number': '2.0', 'version_type': 'release',
            'game_versions': [game], 'loaders': loaders or ['iris', 'optifine'], 'date_published': '2026-10-30',
            'files': [{'filename': 'shader.zip', 'primary': True, 'size': len(body),
                       'url': 'https://cdn.modrinth.com/test/shader.zip',
                       'hashes': {'sha512': hashlib.sha512(body).hexdigest()}}]}


class Response:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def raise_for_status(self): pass
    def iter_content(self, *args): return iter([self.body[:20], self.body[20:]])


class ShaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'data')
        self.p = self.store.create('Shader player', '1.20.1', 'vanilla')
        self.api = Api()
        self.addCleanup(self.api.session.close)
        self.v = version()
        self.project = {'id': 'pack', 'project_type': 'shader', 'title': 'Test Shader'}
        def get(url, **params):
            if url.endswith('/search'): return {'hits': [], 'total_hits': 0}
            if url.endswith('/project/pack/version'): return [copy.deepcopy(self.v)]
            if '/version/' in url: return copy.deepcopy(self.v)
            return copy.deepcopy(self.project)
        self.api.get = Mock(side_effect=get)
        self.api.session.get = Mock(return_value=Response(shader_bytes()))
        self.manager = ShaderManager(self.store, self.api)

    def test_vanilla_catalog_uses_shader_engines_not_mod_loader(self):
        self.manager.search(self.p, 'water', 20, 'updated', 'iris')
        params = self.api.get.call_args.kwargs
        facets = json.loads(params['facets'])
        self.assertIn(['project_type:shader'], facets)
        self.assertIn(['categories:iris'], facets)
        self.assertNotIn(['categories:vanilla'], facets)
        self.assertEqual((params['index'], params['offset']), ('updated', 20))

    def test_choose_checks_actual_game_version_and_engine(self):
        self.v['game_versions'] = ['1.21']
        with self.assertRaises(LauncherError): self.manager.choose('pack', self.p)
        self.v = version(loaders=['optifine'])
        with self.assertRaises(LauncherError): self.manager.choose('pack', self.p, 'iris')

    def test_download_is_verified_and_installed_in_profile_shaderpacks_only(self):
        notifications = []
        self.manager.install('pack', self.p, Task(lambda *args: notifications.append(args)), 'v1')
        path = self.manager.folder(self.p) / 'shader.zip'
        self.assertEqual(path.read_bytes(), shader_bytes())
        self.assertEqual(self.manager.records(self.p)['pack']['version_number'], '2.0')
        self.assertFalse(list(self.store.mods(self.p).iterdir()))
        self.assertTrue(any(maximum and value == maximum for _, value, maximum in notifications))
        other = self.store.create('Other', '1.20.1', 'fabric')
        self.assertFalse(list(self.manager.folder(other).iterdir()))

    def test_hash_failure_does_not_leave_pack_or_metadata(self):
        self.v['files'][0]['hashes']['sha512'] = '0' * 128
        with self.assertRaises(LauncherError): self.manager.install('pack', self.p, Task())
        self.assertFalse(list(self.manager.folder(self.p).iterdir()))
        self.assertEqual(self.manager.records(self.p), {})
        self.assertFalse(list(self.store.directory(self.p).glob('.shader-*')))

    def test_rejects_non_shader_project_and_version_from_other_project(self):
        self.project['project_type'] = 'mod'
        with self.assertRaises(LauncherError): self.manager.install('pack', self.p, Task())
        self.project['project_type'] = 'shader'
        self.v['project_id'] = 'other'
        with self.assertRaises(LauncherError): self.manager.install('pack', self.p, Task(), 'v1')
        self.assertFalse(list(self.manager.folder(self.p).iterdir()))

    def test_local_import_validates_all_files_before_committing(self):
        good = Path(self.temp.name) / 'good.zip'
        bad = Path(self.temp.name) / 'bad.zip'
        good.write_bytes(shader_bytes())
        bad.write_bytes(shader_bytes({'pack.mcmeta': '{}'}))
        with self.assertRaises(LauncherError): self.manager.import_local(self.p, [good, bad], Task())
        self.assertFalse(list(self.manager.folder(self.p).iterdir()))
        self.manager.import_local(self.p, [good], Task())
        self.assertEqual((self.manager.folder(self.p) / good.name).read_bytes(), good.read_bytes())

    def test_zip_with_traversal_is_rejected_without_extraction(self):
        bad = Path(self.temp.name) / 'evil.zip'
        bad.write_bytes(shader_bytes({'shaders/test.fsh': 'shader', '../world.dat': 'bad'}))
        with self.assertRaises(LauncherError): validate_shaderpack(bad)
        self.assertFalse((Path(self.temp.name) / 'world.dat').exists())

    def test_local_pack_is_not_overwritten_case_insensitively(self):
        original = self.manager.folder(self.p) / 'SHADER.ZIP'
        original.write_bytes(b'original-local-pack')
        with self.assertRaises(LauncherError): self.manager.install('pack', self.p, Task())
        self.assertEqual(original.read_bytes(), b'original-local-pack')

    def test_metadata_failure_rolls_back_new_zip(self):
        with patch('shaders.atomic_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.manager.install('pack', self.p, Task())
        self.assertFalse(list(self.manager.folder(self.p).iterdir()))

    def test_remove_failure_restores_pack_then_success_removes_record(self):
        self.manager.install('pack', self.p, Task())
        with patch('shaders.atomic_json', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.manager.remove(self.p, 'shader.zip', Task())
        self.assertTrue((self.manager.folder(self.p) / 'shader.zip').is_file())
        self.assertIn('pack', self.manager.records(self.p))
        self.manager.remove(self.p, 'shader.zip', Task())
        self.assertFalse(list(self.manager.folder(self.p).iterdir()))
        self.assertEqual(self.manager.records(self.p), {})

    def test_cancelled_download_leaves_existing_mods_and_worlds_unchanged(self):
        world = self.store.directory(self.p) / 'level.dat'
        world.write_bytes(b'my world')
        task = Task()
        task.cancel.set()
        with self.assertRaises(Cancelled): self.manager.install('pack', self.p, task)
        self.assertEqual(world.read_bytes(), b'my world')
        self.assertFalse(list(self.manager.folder(self.p).iterdir()))

    def test_running_game_blocks_shader_changes(self):
        launcher = Launcher(self.store)
        self.addCleanup(launcher.api.session.close)
        launcher.process = Mock()
        launcher.process.poll.return_value = None
        local = Path(self.temp.name) / 'pack.zip'
        local.write_bytes(shader_bytes())
        with self.assertRaises(LauncherError): launcher.shaders.import_local(self.p, [local], Task())
        self.assertFalse(list(launcher.shaders.folder(self.p).iterdir()))

    def test_shaderpacks_cannot_be_installed_to_server(self):
        server = {**self.p, 'kind': 'server'}
        with self.assertRaises(LauncherError): self.manager.folder(server)


if __name__ == '__main__': unittest.main()
