import json, os, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
SEQ = 4206
def cas(n):
    return f"CAS {n}/10/2026"
REPORTS = [{
    "id": "KZN-4206", "cas": cas(4206), "label": "Armed robbery", "pri": "alpha",
    "cluster": "Durban Central", "name": "Thandi Mkhize", "mobile": "076 272 3701",
    "address": "14 Oak Street, Berea, Durban", "named": True,
    "note": "Two men at the gate. She cannot speak freely.", "status": "waiting",
    "desk": "saps", "log": [], "face": "/static/face.jpg", "at": time.time()-40,
    "crime": "Armed robbery", "call": "incoming", "transcript": "", "kind": "case", "officer": ""
}]
TIPS = [{
    "id": "TIP-4205", "cas": "TIP 4205/10/2026", "label": "Suspicious vehicle", "cluster": "Inanda",
    "address": "KwaMashu Highway", "named": False, "note": "Anonymous tip. Name not stored.",
    "status": "waiting", "desk": "headoffice", "log": ["Tip received. Not a case."], "kind": "tip", "verified": False
}]
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript", ".png": "image/png", ".jpg": "image/jpeg", ".mp3": "audio/mpeg"}
class App(BaseHTTPRequestHandler):
    def log_message(self, *a):
        return
    def send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        pages = {"/": "citizen.html", "/citizen": "citizen.html", "/desk": "desk.html", "/commissioner": "commissioner.html", "/headoffice": "headoffice.html", "/brief": "brief.html", "/municipality": "municipality.html", "/weather": "weather.html"}
        if path in pages:
            return self.send(200, (ROOT / pages[path]).read_text())
        doors = {"/flying", "/cluster", "/station", "/fcs", "/hold", "/ems", "/durban", "/umlazi", "/chatsworth", "/pmb", "/richards"}
        if path in doors:
            page = (ROOT / "portal.html").read_text().replace('get("desk") || location.pathname.replace("/", "")', 'get("desk") || "' + path[1:] + '"')
            return self.send(200, page)
        if path == "/api/reports":
            return self.send(200, json.dumps(REPORTS + TIPS), "application/json")
        if path.startswith("/static/"):
            file = STATIC / path.split("/static/", 1)[1]
            if not file.exists():
                return self.send(404, "missing", "text/plain")
            return self.send(200, file.read_bytes(), TYPES.get(file.suffix, "application/octet-stream"))
        return self.send(404, "missing", "text/plain")
    def do_POST(self):
        global SEQ
        path = self.path.split("?", 1)[0]
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        data = json.loads(raw.decode() or "{}")
        if path == "/api/reports":
            SEQ += 1
            anonymous = data.get("kind") == "tip" or not data.get("named") and data.get("label", "").lower().startswith("anon")
            if data.get("kind") == "tip":
                item = {"id": f"TIP-{SEQ}", "cas": f"TIP {SEQ}/10/2026", "label": data.get("label", "Tip"), "pri": "bravo", "cluster": data.get("cluster", "Durban Central"), "name": "", "mobile": "", "address": data.get("address", ""), "named": False, "note": data.get("note", "Anonymous tip. Name not stored."), "status": "waiting", "desk": "headoffice", "log": ["Tip received. Not a case."], "face": "", "at": time.time(), "crime": data.get("label", "Tip"), "call": "", "transcript": "", "kind": "tip", "verified": False}
                TIPS.insert(0, item)
            elif data.get("kind") == "area":
                item = {"id": f"MUN-{SEQ}", "cas": f"MUN {SEQ}/10/2026", "label": data.get("label", "Unsafe area"), "pri": "info", "cluster": data.get("cluster", "Durban Central"), "name": "", "mobile": "", "address": data.get("address", ""), "named": False, "note": data.get("note", "Unsafe area. For the municipality."), "status": "waiting", "desk": "municipality", "log": ["Unsafe area. Share with the municipality."], "face": "", "at": time.time(), "crime": data.get("label", "Unsafe area"), "call": "", "transcript": "", "kind": "area"}
                REPORTS.insert(0, item)
            else:
                item = {"id": f"KZN-{SEQ}", "cas": cas(SEQ), "label": data.get("label", "Emergency"), "pri": "alpha", "cluster": data.get("cluster", "Durban Central"), "name": data.get("name", ""), "mobile": data.get("mobile", ""), "address": data.get("address", ""), "named": bool(data.get("named")), "note": data.get("note", ""), "status": "waiting", "desk": "saps", "log": ["File opened."], "face": "/static/face.jpg" if data.get("named") else "", "at": time.time(), "crime": data.get("label", "Emergency"), "call": data.get("call", ""), "transcript": "", "kind": "case", "officer": ""}
                REPORTS.insert(0, item)
            return self.send(200, json.dumps(item), "application/json")
        if path.startswith("/api/route/"):
            rid = path.split("/api/route/", 1)[1]
            for item in REPORTS + TIPS:
                if item["id"] == rid:
                    if data.get("officer"):
                        item["officer"] = data["officer"]
                    if data.get("verified"):
                        item["verified"] = True
                        item["log"].append("Verified by head office.")
                    if data.get("desk"):
                        item["desk"] = data["desk"]
                        item["status"] = "referred"
                    if data.get("call"):
                        item["call"] = data["call"]
                    if data.get("transcript") is not None:
                        item["transcript"] = data["transcript"]
                    if data.get("log"):
                        item["log"].append(data["log"])
            return self.send(200, b"ok", "text/plain")
        return self.send(404, "missing", "text/plain")
if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), App).serve_forever()
