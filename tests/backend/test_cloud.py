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
        login(client, MEMBER)  # console users have everything (Cloud admin)
        assert client.get("/api/auth/me").json()["user"]["cloud"] == "admin"
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


# --- permissions of one folder or file (cloud_acl.py; user, 2026-11-16) ------------------------------------------------

RULES = "/api/cloud/permissions"
SOMEONE = "470000000000000047"  # in the fake server, no permission anywhere


def rule(client, path, private=False, grants=()):
    """Set as the console user, then log out again."""
    client.cookies.clear()
    login(client, MEMBER)
    r = client.post(RULES, json={"path": path, "private": private,
                                 "grants": [{"type": t, "id": i, "level": lv} for t, i, lv in grants]}, headers=CONSOLE)
    client.cookies.clear()
    return r


def names(client, path=""):
    return [e["name"] for e in client.get("/api/cloud/list", params={"path": path}).json()["entries"]]


def tree(client):
    """Console user: Team/plan.txt, Team/Deep/inner.txt, Secret/key.txt, open.txt."""
    login(client, MEMBER)
    for folder, name in (("", "Team"), ("Team", "Deep"), ("", "Secret")):
        assert client.post("/api/cloud/folder", json={"path": folder, "name": name}, headers=CONSOLE).status_code == 200
    for folder, name in (("Team", "plan.txt"), ("Team/Deep", "inner.txt"), ("Secret", "key.txt"), ("", "open.txt")):
        assert put(client, name, name.encode(), path=folder).json()["done"] is True
    client.cookies.clear()


