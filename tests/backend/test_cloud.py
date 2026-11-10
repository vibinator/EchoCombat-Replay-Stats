"""Open Cloud (cloud.py): only Discord members with Cloud view / Cloud edit (or the console) reach the files."""

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
        assert put(client, "big.bin", data, chunk=3000).json() == {"done": True, "received": len(data), "path": "big.bin"}
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
        assert put(client, "b.bin", b"x" * 300).json()["done"] is True
