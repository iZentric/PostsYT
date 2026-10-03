"""Teste PostsYT (stdlib unittest): python -m unittest discover -s tests -v"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from postsyt import feeds
from postsyt.brain import Brain, cap_emojis, trim
from postsyt.config import Config
from postsyt.innertube import sapisidhash, load_json_cookies
from postsyt.imagemaker import ImageMaker, svg_card, svg_poll
from postsyt.models import (KIND_MEME, KIND_POLL, KIND_QUESTION, KIND_TREND,
                            KIND_VIDEO, STATUS_DRAFT)
from postsyt.scheduler import next_slot, in_quiet_hours, RO_DAYS
from postsyt.store import Store
from postsyt.util import (extract_balanced_json, extract_ytcfg,
                          parse_relative_time_ro, jaccard, word_set, text_hash)

FEED_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
 <title>iSentric</title>
 <entry>
  <yt:videoId>n0wjz5kTAtI</yt:videoId>
  <yt:channelId>UCBoZcTLayAUgYTPsyrStiLg</yt:channelId>
  <title>POKEMONII ĂȘTIA SUNT PREA INTELIGENȚI?! 🧠 #minecraft #pokecity #shorts</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=n0wjz5kTAtI"/>
  <author><name>iSentric</name></author>
  <published>2026-10-03T11:53:11+00:00</published>
  <media:group><media:community><media:statistics views="1234"/></media:community></media:group>
 </entry>
 <entry>
  <yt:videoId>ZcSy0AyrDWQ</yt:videoId>
  <yt:channelId>UCBoZcTLayAUgYTPsyrStiLg</yt:channelId>
  <title>🔴 CONSTRUIM CAMERA CU GOLEMI DE COPRU în POKECITY!</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=ZcSy0AyrDWQ"/>
  <author><name>iSentric</name></author>
  <published>2026-09-18T16:30:18+00:00</published>
 </entry>
</feed>"""


class TestFeeds(unittest.TestCase):
    def test_parse_feed(self):
        vids = feeds.parse_feed(FEED_FIXTURE)
        self.assertEqual(len(vids), 2)
        self.assertEqual(vids[0].video_id, "n0wjz5kTAtI")
        self.assertTrue(vids[0].is_short)
        self.assertFalse(vids[0].is_live)
        self.assertEqual(vids[0].views, 1234)
        self.assertTrue(vids[1].is_live)
        self.assertEqual(vids[1].channel_title, "iSentric")
        self.assertIn("watch?v=", vids[0].url)


class TestUtil(unittest.TestCase):
    def test_balanced_json(self):
        page = 'xxx ytcfg.set({"a":{"b":[1,2,{"c":"str with } inside"}]}}); garbage'
        obj, _ = extract_balanced_json(page, page.find("ytcfg"))
        self.assertEqual(obj["a"]["b"][2]["c"], "str with } inside")

    def test_ytcfg_merge(self):
        page = ('window.ytplayer={};ytcfg.set({"INNERTUBE_API_KEY":"K3Y"});'
                'ytcfg.set({"LOGGED_IN":true, "DELEGATED_SESSION_ID":"123"});')
        cfg = extract_ytcfg(page)
        self.assertEqual(cfg["INNERTUBE_API_KEY"], "K3Y")
        self.assertTrue(cfg["LOGGED_IN"])
        self.assertEqual(cfg["DELEGATED_SESSION_ID"], "123")

    def test_relative_ro(self):
        ref = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
        self.assertEqual((ref - parse_relative_time_ro("acum 3 ore", ref)).total_seconds(), 3 * 3600)
        self.assertEqual((ref - parse_relative_time_ro("acum 2 zile", ref)).days, 2)
        self.assertIsNone(parse_relative_time_ro("text random", ref))

    def test_jaccard(self):
        self.assertGreater(jaccard(word_set("am prins un leu in nether"),
                                   word_set("leu prins nether")), 0.4)
        self.assertLess(jaccard(word_set("sectiune complet diferita"),
                                word_set("altceva fara legatura")), 0.2)


