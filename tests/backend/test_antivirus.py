"""Virus scanning of cloud uploads (user, 2026-11-10): ClamAV before a file can be downloaded, VirusTotal fingerprint check
after. ClamAV is faked by a small server speaking clamd's TCP protocol; the "virus" is a marker (the real EICAR test file
would be quarantined by the PC's own antivirus and make the test flaky)."""

import hashlib
import secrets
import socketserver
import threading
import time

import httpx
import pytest
from app_helpers import app_client
from test_cloud import grant, put
from test_discord_preview import CONSOLE, DB_MEMBER, DB_ROLE, MEMBER, discord, login, settings  # noqa: F401 (fixture)

from backend import antivirus

MARK = b"FAKE-VIRUS-MARKER"


class FakeClamd(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), self.Handler)
        self.scanned: list[str] = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            data = b""
            while not data.endswith(b"\0"):
                part = self.request.recv(4096)
                if not part:
                    return
                data += part
            cmd = data[1:-1].decode()
            if cmd == "PING":
                answer = "PONG"
            elif cmd == "VERSION":
                answer = "ClamAV 1.4.3/27455/Mon Nov 10 08:00:00 2026"
            elif cmd.startswith("SCAN "):
                path = cmd[5:]
                self.server.scanned.append(path)
                try:
                    content = open(path, "rb").read()
                    answer = f"{path}: Test.Fake.Virus FOUND" if MARK in content else f"{path}: OK"
                except OSError as e:
                    answer = f"{path}: {e} ERROR"
            else:
                answer = "UNKNOWN COMMAND"
            self.request.sendall(answer.encode() + b"\0")


@pytest.fixture
def clamd():
    server = FakeClamd()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def av_settings(tmp_path, clamd, **kw):
    return settings(tmp_path, clamav_address=f"127.0.0.1:{clamd.server_address[1]}", **kw)


def wait_for(check, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.05)
    return False


def names(client, path=""):
    return {(e["name"], e.get("state")) for e in client.get("/api/cloud/list", params={"path": path}).json()["entries"]}


def test_a_clean_upload_is_held_until_scanned_then_downloadable(tmp_path, discord, clamd, monkeypatch):
    with app_client(av_settings(tmp_path, clamd)) as client:
        login(client, MEMBER)
        scanner = client.app.state.antivirus
        monkeypatch.setattr(scanner, "notify", lambda: None)  # hold the scan to see the waiting state
        r = put(client, "report.pdf", b"clean data")
        assert r.json()["scanning"] is True
        assert names(client) == {("report.pdf", "scanning")}  # listed as checking ...
        r = client.get("/api/cloud/download", params={"path": "report.pdf"})
        assert r.status_code == 409 and "being checked for viruses" in r.json()["message"]  # ... not downloadable
        scanner.wake.set()
        assert wait_for(lambda: names(client) == {("report.pdf", None)})
        assert client.get("/api/cloud/download", params={"path": "report.pdf"}).content == b"clean data"
        assert clamd.scanned and clamd.scanned[0].endswith("item")  # scanned in the waiting area, by path (no bytes sent)
        log = [r for r in reversed(client.get("/api/cloud/log").json()) if r["ok"]]
        assert [r["action"] for r in log] == ["upload", "scan", "download"]
        assert log[0]["detail"] == "checking for viruses" and log[1]["detail"] == "no virus found"


