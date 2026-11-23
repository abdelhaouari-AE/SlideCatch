"""Update check, download, unpacking, and the terms shown at first start."""

import hashlib
import http.server
import json
import os
import threading
import zipfile

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from slidecatch import app as app_module
from slidecatch import config, updater
from tests.conftest import wait_until

PREFIX = updater.DOWNLOAD_PREFIX


def release_json(tag="v9.9.9", zip_url=None, sha_url=None, extra_assets=()):
    assets = [{"name": "SlideCatch-9.9.9-portable.zip", "size": 100,
               "browser_download_url": zip_url or PREFIX + tag + "/SlideCatch-9.9.9-portable.zip"},
              {"name": "SlideCatch-9.9.9-portable.zip.sha256", "size": 90,
               "browser_download_url": sha_url or PREFIX + tag + "/SlideCatch-9.9.9-portable.zip.sha256"}]
    return {"tag_name": tag, "body": "- faster", "html_url": "https://github.com/x/y/releases/tag/" + tag,
            "assets": assets + list(extra_assets)}


# ------------------------------------------------------------ versions
def test_version_order():
    assert updater.parse_version("v0.10.2") == (0, 10, 2)
    assert updater.parse_version("1.2") == (1, 2, 0)
    assert updater.is_newer("0.10.0", "0.9.9")
    assert updater.is_newer("v1.0.0", "0.9.9")
    assert not updater.is_newer("0.1.0", "0.1.0")
    assert not updater.is_newer("0.1.0", "0.2.0")


def test_release_is_read():
    release = updater.parse_release(release_json())
    assert release.version == "9.9.9" and release.can_download
    assert release.notes == "- faster"


def test_release_from_another_host_is_not_downloadable():
    data = release_json(zip_url="https://evil.example/SlideCatch-9.9.9-portable.zip")
    assert not updater.parse_release(data).can_download


def test_release_without_checksum_is_not_downloadable():
    data = release_json()
    data["assets"] = data["assets"][:1]
    assert not updater.parse_release(data).can_download


def test_bad_answer_is_refused():
    with pytest.raises(updater.UpdateError):
        updater.parse_release_json(b"<html>nope</html>")
    with pytest.raises(updater.UpdateError):
        updater.parse_release_json(b'{"message": "Not Found"}')


def test_checksum_file():
    digest = hashlib.sha256(b"x").hexdigest()
    assert updater.expected_checksum(digest.upper() + "  SlideCatch.zip\n") == digest
    with pytest.raises(updater.UpdateError):
        updater.expected_checksum("not a checksum")


# ------------------------------------------------------------ unpacking
def make_zip(path, names):
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, "data")


def test_stage_finds_the_program_folder(tmp_path):
    make_zip(tmp_path / "r.zip", ["SlideCatch/SlideCatch.exe", "SlideCatch/_internal/a.dll"])
    folder = updater.stage(str(tmp_path / "r.zip"), str(tmp_path / "out"))
    assert os.path.isfile(os.path.join(folder, "SlideCatch.exe"))
    assert os.path.isfile(os.path.join(folder, "_internal", "a.dll"))


def test_stage_refuses_paths_outside_the_folder(tmp_path):
    make_zip(tmp_path / "r.zip", ["SlideCatch/SlideCatch.exe", "../evil.txt"])
    with pytest.raises(updater.UpdateError):
        updater.stage(str(tmp_path / "r.zip"), str(tmp_path / "out"))
    assert not (tmp_path / "evil.txt").exists()


def test_stage_refuses_something_that_is_not_slidecatch(tmp_path):
    make_zip(tmp_path / "r.zip", ["other/readme.txt"])
    with pytest.raises(updater.UpdateError):
        updater.stage(str(tmp_path / "r.zip"), str(tmp_path / "out"))


def test_stage_refuses_a_damaged_zip(tmp_path):
    (tmp_path / "r.zip").write_bytes(b"this is not a zip")
    with pytest.raises(updater.UpdateError):
        updater.stage(str(tmp_path / "r.zip"), str(tmp_path / "out"))


def test_helper_script_is_plain_ascii_and_has_the_safety_steps(tmp_path):
    path = updater.write_script(str(tmp_path))
    text = open(path, "rb").read().decode("ascii")      # must be pure ASCII
    assert "\r\n" in text
    for needle in ("_internal.old", "robocopy", ":rollback", "%EXE%.old"):
        assert needle in text
    assert "/MIR" not in text and "/PURGE" not in text   # never deletes the person's files


# ------------------------------------------------- network, on this computer
class Handler(http.server.BaseHTTPRequestHandler):
    zip_bytes = b""

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api":
            body = json.dumps(release_json()).encode()
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/zip")
            self.end_headers()
            return
        elif self.path == "/zip":
            body = Handler.zip_bytes
        elif self.path == "/missing":
            self.send_response(404)
            self.end_headers()
            return
        else:
            body = b""
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    Handler.zip_bytes = os.urandom(300_000)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown()


_alive = []        # a Fetcher must not be deleted while it is still emitting its last signal


def fetch(qapp, url, to_file=""):
    from slidecatch.ui.updates import Fetcher
    fetcher = Fetcher()
    _alive.append(fetcher)
    result, progress = {}, []
    loop = QEventLoop()
    fetcher.done.connect(lambda ok, data, error: (result.update(ok=ok, data=data, error=error), loop.quit()))
    fetcher.progress.connect(lambda done, total: progress.append((done, total)))
    QTimer.singleShot(15000, loop.quit)
    fetcher.get(url, to_file)
    loop.exec()
    return result, progress


