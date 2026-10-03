"""Teste PC Bridge universal: hub, transport, proxy-lock, integrare publisher."""
import base64
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from postsyt.bridge_hub import BridgeHub
from postsyt.util import HttpError


class HubTest(unittest.TestCase):
    def test_roundtrip_poll_deliver(self):
        """Agentul pune task (submit), PC-ul îl ia (poll) și livrează rezultatul."""
        hub = BridgeHub("s3cret")
        out = {}
        body = b'{"ok": true}'
        def pc_side():  # PC-ul: long-poll în buclă, execută, livrează
            for _ in range(6):
                task = hub.poll("pc-test", "postsyt", wait=2)
                if task:
                    out["task"] = task
                    hub.deliver(task["id"], {"status": 200, "headers": {"C": "j"},
                                             "body_b64": base64.b64encode(body).decode()})
                    return
        t = threading.Thread(target=pc_side, daemon=True)
        t.start()
        time.sleep(0.3)  # PC-ul se înregistrează întâi (ca-n realitate)
        res = hub.submit("https://www.youtube.com/feed",
                         method="GET", headers={"X": "1"},
                         timeout=10, project="test")
        t.join(timeout=8)
        self.assertIn("task", out, "PC-ul nu a primit taskul din coadă")
        self.assertEqual(out["task"]["url"], "https://www.youtube.com/feed")
        self.assertEqual(out["task"]["project"], "test")
        self.assertEqual(res["status"], 200)
        self.assertEqual(base64.b64decode(res["body_b64"]), body)
        self.assertTrue(any(b["online"] and b["name"] == "pc-test"
                            for b in hub.status()))

    def test_submit_fara_bridge_status_0(self):
        hub = BridgeHub("s3cret")
        res = hub.submit("https://www.youtube.com", timeout=1)
        self.assertEqual(res["status"], 0)
        self.assertIn("error", res)

    def test_secret_gate(self):
        self.assertFalse(BridgeHub("").check_secret("ceva"))
        self.assertTrue(BridgeHub("abc").check_secret("abc"))
        self.assertFalse(BridgeHub("abc").check_secret("xyz"))


class TransportTest(unittest.TestCase):
    class _Hub(BridgeHub):
        def __init__(self, mapping):
            super().__init__("s")
            self.mapping = mapping
        def submit(self, url, method="GET", headers=None, body=None,
                   timeout=45, project="*"):
            return self.mapping

    def test_transport_ok(self):
        hub = self._Hub({"status": 200, "headers": {"H": "1"},
                         "body_b64": base64.b64encode(b"pagina").decode()})
        status, headers, text = hub.make_transport()("GET", "https://www.youtube.com", {}, None)
        self.assertEqual((status, text), (200, "pagina"))

    def test_transport_http_error(self):
        hub = self._Hub({"status": 403, "headers": {},
                         "body_b64": base64.b64encode(b"nay").decode()})
        with self.assertRaises(HttpError):
            hub.make_transport()("GET", "u", {}, None)

    def test_transport_connection_error(self):
        hub = self._Hub({"status": 0, "error": "niciun bridge"})
        with self.assertRaises(ConnectionError):
            hub.make_transport()("GET", "u", {}, None)


class ProxyLockTest(unittest.TestCase):
    def test_allowlist_default_youtube_google(self):
        from bridge.pc_bridge import host_allowed
        ok = ["https://www.youtube.com/feed",
              "https://youtubei.googleapis.com/youtubei/v1/browse",
              "https://i.ytimg.com/vi/x/hq.jpg",
              "https://yt3.ggpht.com/a"]
        nu = ["https://evil.com", "https://youtube.com.evil.ro/x",
              "https://www.youtube.com@evil.ro/", "nu-e-url", "",
              "https://evil-youtube.com/"]
        for u in ok:
            self.assertTrue(host_allowed(u), u)
        for u in nu:
            self.assertFalse(host_allowed(u), u)

    def test_allow_star_orice_public_dar_lan_blocat(self):
        from bridge.pc_bridge import make_checker
        ok = make_checker("*")
        self.assertTrue(ok.allow_all)
        for u in ["https://example.com/x", "https://api.github.com", "https://reddit.com/r/all"]:
            self.assertTrue(ok(u), u)
        # LAN/localhost NU se deblochează niciodată, nici cu *
        for u in ["http://127.0.0.1/", "http://localhost:8080", "http://192.168.1.1/",
                  "http://10.0.0.5", "http://172.16.0.1", "http://169.254.1.1", "http://[::1]/"]:
            self.assertFalse(ok(u), u)

    def test_allow_lista_custom_si_gol_revine_la_default(self):
        from bridge.pc_bridge import make_checker
        ok = make_checker("github.com, python.org")
        self.assertTrue(ok("https://api.github.com/x"))
        self.assertTrue(ok("https://python.org"))
        self.assertFalse(ok("https://www.youtube.com/"))
        default = make_checker("")
        self.assertTrue(default("https://www.youtube.com/"))
        self.assertFalse(default("https://example.com/"))