class TestInnertube(unittest.TestCase):
    def test_sapisidhash(self):
        h = sapisidhash({"SAPISID": "abc123"})
        self.assertTrue(h.startswith("SAPISIDHASH "))
        self.assertRegex(h, r"SAPISIDHASH \d+_[0-9a-f]{40}")

    def test_sapisid_3p(self):
        h = sapisidhash({"__Secure-3PAPISID": "xyz"})
        self.assertTrue(h.startswith("SAPISID3PHASH "))

    def test_load_json_cookies(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump([{"name": "SAPISID", "value": "v1"}, {"name": "A", "value": "b"}], f)
            path = f.name
        self.assertEqual(load_json_cookies(path), {"SAPISID": "v1", "A": "b"})
        os.unlink(path)


class TestBrain(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.brain = Brain(self.cfg)

    def _video_row(self):
        return {"id": "n0wjz5kTAtI", "title": "POKECITY?! 😱 AM PRINS UN LEU IN NETHER !",
                "url": "https://www.youtube.com/watch?v=n0wjz5kTAtI", "is_live": 0}

    def test_video_post_golden_rule(self):
        d = self.brain.gen_video_post(self._video_row())
        self.assertEqual(d.kind, KIND_VIDEO)
        self.assertIn(self._video_row()["url"], d.text)   # link obligatoriu
        self.assertGreater(len(d.text), 40)               # hook
        self.assertLessEqual(len(d.text), 1201)

    def test_poll_shape(self):
        d = self.brain.gen_poll("https://youtu.be/x")
        self.assertEqual(d.kind, KIND_POLL)
        self.assertTrue(2 <= len(d.poll_options) <= 5)
        self.assertTrue(d.poll_question)
        self.assertIn("https://youtu.be/x", d.text)

    def test_trend_not_copy(self):
        source = "L-am GASIT in Padure pe Roblox !"
        d = self.brain.gen_trend_post(source, "Jocuri Horror", "https://youtu.be/mine")
        sim = jaccard(word_set(d.text), word_set(source))
        self.assertLess(sim, 0.45, "postarea B nu trebuie să copieze titlul sursei")
        self.assertNotIn("L-am GASIT in Padure pe Roblox", d.text)

    def test_question_and_meme(self):
        dq = self.brain.gen_question("https://youtu.be/l")
        self.assertIn("https://youtu.be/l", dq.text)
        dm = self.brain.gen_meme("https://youtu.be/l")
        self.assertEqual(dm.kind, KIND_MEME)

    def test_emoji_cap(self):
        spam = "x " + "🔥" * 40
        self.assertLessEqual(len(cap_emojis(spam).replace("x", "").strip()), 14 * 4)


class TestScheduler(unittest.TestCase):
    def test_next_slot(self):
        cfg = Config()
        now = datetime(2026, 10, 4, 10, 0)
        s = next_slot(cfg, [12, 19], after=now, jitter_min=0)
        self.assertEqual(s.hour, 12)
        s2 = next_slot(cfg, [8], after=now, jitter_min=0)
        self.assertEqual(s2.day, 5)  # a doua zi

    def test_quiet(self):
        self.assertTrue(in_quiet_hours(datetime(2026, 1, 1, 3), [0, 8]))
        self.assertFalse(in_quiet_hours(datetime(2026, 1, 1, 12), [0, 8]))


class TestStore(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.store = Store(self.path)

    def tearDown(self):
        try:
            self.store.conn.close()
        finally:
            os.unlink(self.path)

    def test_draft_dedupe(self):
        from postsyt.models import Draft
        d = Draft(kind=KIND_POLL, text="Întrebare unică?", poll_question="Întrebare unică?",
                  poll_options=["a", "b"], status=STATUS_DRAFT)
        id1 = self.store.add_draft(d)
        id2 = self.store.add_draft(d)
        self.assertIsNotNone(id1)
        self.assertIsNone(id2, "dedupe: același text în 48h nu intră de 2 ori")

    def test_video_announce_flow(self):
        from postsyt.models import Video
        v = Video(video_id="v1", channel_id="UC", channel_title="iSentric",
                  title="Test", url="https://youtu.be/v1",
                  published=datetime.now(timezone.utc))
        self.assertTrue(self.store.add_video(v))
        self.assertFalse(self.store.add_video(v))
        un = self.store.unannounced_videos()
        self.assertEqual(len(un), 1)
        self.store.mark_announced("v1")
        self.assertEqual(self.store.unannounced_videos(), [])

    def test_caps(self):
        from postsyt.models import Draft
        for _ in range(3):
            did = self.store.add_draft(Draft(
                kind="C", text=f"t{os.urandom(4).hex()}", status="published"))
            self.store.update_draft(did, published_at=datetime.now(timezone.utc))
        self.assertEqual(self.store.published_today(), 3)
        cfg = Config()
        ok, reason = __import__("postsyt.scheduler", fromlist=["can_publish_now"]) \
            .can_publish_now(self.store, cfg)
        self.assertFalse(ok)


class TestImageMaker(unittest.TestCase):
    def test_svg_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            im = ImageMaker(td)
            p1 = im.for_video("POKECITY?! AM PRINS UN LEU IN NETHER", seed=1, want_png=False)
            self.assertTrue(p1.endswith(".svg"))
            svg = open(p1, encoding="utf-8").read()
            self.assertIn("<svg", svg)
            self.assertIn("POKECITY", svg)
            p2 = im.for_poll("Care e cel mai OP?", ["Charizard", "Gyarados"], seed=2)
            svg2 = open(p2, encoding="utf-8").read()
            self.assertIn("A", svg2)
            self.assertIn("Charizard", svg2)


if __name__ == "__main__":
    unittest.main()
