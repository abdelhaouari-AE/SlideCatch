"""Update check and one-click update (the network and the windows).

The logic that needs no Qt (version numbers, zip, helper script) is in
slidecatch/updater.py. Here: asking GitHub, downloading with a progress bar,
and the dialogs. Qt's own network classes are used (not Python's ssl module):
they use the Windows certificate store and add much less to the program size.
"""

import logging
import os
import sys

from PySide6.QtCore import QCryptographicHash, QFile, QObject, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QDialog, QProgressBar, QTextBrowser

from .. import APP_NAME, APP_VERSION, config, updater
from ..i18n import tr
from . import widgets as w

log = logging.getLogger(__name__)
TIMEOUT_MS = 20000


def _request(url: str) -> QNetworkRequest:
    request = QNetworkRequest(QUrl(url))
    request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "%s/%s" % (APP_NAME, APP_VERSION))
    request.setRawHeader(b"Accept", b"application/vnd.github+json, application/octet-stream, */*")
    request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
    request.setTransferTimeout(TIMEOUT_MS)
    return request


def _explain(reply: QNetworkReply) -> str:
    """A short, honest reason for a failed request."""
    status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
    if status == 404:
        return tr("No update information was found (the project page may be private).")
    if status in (403, 429):
        return tr("GitHub refused the request for now. Try again later.")
    return tr("Could not reach the update server. Check your internet connection and try again.")


class Fetcher(QObject):
    """One download at a time: to memory (small answers) or to a file (the zip)."""

    progress = Signal(object, object)       # bytes received, total (0 = unknown)
    done = Signal(bool, object, str)        # ok, data (bytes) or None, error text

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self._reply = None
        self._file = None

    def get(self, url: str, to_file: str = ""):
        self._file = None
        if to_file:
            os.makedirs(os.path.dirname(to_file), exist_ok=True)
            self._file = QFile(to_file)
            if not self._file.open(QFile.OpenModeFlag.WriteOnly | QFile.OpenModeFlag.Truncate):
                self.done.emit(False, None, tr("The update could not be saved on this computer."))
                return
        self._reply = self.manager.get(_request(url))
        self._reply.downloadProgress.connect(lambda done, total: self.progress.emit(done, total))
        if self._file is not None:
            self._reply.readyRead.connect(self._write)
        self._reply.finished.connect(self._finished)

    def cancel(self):
        if self._reply is not None:
            self._reply.abort()

    def _write(self):
        if self._file is not None and self._reply is not None:
            self._file.write(self._reply.readAll())

    def _finished(self):
        reply, self._reply = self._reply, None
        data = None
        ok = reply.error() == QNetworkReply.NetworkError.NoError
        error = "" if ok else _explain(reply)
        if self._file is not None:
            if ok:
                self._file.write(reply.readAll())
            self._file.close()
            if not ok:
                self._file.remove()
        elif ok:
            data = bytes(reply.readAll())
        reply.deleteLater()
        self.done.emit(ok, data, error)


def file_sha256(path: str) -> str:
    digest = QCryptographicHash(QCryptographicHash.Algorithm.Sha256)
    handle = QFile(path)
    if not handle.open(QFile.OpenModeFlag.ReadOnly):
        raise updater.UpdateError(tr("The update could not be read from this computer."))
    while not handle.atEnd():
        digest.addData(handle.read(1 << 20))
    handle.close()
    return bytes(digest.result().toHex()).decode()


class StageThread(QThread):
    """Unpacks the zip (a few seconds) without freezing the window."""

    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, zip_path, destination, parent=None):
        super().__init__(parent)
        self._zip, self._dest = zip_path, destination

    def run(self):
        try:
            self.finished_ok.emit(updater.stage(self._zip, self._dest))
        except updater.UpdateError as exc:
            self.failed.emit(str(exc))
        except OSError as exc:
            self.failed.emit(str(exc))


