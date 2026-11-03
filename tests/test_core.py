"""core.py testleri. Çalıştırmak için: python -m unittest discover tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core  # noqa: E402

LANGS = {"tr", "en"}


def normalize(data):
    return core.normalize_settings(data, LANGS, "en")


class FakeKeyboard:
    """Gerçek tuş göndermek yerine olayları kaydeder."""

    def __init__(self):
        self.events = []

    def press(self, choice):
        self.events.append(("down", choice))

    def release(self, choice):
        self.events.append(("up", choice))


def make_holder():
    kb = FakeKeyboard()
    return core.Holder(kb.press, kb.release), kb


class KeyCatalogTests(unittest.TestCase):
    def test_new_keys_exist(self):
        for name in [f"F{n}" for n in range(1, 13)] + [
                "tab", "esc", "backspace", "insert", "delete", "home", "end", "pgup", "pgdn",
                "capslock", "num0", "num9", "num_add", "num_sub", "num_mul", "num_div", "num_dec"]:
            self.assertIn(name, core.KEYS, name)

    def test_virtual_key_codes(self):
        self.assertEqual(core.KEYS["F1"], 0x70)
        self.assertEqual(core.KEYS["F12"], 0x7B)
        self.assertEqual(core.KEYS["tab"], 0x09)
        self.assertEqual(core.KEYS["esc"], 0x1B)
        self.assertEqual(core.KEYS["num0"], 0x60)
        self.assertEqual(core.KEYS["num_div"], 0x6F)

    def test_navigation_keys_are_extended(self):
        for name in ["insert", "delete", "home", "end", "pgup", "pgdn", "num_div", "up"]:
            self.assertIn(core.KEYS[name], core.EXTENDED, name)
        self.assertNotIn(core.KEYS["num0"], core.EXTENDED)

    def test_choices_exclude_hotkey(self):
        choices = core.key_choices("F8")
        self.assertNotIn("F8", choices)
        self.assertIn("F7", choices)
        self.assertIn("mouse_left", choices)


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        s = normalize({})
        self.assertEqual(s["keys"], ["W"])
        self.assertEqual(s["mode"], "hold")
        self.assertEqual(s["hotkey"], "F8")
        self.assertEqual(s["duration_s"], 0)
        self.assertEqual(s["language"], "en")

    def test_migrates_old_single_key(self):
        s = normalize({"key": "space", "language": "tr"})
        self.assertEqual(s["keys"], ["space"])
        self.assertNotIn("key", s)
        self.assertEqual(s["language"], "tr")

    def test_drops_invalid_duplicate_and_extra_keys(self):
        s = normalize({"keys": ["Shift", "bogus", "Shift", "W", "A", "D"]})
        self.assertEqual(s["keys"], ["Shift", "W", "A"])

    def test_drops_key_that_is_the_hotkey(self):
        s = normalize({"keys": ["F9", "W"], "hotkey": "F9"})
        self.assertEqual(s["keys"], ["W"])

    def test_falls_back_when_no_valid_key(self):
        self.assertEqual(normalize({"keys": ["F8"]})["keys"], ["W"])

    def test_wrong_json_types_do_not_crash(self):
        s = normalize({"hotkey": ["F8"], "language": {}, "keys": [["W"], 5, "A"], "mode": [],
                       "topmost": "yes"})
        self.assertEqual(s["hotkey"], "F8")
        self.assertEqual(s["language"], "en")
        self.assertEqual(s["keys"], ["A"])
        self.assertEqual(s["mode"], "hold")
        self.assertEqual(normalize({"key": []})["keys"], ["W"])

    def test_infinite_and_nan_numbers(self):
        s = normalize({"interval_ms": float("inf"), "duration_s": float("nan")})
        self.assertEqual(s["interval_ms"], core.DEFAULT_SETTINGS["interval_ms"])
        self.assertEqual(s["duration_s"], 0)
        self.assertEqual(normalize({"duration_s": "nan"})["duration_s"], 0)

    def test_clamps_numbers(self):
        s = normalize({"mode": "repeat", "interval_ms": 1, "duration_s": -5})
        self.assertEqual(s["mode"], "repeat")
        self.assertEqual(s["interval_ms"], core.MIN_INTERVAL_MS)
        self.assertEqual(s["duration_s"], 0)
        s = normalize({"interval_ms": "abc", "duration_s": "x", "mode": "weird"})
        self.assertEqual(s["interval_ms"], core.DEFAULT_SETTINGS["interval_ms"])
        self.assertEqual(s["duration_s"], 0)
        self.assertEqual(s["mode"], "hold")


class HoldModeTests(unittest.TestCase):
    def test_combo_presses_in_order_and_releases_in_reverse(self):
        h, kb = make_holder()
        h.start(["Shift", "W"], "hold", 100, 0, now=0)
        self.assertEqual(kb.events, [("down", "Shift"), ("down", "W")])
        kb.events.clear()
        h.stop()
        self.assertEqual(kb.events, [("up", "W"), ("up", "Shift")])
        self.assertFalse(h.active)

    def test_tick_repeats_keydown_but_not_mouse(self):
        h, kb = make_holder()
        h.start(["mouse_left", "W"], "hold", 100, 0, now=0)
        kb.events.clear()
        self.assertTrue(h.tick(now=0.03))
        self.assertEqual(kb.events, [("down", "W")])

    def test_keydown_repeat_is_throttled_like_real_autorepeat(self):
        h, kb = make_holder()
        h.start(["W"], "hold", 100, 0, now=0)
        kb.events.clear()
        for ms in range(1, 30):
            h.tick(now=ms / 1000)
        self.assertEqual(kb.events, [])
        h.tick(now=0.03)
        h.tick(now=0.031)
        self.assertEqual(kb.events, [("down", "W")])

    def test_duration_releases_automatically(self):
        h, kb = make_holder()
        h.start(["W"], "hold", 100, 2, now=10)
        self.assertTrue(h.tick(now=11.9))
        kb.events.clear()
        self.assertFalse(h.tick(now=12.0))
        self.assertEqual(kb.events, [("up", "W")])
        self.assertFalse(h.active)

    def test_remaining_time(self):
        h, _ = make_holder()
        h.start(["W"], "hold", 100, 5, now=0)
        self.assertAlmostEqual(h.remaining(now=1.5), 3.5)
        h2, _ = make_holder()
        h2.start(["W"], "hold", 100, 0, now=0)
        self.assertIsNone(h2.remaining(now=100))


class RepeatModeTests(unittest.TestCase):
    def test_taps_combo_at_interval(self):
        h, kb = make_holder()
        h.start(["Ctrl", "C"], "repeat", 100, 0, now=0)
        tap = [("down", "Ctrl"), ("down", "C"), ("up", "C"), ("up", "Ctrl")]
        self.assertEqual(kb.events, tap)
        kb.events.clear()
        h.tick(now=0.05)
        self.assertEqual(kb.events, [])
        h.tick(now=0.1)
        self.assertEqual(kb.events, tap)

    def test_does_not_burst_after_a_long_pause(self):
        h, kb = make_holder()
        h.start(["W"], "repeat", 100, 0, now=0)
        kb.events.clear()
        h.tick(now=5)
        h.tick(now=5.01)
        self.assertEqual(kb.events, [("down", "W"), ("up", "W")])

    def test_stop_sends_nothing_because_keys_are_already_up(self):
        h, kb = make_holder()
        h.start(["W"], "repeat", 100, 0, now=0)
        kb.events.clear()
        h.stop()
        self.assertEqual(kb.events, [])

    def test_duration_stops_repeat(self):
        h, _ = make_holder()
        h.start(["W"], "repeat", 100, 1, now=0)
        self.assertFalse(h.tick(now=1.0))
        self.assertFalse(h.active)


if __name__ == "__main__":
    unittest.main()