def test_a_virus_goes_to_the_quarantine_console_users_decide(tmp_path, discord, clamd):
    with app_client(av_settings(tmp_path, clamd)) as client:
        grant(client, "cloud_edit", "role", DB_ROLE)
        login(client, DB_MEMBER)  # Cloud edit, not console
        put(client, "game.zip", b"zip " + MARK)
        assert wait_for(lambda: antivirus.pending_count(client.app.state.settings) == 0)
        assert names(client) == set()  # never reached the cloud
        assert client.get("/api/cloud/quarantine").status_code == 403  # console users only

        client.cookies.clear()
        login(client, MEMBER)  # console
        q = client.get("/api/cloud/quarantine").json()
        assert q["scanner"]["reachable"] is True and q["scanner"]["version"].startswith("ClamAV")
        [item] = q["items"]
        assert item["path"] == "game.zip" and item["virus"] == "Test.Fake.Virus" and item["by_id"] == DB_MEMBER
        log = client.get("/api/cloud/log").json()
        virus = next(r for r in log if r["action"] == "virus")
        assert virus["ok"] is False and virus["detail"] == "Test.Fake.Virus" and virus["who_id"] == DB_MEMBER
        assert any(r["action"] == "denied" and "console only" in r["detail"] for r in log)  # the editor's try is logged

        # a false alarm: released into the cloud by a console user (logged)
        assert client.post("/api/cloud/quarantine/release", json={"id": item["id"]}, headers=CONSOLE).json()["path"] == "game.zip"
        assert names(client) == {("game.zip", None)}
        assert client.get("/api/cloud/log").json()[0]["action"] == "release"
        # another one deleted from the quarantine: its space is freed
        put(client, "bad.exe", MARK)
        assert wait_for(lambda: client.get("/api/cloud/quarantine").json()["items"])
        qid = client.get("/api/cloud/quarantine").json()["items"][0]["id"]
        assert client.post("/api/cloud/quarantine/delete", json={"id": qid}, headers=CONSOLE).json()["virus"] == "Test.Fake.Virus"
        assert client.get("/api/cloud/quarantine").json()["items"] == []


def test_files_wait_while_the_scanner_is_down(tmp_path, discord, clamd, monkeypatch):
    monkeypatch.setattr(antivirus, "RETRY_S", 0.2)
    port = clamd.server_address[1]
    clamd.shutdown()
    clamd.server_close()  # ClamAV not running (yet)
    with app_client(settings(tmp_path, clamav_address=f"127.0.0.1:{port}")) as client:
        login(client, MEMBER)
        put(client, "notes.txt", b"hello")
        time.sleep(0.6)
        assert names(client) == {("notes.txt", "scanning")}  # waits, never let through unscanned
        assert client.get("/api/cloud/quarantine").json()["scanner"]["reachable"] is False

        server = FakeClamd.__new__(FakeClamd)  # ClamAV comes up on the same port
        socketserver.ThreadingTCPServer.__init__(server, ("127.0.0.1", port), FakeClamd.Handler)
        server.scanned = []
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            assert wait_for(lambda: names(client) == {("notes.txt", None)})
        finally:
            server.shutdown()
            server.server_close()


def test_a_replaced_file_stays_available_until_the_new_one_is_clean(tmp_path, discord, clamd, monkeypatch):
    with app_client(av_settings(tmp_path, clamd)) as client:
        login(client, MEMBER)
        put(client, "doc.txt", b"version 1")
        assert wait_for(lambda: names(client) == {("doc.txt", None)})
        scanner = client.app.state.antivirus
        monkeypatch.setattr(scanner, "notify", lambda: None)
        put(client, "doc.txt", b"version 2", overwrite=True)
        assert names(client) == {("doc.txt", None), ("doc.txt", "scanning")}
        assert client.get("/api/cloud/download", params={"path": "doc.txt"}).content == b"version 1"
        scanner.wake.set()
        assert wait_for(lambda: client.get("/api/cloud/download", params={"path": "doc.txt"}).content == b"version 2")
        assert names(client) == {("doc.txt", None)}


def test_files_over_the_scan_limit_are_labelled_not_scanned(tmp_path, discord, clamd):
    with app_client(av_settings(tmp_path, clamd, clamav_max_mb=0)) as client:  # every file is "too big"
        login(client, MEMBER)
        r = put(client, "movie.mkv", b"x" * 1000)
        assert r.json()["scanning"] is False
        assert names(client) == {("movie.mkv", "unscanned")}  # downloadable, never called clean
        assert client.get("/api/cloud/download", params={"path": "movie.mkv"}).status_code == 200
        assert not clamd.scanned


def test_scan_all_existing_files(tmp_path, discord, clamd):
    with app_client(av_settings(tmp_path, clamd)) as client:
        login(client, MEMBER)
        cloud_dir = tmp_path / "data" / "cloud" / "old"
        cloud_dir.mkdir(parents=True)
        (cloud_dir / "fine.txt").write_bytes(b"fine")
        (cloud_dir / "worm.bin").write_bytes(MARK)  # put there before scanning existed
        assert client.post("/api/cloud/scan-all", headers=CONSOLE).json() == {"queued": 2}
        assert wait_for(lambda: not client.get("/api/cloud/quarantine").json()["sweep"]["running"])
        assert names(client, "old") == {("fine.txt", None)}
        [item] = client.get("/api/cloud/quarantine").json()["items"]
        assert item["path"] == "old/worm.bin" and item["by_name"] == "(already in the cloud)"


