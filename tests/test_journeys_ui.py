import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtCore import Qt,QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from ui import Window
from deep_links import listen,forward,invite_link
from invites import encode_invite
from appearance import stylesheet

app=QApplication.instance() or QApplication([])


class JourneyUiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.window=Window(Path(self.temp.name)/'data',False)
        self.p=self.window.store.create('Dünyalarım','1.20.1','fabric');self.window.reload_profiles(self.p['id'])
        self.window.show();app.processEvents()

    def tearDown(self):
        QThreadPool.globalInstance().waitForDone();app.processEvents()
        self.window.close();self.window.launcher.api.session.close();self.temp.cleanup()

    def test_all_new_tools_reachable_without_changing_sidebar_routes(self):
        self.assertEqual(self.window.management_tabs.count(),6)
        for i in (3,4,5):
            self.window.open_journey(i);self.assertEqual(self.window.tools_tabs.currentIndex(),7);self.assertEqual(self.window.management_tabs.currentIndex(),i)
        self.assertTrue(self.window.continue_button.isEnabled())

    def test_live_theme_scale_and_language_round_trip_preserves_profile_names(self):
        w=self.window
        w.theme_choice.setCurrentIndex(w.theme_choice.findData('sunset'));w.interface_scale.setValue(120)
        w.language_choice.setCurrentIndex(w.language_choice.findData('en'));w.save_interface()
        self.assertEqual(w.property('visual_theme'),'sunset');self.assertIn('font-size: 16px',w.styleSheet())
        self.assertIn('Game hub',w.nav[0].text());self.assertEqual(w.profiles.currentText(),'Dünyalarım')
        self.assertEqual(w.management_tabs.tabText(3),'Favorite servers');self.assertEqual(w.theme_choice.currentData(),'sunset')
        w.theme_choice.setCurrentIndex(w.theme_choice.findData('light'));w.language_choice.setCurrentIndex(w.language_choice.findData('tr'));w.save_interface()
        self.assertIn('Oyun merkezi',w.nav[0].text());self.assertEqual(w.management_tabs.tabText(3),'Favori sunucular')
        self.assertEqual(w.property('visual_theme'),'light')

    def test_all_theme_tokens_resolve_and_custom_accent_does_not_corrupt_gradient(self):
        for theme in ('light','sunset','contrast','system'):
            css,palette,selected=stylesheet({'theme':theme,'accent':'#ff0000','ui_scale':140})
            self.assertNotIn('@',css);self.assertNotIn('#ff00002',css);self.assertIn('font-size: 18px',css)

    def test_keyboard_navigation_shortcuts(self):
        QTest.keyClick(self.window,Qt.Key_3,Qt.ControlModifier);app.processEvents()
        self.assertEqual(self.window.pages.currentIndex(),9)
        QTest.keyClick(self.window,Qt.Key_1,Qt.ControlModifier);app.processEvents()
        self.assertEqual(self.window.pages.currentIndex(),0)

    def test_local_invite_forwarding_delivers_to_existing_instance(self):
        w=self.window;listen(w)
        code=encode_invite('test.ply.gg:12345',{'version':'1.20.1','loader':'vanilla','loader_version':None});value=invite_link(code)
        with patch.object(w,'receive_invite_link') as receive:
            # A second launcher is a different process. Pump this instance's event
            # loop while its peer waits for Windows to accept the named pipe.
            code="import sys;sys.path.insert(0,sys.argv[1]);from PySide6.QtCore import QCoreApplication;from deep_links import forward;a=QCoreApplication([]);print(forward(sys.argv[2],sys.argv[3]))"
            peer=subprocess.Popen([sys.executable,'-c',code,str(Path(__file__).resolve().parents[1]/'src'),str(w.store.root),value],stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.addCleanup(lambda:peer.kill() if peer.poll() is None else None)
            for _ in range(500):
                QTest.qWait(10)
                if receive.called and peer.poll() is not None:break
            out,err=peer.communicate(timeout=3);self.assertEqual(peer.returncode,0,err);self.assertEqual(out.strip(),b'True',err)
            receive.assert_called_once_with(value)
        w.invite_listener.close()

    def test_external_invite_previews_and_no_does_not_launch_game(self):
        code=encode_invite('test.ply.gg:12345',{'version':'1.20.1','loader':'vanilla','loader_version':None})
        with patch('journeys_ui.QMessageBox.question',return_value=QMessageBox.No) as question,patch.object(self.window,'join_invitation') as join:
            self.window.receive_invite_link(invite_link(code));question.assert_called_once();join.assert_not_called()
        self.assertEqual(self.window.invite_input.text(),code)

    def test_favorite_server_save_uses_actual_profile_identity(self):
        self.window.favorite_name.setText('Friends');self.window.favorite_address.setText('localhost:25565');self.window.add_favorite_server()
        self.assertEqual(self.window.favorite_rows[0]['profile'],self.p['id']);self.assertEqual(self.window.favorites_table.rowCount(),1)
        self.window.favorites_table.selectRow(0);self.window.remove_favorite_server();self.assertEqual(self.window.favorites_table.rowCount(),0)


if __name__=='__main__':unittest.main()
