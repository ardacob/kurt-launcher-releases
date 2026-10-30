import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from core import Task, ModManager, LauncherError


class ProgressTests(unittest.TestCase):
    def test_filename_does_not_reset_batch_percentage(self):
        events=[]
        task=Task(lambda *event:events.append(event))
        callbacks=task.callbacks
        callbacks["setStatus"]("Download Assets")
        callbacks["setMax"](100)
        callbacks["setProgress"](42)
        callbacks["setStatus"]("Download asset-file.ogg")
        self.assertEqual(events[-1],("İndiriliyor: asset-file.ogg",42,100))
        callbacks["setStatus"]("Install java runtime")
        self.assertEqual(events[-1],("Java hazırlanıyor…",0,0))
        callbacks["setMax"](50)
        self.assertEqual(events[-1],("Java hazırlanıyor…",0,50))

    def test_completed_batch_not_reused_for_standalone_download(self):
        events=[]
        task=Task(lambda *event:events.append(event))
        task.set_max(10)
        task.progress(10)
        task.callbacks["setStatus"]("Download minecraft.jar")
        self.assertEqual(events[-1],("İndiriliyor: minecraft.jar",0,0))

    def test_search_sort_applies_to_entire_filtered_catalog(self):
        api=Mock()
        manager=ModManager(Mock(),api)
        profile={"version":"1.20.1","loader":"fabric"}
        manager.search(profile,"Sodium",40,sort="downloads")
        params=api.get.call_args.kwargs
        self.assertEqual(params["index"],"downloads")
        self.assertEqual(params["offset"],40)
        self.assertEqual(params["query"],"Sodium")
        self.assertIn("versions:1.20.1",params["facets"])
        with self.assertRaises(LauncherError): manager.search(profile,sort="invalid-sort")
        self.assertEqual(api.get.call_count,1)


if __name__=="__main__": unittest.main()