def test_virustotal_fingerprint_check(tmp_path, discord, monkeypatch):
    """Only the SHA-256 is sent; enough engines -> quarantined; unknown to VirusTotal -> stays."""
    monkeypatch.setattr(antivirus, "VT_SPACING_S", 0.0)
    asked = []
    bad = hashlib.sha256(b"known malware").hexdigest()

    def handle(request: httpx.Request) -> httpx.Response:
        digest = request.url.path.rsplit("/", 1)[1]
        asked.append((digest, request.headers.get("x-apikey")))
        if digest == bad:
            return httpx.Response(200, json={"data": {"attributes": {
                "last_analysis_stats": {"malicious": 12, "undetected": 58, "harmless": 0},
                "last_analysis_results": {"E1": {"category": "malicious", "result": "Trojan.Gen"}}}}})
        return httpx.Response(404, json={"error": {"code": "NotFoundError"}})

    monkeypatch.setattr(antivirus, "vt_client", lambda: httpx.Client(transport=httpx.MockTransport(handle)))
    with app_client(settings(tmp_path, virustotal_key="test-key")) as client:
        login(client, MEMBER)
        put(client, "tool.exe", b"known malware")
        put(client, "photo.jpg", b"my own photo")
        vt = client.app.state.virustotal
        assert wait_for(lambda: vt.checked == 2)
        assert {d for d, _ in asked} == {bad, hashlib.sha256(b"my own photo").hexdigest()}  # fingerprints only
        assert all(k == "test-key" for _, k in asked)
        assert names(client) == {("photo.jpg", None)}  # unknown to VirusTotal: stays
        [item] = client.get("/api/cloud/quarantine").json()["items"]
        assert item["path"] == "tool.exe" and item["virus"] == "VirusTotal: 12 of 70 engines (Trojan.Gen)"
        assert vt.status()["found"] == 1 and vt.status()["unknown"] == 1


def test_virustotal_bad_key_stops_lookups(tmp_path, discord, monkeypatch):
    monkeypatch.setattr(antivirus, "VT_SPACING_S", 0.0)
    calls = []
    monkeypatch.setattr(antivirus, "vt_client", lambda: httpx.Client(transport=httpx.MockTransport(
        lambda r: (calls.append(1), httpx.Response(401))[1])))
    with app_client(settings(tmp_path, virustotal_key="wrong")) as client:
        login(client, MEMBER)
        put(client, "a.txt", b"a")
        assert wait_for(lambda: client.app.state.virustotal.bad_key)
        put(client, "b.txt", b"b")
        time.sleep(0.3)
        assert len(calls) == 1  # no more lookups with a refused key
        assert "refused the API key" in client.get("/api/cloud/quarantine").json()["virustotal"]["error"]


def test_no_scanning_configured_changes_nothing(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        login(client, MEMBER)
        assert put(client, "a.txt", b"a").json()["scanning"] is False
        assert names(client) == {("a.txt", None)}
        q = client.get("/api/cloud/quarantine").json()
        assert q["scanner"] == {"enabled": False} and q["virustotal"] == {"enabled": False}
        assert client.post("/api/cloud/scan-all", headers=CONSOLE).status_code == 409


def test_many_uploads_finishing_at_once_all_land_inside_the_cloud(tmp_path, discord, clamd):
    """A waiting box seen half-built once sent a file next to the cloud folder: boxes now appear complete or not at all."""
    import concurrent.futures as cf

    with app_client(av_settings(tmp_path, clamd)) as client:
        login(client, MEMBER)
        client.post("/api/cloud/folder", json={"name": "batch"}, headers=CONSOLE)

        def one(i):
            return put(client, f"f{i}.txt", b"x" * (i + 1), path="batch").status_code
        with cf.ThreadPoolExecutor(8) as pool:
            assert set(pool.map(one, range(20))) == {200}
        assert wait_for(lambda: len(names(client, "batch")) == 20 and all(s is None for _, s in names(client, "batch")), 30)
        known = {"cloud", "cloud-pending", "cloud-quarantine", "cloud-trash", "cloud-uploads"}
        assert {p.name for p in (tmp_path / "data").iterdir() if p.name.startswith("cloud")} <= known  # nothing beside it
        assert client.get("/api/cloud/quarantine").json()["items"] == []
