import http.server
import json
from pathlib import Path
import threading
import unittest
from lab_tools import authorize, connectivity, headers

class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.scope = {"authorization_confirmed":True, "targets":["127.0.0.1","::1","8.8.8.8","10.0.0.1"], "ports":[8000]}

    def test_public_private_and_hostnames_blocked(self):
        for host in ["8.8.8.8","10.0.0.1","169.254.169.254","localhost","127.0.0.1.example.org","2130706433","::ffff:8.8.8.8"]:
            with self.subTest(host=host), self.assertRaises(ValueError):
                authorize(self.scope,host,[8000])

    def test_scope_and_authorization(self):
        for scope, host, ports in [({},"127.0.0.1",[8000]),(self.scope,"127.0.0.2",[8000]),
            (self.scope,"127.0.0.1",[22]), (self.scope,"127.0.0.1",[8000]*9),
            (self.scope,"127.0.0.1",[]), (self.scope,"127.0.0.1",[True])]:
            with self.assertRaises(ValueError):
                authorize(scope,host,ports)

    def test_allowed_loopback(self):
        self.assertTrue(authorize(self.scope,"127.0.0.1",[8000]).is_loopback)
        self.assertTrue(authorize(self.scope,"::1",[8000]).is_loopback)

    def test_local_http_and_no_redirect(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_HEAD(self):
                self.send_response(302)
                self.send_header("Location","http://192.0.2.1/")
                self.end_headers()
            def log_message(self,*args):
                pass
        server = http.server.HTTPServer(("127.0.0.1",0),Handler)
        port = server.server_address[1]
        scope = {"authorization_confirmed":True,"targets":["127.0.0.1"],"ports":[port]}
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            self.assertTrue(connectivity(scope,"127.0.0.1",[port])[0]["open"])
            result = headers(scope,"127.0.0.1",port)
            self.assertEqual(result["status"],302)
            self.assertFalse(result["redirects_followed"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_dataset_separation(self):
        root = Path(__file__).resolve().parent / "data"
        train = [json.loads(s) for s in (root/"train.jsonl").read_text(encoding="utf-8").splitlines()]
        evaluation = [json.loads(s) for s in (root/"eval.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len({r["prompt"] for r in train}),len(train))
        self.assertFalse({r["prompt"] for r in train} & {r["prompt"] for r in evaluation})

if __name__ == "__main__":
    unittest.main()