class AgentClientTest(unittest.TestCase):
    def test_parser_cautari(self):
        from bridge import agent_client
        fixture = '''
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexemplu.ro%2Fpagina&rut=ab12">Titlu <b>important</b></a>
        <a class="result__a" href="https://direct.com/y">Legatură directă</a>
        <a class="result__a" href="javascript:void(0)">fără link real</a>
        '''
        res = agent_client.extrage_rezultate_ddg(fixture.encode())
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0], {"titlu": "Titlu important",
                                  "url": "https://exemplu.ro/pagina"})
        self.assertEqual(res[1]["url"], "https://direct.com/y")


class PublisherBridgeTest(unittest.TestCase):
    class StubHub:
        enabled = True
        def __init__(self, tr, online=True):
            self.tr, self.online = tr, online
        def status(self):
            return [{"name": "PC-ACASA", "online": self.online}]
        def make_transport(self):
            return self.tr

    PAGE = ('ytcfg.set({"INNERTUBE_API_KEY":"K","LOGGED_IN":true,'
            '"INNERTUBE_CONTEXT":'
            '{"client":{"clientName":1,"clientVersion":"2.2024"}}}); '
            'pagina Community "createBackstagePostParams":"PP-1"')

    def _publisher(self):
        from postsyt.config import Config
        from postsyt.publisher import Publisher
        tmp = tempfile.mkdtemp()
        cfg = Config()
        cfg.data_dir = cfg.images_dir = tmp
        cfg.db_path = os.path.join(tmp, "t.db")
        cfg.bridge_secret = "s"
        cfg.publish_via_bridge = True
        cfg.cookies_file = os.path.join(tmp, "cookies.txt")
        cfg.cookies_json = os.path.join(tmp, "nope.json")
        with open(cfg.cookies_file, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n"
                    ".youtube.com\tTRUE\t/\tFALSE\t1999999999\tSAPISID\tv\n"
                    ".youtube.com\tTRUE\t/\tFALSE\t1999999999\tSID\tv\n")
        return Publisher(cfg, None, log=lambda *a, **k: None)

    def test_bridge_transport_used(self):
        calls = []
        def tr(method, url, headers, body):
            calls.append((method, url))
            if "create_post" in url:
                return 200, {}, '{"postId":"UGtest123"}'
            return 200, {}, self.PAGE
        pub = self._publisher()
        pub.set_hub(self.StubHub(tr))
        res = pub._post_text("Salut!", None, "innertube")
        self.assertTrue(res.ok, res.error)
        self.assertIn("+bridge", res.mode)
        self.assertEqual(res.post_id, "UGtest123")
        self.assertTrue(any("create_post" in u for _, u in calls))

    def test_bridge_offline_goes_direct(self):
        class FakeDirect:
            def create_text_or_image_post(self, text, img):
                return "pid_direct"
        pub = self._publisher()
        pub.set_hub(self.StubHub(lambda m, u, h, b: (_ for _ in ()).throw(AssertionError("nu bridge!")),
                                 online=False))
        pub._client = FakeDirect()
        res = pub._post_text("x", None, "innertube")
        self.assertTrue(res.ok)
        self.assertNotIn("bridge", res.mode)
        self.assertEqual(res.post_id, "pid_direct")

    def test_bridge_cade_fallback_direct(self):
        def boom(method, url, headers, body):
            raise ConnectionError("PC oprit brusc")
        class FakeDirect:
            def create_text_or_image_post(self, text, img):
                return "pid_fallback"
        pub = self._publisher()
        pub.set_hub(self.StubHub(boom))
        pub._client = FakeDirect()
        res = pub._post_text("x", None, "innertube")
        self.assertTrue(res.ok)
        self.assertIn("fallback", res.mode)
        self.assertEqual(res.post_id, "pid_fallback")


if __name__ == "__main__":
    unittest.main()
