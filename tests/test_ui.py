import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from PySide6.QtCore import QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from core import APP_VERSION, LauncherError, Store
from ui import Window, mod_version_text

app=QApplication.instance() or QApplication([])


class UiTests(unittest.TestCase):
    def test_sidebar_groups_keep_page_routes_and_settings_at_bottom(self):
        order = [self.window.main_navigation.itemAt(i).widget().property("page_index") for i in range(8)]
        self.assertEqual(order, [0,1,7,6,8,9,5,4])
        self.assertIs(self.window.utility_navigation.itemAt(2).widget(), self.window.nav[2])
        self.window.nav[2].click()
        self.assertEqual(self.window.pages.currentIndex(), 2)
        self.assertTrue(self.window.nav[2].isChecked())
        self.window.sidebar_updates.click()
        self.assertEqual(self.window.pages.currentIndex(), 5)
        self.assertIs(self.window.tools_tabs.currentWidget(), self.window.launcher_updates_page)

    def test_background_update_check_does_not_lock_game_controls(self):
        next_version = ".".join(APP_VERSION.split(".")[:2] + [str(int(APP_VERSION.split(".")[2]) + 1)])
        with patch.object(self.window.updater, "check_feed", return_value={"available": True, "message": "Yeni sürüm", "manifest": {"version":next_version}}):
            self.window.check_updates_background()
            self.assertTrue(self.window.profiles.isEnabled())
            self.assertTrue(self.window.login_button.isEnabled())
            for _ in range(200):
                QTest.qWait(10)
                if self.window.update_checker is None: break
        self.assertIsNone(self.window.worker)
        self.assertIn("Güncelleme var", self.window.sidebar_updates.text())
        self.assertFalse(self.window.update_notification.isHidden())

    def test_old_game_picker_keeps_both_worlds_and_registers_the_next_launch(self):
        from data_paths import remembered_data_folder
        old = Store(Path(self.temp.name) / "old/data")
        profile = old.create("Önceki oyunum", "1.20.1", "fabric")
        world = old.directory(profile) / "saves/Dunyam/level.dat"
        world.parent.mkdir(parents=True)
        world.write_bytes(b"old-world")
        config = Path(self.temp.name) / "config/data-location.json"
        current = self.window.store.root
        with patch("data_paths.location_file", return_value=config), \
                patch("ui.QFileDialog.getExistingDirectory", return_value=str(old.root.parent)):
            self.window.previous_games.click()
            self.wait_job(attempts=1000)
            self.assertEqual(remembered_data_folder(), (config.parent / "data").resolve())
            self.assertEqual((config.parent / "data" / world.relative_to(old.root)).read_bytes(), b"old-world")
        self.assertEqual(world.read_bytes(), b"old-world")
        self.assertEqual(self.window.store.root, current)
        self.assertIn("ortak klasöre", self.window.status.text())

    def test_old_game_picker_does_not_switch_archive_while_minecraft_is_running(self):
        from unittest.mock import Mock
        self.window.launcher.process = Mock()
        self.window.launcher.process.poll.return_value = None
        with patch("ui.QFileDialog.getExistingDirectory") as dialog:
            self.window.previous_games.click()
            dialog.assert_not_called()
        self.assertIn("Önce oyunu", self.window.status.text())
        self.window.launcher.process = None

    def automatic_release(self):
        next_version = ".".join(APP_VERSION.split(".")[:2] + [str(int(APP_VERSION.split(".")[2]) + 1)])
        self.window.online_release = {"version": next_version}
        return next_version

    def test_automatic_update_downloads_stages_and_restarts_without_questions(self):
        self.automatic_release()
        package = Path(self.temp.name) / "release.kurtupdate"
        package.write_bytes(b"test-package")
        stage = str(Path(self.temp.name) / "updates/verified-test")
        with patch("sys.frozen", True, create=True), \
                patch.object(self.window.updater, "download_release", return_value=str(package)) as download, \
                patch.object(self.window.updater, "stage", return_value=stage) as prepare, \
                patch.object(self.window, "apply_launcher_update") as apply, \
                patch("extras_ui.QMessageBox.question") as question:
            self.window.maybe_auto_update()
            self.wait_job()
            download.assert_called_once()
            prepare.assert_called_once()
            apply.assert_called_once_with(stage)
            question.assert_not_called()
        self.assertFalse(package.exists())

    def test_automatic_update_waits_for_minecraft_to_close(self):
        from unittest.mock import Mock
        self.automatic_release()
        self.window.pending_update_stage = "prepared-stage"
        self.window.launcher.process = Mock()
        self.window.launcher.process.poll.return_value = None
        with patch("sys.frozen", True, create=True), patch.object(self.window, "apply_launcher_update") as apply:
            self.window.maybe_auto_update()
            apply.assert_not_called()
            self.window.launcher.process.poll.return_value = 0
            self.window.maybe_auto_update()
            apply.assert_called_once_with("prepared-stage")
        self.window.launcher.process = None

    def test_automatic_update_waits_for_server_and_other_jobs(self):
        from unittest.mock import Mock
        self.window.pending_update_stage = "prepared-stage"
        self.window.server_manager.process = Mock()
        self.window.server_manager.process.poll.return_value = None
        with patch("sys.frozen", True, create=True), patch.object(self.window, "apply_launcher_update") as apply:
            self.window.maybe_auto_update()
            apply.assert_not_called()
            self.window.server_manager.process.poll.return_value = 0
            self.window.worker = Mock()
            self.window.maybe_auto_update()
            apply.assert_not_called()
            self.window.worker = None
            self.window.maybe_auto_update()
            apply.assert_called_once()
        self.window.server_manager.process = None

    def test_automatic_install_can_be_disabled(self):
        self.window.automatic_update_install.setChecked(False)
        self.window.pending_update_stage = "prepared-stage"
        with patch("sys.frozen", True, create=True), patch.object(self.window, "apply_launcher_update") as apply:
            self.window.maybe_auto_update()
            apply.assert_not_called()
        self.assertFalse(self.window.store.settings["auto_install_updates"])

    def test_failed_startup_is_not_retried_forever_but_user_can_retry(self):
        version = self.automatic_release()
        updates = Path(self.temp.name) / "updates"
        updates.mkdir()
        (updates / "last-failure.json").write_text('{"version":"' + version + '"}')
        package = updates / "release.kurtupdate"
        package.write_bytes(b"retry-package")
        with patch("sys.frozen", True, create=True), \
                patch.object(self.window.updater, "download_release", return_value=str(package)) as download, \
                patch.object(self.window.updater, "stage", return_value="verified-retry"), \
                patch.object(self.window, "apply_launcher_update") as apply:
            self.window.maybe_auto_update()
            download.assert_not_called()
            self.assertIn("geri yüklendi", self.window.launcher_update_status.text())
            self.window.maybe_auto_update(force=True)
            self.wait_job()
            apply.assert_called_once_with("verified-retry")

    def test_bad_automatic_package_does_not_restart_or_retry_in_a_loop(self):
        version = self.automatic_release()
        package = Path(self.temp.name) / "bad.kurtupdate"
        package.write_bytes(b"bad-package")
        with patch("sys.frozen", True, create=True), \
                patch.object(self.window.updater, "download_release", return_value=str(package)) as download, \
                patch.object(self.window.updater, "stage", side_effect=LauncherError("bad signature")), \
                patch.object(self.window, "apply_launcher_update") as apply:
            self.window.maybe_auto_update()
            self.wait_job()
            self.window.maybe_auto_update()
            download.assert_called_once()
            apply.assert_not_called()
        self.assertEqual(self.window.auto_update_failed_version, version)
        self.assertFalse(package.exists())

    def test_automatic_update_waits_for_shared_folder_installation(self):
        self.window.maintenance_pending = True
        self.window.pending_update_stage = "prepared-stage"
        with patch("sys.frozen", True, create=True), patch.object(self.window, "apply_launcher_update") as apply:
            self.window.maybe_auto_update()
            apply.assert_not_called()
            self.window.maintenance_pending = False
            self.window.maybe_auto_update()
            apply.assert_called_once()

    def test_library_tools_and_backup_actions_are_reachable(self):
        p = self.window.store.create("Test", "1.20.1", "fabric")
        self.window.reload_profiles(p["id"])
        self.window.open_tools(0)
        self.assertEqual(self.window.pages.currentIndex(), 5)
        self.assertEqual(self.window.tools_tabs.count(), 7)
        (self.window.store.directory(p) / "options.txt").write_text("music:0.5\n")
        self.window.make_backup()
        self.wait_job()
        self.assertEqual(self.window.backup_table.rowCount(), 1)

    def test_transfer_details_and_retry_use_the_original_operation(self):
        attempts = []
        def operation(task):
            attempts.append(1)
            if len(attempts) == 1: raise LauncherError("temporary failure")
            return "retried"
        self.window.run_job("retryable", operation)
        self.wait_job()
        self.assertFalse(self.window.retry_button.isHidden())
        self.window.retry_job()
        self.wait_job()
        self.assertEqual(self.window.status.text(), "retried")
        self.assertEqual(len(attempts), 2)

    def test_recent_profiles_and_collection_refresh(self):
        p = self.window.store.create("Test", "1.20.1", "fabric")
        self.window.reload_profiles(p["id"])
        self.assertEqual(self.window.recent_table.item(0, 0).text(), "Test")
        self.window.collections.add("Favoriler", {"project_id": "sodium", "title": "Sodium"})
        self.window.refresh_extras()
        self.assertEqual(self.window.collection_table.rowCount(), 1)

    def test_comparison_does_not_start_game_without_approval(self):
        p = self.window.store.create("Test", "1.20.1", "fabric")
        description = {"format": 1, "version": "1.20.1", "loader": "fabric", "files": []}
        result = self.window.packs.compare(p, description)
        with patch.object(self.window.launcher, "play") as play:
            self.window.show_comparison(p, description, result)
        play.assert_not_called()
        self.window.comparison_dialog.close()

    def test_performance_preset_runs_in_worker_and_preserves_options(self):
        p = self.window.store.create("Test", "1.20.1", "fabric")
        path = self.window.store.directory(p) / "options.txt"
        path.write_text("music:0.5\n", encoding="utf-8")
        self.window.reload_profiles(p["id"])
        self.window.use_graphics_preset()
        self.wait_job()
        self.assertIn("music:0.5", path.read_text())
        self.assertEqual(len(self.window.launcher.snapshots.list(p)), 1)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.appdata_patch = patch.dict(os.environ, {"LOCALAPPDATA": str(Path(self.temp.name) / "LocalAppData")})
        self.appdata_patch.start()
        self.window=Window(Path(self.temp.name),autostart=False)
        self.window.show()
        app.processEvents()

    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(10000)
        app.processEvents()
        self.window.close()
        self.appdata_patch.stop()
        self.temp.cleanup()

    def wait_job(self, attempts=800):
        # Verified copies/backups can briefly wait on Windows filesystem filters.
        for i in range(attempts):
            QTest.qWait(10)
            if self.window.worker is None:
                break
        self.assertIsNone(self.window.worker)

    def test_background_result_returns_to_ui(self):
        self.window.run_job("test",lambda task:"completed")
        self.wait_job()
        self.assertEqual(self.window.status.text(),"completed")
        self.assertTrue(self.window.login_button.isEnabled())
        self.assertEqual(self.window.progress_value.text(),"%100")

    def test_background_failure_restores_controls(self):
        def fail(task): raise LauncherError("expected error")
        self.window.run_job("test",fail)
        self.wait_job()
        self.assertEqual(self.window.status.text(),"expected error")
        self.assertTrue(self.window.profiles.isEnabled())
        self.assertEqual(self.window.progress_value.text(),"Hata")
        self.assertEqual(self.window.progress.value(),0)

    def test_version_channels_and_profile_switch(self):
        data={"versions":[{"id":"1.20.1","type":"release"},{"id":"24w14a","type":"snapshot"},
                           {"id":"b1.7.3","type":"old_beta"},{"id":"a1.2.6","type":"old_alpha"}]}
        self.window.loaded_versions((data,False))
        self.assertEqual(self.window.version.count(),1)
        self.window.channel.setCurrentIndex(4)
        self.assertEqual(self.window.version.count(),4)
        p=self.window.store.create("Test","1.20.1","fabric")
        self.window.reload_profiles(p["id"])
        self.assertEqual(self.window.profile_title.text(),"Test")
        self.window.navigate(1)
        self.assertEqual(self.window.pages.currentIndex(),1)

    def test_mod_cards_expand_scroll_area(self):
        p=self.window.store.create("Test","1.20.1","fabric")
        self.window.reload_profiles(p["id"])
        self.window.navigate(1)
        hits=[{"project_id":str(i),"title":"Mod "+str(i),"description":"A compatible mod.",
               "downloads":12,"author":"Author"} for i in range(20)]
        self.window.show_results({"total_hits":20,"hits":hits},0)
        QTest.qWait(100)
        self.assertGreater(self.window.pages.currentWidget().verticalScrollBar().maximum(),2000)
        self.assertGreaterEqual(self.window.results.itemAt(0).widget().height(),154)

    def test_username_launch_does_not_require_microsoft_account(self):
        p = self.window.store.create("Test", "1.20.1", "fabric")
        self.window.reload_profiles(p["id"])
        self.window.username.setText("ArdaTest")
        with patch.object(self.window, "run_job") as run:
            self.window.play()
        run.assert_called_once()
        self.assertEqual(self.window.store.settings["offline_username"], "ArdaTest")
        self.assertFalse(self.window.store.account)

    def test_login_mode_and_name_persist(self):
        self.window.username.setText("Player_123")
        self.window.save_player_name()
        self.window.account_mode.setCurrentIndex(1)
        self.assertFalse(self.window.username.isVisible())
        self.assertEqual(self.window.login_button.text(),"Microsoft ile giriş")
        self.window.account_mode.setCurrentIndex(0)
        self.assertTrue(self.window.username.isVisible())
        self.assertEqual(self.window.login_button.text(),"Giriş yap")
        from core import Store
        settings = Store(Path(self.temp.name)).settings
        self.assertEqual(settings["offline_username"], "Player_123")
        self.assertEqual(settings["login_mode"], "offline")

    def test_version_text_shows_actual_version_and_compatibility(self):
        text = mod_version_text({"version_info": {"version_number": "0.5.13", "game_versions": ["1.20.1"], "loaders": ["fabric"]}})
        self.assertIn("0.5.13", text)
        self.assertIn("1.20.1", text)
        self.assertIn("Fabric", text)
        self.assertIn("doğrulanamadı", mod_version_text({}))

    def test_installed_table_keeps_original_filename_for_actions(self):
        from core import atomic_json
        p = self.window.store.create("Test", "1.20.1", "fabric")
        (self.window.store.mods(p) / "mod-2.0.jar").write_bytes(b"test")
        atomic_json(self.window.store.directory(p) / "mods.lock.json", {"main": {
            "name": "Readable mod name", "file": "mod-2.0.jar", "version_id": "version2", "version_number": "2.0",
            "game_versions": ["1.20.1"], "loaders": ["fabric"]}})
        self.window.reload_profiles(p["id"])
        self.window.installed.selectRow(0)
        self.assertEqual(self.window.selected_mod(), "mod-2.0.jar")
        self.assertEqual(self.window.installed.item(0,1).text(), "2.0")
        self.assertEqual(self.window.installed.item(0,2).text(), "Uyumlu")

    def test_server_page_creation_requires_explicit_eula_before_start(self):
        self.window.manifest = {"versions": [{"id": "1.20.1", "type": "release"}]}
        self.window.server_version.addItem("1.20.1")
        self.window.server_name.setText("Friends")
        self.window.create_server()
        self.window.navigate(4)
        self.assertEqual(len(self.window.store.servers), 1)
        self.assertFalse(self.window.server_eula.isChecked())
        with patch.object(self.window, "run_job") as run:
            self.window.start_server()
        run.assert_not_called()
        self.assertIn("EULA", self.window.status.text())

    def test_invite_join_ui_accepts_username_without_hosting_server(self):
        from invites import encode_invite
        self.window.username.setText("Friend_1")
        self.window.invite_input.setText(encode_invite("friends.joinmc.link:30000",{"version":"1.20.1","loader":"vanilla"}))
        with patch.object(self.window,"run_job") as run:
            self.window.join_invitation()
        run.assert_called_once()
        self.assertEqual(self.window.store.settings["offline_username"],"Friend_1")
        self.assertFalse(self.window.relay.running)

    def test_invalid_invitation_does_not_start_game_or_relay(self):
        self.window.invite_input.setText("bad-code")
        with patch.object(self.window,"run_job") as run:
            self.window.join_invitation()
        run.assert_not_called()
        self.assertFalse(self.window.relay.running)

    def test_large_download_percentage_and_unknown_phase(self):
        self.window.on_progress("Mod indiriliyor…",4*1024**3,8*1024**3)
        self.assertEqual(self.window.progress_value.text(),"%50")
        self.assertEqual(self.window.progress.value(),500)
        self.window.on_progress("Yükleyici çalıştırılıyor…",0,0)
        self.assertEqual(self.window.progress_value.text(),"İşleniyor…")
        self.assertEqual(self.window.progress.maximum(),0)

    def test_cancelled_work_keeps_last_percentage_without_completing(self):
        def cancel(task):
            task.status("Test indiriliyor")
            task.set_max(100)
            task.progress(37)
            task.cancel.set()
            task.check()
        self.window.run_job("test",cancel)
        self.wait_job()
        self.assertEqual(self.window.progress_value.text(),"İptal · %37")
        self.assertEqual(self.window.progress.value(),370)
        self.assertTrue(self.window.login_button.isEnabled())

    def test_failed_work_keeps_last_percentage(self):
        def fail(task):
            task.set_max(200)
            task.progress(50)
            raise LauncherError("download interrupted")
        self.window.run_job("test",fail)
        self.wait_job()
        self.assertEqual(self.window.progress_value.text(),"Hata · %25")
        self.assertEqual(self.window.progress.value(),250)

    def test_mod_sort_resets_page_and_passes_global_api_sort(self):
        from core import Task
        p=self.window.store.create("Test","1.20.1","fabric")
        self.window.reload_profiles(p["id"])
        self.window.offset=40
        self.window.last_query="Sodium"
        self.window.search_input.setText("Sodium")
        with patch.object(self.window,"run_job") as run, patch.object(self.window.launcher.mods,"catalog",return_value={"hits":[],"total_hits":0}) as catalog:
            self.window.mod_sort.setCurrentIndex(2)
            run.assert_called_once()
            run.call_args.args[1](Task())
        self.assertEqual(self.window.offset,0)
        self.assertEqual(catalog.call_args.args[1:3],("Sodium",0))
        self.assertEqual(catalog.call_args.kwargs["sort"],"updated")

    def test_normal_login_saves_username_without_microsoft_or_client_id(self):
        self.window.username.setText("ArdaTest")
        with patch.object(self.window,"run_job") as run, patch.object(self.window.launcher.account,"login") as microsoft:
            self.window.login_button.click()
        run.assert_not_called()
        microsoft.assert_not_called()
        self.assertEqual(self.window.account_label.text(),"ArdaTest")
        self.assertEqual(self.window.store.settings["offline_username"],"ArdaTest")
        self.assertIn("giriş yapıldı",self.window.status.text())
        self.assertEqual(self.window.pages.currentIndex(),0)

    def test_normal_login_rejects_invalid_name_without_opening_settings(self):
        self.window.username.setText("bad name")
        self.window.login()
        self.assertIn("3–16",self.window.status.text())
        self.assertEqual(self.window.store.settings["offline_username"],"")
        self.assertEqual(self.window.pages.currentIndex(),0)

    def test_new_catalogs_worlds_and_management_routes_are_reachable(self):
        for index in (7,8,9):
            self.window.nav[index].click();self.assertEqual(self.window.pages.currentIndex(),index)
        self.window.open_tools(self.window.tools_tabs.indexOf(self.window.management_page))
        self.assertIs(self.window.tools_tabs.currentWidget(),self.window.management_page)
        self.assertEqual(self.window.tools_tabs.count(),7)

    def test_resource_selection_order_is_written_from_the_ui(self):
        from test_content import resource_bytes
        from core import Task
        from PySide6.QtCore import Qt
        p=self.window.store.create('Test','1.20.1','vanilla');self.window.reload_profiles(p['id'])
        source=Path(self.temp.name)/'test.zip';source.write_bytes(resource_bytes())
        self.window.launcher.resources.before_change=lambda *args:None
        self.window.launcher.resources.import_local(p,[source],Task());self.window.refresh_resources()
        self.window.resource_table.item(0,0).setCheckState(Qt.Checked)
        self.window.apply_resource_selection();self.wait_job()
        self.assertEqual(self.window.launcher.resources.order(p),['test.zip'])

    def test_world_ui_lists_metadata_and_creates_world_specific_backup(self):
        from test_worlds_management import level_bytes
        p=self.window.store.create('Test','1.20.1','fabric');self.window.reload_profiles(p['id'])
        world=self.window.store.directory(p)/'saves/MyWorld';world.mkdir(parents=True);(world/'level.dat').write_bytes(level_bytes())
        self.window.refresh_worlds();self.wait_job();self.assertEqual(self.window.world_table.rowCount(),1)
        self.window.world_table.selectRow(0);self.window.backup_world();self.wait_job()
        self.assertEqual(self.window.world_backup_choice.count(),1)
        self.assertEqual(self.window.world_table.item(0,1).text(),'1.20.1')

    def test_profile_copy_ui_creates_separate_profile_with_world_checkbox(self):
        p=self.window.store.create('Original','1.20.1','fabric');self.window.reload_profiles(p['id'])
        world=self.window.store.directory(p)/'saves/MyWorld';world.mkdir(parents=True);(world/'level.dat').write_bytes(b'world')
        self.window.clone_name.setText('Copy');self.window.clone_worlds.setChecked(True)
        self.window.clone_profile();self.wait_job()
        self.assertNotEqual(self.window.profile['id'],p['id'])
        self.assertEqual((self.window.store.directory(self.window.profile)/'saves/MyWorld/level.dat').read_bytes(),b'world')

    def test_modpack_catalog_search_works_before_creating_a_profile(self):
        from core import Task
        catalog=self.window.modpacks_catalog_widget;catalog.query.setText('Optimized')
        with patch.object(self.window,'run_job') as run,patch.object(self.window.modpack_catalog,'search',return_value={'hits':[],'total_hits':0}) as search:
            catalog.search();run.assert_called_once();run.call_args.args[1](Task())
        self.assertEqual(search.call_args.args[0],'Optimized')

    def test_download_pause_resume_and_rate_limit_controls(self):
        from ui import Worker
        self.window.worker=Worker(lambda task:None);task=self.window.worker.task;task.begin_bytes(100)
        self.window.toggle_download_pause();self.assertTrue(task.paused.is_set())
        self.assertEqual(self.window.pause_download.text(),'Devam et')
        self.window.save_download_limit(512);self.assertEqual(task.rate_limit,512*1024)
        self.window.toggle_download_pause();self.assertFalse(task.paused.is_set())
        self.window.worker=None

    def test_storage_ui_requires_explicit_selection_before_cleaning(self):
        cache=self.window.store.root/'cache/downloads/test.part';cache.parent.mkdir(parents=True);cache.write_bytes(b'cache')
        self.window.scan_storage();self.wait_job()
        self.assertEqual(self.window.storage_files.rowCount(),1)
        with patch('management_ui.QMessageBox.question') as confirm:
            self.window.clean_storage();confirm.assert_not_called()
        self.assertTrue(cache.is_file())

    def test_shader_page_supports_vanilla_search_and_engine_sort_filters(self):
        from core import Task
        p = self.window.store.create('Shaders', '1.20.1', 'vanilla')
        self.window.reload_profiles(p['id'])
        self.window.nav[6].click()
        self.assertEqual(self.window.pages.currentIndex(), 6)
        self.assertIn('SHADERPACK', self.window.breadcrumb.text())
        self.assertFalse(self.window.shader_iris.isEnabled())
        self.window.shader_search_input.setText('water')
        self.window.shader_offset = 40
        with patch.object(self.window, 'run_job') as run, patch.object(self.window.launcher.shaders, 'catalog') as catalog:
            self.window.shader_engine.setCurrentIndex(1)
            run.assert_called_once()
            run.call_args.args[1](Task())
        self.assertEqual(catalog.call_args.args[1:3], ('water', 0))
        self.assertEqual(catalog.call_args.kwargs['engine'], 'iris')

    def test_shader_download_table_is_separate_from_mods_and_clears_on_profile_switch(self):
        from PySide6.QtCore import Qt
        import io, zipfile
        p = self.window.store.create('Shaders', '1.20.1', 'fabric')
        self.window.reload_profiles(p['id'])
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('shaders/composite.fsh', 'void main() {}')
        path = self.window.launcher.shaders.folder(p) / 'local.zip'
        path.write_bytes(stream.getvalue())
        self.window.refresh_shaders()
        self.assertEqual(self.window.shader_installed.rowCount(), 1)
        self.assertEqual(self.window.installed.rowCount(), 0)
        self.assertEqual(self.window.shader_installed.item(0, 0).data(Qt.UserRole), 'local.zip')
        other = self.window.store.create('Other', '1.21', 'vanilla')
        self.window.reload_profiles(other['id'])
        self.assertEqual(self.window.shader_installed.rowCount(), 0)
        self.assertIsNone(self.window.shader_query_state)
        self.assertTrue(path.is_file())

    def test_shader_install_is_blocked_while_game_is_running(self):
        from unittest.mock import Mock
        p = self.window.store.create('Shaders', '1.20.1', 'fabric')
        self.window.reload_profiles(p['id'])
        self.window.launcher.process = Mock()
        self.window.launcher.process.poll.return_value = None
        with patch.object(self.window, 'run_job') as run:
            self.window.install_shaderpack('pack', 'v1')
        run.assert_not_called()
        self.window.launcher.process = None


if __name__=="__main__": unittest.main()
