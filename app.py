from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from edutatar import EduTatarBrowser


class BrowserWorker(QObject):
    log = Signal(str)
    finished = Signal(str, bool)
    failed = Signal(str)

    def __init__(self, action: str, username: str = "", password: str = "") -> None:
        super().__init__()
        self.action = action
        self.username = username
        self.password = password

    def run(self) -> None:
        browser = EduTatarBrowser(log=self.log.emit)

        try:
            browser.start(headless=False)

            if self.action == "login":
                ok = browser.login(self.username, self.password)
                self.finished.emit("login", ok)
            elif self.action == "check":
                ok = browser.is_logged_in()
                self.finished.emit("check", ok)
            elif self.action == "open":
                browser.open_profile()
                self.log.emit("Страница профиля открыта. Закройте Chromium после проверки.")
                input("Press Enter to close browser...")
                self.finished.emit("open", True)
            else:
                raise ValueError(f"Неизвестное действие: {self.action}")

        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")
        finally:
            # For login/check we can close safely because the persistent
            # profile stores session state on disk.
            if self.action != "open":
                browser.close()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EduTatar Publisher")
        self.resize(760, 560)

        self.thread: QThread | None = None
        self.worker: BrowserWorker | None = None

        self.status_label = QLabel("Сессия не проверена")

        self.login_edit = QLineEdit()
        self.login_edit.setPlaceholderText("Логин edu.tatar.ru")

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Пароль")

        self.login_button = QPushButton("Войти")
        self.check_button = QPushButton("Проверить сессию")
        self.open_button = QPushButton("Открыть профиль")

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Логин:", self.login_edit)
        form.addRow("Пароль:", self.password_edit)

        buttons = QHBoxLayout()
        buttons.addWidget(self.login_button)
        buttons.addWidget(self.check_button)
        buttons.addWidget(self.open_button)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("<b>edu.tatar.ru</b>"))
        layout.addWidget(self.status_label)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(QLabel("Журнал:"))
        layout.addWidget(self.log_edit, 1)

        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

        self.login_button.clicked.connect(self.login)
        self.check_button.clicked.connect(self.check_session)
        self.open_button.clicked.connect(self.open_profile)

    def append_log(self, message: str) -> None:
        self.log_edit.appendPlainText(message)

    def set_busy(self, busy: bool) -> None:
        self.login_button.setDisabled(busy)
        self.check_button.setDisabled(busy)
        self.open_button.setDisabled(busy)

    def start_worker(self, action: str, username: str = "", password: str = "") -> None:
        if self.thread is not None:
            return

        self.set_busy(True)

        thread = QThread(self)
        worker = BrowserWorker(action, username, password)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.log.connect(self.append_log)
        worker.finished.connect(self.worker_finished)
        worker.failed.connect(self.worker_failed)

        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self.cleanup_worker)

        self.thread = thread
        self.worker = worker
        thread.start()

    def cleanup_worker(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        if self.thread is not None:
            self.thread.deleteLater()

        self.worker = None
        self.thread = None
        self.set_busy(False)

    def login(self) -> None:
        username = self.login_edit.text().strip()
        password = self.password_edit.text()

        if not username or not password:
            QMessageBox.warning(self, "EduTatar", "Введите логин и пароль.")
            return

        self.append_log("Начинаю авторизацию...")
        self.start_worker("login", username, password)

    def check_session(self) -> None:
        self.start_worker("check")

    def open_profile(self) -> None:
        # This action is intentionally not used yet because keeping a worker
        # alive while the browser is open needs a dedicated lifecycle.
        QMessageBox.information(
            self,
            "EduTatar",
            "В первой версии используйте «Проверить сессию». "
            "Постоянное окно браузера добавим вместе с редактором новостей.",
        )

    def worker_finished(self, action: str, ok: bool) -> None:
        if action in {"login", "check"}:
            self.status_label.setText(
                "● Авторизация активна" if ok else "○ Авторизация не подтверждена"
            )

        if action == "login" and ok:
            # Do not retain password in the GUI after successful login.
            self.password_edit.clear()

    def worker_failed(self, details: str) -> None:
        self.append_log(details)
        self.status_label.setText("Ошибка")
        QMessageBox.critical(
            self,
            "Ошибка",
            "Операция не выполнена. Подробности записаны в журнал.",
        )


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
