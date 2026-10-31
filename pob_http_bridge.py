from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import time
import json

ROOT = os.environ.get("POB_AI_IPC_ROOT")
if not ROOT:
    raise SystemExit("Set POB_AI_IPC_ROOT (example: D:\\Dev\\pob\\pob1-ai-api\\src)")

INBOX = os.path.join(ROOT, "aiipc", "inbox")
OUTBOX = os.path.join(ROOT, "aiipc", "outbox")


def send_cmd(cmd, params=None, timeout=2.0):
    os.makedirs(INBOX, exist_ok=True)
    os.makedirs(OUTBOX, exist_ok=True)

    rid = str(int(time.time() * 1000))
    lines = [f"id={rid}", f"cmd={cmd}"]

    params = params or {}
    for k, v in params.items():
        lines.append(f"{k}={v}")

    req_path = os.path.join(INBOX, f"{rid}.req")
    with open(req_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    resp_path = os.path.join(OUTBOX, f"{rid}.resp")
    t0 = time.time()
    while (time.time() - t0) < timeout:
        if os.path.exists(resp_path):
            with open(resp_path, "r", encoding="utf-8") as f:
                txt = f.read()

            # try cleanup
            try:
                os.remove(resp_path)
            except Exception:
                pass

            body = ""
            for line in txt.splitlines():
                if line.startswith("body="):
                    body = line[len("body="):]
                    break

            return body or json.dumps({"ok": False, "error": "empty_body"})

        time.sleep(0.02)

    return json.dumps({"ok": False, "error": "timeout"})


class H(BaseHTTPRequestHandler):
    def _json(self, payload, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload.encode("utf-8"))

    def do_GET(self):
        if self.path.startswith("/health"):
            self._json(send_cmd("health", timeout=30.0))
            return

        if self.path.startswith("/debug/modes"):
            self._json(send_cmd("debug_modes", timeout=5.0))
            return

        if self.path.startswith("/debug/main_keys"):
            self._json(send_cmd("debug_main_keys", timeout=30.0))
            return

        # aliases (на будущее)
        if self.path.startswith("/state") or self.path.startswith("/debug/active_mode"):
            self._json(send_cmd("state", timeout=30.0))
            return

        self._json(json.dumps({"error": "not_found"}), 404)


if __name__ == "__main__":
    print("IPC ROOT =", ROOT)
    print("INBOX    =", INBOX)
    print("OUTBOX   =", OUTBOX)
    print("HTTP bridge on http://127.0.0.1:18080")
    HTTPServer(("127.0.0.1", 18080), H).serve_forever()
