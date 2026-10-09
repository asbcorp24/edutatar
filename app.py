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

    def __init__(
        self,
        action: str,
        username: str = "",
        password: str = "",
        news_id: str = "",
    ) -> None:
        super().__init__()
        self.action = action
        self.username = username
        self.password = password
        self.news_id = news_id

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

            elif self.action == "news_list":
                browser.open_news_list()
                browser.wait_until_browser_closed()
                self.finished.emit("news_list", True)

            elif self.action == "news_create":
                browser.open_news_create()
                browser.wait_until_browser_closed()
                self.finished.emit("news_create", True)

            elif self.action == "news_edit":
                browser.open_news_edit(self.news_id)
                browser.wait_until_browser_closed()
                self.finished.emit("news_edit", True)

            else:
                raise ValueError(f"Неизвестное действие: {self.action}")

        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")
        finally:
            browser.close()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EduTatar Publisher")
        self.resize(820, 620)

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

        self.news_list_button = QPushButton("Список новостей")
        self.news_create_button = QPushButton("Добавить новость")
        self.news_id_edit = QLineEdit()
        self.news_id_edit.setPlaceholderText("ID новости, например 4185547")
        self.news_edit_button = QPushButton("Редактировать по ID")

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)

        auth_form = QFormLayout()
        auth_form.addRow("Логин:", self.login_edit)
        auth_form.addRow("Пароль:", self.password_edit)

        auth_buttons = QHBoxLayout()
        auth_buttons.addWidget(self.login_button)
        auth_buttons.addWidget(self.check_button)

        news_buttons = QHBoxLayout()
        news_buttons.addWidget(self.news_list_button)
        news_buttons.addWidget(self.news_create_button)

        edit_news = QHBoxLayout()
        edit_news.addWidget(self.news_id_edit, 1)
        edit_news.addWidget(self.news_edit_button)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("<h2>EduTatar Publisher</h2>"))
        layout.addWidget(self.status_label)
        layout.addLayout(auth_form)
        layout.addLayout(auth_buttons)
        layout.addWidget(QLabel("<b>Новости — блок 41120</b>"))
        layout.addLayout(news_buttons)
        layout.addLayout(edit_news)
        layout.addWidget(QLabel("Журнал:"))
        layout.addWidget(self.log_edit, 1)

        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

        self.login_button.clicked.connect(self.login)
        self.check_button.clicked.connect(self.check_session)
        self.news_list_button.clicked.connect(
            lambda: self.start_worker("news_list")
        )
        self.news_create_button.clicked.connect(
            lambda: self.start_worker("news_create")
        )
        self.news_edit_button.clicked.connect(self.edit_news)

    def append_log(self, message: str) -> None:
        self.log_edit.appendPlainText(message)

    def set_busy(self, busy: bool) -> None:
        for button in (
            self.login_button,
            self.check_button,
            self.news_list_button,
            self.news_create_button,
            self.news_edit_button,
        ):
            button.setDisabled(busy)

    def start_worker(
        self,
        action: str,
        username: str = "",
        password: str = "",
        news_id: str = "",
    ) -> None:
        if self.thread is not None:
            return

        self.set_busy(True)

        thread = QThread(self)
        worker = BrowserWorker(action, username, password, news_id)
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

    def edit_news(self) -> None:
        news_id = self.news_id_edit.text().strip()

        if not news_id.isdigit():
            QMessageBox.warning(
                self,
                "EduTatar",
                "Введите числовой ID новости.",
            )
            return

        self.start_worker("news_edit", news_id=news_id)

    def worker_finished(self, action: str, ok: bool) -> None:
        if action in {"login", "check"}:
            self.status_label.setText(
                "● Авторизация активна" if ok else "○ Авторизация не подтверждена"
            )

        if action == "login" and ok:
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
