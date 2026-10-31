from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from appearance import PALETTE_THEMES,PALETTES,contrast,stylesheet,gradient_samples,hero_colors


class PaletteTests(unittest.TestCase):
    def test_every_palette_keeps_body_and_gradient_text_readable(self):
        for key,*_ in PALETTE_THEMES:
            with self.subTest(theme=key):
                css,colors,selected=stylesheet({'theme':key})
                self.assertEqual(selected,key);self.assertNotIn('@',css)
                for text in ('text','muted','accent'):
                    for surface in ('bg','surface','side','field','soft','hover','selected'):
                        self.assertGreaterEqual(contrast(colors[text],colors[surface]),4.5,(key,text,surface))
                for background in gradient_samples([colors['primary'],colors['primary_mid'],colors['primary2']]):
                    self.assertGreaterEqual(contrast(colors['onprimary'],background),4.5,key)

    def test_old_custom_accent_cannot_mask_a_palette_and_override_is_explicit(self):
        original=dict(PALETTES['coral_mint'])
        _,palette,_=stylesheet({'theme':'coral_mint','accent':'#0011ff'})
        self.assertEqual(palette['primary'],original['primary'])
        _,custom,_=stylesheet({'theme':'coral_mint','accent':'#0011ff','use_custom_accent':True})
        self.assertEqual(custom['primary'],'#0011ff');self.assertGreaterEqual(contrast(custom['onprimary'],'#0011ff'),4.5)
        self.assertEqual(PALETTES['coral_mint'],original)

    def test_home_landscape_uses_each_references_sky_colors_and_readable_overlay(self):
        for key,title,swatches,*_ in PALETTE_THEMES:
            colors=hero_colors(key,PALETTES[key])
            self.assertEqual((colors['sky0'],colors['sky1'],colors['sky2']),swatches[:3])
            self.assertGreaterEqual(contrast(colors['title'],colors['shade']),4.5,key)


if __name__=='__main__':unittest.main()
