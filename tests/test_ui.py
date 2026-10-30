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
from core import LauncherError
from ui import Window, mod_version_text

app=QApplication.instance() or QApplication([])


class UiTests(unittest.TestCase):
    def test_sidebar_groups_keep_page_routes_and_settings_at_bottom(self):
        order = [self.window.main_navigation.itemAt(i).widget().property("page_index") for i in range(4)]
        self.assertEqual(order, [0,1,5,4])
        self.assertIs(self.window.utility_navigation.itemAt(2).widget(), self.window.nav[2])
        self.window.nav[2].click()
        self.assertEqual(self.window.pages.currentIndex(), 2)
        self.assertTrue(self.window.nav[2].isChecked())
        self.window.sidebar_updates.click()
        self.assertEqual(self.window.pages.currentIndex(), 5)
        self.assertEqual(self.window.tools_tabs.currentIndex(), 6)

    def test_background_update_check_does_not_lock_game_controls(self):
        with patch.object(self.window.updater, "check_feed", return_value={"available": True, "message": "Yeni sürüm", "manifest": {"version":"0.4.2"}}):
            self.window.check_updates_background()
            self.assertTrue(self.window.profiles.isEnabled())
            self.assertTrue(self.window.login_button.isEnabled())
            for _ in range(200):
                QTest.qWait(10)
                if self.window.update_checker is None: break
        self.assertIsNone(self.window.worker)
        self.assertIn("Güncelleme var", self.window.sidebar_updates.text())
        self.assertFalse(self.window.update_notification.isHidden())

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
        self.window=Window(Path(self.temp.name),autostart=False)
        self.window.show()
        app.processEvents()

    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(10000)
        app.processEvents()
        self.window.close()
        self.temp.cleanup()

    def wait_job(self):
        for i in range(200):
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


if __name__=="__main__": unittest.main()
