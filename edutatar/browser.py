from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import (
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


BASE_URL = "https://edu.tatar.ru"
LOGIN_PAGE = f"{BASE_URL}/login/"
PROFILE_PAGE = f"{BASE_URL}/user/anketa"


class EduTatarBrowser:
    """Browser automation for edu.tatar.ru.

    The class intentionally uses a real persistent Chromium profile instead
    of manually replaying cookies or HTTP requests.
    """

    def __init__(
        self,
        profile_dir: Path | str = Path("data/browser_profile"),
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.profile_dir = Path(profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.log = log or (lambda _message: None)

        self._playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def start(self, headless: bool = False) -> None:
        if self.context is not None:
            return

        self.log("Запуск Chromium...")
        self._playwright = sync_playwright().start()
        self.context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=headless,
            viewport={"width": 1400, "height": 900},
        )

        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.log("Chromium запущен.")

    def close(self) -> None:
        if self.context is not None:
            self.context.close()
            self.context = None
            self.page = None

        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def _require_page(self) -> Page:
        if self.page is None:
            raise RuntimeError("Браузер не запущен.")
        return self.page

    def open_login(self) -> None:
        page = self._require_page()
        self.log("Открываю страницу входа...")
        page.goto(LOGIN_PAGE, wait_until="domcontentloaded", timeout=30_000)

    def login(self, username: str, password: str) -> bool:
        if not username.strip():
            raise ValueError("Введите логин.")
        if not password:
            raise ValueError("Введите пароль.")

        page = self._require_page()
        self.open_login()

        login_field = page.locator('input[name="main_login2"]')
        password_field = page.locator('input[name="main_password2"]')

        login_field.wait_for(state="visible", timeout=15_000)
        password_field.wait_for(state="visible", timeout=15_000)

        login_field.fill(username.strip())
        password_field.fill(password)

        self.log("Отправляю форму входа...")

        form = page.locator('form:has(input[name="main_login2"])').first
        submit = form.locator(
            'button[type="submit"], input[type="submit"], button:not([type])'
        ).first

        if submit.count():
            submit.click()
        else:
            password_field.press("Enter")

        try:
            page.wait_for_url(
                lambda url: "/user/anketa" in url,
                timeout=30_000,
                wait_until="domcontentloaded",
            )
        except PlaywrightTimeoutError:
            # Some installations may land on another authenticated page.
            pass

        ok = self.is_logged_in(navigate=False)
        self.log("Вход выполнен." if ok else f"Вход не подтверждён. Текущий URL: {page.url}")
        return ok

    def is_logged_in(self, navigate: bool = True) -> bool:
        page = self._require_page()

        if navigate:
            self.log("Проверяю сохранённую сессию...")
            page.goto(PROFILE_PAGE, wait_until="domcontentloaded", timeout=30_000)

        url = page.url.lower()

        if "/login" in url or url.rstrip("/").endswith("/logon"):
            return False

        # Do not log cookie values. Only use names as an additional signal.
        cookie_names = {
            c["name"]
            for c in self.context.cookies(BASE_URL)  # type: ignore[union-attr]
        }

        if "/user/anketa" in url:
            return True

        return "HLP" in cookie_names

    def open_profile(self) -> None:
        page = self._require_page()
        page.goto(PROFILE_PAGE, wait_until="domcontentloaded", timeout=30_000)