def test_fetch_small_answer(qapp, server):
    result, _ = fetch(qapp, server + "/api")
    assert result["ok"]
    assert updater.parse_release_json(result["data"]).version == "9.9.9"


def test_fetch_file_follows_redirect_and_checksum_matches(qapp, server, tmp_path):
    from slidecatch.ui.updates import file_sha256
    target = str(tmp_path / "dl" / "r.zip")
    result, progress = fetch(qapp, server + "/redirect", target)
    assert result["ok"], result
    assert os.path.getsize(target) == len(Handler.zip_bytes)
    assert file_sha256(target) == hashlib.sha256(Handler.zip_bytes).hexdigest()
    assert progress


def test_fetch_failure_has_a_readable_reason(qapp, server, tmp_path):
    result, _ = fetch(qapp, server + "/missing", str(tmp_path / "x.zip"))
    assert not result["ok"] and "private" in result["error"]
    assert not (tmp_path / "x.zip").exists()
    result, _ = fetch(qapp, "http://127.0.0.1:1/none")           # nothing listens there
    assert not result["ok"] and result["error"]


def test_manager_shows_the_dialog_for_a_newer_version(qapp, start_app, monkeypatch, server, dialogs):
    from slidecatch.ui import updates
    monkeypatch.setattr(updater, "API_URL", server + "/api")
    shown = []
    monkeypatch.setattr(updates.UpdateDialog, "exec", lambda self: shown.append(self.release.version) or 0)
    controller = start_app()
    controller.updates.check(silent=False)
    assert wait_until(qapp, lambda: shown)
    assert shown == ["9.9.9"]


def test_manager_is_quiet_when_current_or_unreachable(qapp, start_app, monkeypatch, dialogs):
    monkeypatch.setattr(updater, "API_URL", "http://127.0.0.1:1/none")
    controller = start_app()
    controller.updates.check(silent=True)
    assert wait_until(qapp, lambda: not controller.updates._busy)
    assert dialogs == []                                      # silent: no message at all
    controller.updates.check(silent=False)
    assert wait_until(qapp, lambda: dialogs)                  # manual: the reason is shown


def test_automatic_check_runs_at_every_start_but_never_while_capturing(qapp, start_app, monkeypatch):
    controller = start_app()
    calls = []
    monkeypatch.setattr(controller.updates, "check", lambda silent=False: calls.append(silent))
    controller.updates.auto_check()
    controller.updates.auto_check()
    assert calls == [True, True]                              # no delay, no setting to switch it off
    controller.capture_worker = object()
    controller.updates.auto_check()
    assert calls == [True, True]
    controller.capture_worker = None


def test_update_dialog_offers_only_update_now_and_later(qapp, start_app):
    from slidecatch.ui.updates import UpdateDialog
    controller = start_app()
    dialog = UpdateDialog(updater.parse_release(release_json()), controller)
    texts = {b.text() for b in dialog.findChildren(type(dialog.go_button))}
    assert not any("kip" in t for t in texts)
    assert dialog.later_button.isEnabled() and dialog.go_button.isEnabled()
    dialog.close()


# ---------------------------------------------------------------- terms
class FakeTerms:
    answer = None

    def __init__(self, *a):
        pass

    class DialogCode:
        Accepted = 1

    def exec(self):
        return FakeTerms.answer


def test_terms_are_asked_at_first_start_and_saved(tmp_path, monkeypatch):
    from slidecatch.ui import dialogs
    monkeypatch.setattr(dialogs, "TermsDialog", FakeTerms)
    settings = config.Settings()
    FakeTerms.answer = 0                                       # "Decline"
    assert app_module.ensure_terms(settings) is False
    assert settings.terms_accepted == ""
    FakeTerms.answer = 1                                       # "I agree"
    assert app_module.ensure_terms(settings) is True
    assert settings.terms_accepted == app_module.TERMS_VERSION


def test_terms_are_not_asked_again_once_accepted(monkeypatch):
    from slidecatch.ui import dialogs

    def boom(*a):
        raise AssertionError("the terms must not be shown again")
    monkeypatch.setattr(dialogs, "TermsDialog", boom)
    assert app_module.ensure_terms(config.Settings(terms_accepted=app_module.TERMS_VERSION))


def test_changed_terms_are_asked_again(monkeypatch):
    from slidecatch.ui import dialogs
    monkeypatch.setattr(dialogs, "TermsDialog", FakeTerms)
    FakeTerms.answer = 1
    settings = config.Settings(terms_accepted="1")             # accepted an older version
    assert app_module.TERMS_VERSION != "1"
    assert app_module.ensure_terms(settings) is True
    assert settings.terms_accepted == app_module.TERMS_VERSION


def test_terms_box_needs_scrolling_then_the_tick(qapp):
    from slidecatch.ui.dialogs import TermsDialog
    dialog = TermsDialog()
    dialog.resize(640, 260)                                    # short: the text must scroll
    dialog.show()
    qapp.processEvents()
    assert not dialog.check.isEnabled() and not dialog.agree.isEnabled()
    bar = dialog.browser.verticalScrollBar()
    bar.setValue(bar.maximum())
    qapp.processEvents()
    assert dialog.check.isEnabled() and not dialog.agree.isEnabled()
    dialog.check.setChecked(True)
    assert dialog.agree.isEnabled()
    dialog.close()
