"""Open Cloud (cloud.py): only Discord members with Cloud view / Cloud edit (or the console) reach the files."""

import json
import secrets

import pytest
from app_helpers import app_client
from test_discord_preview import CONSOLE, DB_MEMBER, DB_ROLE, MEMBER, NO_ROLE, discord, login, settings  # noqa: F401 (fixture)

from backend import cloud

PERMS = "/api/admin/permissions"
VIEWER = "123456789012345670"  # in the fake server with only the Member role


def grant(client, permission, type_, id_):
    client.cookies.clear()
    login(client, MEMBER)  # console via the YAML role
    assert client.post(PERMS, json={"permission": permission, "type": type_, "id": id_}, headers=CONSOLE).status_code == 200
    client.cookies.clear()


def put(client, name, data: bytes, path="", chunk=None, overwrite=False):
    """Uploads like the page: chunks in order with one random id."""
    upload, chunk = secrets.token_hex(16), chunk or max(len(data), 1)
    r = None
    for offset in range(0, max(len(data), 1), chunk):
        r = client.post("/api/cloud/upload", params={"path": path, "name": name, "upload": upload, "offset": offset,
                                                     "total": len(data), "overwrite": overwrite},
                        content=data[offset:offset + chunk], headers=CONSOLE)
        if r.status_code != 200:
            return r
    return r


