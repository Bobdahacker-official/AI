"""Local chat UI and a JSON inference endpoint."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from .chat import Assistant


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--checkpoint", help="Defaults to the reviewed conversation checkpoint when present")
    parser.add_argument("--tokenizer", default="data/processed/tokenizer.json")
    args = parser.parse_args()
    assistant = Assistant(args.checkpoint, args.tokenizer)
    lock = threading.Lock()
    page = Path(__file__).with_name("chat.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def respond(self, code, body, content_type="application/json"):
            if isinstance(body, dict):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self.respond(200, page, "text/html; charset=utf-8")
            elif self.path == "/health":
                self.respond(200, {"model": "Astheral", "parameters": assistant.model.parameter_count, "checkpoint_step": assistant.step, "tokens_seen": assistant.tokens_seen, "validation_loss": assistant.validation_loss})
            else:
                self.respond(404, {"error": "Not found"})

        def do_POST(self):
            if self.path != "/chat":
                return self.respond(404, {"error": "Not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    return self.respond(413, {"error": "Body must be 1..65536 bytes"})
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict) or not isinstance(request.get("messages"), list):
                    raise ValueError("Expected a messages array")
                if not all(isinstance(message, dict) for message in request["messages"]):
                    raise ValueError("Each message must be an object")
                with lock:
                    result = assistant.reply(request["messages"], int(request.get("max_tokens", 64)), float(request.get("temperature", 0)))
                self.respond(200, result)
            except (ValueError, TypeError, KeyError) as error:
                self.respond(400, {"error": str(error)})

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(json.dumps({"event": "serving", "port": args.port, "step": assistant.step}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
