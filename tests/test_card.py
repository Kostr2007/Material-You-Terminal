"""Geometry and text/color fidelity of the composed entrance."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cli'))
import myt_card as card

PALETTE={'on_surface':'#eeeeee','surface':'#101010','ansi6':'#97ccf8'}
CARD='\x1b[31m          user@nixos\x1b[0m\n          ──────────\n          memory \x1b[24G\x1b[38;2;100;200;255m━━━━ 4 GiB\x1b[0m\n          \x1b[38;5;6m● ● ●\x1b[0m\n'


class CardTests(unittest.TestCase):
    def test_vertical_centers_match_and_logo_size_is_preserved(self):
        balanced,box=card.align_card(CARD,(2,1,7,10),80)
        area=card.bounds(balanced)
        self.assertLessEqual(abs(box[1]+(box[3]-1)/2-(area[1]+area[3])/2),.5)
        self.assertEqual(box[2:],(7,10))
        original=[''.join(c for x,c in card.cells(l)).strip() for l in CARD.splitlines()]
        after=[''.join(c for x,c in card.cells(l)).strip() for l in balanced.splitlines() if l]
        self.assertEqual(original,after)

    def test_centering_relocates_absolute_columns(self):
        balanced,box=card.align_card(CARD,(2,1,7,10),100,horizontal='center')
        area=card.bounds(balanced)
        left=min(box[0],area[0]);right=max(box[0]+box[2]-1,area[2])
        self.assertLessEqual(abs((left+right)/2-49.5),.5)
        offset=box[0]-2
        self.assertIn(f'\x1b[{24+offset}G',balanced)

    def test_original_alignment_keeps_text_rows(self):
        aligned,box=card.align_card(CARD,(2,1,7,10),80,vertical='original')
        self.assertEqual(box,(2,1,7,10))
        self.assertEqual(card.bounds(aligned)[1],0)

    def test_final_frame_is_exact_including_colors_and_columns(self):
        self.assertEqual(card.frame(CARD,1,PALETTE),CARD)
        early=card.frame(CARD,.2,PALETTE)
        self.assertNotEqual(early,CARD)
        self.assertIn('\x1b[24G',early)
        self.assertEqual(card.bounds(early),card.bounds(CARD))
        self.assertIn('●',card.frame(CARD,.95,PALETTE))

    def test_indexed_colors_and_background_parameters(self):
        self.assertEqual(card.foreground('\x1b[38;5;6m','#ffffff',PALETTE),'#97ccf8')
        self.assertEqual(card.foreground('\x1b[38;5;196m','#ffffff',PALETTE),'#ff0000')
        self.assertEqual(card.foreground('\x1b[48;2;0;0;0m','#abcdef',PALETTE),'#abcdef')
        self.assertEqual(card.foreground('\x1b[38;2;11;22;33m','#ffffff',PALETTE),'#0b1621')

    def test_empty_card_is_unchanged(self):
        self.assertEqual(card.frame('\n\n',.5,PALETTE),'\n\n')
        self.assertEqual(card.align_card('\n',(0,0,8,8),80),('\n',(0,0,8,8)))