def test_cloud_needs_login_and_permission(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        assert client.get("/api/cloud/list").status_code == 401
        assert client.get("/api/cloud/download", params={"path": "x"}).status_code == 401
        login(client, NO_ROLE)
        assert client.get("/api/auth/me").json()["user"]["cloud"] is None
        assert client.get("/api/cloud/list").json()["error_code"] == "cloud_only"
        assert put(client, "a.txt", b"hi").status_code == 403

        client.cookies.clear()
        login(client, MEMBER)  # console users have Cloud edit
        assert client.get("/api/auth/me").json()["user"]["cloud"] == "edit"
        assert put(client, "a.txt", b"hi").json()["done"] is True
        assert "no-store" in client.get("/api/cloud/list").headers["cache-control"]


def test_view_downloads_only_edit_changes(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        grant(client, "cloud_view", "user", VIEWER)
        grant(client, "cloud_edit", "role", DB_ROLE)

        login(client, DB_MEMBER)  # edit by role
        assert client.get("/api/auth/me").json()["user"]["cloud"] == "edit"
        assert client.post("/api/cloud/folder", json={"path": "", "name": "Maps"}, headers=CONSOLE).status_code == 200
        assert put(client, "notes.html", b"<script>alert(1)</script>", path="Maps").json()["path"] == "Maps/notes.html"

        client.cookies.clear()
        login(client, VIEWER)  # view by user id
        listing = client.get("/api/cloud/list", params={"path": "Maps"}).json()
        assert listing["can_edit"] is False and [e["name"] for e in listing["entries"]] == ["notes.html"]
        r = client.get("/api/cloud/download", params={"path": "Maps/notes.html"})
        assert r.status_code == 200 and r.content == b"<script>alert(1)</script>"
        # never shown as a page on this site
        assert r.headers["content-type"] == "application/octet-stream"
        assert r.headers["content-disposition"].startswith("attachment")
        assert r.headers["content-security-policy"] == "sandbox"
        assert put(client, "b.txt", b"x").status_code == 403
        assert client.post("/api/cloud/delete", json={"path": "Maps/notes.html"}, headers=CONSOLE).status_code == 403
        assert client.post("/api/cloud/rename", json={"path": "Maps", "name": "X"}, headers=CONSOLE).status_code == 403


def test_writes_need_the_site_header(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        login(client, MEMBER)
        assert client.post("/api/cloud/folder", json={"name": "A"}).status_code == 405  # no X-EchoVR: another site's form
        assert client.post("/api/cloud/folder", json={"name": "A"}, headers=CONSOLE).status_code == 200


def test_chunked_upload_rename_delete(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        login(client, MEMBER)
        data = bytes(range(256)) * 40  # 10 KB in 3 KB chunks
        assert put(client, "big.bin", data, chunk=3000).json() == {"done": True, "received": len(data), "path": "big.bin", "scanning": False}
        assert client.get("/api/cloud/download", params={"path": "big.bin"}).content == data
        assert not list((tmp_path / "data" / "cloud-uploads").glob("*.part"))  # moved, not copied

        assert put(client, "big.bin", b"new").json()["error_code"] == "exists"
        assert put(client, "big.bin", b"new", overwrite=True).json()["done"] is True
        assert put(client, "empty.txt", b"").json()["done"] is True

        r = client.post("/api/cloud/rename", json={"path": "big.bin", "name": "small.bin"}, headers=CONSOLE)
        assert r.json() == {"path": "small.bin"}
        assert client.post("/api/cloud/rename", json={"path": "small.bin", "name": "empty.txt"}, headers=CONSOLE).json()["error_code"] == "exists"
        client.post("/api/cloud/folder", json={"name": "Dir"}, headers=CONSOLE)
        put(client, "in.txt", b"x", path="Dir")
        assert client.post("/api/cloud/delete", json={"path": "Dir"}, headers=CONSOLE).json() == {"ok": True}
        names = [e["name"] for e in client.get("/api/cloud/list").json()["entries"]]
        assert names == ["empty.txt", "small.bin"]


def test_upload_out_of_order_or_too_long_is_refused(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        login(client, MEMBER)
        upload = secrets.token_hex(16)
        base = {"name": "f.bin", "upload": upload, "total": 10}
        r = client.post("/api/cloud/upload", params=base | {"offset": 5}, content=b"12345", headers=CONSOLE)
        assert r.json()["error_code"] == "out_of_sync"
        r = client.post("/api/cloud/upload", params=base | {"offset": 0}, content=b"0123456789AB", headers=CONSOLE)
        assert r.json()["error_code"] == "bad_upload"
        assert client.get("/api/cloud/list").json()["entries"] == []

        # a chunk sent again after a dropped connection replaces its first (partial) try
        base = base | {"upload": secrets.token_hex(16)}
        assert client.post("/api/cloud/upload", params=base | {"offset": 0}, content=b"01234", headers=CONSOLE).json()["done"] is False
        assert client.post("/api/cloud/upload", params=base | {"offset": 5}, content=b"5", headers=CONSOLE).json()["done"] is False
        assert client.post("/api/cloud/upload", params=base | {"offset": 5}, content=b"56789", headers=CONSOLE).json()["done"] is True
        assert client.get("/api/cloud/download", params={"path": "f.bin"}).content == b"0123456789"
        r = client.post("/api/cloud/upload", params=base | {"upload": "../../x", "offset": 0}, content=b"1", headers=CONSOLE)
        assert r.json()["error_code"] == "bad_upload"


@pytest.mark.parametrize("path", ["..", "../data", "a/../../x", "/etc/passwd", "..\\..\\x", "a\x00b", "con"])
def test_paths_stay_inside_the_cloud_folder(tmp_path, discord, path):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "secret.txt").write_text("no")
    with app_client(settings(tmp_path)) as client:
        login(client, MEMBER)
        r = client.get("/api/cloud/download", params={"path": path})
        assert r.status_code in (400, 404) and r.content != b"no"
        assert client.get("/api/cloud/list", params={"path": path}).status_code in (400, 404)
        assert put(client, "x.txt", b"x", path=path).status_code in (400, 404)
        assert client.post("/api/cloud/delete", json={"path": path}, headers=CONSOLE).status_code in (400, 404)
    assert (tmp_path / "data" / "secret.txt").read_text() == "no"


def test_quota(tmp_path, discord):
    cloud._forget_usage()
    with app_client(settings(tmp_path, cloud_quota_gb=1000 / 1024**3)) as client:  # 1000 bytes
        login(client, MEMBER)
        assert put(client, "a.bin", b"x" * 800).json()["done"] is True
        r = put(client, "b.bin", b"x" * 300)
        assert r.status_code == 413 and r.json()["error_code"] == "quota"
        assert put(client, "a.bin", b"x" * 900, overwrite=True).json()["done"] is True  # replacing frees the old size
        client.post("/api/cloud/delete", json={"path": "a.bin"}, headers=CONSOLE)
        # in the recycle bin it still takes its space (delete-and-upload again cannot fill the disk) ...
        assert put(client, "b.bin", b"x" * 300).json()["error_code"] == "quota"
        assert client.get("/api/cloud/list").json()["trash_bytes"] == 900
        # ... until a console user removes it for good
        client.post("/api/cloud/trash/purge", json={"all": True}, headers=CONSOLE)
        assert put(client, "b.bin", b"x" * 300).json()["done"] is True

        # uploads still in progress reserve their full size: two half-sent 600-byte files cannot both fit in 700 left
        def start(name, upload):
            return client.post("/api/cloud/upload", params={"name": name, "upload": upload, "offset": 0, "total": 600},
                               content=b"x" * 100, headers=CONSOLE)
        first, second = secrets.token_hex(16), secrets.token_hex(16)
        assert start("c.bin", first).json()["done"] is False
        assert start("d.bin", second).json()["error_code"] == "quota"
        assert start("c.bin", first).json()["done"] is False  # the same upload started again does not count twice


def test_audit_log(tmp_path, discord):
    """Every change and download is logged with who did it; refusals of logged-in people too; console users read it."""
    with app_client(settings(tmp_path)) as client:
        grant(client, "cloud_view", "user", VIEWER)
        login(client, MEMBER)
        put(client, "a.txt", b"hello")
        put(client, "a.txt", b"hello again", overwrite=True)
        client.post("/api/cloud/folder", json={"name": "Dir"}, headers=CONSOLE)
        client.post("/api/cloud/rename", json={"path": "a.txt", "name": "b.txt"}, headers=CONSOLE)
        client.get("/api/cloud/download", params={"path": "b.txt"})
        client.get("/api/cloud/download", params={"path": "b.txt"}, headers={"Range": "bytes=5-"})  # a resume: not again
        client.post("/api/cloud/delete", json={"path": "b.txt"}, headers=CONSOLE)
        assert put(client, "../x", b"x").status_code == 400  # refused: logged

        client.cookies.clear()
        login(client, VIEWER)
        client.post("/api/cloud/delete", json={"path": "Dir"}, headers=CONSOLE)  # no Cloud edit: logged as denied
        assert client.get("/api/cloud/log").status_code == 403  # only console users read it

        client.cookies.clear()
        client.get("/api/cloud/list")  # anonymous: nothing to log
        login(client, MEMBER)
        rows = client.get("/api/cloud/log").json()
        BAD_NAME = next(r["detail"] for r in rows if r["path"] == "../x")
        assert BAD_NAME.startswith("Names cannot contain")
        got = [(r["who_id"], r["action"], r["path"], r["detail"], r["size"], r["ok"]) for r in reversed(rows)]
        assert got == [
            (MEMBER, "upload", "a.txt", None, 5, True),
            (MEMBER, "upload", "a.txt", "replaced", 11, True),
            (MEMBER, "folder", "Dir", None, None, True),
            (MEMBER, "rename", "a.txt", "b.txt", None, True),
            (MEMBER, "download", "b.txt", None, 11, True),
            (MEMBER, "delete", "b.txt", "to the recycle bin", 11, True),
            (MEMBER, "upload", "../x", BAD_NAME, 1, False),
            (VIEWER, "denied", "Dir", "delete: needs Cloud edit", None, False),
        ]
        assert all(r["ip"] and r["at"] for r in rows)
        assert [r["action"] for r in client.get("/api/cloud/log", params={"q": "denied"}).json()] == ["denied"]
        assert len(client.get("/api/cloud/log", params={"before": rows[1]["id"]}).json()) == len(rows) - 2


def test_upload_chunks_skip_the_rate_limit_when_logged_in(tmp_path, discord):
    """A big file is hundreds of chunk requests: a logged-in person is not cut off; anyone else is limited as usual."""
    s = settings(tmp_path, scraper_guard=True, rate_limit_per_min=5)
    browser = {"User-Agent": "Mozilla/5.0 Chrome/141", "X-EchoVR": "1"}
    with app_client(s) as client:
        client.headers.update(browser)
        login(client, MEMBER)
        data = b"x" * 300
        assert put(client, "many.bin", data, chunk=10).json()["done"] is True  # 30 chunks, limit 5/min (burst 10)
        codes = [client.get("/api/cloud/list").status_code for _ in range(15)]
        assert 429 in codes  # other requests still count
        client.cookies.clear()
        codes = [put(client, f"{i}.bin", b"x").status_code for i in range(15)]
        assert 429 in codes  # anonymous chunks are limited


def test_folder_uploads_make_their_folders(tmp_path, discord):
    """User, 2026-11-10: whole folders at once. A file of a folder tree makes its missing folders; checks stay the same."""
    with app_client(settings(tmp_path)) as client:
        login(client, MEMBER)

        def up(path, name, data=b"x", folders=True):
            return client.post("/api/cloud/upload", params={"path": path, "name": name, "upload": secrets.token_hex(16),
                                                            "offset": 0, "total": len(data), "folders": folders},
                               content=data, headers=CONSOLE)

        assert up("Photos/2026/Nov", "a.jpg").json()["path"] == "Photos/2026/Nov/a.jpg"
        assert up("Photos/2026", "b.jpg").json()["done"] is True  # an existing folder: fine
        assert up("Other/x", "c.jpg", folders=False).status_code == 404  # without the option: the folder must exist
        assert up("Photos/2026/Nov/a.jpg/deeper", "d.jpg").json()["error_code"] == "exists"  # a file is in the way
        assert up("/".join(["d"] * 33), "e.jpg").json()["error_code"] == "bad_path"  # 32 deep at most
        assert up("Photos/../../escape", "f.jpg").status_code == 400  # every part still checked
        r = client.post("/api/cloud/folder", json={"path": "Empty/Inside", "name": "Leaf", "parents": True}, headers=CONSOLE)
        assert r.json() == {"path": "Empty/Inside/Leaf"}  # an empty folder of a dropped tree
        names = lambda p: [e["name"] for e in client.get("/api/cloud/list", params={"path": p}).json()["entries"]]
        assert names("") == ["Empty", "Photos"] and names("Photos/2026") == ["Nov", "b.jpg"]
        assert not (tmp_path / "escape").exists()


def test_an_interrupted_upload_resumes_where_it_stopped(tmp_path, discord):
    """User, 2026-11-10: the page asks how much the server has, then sends only the rest (same upload id)."""
    with app_client(settings(tmp_path)) as client:
        login(client, MEMBER)
        data = bytes(range(256)) * 100  # 25,600 bytes
        upload = secrets.token_hex(16)
        status = lambda: client.get("/api/cloud/upload/status", params={"upload": upload, "total": len(data)}, headers=CONSOLE).json()
        assert status() == {"received": 0}
        base = {"name": "resume.bin", "upload": upload, "total": len(data)}
        client.post("/api/cloud/upload", params=base | {"offset": 0}, content=data[:10_000], headers=CONSOLE)
        assert status() == {"received": 10_000}  # the connection dropped here; later the page asks
        r = client.post("/api/cloud/upload", params=base | {"offset": 10_000}, content=data[10_000:], headers=CONSOLE)
        assert r.json()["done"] is True
        assert client.get("/api/cloud/download", params={"path": "resume.bin"}).content == data
        assert status() == {"received": 0}  # finished: nothing left to resume

        client.cookies.clear()
        login(client, NO_ROLE)  # only the person's own uploads, and only with Cloud edit
        assert client.get("/api/cloud/upload/status", params={"upload": upload, "total": 1}, headers=CONSOLE).status_code == 403


def test_recycle_bin(tmp_path, discord):
    """User, 2026-11-10: Delete moves to a recycle bin; a console user restores it easily, or removes it for good."""
    with app_client(settings(tmp_path)) as client:
        grant(client, "cloud_edit", "role", DB_ROLE)
        login(client, DB_MEMBER)  # Cloud edit, not console
        client.post("/api/cloud/folder", json={"name": "Docs"}, headers=CONSOLE)
        put(client, "report.pdf", b"v1", path="Docs")
        put(client, "notes.txt", b"n", path="Docs")
        assert client.post("/api/cloud/delete", json={"path": "Docs/report.pdf"}, headers=CONSOLE).json() == {"ok": True}
        assert client.post("/api/cloud/delete", json={"path": "Docs"}, headers=CONSOLE).json() == {"ok": True}  # the folder too
        assert client.get("/api/cloud/list").json()["entries"] == []
        assert client.get("/api/cloud/trash").status_code == 403  # an editor cannot see or restore: console users only
        assert client.post("/api/cloud/trash/restore", json={"id": "x"}, headers=CONSOLE).status_code == 403

        client.cookies.clear()
        login(client, MEMBER)  # console
        trash = client.get("/api/cloud/trash").json()
        assert trash["days"] == 30 and trash["bytes"] == 3
        items = {i["path"]: i for i in trash["items"]}
        assert set(items) == {"Docs/report.pdf", "Docs"}
        assert items["Docs"]["dir"] is True and items["Docs/report.pdf"]["by_id"] == DB_MEMBER
        assert items["Docs/report.pdf"]["expires_at"] - items["Docs/report.pdf"]["deleted_at"] == 30 * 86400

        # the file comes back where it was, its folder made again (the folder itself is still in the bin)
        r = client.post("/api/cloud/trash/restore", json={"id": items["Docs/report.pdf"]["id"]}, headers=CONSOLE).json()
        assert r["path"] == "Docs/report.pdf"
        assert client.get("/api/cloud/download", params={"path": "Docs/report.pdf"}).content == b"v1"
        # the folder: "Docs" exists again now, so it comes back beside it under a new name, nothing overwritten
        r = client.post("/api/cloud/trash/restore", json={"id": items["Docs"]["id"]}, headers=CONSOLE).json()
        assert r["path"].startswith("Docs (restored ") and r["path"] != "Docs"
        assert [e["name"] for e in client.get("/api/cloud/list", params={"path": r["path"]}).json()["entries"]] == ["notes.txt"]
        assert client.post("/api/cloud/trash/restore", json={"id": items["Docs"]["id"]}, headers=CONSOLE).status_code == 404
        assert client.post("/api/cloud/trash/restore", json={"id": "../../etc"}, headers=CONSOLE).status_code == 400

        # removed for good: one item, or the whole bin
        put(client, "a.txt", b"a"); put(client, "b.txt", b"b")
        client.post("/api/cloud/delete", json={"path": "a.txt"}, headers=CONSOLE)
        client.post("/api/cloud/delete", json={"path": "b.txt"}, headers=CONSOLE)
        first = client.get("/api/cloud/trash").json()["items"][0]["id"]
        assert client.post("/api/cloud/trash/purge", json={"id": first}, headers=CONSOLE).json()["size"] == 1
        assert client.post("/api/cloud/trash/purge", json={"all": True}, headers=CONSOLE).json() == {"count": 1, "size": 1}
        assert client.get("/api/cloud/trash").json()["items"] == []
        log = client.get("/api/cloud/log").json()
        done = [r["action"] for r in log if r["ok"]]
        assert done.count("restore") == 2 and done.count("purge") == 2
        assert [r["action"] for r in log if not r["ok"]].count("restore") == 2  # the refused tries are logged too


def test_recycle_bin_items_go_after_the_days_set(tmp_path, discord):
    with app_client(settings(tmp_path, cloud_trash_days=30)) as client:
        login(client, MEMBER)
        put(client, "old.txt", b"o")
        client.post("/api/cloud/delete", json={"path": "old.txt"}, headers=CONSOLE)
        box = next((tmp_path / "data" / "cloud-trash").iterdir())
        info = json.loads((box / "info.json").read_text())
        (box / "info.json").write_text(json.dumps(info | {"deleted_at": info["deleted_at"] - 31 * 86400}))
        assert client.get("/api/cloud/trash").json()["items"] == []  # older than 30 days: gone for good
        assert not box.exists()


def test_a_link_planted_on_the_nas_is_never_followed(tmp_path, discord):
    import os
    (tmp_path / "data" / "cloud").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "secret.txt").write_text("no")
    try:
        os.symlink(tmp_path / "data", tmp_path / "data" / "cloud" / "out", target_is_directory=True)
    except OSError:
        pytest.skip("this system needs admin rights for links (Windows); runs on Linux, like the NAS")
    with app_client(settings(tmp_path)) as client:
        login(client, MEMBER)
        assert client.get("/api/cloud/download", params={"path": "out/secret.txt"}).status_code == 400
        assert client.get("/api/cloud/list", params={"path": "out"}).status_code == 400
        assert put(client, "x.txt", b"x", path="out").status_code == 400