def test_a_folder_shared_with_someone_without_cloud_access(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        tree(client)
        login(client, NO_ROLE)
        assert client.get("/api/auth/me").json()["user"]["cloud"] is None
        assert rule(client, "Team/Deep", grants=[("user", NO_ROLE, "view")]).status_code == 200

        login(client, NO_ROLE)
        assert client.get("/api/auth/me").json()["user"]["cloud"] == "view"  # the Cloud tab shows
        top = client.get("/api/cloud/list").json()
        assert [e["name"] for e in top["entries"]] == ["Team"] and top["limited"] is True and top["can_edit"] is False
        assert names(client, "Team") == ["Deep"]  # the way there, nothing else in it
        assert names(client, "Team/Deep") == ["inner.txt"]
        assert client.get("/api/cloud/download", params={"path": "Team/Deep/inner.txt"}).content == b"inner.txt"
        for hidden in ("Team/plan.txt", "open.txt", "Secret/key.txt"):
            assert client.get("/api/cloud/download", params={"path": hidden}).status_code == 403
        assert client.get("/api/cloud/list", params={"path": "Secret"}).status_code == 403
        assert put(client, "new.txt", b"x", path="Team/Deep").status_code == 403  # view only

        # edit, by role this time: upload, rename and delete inside the shared folder, nowhere else
        assert rule(client, "Team/Deep", grants=[("role", DB_ROLE, "edit")]).status_code == 200
        login(client, DB_MEMBER)
        assert client.get("/api/auth/me").json()["user"]["cloud"] == "edit"
        assert put(client, "new.txt", b"x", path="Team/Deep").json()["done"] is True
        assert put(client, "new.txt", b"x", path="Team").status_code == 403
        r = client.post("/api/cloud/rename", json={"path": "Team/Deep/new.txt", "name": "newer.txt"}, headers=CONSOLE)
        assert r.json() == {"path": "Team/Deep/newer.txt"}
        assert client.post("/api/cloud/delete", json={"path": "Team/Deep/newer.txt"}, headers=CONSOLE).status_code == 200
        assert client.post("/api/cloud/delete", json={"path": "Team"}, headers=CONSOLE).status_code == 403
        assert client.get(RULES, params={"path": "Team/Deep"}).status_code == 403  # console users only
        assert client.post(RULES, json={"path": "Team", "grants": [{"type": "user", "id": NO_ROLE, "level": "edit"}]},
                           headers=CONSOLE).status_code == 403


def test_permissions_are_set_on_folders_only(tmp_path, discord):
    """User, 2026-11-16: a file has no permissions of its own, it follows its folder."""
    with app_client(settings(tmp_path)) as client:
        tree(client)
        r = rule(client, "Team/plan.txt", grants=[("user", NO_ROLE, "view")])
        assert r.status_code == 400 and r.json()["error_code"] == "folders_only"
        login(client, MEMBER)
        assert client.get(RULES, params={"path": "open.txt"}).json()["error_code"] == "folders_only"
        assert client.get(f"{RULES}/all").json()["rules"] == []
        rows = {e["name"]: e.get("can_manage") for e in client.get("/api/cloud/list").json()["entries"]}
        assert rows == {"Secret": True, "Team": True, "open.txt": None}  # no Permissions link on a file


def test_a_private_folder_is_hidden_from_everyone_not_listed(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        tree(client)
        grant(client, "cloud_edit", "role", DB_ROLE)
        grant(client, "cloud_view", "user", VIEWER)
        assert rule(client, "Secret", private=True, grants=[("user", VIEWER, "view")]).status_code == 200

        login(client, DB_MEMBER)  # Cloud edit on the whole cloud, not listed
        assert names(client) == ["Team", "open.txt"]
        assert client.get("/api/cloud/list", params={"path": "Secret"}).status_code == 403
        # another spelling of the same path is the same path
        for spelling in ("Secret/key.txt", "secret/key.txt", "Secret /key.txt", "/Secret//key.txt", "Secret\\key.txt"):
            assert client.get("/api/cloud/download", params={"path": spelling}).status_code == 403
        assert put(client, "x.txt", b"x", path="Secret").status_code == 403
        assert put(client, "key.txt", b"x", path="Secret", overwrite=True).status_code == 403
        assert client.post("/api/cloud/folder", json={"path": "Secret", "name": "In"}, headers=CONSOLE).status_code == 403
        assert client.post("/api/cloud/rename", json={"path": "Secret", "name": "Mine"}, headers=CONSOLE).status_code == 403
        assert client.post("/api/cloud/delete", json={"path": "Secret/key.txt"}, headers=CONSOLE).status_code == 403
        assert client.post("/api/cloud/delete", json={"path": "Secret"}, headers=CONSOLE).status_code == 403
        assert client.post("/api/cloud/delete", json={"path": "open.txt"}, headers=CONSOLE).status_code == 200  # the rest: as before

        client.cookies.clear()
        login(client, VIEWER)  # listed with view
        assert names(client) == ["Secret", "Team"]
        assert client.get("/api/cloud/download", params={"path": "Secret/key.txt"}).content == b"key.txt"

        # listed as view: someone with Cloud edit can only download there
        assert rule(client, "Secret", private=True, grants=[("role", DB_ROLE, "view")]).status_code == 200
        login(client, DB_MEMBER)
        assert client.get("/api/cloud/download", params={"path": "Secret/key.txt"}).status_code == 200
        assert put(client, "x.txt", b"x", path="Secret").status_code == 403
        assert client.get("/api/cloud/list", params={"path": "Secret"}).json()["can_edit"] is False
        client.cookies.clear()
        login(client, VIEWER)
        assert names(client) == ["Team"]  # no longer listed

        client.cookies.clear()
        login(client, MEMBER)  # console users always see and change everything, and see what has rules
        entry = next(e for e in client.get("/api/cloud/list").json()["entries"] if e["name"] == "Secret")
        assert entry["private"] is True and entry["shared"] == 1 and entry["can_edit"] is True
        assert client.get("/api/cloud/list").json()["can_manage"] is True
        denied = [r["detail"] for r in client.get("/api/cloud/log", params={"q": "denied"}).json()]
        assert "delete: no access to this item" in denied and "download: no access to this item" in denied


def test_a_folder_holding_a_private_item_cannot_be_renamed_or_deleted_around_it(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        tree(client)
        grant(client, "cloud_edit", "role", DB_ROLE)
        assert rule(client, "Team/Deep", private=True).status_code == 200  # console users only
        login(client, DB_MEMBER)
        assert names(client, "Team") == ["plan.txt"]
        r = client.post("/api/cloud/delete", json={"path": "Team"}, headers=CONSOLE)
        assert r.status_code == 403 and "holds items" in r.json()["message"]
        assert client.post("/api/cloud/rename", json={"path": "Team", "name": "T2"}, headers=CONSOLE).status_code == 403
        # a deeper rule wins over the private folder above it
        login(client, MEMBER)
        client.post("/api/cloud/folder", json={"path": "Team/Deep", "name": "Open"}, headers=CONSOLE)
        put(client, "in.txt", b"x", path="Team/Deep/Open")
        assert rule(client, "Team/Deep/Open", grants=[("role", DB_ROLE, "view")]).status_code == 200
        login(client, DB_MEMBER)
        assert names(client, "Team") == ["Deep", "plan.txt"] and names(client, "Team/Deep") == ["Open"]
        assert client.get("/api/cloud/list", params={"path": "Team/Deep"}).json()["limited"] is True
        assert client.get("/api/cloud/download", params={"path": "Team/Deep/Open/in.txt"}).status_code == 200
        assert client.get("/api/cloud/download", params={"path": "Team/Deep/inner.txt"}).status_code == 403


def test_rules_follow_a_rename_and_come_back_from_the_recycle_bin(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        tree(client)
        grant(client, "cloud_view", "user", VIEWER)
        assert rule(client, "Team", private=True).status_code == 200
        assert rule(client, "Team/Deep", grants=[("user", NO_ROLE, "view")]).status_code == 200
        login(client, MEMBER)
        assert client.post("/api/cloud/rename", json={"path": "Team", "name": "Crew"}, headers=CONSOLE).json() == {"path": "Crew"}
        state = client.get(RULES, params={"path": "Crew/Deep"}).json()
        assert [g["id"] for g in state["grants"]] == [NO_ROLE] and state["above"] == [{"path": "Crew", "private": True, "grants": []}]
        client.cookies.clear()
        login(client, VIEWER)
        assert names(client) == ["Secret", "open.txt"]  # still private under its new name
        client.cookies.clear()
        login(client, NO_ROLE)
        assert names(client, "Crew/Deep") == ["inner.txt"]

        client.cookies.clear()
        login(client, MEMBER)
        assert client.post("/api/cloud/delete", json={"path": "Crew"}, headers=CONSOLE).status_code == 200
        # a new folder with the old name starts without the old rules
        client.post("/api/cloud/folder", json={"name": "Crew"}, headers=CONSOLE)
        client.cookies.clear()
        login(client, VIEWER)
        assert "Crew" in names(client)
        client.cookies.clear()
        login(client, MEMBER)
        bin_id = client.get("/api/cloud/trash").json()["items"][0]["id"]
        back = client.post("/api/cloud/trash/restore", json={"id": bin_id}, headers=CONSOLE).json()["path"]
        assert back.startswith("Crew (restored ")
        assert client.get(RULES, params={"path": back}).json()["private"] is True
        assert [g["id"] for g in client.get(RULES, params={"path": f"{back}/Deep"}).json()["grants"]] == [NO_ROLE]
        client.cookies.clear()
        login(client, VIEWER)
        assert back not in names(client) and "Crew" in names(client)


def test_setting_rules_is_checked_and_logged(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        tree(client)
        assert rule(client, "", private=True).status_code == 404  # the whole cloud: the Permissions page
        assert rule(client, "Nope", private=True).status_code == 404
        assert rule(client, "Team", grants=[("user", "abc", "view")]).json()["error_code"] == "bad_id"
        assert rule(client, "Team", grants=[("user", NO_ROLE, "own")]).json()["error_code"] == "bad_rule"
        assert rule(client, "Team", grants=[("role", NO_ROLE, "view")]).json()["error_code"] == "not_a_role"
        assert rule(client, "Team", grants=[("user", DB_ROLE, "view")]).json()["error_code"] == "not_a_user"
        ok = rule(client, "Team", private=True, grants=[("role", DB_ROLE, "edit"), ("user", NO_ROLE, "view")]).json()
        assert ok["private"] is True and ok["dir"] is True
        assert [(g["type"], g["name"], g["level"]) for g in ok["grants"]][0] == ("role", "Preview", "edit")
        assert rule(client, "Team").json()["grants"] == []  # cleared
        login(client, MEMBER)
        assert client.post(RULES, json={"path": "Team", "private": True}).status_code == 405  # no X-EchoVR
        rows = client.get("/api/cloud/log", params={"q": "permissions"}).json()
        assert [(r["path"], r["detail"]) for r in rows if r["ok"]] == [
            ("Team", "cleared"), ("Team", f"private, edit: role {DB_ROLE}, view: user {NO_ROLE}")]
        client.cookies.clear()
        login(client, NO_ROLE)
        assert client.get("/api/auth/me").json()["user"]["cloud"] is None  # nothing shared any more


def test_console_overview_view_as_and_who_gets_in(tmp_path, discord):
    """User, 2026-11-16: admins see every rule in one place, check what a role or person ends up with, look at the
    cloud as them, and clear what a file removed outside the site left behind."""
    import shutil
    with app_client(settings(tmp_path)) as client:
        tree(client)
        grant(client, "cloud_edit", "role", DB_ROLE)
        grant(client, "cloud_view", "user", VIEWER)
        assert rule(client, "Secret", private=True, grants=[("user", VIEWER, "view")]).status_code == 200
        assert rule(client, "Team/Deep", grants=[("user", NO_ROLE, "edit")]).status_code == 200

        login(client, MEMBER)
        rules = client.get(f"{RULES}/all").json()["rules"]
        assert [(r["path"], r["private"], r["exists"], r["dir"], r["by"]) for r in rules] == [
            ("Secret", True, True, True, f"user{MEMBER}"), ("Team/Deep", False, True, True, f"user{MEMBER}")]
        assert rules[0]["grants"][0]["id"] == VIEWER and rules[0]["updated_at"]

        # who ends up with what: the role with Cloud edit loses the private folder, the listed person keeps view
        got = {(p["type"], p["id"]): p["level"] for p in client.get(RULES, params={"path": "Secret"}).json()["effective"]}
        assert got == {("user", VIEWER): "view", ("role", DB_ROLE): None}
        got = {(p["type"], p["id"]): p["level"] for p in client.get(RULES, params={"path": "Team/Deep"}).json()["effective"]}
        assert got == {("user", NO_ROLE): "edit", ("role", DB_ROLE): "edit", ("user", VIEWER): "view"}

        # the folders above pass their state down to the rows (console users only)
        assert client.get("/api/cloud/list", params={"path": "Secret"}).json()["inherited"] == {"path": "Secret", "private": True}
        assert client.get("/api/cloud/list", params={"path": "Team/Deep"}).json()["inherited"] == {"path": "Team/Deep", "private": False}
        assert client.get("/api/cloud/list").json()["inherited"] is None

        # view as a person / a role: what they would see, nothing to change
        seen = client.get("/api/cloud/list", params={"as_type": "user", "as_id": NO_ROLE}).json()
        assert [e["name"] for e in seen["entries"]] == ["Team"] and seen["limited"] and not seen["can_manage"]
        assert (seen["viewing_as"]["type"], seen["viewing_as"]["id"]) == ("user", NO_ROLE) and "inherited" not in seen
        seen = client.get("/api/cloud/list", params={"as_type": "role", "as_id": DB_ROLE}).json()
        assert [e["name"] for e in seen["entries"]] == ["Team", "open.txt"] and seen["can_edit"] is True
        assert all("private" not in e for e in seen["entries"])
        r = client.get("/api/cloud/list", params={"path": "Secret", "as_type": "role", "as_id": DB_ROLE})
        assert r.status_code == 403 and "Preview has no access" in r.json()["message"]
        r = client.get("/api/cloud/list", params={"as_type": "user", "as_id": SOMEONE})
        assert r.status_code == 403 and "no Cloud tab" in r.json()["message"]
        assert client.get("/api/cloud/list", params={"as_type": "x", "as_id": "1"}).status_code == 400
        assert not [r for r in client.get("/api/cloud/log", params={"q": "denied"}).json()]  # looking is not a refusal

        # a folder removed with File Station: its rule shows as gone and can be cleared
        shutil.rmtree(tmp_path / "data" / "cloud" / "Secret")
        assert [r["exists"] for r in client.get(f"{RULES}/all").json()["rules"]] == [False, True]
        assert client.post(RULES, json={"path": "Secret", "private": True}, headers=CONSOLE).status_code == 404
        assert client.post(RULES, json={"path": "Secret"}, headers=CONSOLE).json() == {"path": "Secret", "gone": True}
        assert [r["path"] for r in client.get(f"{RULES}/all").json()["rules"]] == ["Team/Deep"]

        # finding a person by name: here from the cloud audit log
        found = client.get("/api/cloud/people", params={"q": "user42"}).json()["people"]
        assert found == [{"id": MEMBER, "name": f"user{MEMBER}", "from": "used the cloud"}]
        assert client.get("/api/cloud/people", params={"q": "u"}).json() == {"people": []}

        client.cookies.clear()
        login(client, DB_MEMBER)  # Cloud edit is not enough for any of it
        assert client.get(f"{RULES}/all").status_code == 403
        assert client.get("/api/cloud/people", params={"q": "user"}).status_code == 403
        assert client.get("/api/cloud/list", params={"as_type": "user", "as_id": NO_ROLE}).status_code == 403
        assert "inherited" not in client.get("/api/cloud/list").json()


def test_a_private_folder_is_private_from_the_start(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        grant(client, "cloud_edit", "role", DB_ROLE)
        login(client, MEMBER)
        r = client.post("/api/cloud/folder", json={"name": "Board", "private": True}, headers=CONSOLE)
        assert r.json() == {"path": "Board"}
        assert client.get(RULES, params={"path": "Board"}).json()["private"] is True
        assert client.post("/api/cloud/folder", json={"name": "Board", "private": True}, headers=CONSOLE).status_code == 409
        assert client.get(RULES, params={"path": "Board"}).json()["private"] is True  # the refused try changed nothing
        assert client.post("/api/cloud/folder", json={"name": "a/b", "private": True}, headers=CONSOLE).status_code == 400
        assert [r["path"] for r in client.get(f"{RULES}/all").json()["rules"]] == ["Board"]
        client.cookies.clear()
        login(client, DB_MEMBER)
        assert names(client) == []
        assert client.post("/api/cloud/folder", json={"name": "Mine", "private": True}, headers=CONSOLE).status_code == 403
        assert names(client) == []


def test_admin_level_controls_permissions_where_it_is_given(tmp_path, discord):
    """User, 2026-11-16: three levels. View = download; Edit = also upload, rename, delete; Admin = also the permissions."""
    with app_client(settings(tmp_path)) as client:
        tree(client)
        grant(client, "cloud_view", "user", VIEWER)
        assert rule(client, "Team", grants=[("user", NO_ROLE, "admin")]).status_code == 200

        login(client, NO_ROLE)  # admin of Team only
        assert client.get("/api/auth/me").json()["user"]["cloud"] == "admin"
        top = client.get("/api/cloud/list").json()
        assert [(e["name"], e.get("can_manage")) for e in top["entries"]] == [("Team", True)]
        assert top["can_manage"] is False and top["manages"] is True and top["can_edit"] is False
        inside = client.get("/api/cloud/list", params={"path": "Team"}).json()
        assert inside["can_manage"] and inside["can_edit"] and inside["inherited"] == {"path": "Team", "private": False}
        assert put(client, "new.txt", b"x", path="Team").json()["done"] is True  # admin includes edit
        # sets permissions inside Team: make a subfolder private for one more person, make a private folder
        own = {"type": "user", "id": NO_ROLE, "level": "admin"}
        r = client.post(RULES, json={"path": "Team/Deep", "private": True,
                                     "grants": [{"type": "user", "id": SOMEONE, "level": "view"}]}, headers=CONSOLE)
        assert r.status_code == 200 and r.json()["grants"][0]["id"] == SOMEONE
        assert client.post("/api/cloud/folder", json={"path": "Team", "name": "Board", "private": True}, headers=CONSOLE).status_code == 200
        assert names(client, "Team") == ["Board", "Deep", "new.txt", "plan.txt"]  # a folder's admin keeps what is private in it
        assert [r["path"] for r in client.get(f"{RULES}/all").json()["rules"]] == ["Team", "Team/Board", "Team/Deep"]
        assert client.get("/api/cloud/people", params={"q": "user42"}).status_code == 200
        seen = client.get("/api/cloud/list", params={"path": "Team", "as_type": "user", "as_id": VIEWER}).json()
        assert [e["name"] for e in seen["entries"]] == ["new.txt", "plan.txt"]
        # ... and nowhere else
        assert client.get(RULES, params={"path": "Secret"}).status_code == 403
        assert client.post(RULES, json={"path": "Secret", "private": True}, headers=CONSOLE).status_code == 403
        assert client.post("/api/cloud/folder", json={"name": "Mine", "private": True}, headers=CONSOLE).status_code == 403
        assert client.get("/api/cloud/list", params={"as_type": "user", "as_id": VIEWER}).status_code == 403
        assert client.get("/api/cloud/trash").status_code == 403 and client.get("/api/cloud/log").status_code == 403
        # cannot take their own admin away by accident; giving it to someone else as well is fine
        r = client.post(RULES, json={"path": "Team", "grants": [{"type": "user", "id": NO_ROLE, "level": "edit"}]}, headers=CONSOLE)
        assert r.json()["error_code"] == "locks_you_out"
        assert client.post(RULES, json={"path": "Team", "private": True}, headers=CONSOLE).json()["error_code"] == "locks_you_out"
        both = [own, {"type": "role", "id": DB_ROLE, "level": "admin"}]
        assert client.post(RULES, json={"path": "Team", "private": True, "grants": both}, headers=CONSOLE).status_code == 200

        client.cookies.clear()
        login(client, DB_MEMBER)  # admin by role now
        assert client.get(RULES, params={"path": "Team/Deep"}).status_code == 200
        client.cookies.clear()
        login(client, VIEWER)  # whole-Cloud view: Team is private now
        assert names(client) == ["Secret", "open.txt"]

        # the whole cloud: Cloud admin on the Permissions page
        grant(client, "cloud_admin", "user", VIEWER)
        login(client, VIEWER)
        assert client.get("/api/auth/me").json()["user"]["cloud"] == "admin"
        top = client.get("/api/cloud/list").json()
        assert top["can_manage"] and [e["name"] for e in top["entries"]] == ["Secret", "Team", "open.txt"]
        assert client.post(RULES, json={"path": "Secret", "private": True}, headers=CONSOLE).status_code == 200
        assert names(client, "Secret") == ["key.txt"] and names(client, "Team/Deep") == ["inner.txt"]
        assert client.get("/api/cloud/trash").status_code == 403  # the recycle bin stays with console users
        got = {(p["type"], p["id"]): p["level"] for p in client.get(RULES, params={"path": "Team"}).json()["effective"]}
        assert got == {("user", NO_ROLE): "admin", ("role", DB_ROLE): "admin", ("user", VIEWER): "admin"}


def test_move_into_another_folder(tmp_path, discord):
    """User, 2026-11-16: drag and drop. A file follows the folder it is moved into; a folder takes its own rule along."""
    MOVE = "/api/cloud/move"
    with app_client(settings(tmp_path)) as client:
        tree(client)
        grant(client, "cloud_edit", "role", DB_ROLE)
        grant(client, "cloud_view", "user", VIEWER)
        assert rule(client, "Secret", private=True).status_code == 200
        assert rule(client, "Team/Deep", grants=[("user", NO_ROLE, "view")]).status_code == 200

        login(client, DB_MEMBER)  # Cloud edit
        assert client.post(MOVE, json={"path": "open.txt", "to": "Team"}, headers=CONSOLE).json() == {"path": "Team/open.txt"}
        assert names(client) == ["Team"] and names(client, "Team") == ["Deep", "open.txt", "plan.txt"]
        assert client.post(MOVE, json={"path": "Team/open.txt", "to": ""}, headers=CONSOLE).json() == {"path": "open.txt"}
        assert client.post(MOVE, json={"path": "open.txt", "to": ""}, headers=CONSOLE).json()["error_code"] == "exists"
        # Team holds a folder with its own permissions: moving it needs their admin, Cloud edit is not enough
        assert client.post(MOVE, json={"path": "Team", "to": "Secret"}, headers=CONSOLE).json()["error_code"] == "admin_only"
        assert client.post(MOVE, json={"path": "nope.txt", "to": "Team"}, headers=CONSOLE).status_code == 404
        assert client.post(MOVE, json={"path": "open.txt", "to": "Nope"}, headers=CONSOLE).status_code == 404
        assert client.post(MOVE, json={"path": "open.txt", "to": "../x"}, headers=CONSOLE).status_code == 400
        assert client.post(MOVE, json={"path": "open.txt", "to": "Team"}).status_code == 405  # no X-EchoVR
        put(client, "plan.txt", b"other")
        assert client.post(MOVE, json={"path": "plan.txt", "to": "Team"}, headers=CONSOLE).json()["error_code"] == "exists"
        # not into, or out of, a folder they cannot change
        assert client.post(MOVE, json={"path": "open.txt", "to": "Secret"}, headers=CONSOLE).status_code == 403
        assert client.post(MOVE, json={"path": "Secret/key.txt", "to": ""}, headers=CONSOLE).status_code == 403
        client.cookies.clear()
        login(client, VIEWER)  # view only
        assert client.post(MOVE, json={"path": "open.txt", "to": "Team"}, headers=CONSOLE).status_code == 403

        client.cookies.clear()
        login(client, MEMBER)  # console: a file moved into the private folder is private from then on
        assert client.post(MOVE, json={"path": "Team", "to": "Team/Deep"}, headers=CONSOLE).json()["error_code"] == "bad_path"
        assert client.post(MOVE, json={"path": "Team", "to": "Team"}, headers=CONSOLE).json()["error_code"] == "bad_path"
        assert client.post(MOVE, json={"path": "open.txt", "to": "Secret"}, headers=CONSOLE).json() == {"path": "Secret/open.txt"}
        # a folder takes its own permissions along
        assert client.post(MOVE, json={"path": "Team/Deep", "to": ""}, headers=CONSOLE).json() == {"path": "Deep"}
        assert [r["path"] for r in client.get(f"{RULES}/all").json()["rules"]] == ["Deep", "Secret"]
        moved = [(r["path"], r["detail"]) for r in client.get("/api/cloud/log", params={"q": "move"}).json() if r["ok"]]
        assert moved[:2] == [("Team/Deep", "Deep"), ("open.txt", "Secret/open.txt")]
        client.cookies.clear()
        login(client, VIEWER)
        assert names(client) == ["Deep", "Team", "plan.txt"]
        assert client.get("/api/cloud/download", params={"path": "Secret/open.txt"}).status_code == 403
        client.cookies.clear()
        login(client, NO_ROLE)
        assert names(client) == ["Deep"] and names(client, "Deep") == ["inner.txt"]


def test_a_later_chunk_cannot_send_the_file_somewhere_else(tmp_path, discord):
    """Security review, 2026-11-16: the folder is checked when the file starts AND when it lands."""
    with app_client(settings(tmp_path)) as client:
        tree(client)
        grant(client, "cloud_edit", "role", DB_ROLE)
        assert rule(client, "Secret", private=True).status_code == 200
        login(client, DB_MEMBER)
        upload = secrets.token_hex(16)
        base = {"upload": upload, "total": 6}
        ok = client.post("/api/cloud/upload", params=base | {"name": "a.txt", "path": "Team", "offset": 0}, content=b"abc", headers=CONSOLE)
        assert ok.json()["done"] is False
        r = client.post("/api/cloud/upload", params=base | {"name": "key.txt", "path": "Secret", "offset": 3, "overwrite": True},
                        content=b"def", headers=CONSOLE)
        assert r.status_code == 403
        assert not list((tmp_path / "data" / "cloud-uploads").glob("*.part"))
        client.cookies.clear()
        login(client, MEMBER)
        assert client.get("/api/cloud/download", params={"path": "Secret/key.txt"}).content == b"key.txt"  # untouched
        assert names(client, "Secret") == ["key.txt"] and names(client, "Team") == ["Deep", "plan.txt"]


def test_a_folder_with_permissions_is_deleted_or_moved_only_by_its_admin(tmp_path, discord):
    """Security review, 2026-11-16: an editor of a private folder cannot delete it and put an open one in its place."""
    with app_client(settings(tmp_path)) as client:
        tree(client)
        assert rule(client, "Secret", private=True, grants=[("role", DB_ROLE, "edit"), ("user", NO_ROLE, "admin")]).status_code == 200
        login(client, DB_MEMBER)  # edit inside Secret
        assert put(client, "mine.txt", b"x", path="Secret").json()["done"] is True
        assert client.post("/api/cloud/delete", json={"path": "Secret/mine.txt"}, headers=CONSOLE).status_code == 200  # files: yes
        r = client.post("/api/cloud/delete", json={"path": "Secret"}, headers=CONSOLE)
        assert r.status_code == 403 and r.json()["error_code"] == "admin_only"
        assert client.post("/api/cloud/folder", json={"path": "Secret", "name": "Sub"}, headers=CONSOLE).status_code == 200
        assert client.post("/api/cloud/move", json={"path": "Secret/Sub", "to": "Secret"}, headers=CONSOLE).json()["error_code"] == "exists"
        r = client.post("/api/cloud/rename", json={"path": "Secret", "name": "Open"}, headers=CONSOLE)
        assert r.json() == {"path": "Open"}  # a rename keeps the permissions: still private
        client.cookies.clear()
        login(client, MEMBER)
        assert client.get(RULES, params={"path": "Open"}).json()["private"] is True
        client.cookies.clear()
        login(client, NO_ROLE)  # its admin may
        assert client.post("/api/cloud/delete", json={"path": "Open"}, headers=CONSOLE).status_code == 200


def test_names_that_differ_only_by_case_are_refused(tmp_path, discord):
    """Security review, 2026-11-16: on the NAS "Secret" and "SECRET" would be two folders sharing one set of
    permissions. Only a file system that tells them apart can show it (Linux, like the NAS)."""
    probe = tmp_path / "Probe"
    probe.mkdir()
    if (tmp_path / "PROBE").exists():
        pytest.skip("this file system does not tell upper from lower case (Windows); runs on Linux, like the NAS")
    with app_client(settings(tmp_path)) as client:
        tree(client)
        grant(client, "cloud_edit", "role", DB_ROLE)
        assert rule(client, "Secret", private=True, grants=[("role", DB_ROLE, "edit")]).status_code == 200
        login(client, DB_MEMBER)
        assert client.post("/api/cloud/folder", json={"name": "SECRET"}, headers=CONSOLE).json()["error_code"] == "exists"
        assert client.post("/api/cloud/folder", json={"path": "SECRET", "name": "x", "parents": True}, headers=CONSOLE).status_code == 409
        assert put(client, "OPEN.TXT", b"x").json()["error_code"] == "exists"
        assert client.post("/api/cloud/rename", json={"path": "Team", "name": "SECRET"}, headers=CONSOLE).status_code == 409
        assert client.post("/api/cloud/rename", json={"path": "Team", "name": "TEAM"}, headers=CONSOLE).json() == {"path": "TEAM"}
        client.cookies.clear()
        login(client, MEMBER)
        assert client.get(RULES, params={"path": "Secret"}).json()["private"] is True