class UpdateDialog(QDialog):
    """"SlideCatch X is available": what is new, and the update itself."""

    def __init__(self, release, controller, parent=None):
        super().__init__(parent)
        self.release, self.controller = release, controller
        self.fetcher = Fetcher(self)
        self.stager = None
        self.can_install = release.can_download and updater.can_self_update()
        self._working = False
        self.setWindowTitle(tr("Update") + " - " + APP_NAME)
        self.resize(520, 460)
        col = w.vbox(self, (24, 20, 24, 20), 10)
        col.addWidget(w.label(tr("SlideCatch {v} is available", v=release.version), "h1"))
        col.addWidget(w.label(tr("You have version {v}.", v=APP_VERSION), "muted"))
        if release.notes:
            col.addWidget(w.label(tr("What is new"), "h3"))
            notes = QTextBrowser()
            notes.setOpenExternalLinks(False)
            notes.setMarkdown(release.notes)
            col.addWidget(notes, 1)
        else:
            col.addStretch(1)
        self.status = w.label("", "muted", wrap=True)
        self.status.hide()
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.hide()
        col.addWidget(self.status)
        col.addWidget(self.bar)
        if not self.can_install:
            col.addWidget(w.label(self._why_manual(), "small", wrap=True))
        row = w.hbox(spacing=8)
        self.later_button = w.button(tr("Later"))
        self.go_button = w.button(tr("Update now") if self.can_install else tr("Open the download page"),
                                  "primary")
        row.addStretch(1)
        row.addWidget(self.later_button)
        row.addWidget(self.go_button)
        col.addLayout(row)
        self.later_button.clicked.connect(self.reject)
        self.go_button.clicked.connect(self._go)

    @staticmethod
    def _why_manual() -> str:
        if not getattr(sys, "frozen", False) or sys.platform != "win32":
            return tr("This copy of SlideCatch runs from source: download the new version by hand.")
        return tr("SlideCatch cannot replace its own files in this folder. Download the new "
                  "version and unzip it over the old one.")

    def reject(self):
        if self._working:
            return            # the update is being prepared: let it finish
        super().reject()

    # ----------------------------------------------------- the update
    def _go(self):
        if not self.can_install:
            QDesktopServices.openUrl(QUrl(self.release.page_url))
            return
        if not self.controller.ready_for_update():
            w.inform(self, APP_NAME, tr("Stop the capture and close the review windows first, "
                                        "then update."))
            return
        self._busy(True)
        self._show(tr("Preparing the update…"), 0, 0)
        self.fetcher.done.connect(self._checksum_received)
        self.fetcher.get(self.release.sha_url)

    def _busy(self, busy: bool):
        self._working = busy
        for button in (self.later_button, self.go_button):
            button.setEnabled(not busy)

    def _show(self, text, done, total):
        self.status.setText(text)
        self.status.show()
        self.bar.show()
        self.bar.setRange(0, 100 if total else 0)
        self.bar.setValue(int(done * 100 / total) if total else 0)

    def _fail(self, text):
        self._busy(False)
        self.bar.hide()
        self.status.setText(tr("The update could not be completed: {reason}", reason=text))
        self.status.show()

    def _checksum_received(self, ok, data, error):
        self.fetcher.done.disconnect(self._checksum_received)
        try:
            if not ok:
                raise updater.UpdateError(error)
            self._expected = updater.expected_checksum(data.decode("utf-8", "replace"))
        except updater.UpdateError as exc:
            self._fail(str(exc))
            return
        folder = updater.updates_dir()
        self._zip_path = os.path.join(folder, "SlideCatch-%s-portable.zip" % self.release.version)
        self.fetcher.progress.connect(self._download_progress)
        self.fetcher.done.connect(self._zip_received)
        self.fetcher.get(self.release.zip_url, self._zip_path)

    def _download_progress(self, done, total):
        total = total or self.release.zip_size
        percent = int(done * 100 / total) if total else 0
        self._show(tr("Downloading the update… {n} %", n=percent), done, total)

    def _zip_received(self, ok, _data, error):
        self.fetcher.done.disconnect(self._zip_received)
        self.fetcher.progress.disconnect(self._download_progress)
        if not ok:
            self._fail(error)
            return
        self._show(tr("Checking the download…"), 0, 0)
        QTimer.singleShot(0, self._verify)

    def _verify(self):
        try:
            if file_sha256(self._zip_path) != self._expected:
                os.remove(self._zip_path)
                raise updater.UpdateError(tr("The download is damaged (the checksum does not match). "
                                             "Try again."))
        except (updater.UpdateError, OSError) as exc:
            self._fail(str(exc))
            return
        self._show(tr("Unpacking the update…"), 0, 0)
        self.stager = StageThread(self._zip_path, os.path.join(updater.updates_dir(), "new"), self)
        self.stager.finished_ok.connect(self._staged)
        self.stager.failed.connect(self._fail)
        self.stager.start()

    def _staged(self, new_dir):
        self._show(tr("Restarting SlideCatch…"), 0, 0)
        try:
            updater.start_script(config.program_dir(), new_dir)
        except OSError as exc:
            self._fail(str(exc))
            return
        try:
            os.remove(self._zip_path)
        except OSError:
            pass
        self.accept()
        self.controller.quit_for_update()


class UpdateManager(QObject):
    """Decides when to look for a new version and what to show."""

    def __init__(self, controller):
        super().__init__(controller)
        self.controller = controller
        self.fetcher = Fetcher(self)
        self._silent = True
        self._busy = False

    def report_previous_update(self):
        """After a restart by the helper script: tell the person if it failed."""
        result = updater.read_previous_result()
        if result and result != "ok":
            w.inform(self.controller.main, APP_NAME,
                     tr("The last update could not be installed ({reason}). The previous version "
                        "was restored.", reason=result), True)

    def auto_check(self):
        """At every start-up (the only time SlideCatch goes online), never with a capture running."""
        if self.controller.capture_worker is None:
            self.check(silent=True)

    def check(self, silent: bool = False):
        if self._busy:
            return
        self._busy, self._silent = True, silent
        self.fetcher.done.connect(self._answer)
        self.fetcher.get(updater.API_URL)

    def _answer(self, ok, data, error):
        self.fetcher.done.disconnect(self._answer)
        self._busy = False
        parent = self.controller.main
        try:
            if not ok:
                raise updater.UpdateError(error)
            release = updater.parse_release_json(data)
        except updater.UpdateError as exc:
            log.info("Update check failed: %s", exc)
            if not self._silent:
                w.inform(parent, APP_NAME, str(exc) if not ok
                         else tr("The update information was not understood."), True)
            return
        if not updater.is_newer(release.version):
            if not self._silent:
                w.inform(parent, APP_NAME, tr("SlideCatch is up to date (version {v}).",
                                              v=APP_VERSION))
            return
        UpdateDialog(release, self.controller, parent).exec()
