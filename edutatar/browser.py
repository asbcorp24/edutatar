from __future__ import annotations

from dataclasses import dataclass
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

NEWS_BLOCK_ID = 41120
NEWS_LIST_PAGE = f"{BASE_URL}/admin/page/news?news_block_id={NEWS_BLOCK_ID}"
NEWS_CREATE_PAGE = f"{BASE_URL}/admin/page/news/edit?news_block_id={NEWS_BLOCK_ID}"


def news_edit_page(news_id: int | str) -> str:
    return (
        f"{BASE_URL}/admin/page/news/edit/{int(news_id)}"
        f"?news_block_id={NEWS_BLOCK_ID}"
    )


@dataclass
class NewsDraft:
    title: str
    ndate: str
    source: str = ""
    lead: str = ""
    text: str = ""
    trans_region: bool = False
    trans_global: bool = False
    gallery_id: str = ""
    videoteka_id: str = ""


class EduTatarBrowser:
    """Browser automation for edu.tatar.ru using a real persistent Chromium profile."""

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

        cookie_names = {
            c["name"]
            for c in self.context.cookies(BASE_URL)  # type: ignore[union-attr]
        }

        if "/user/anketa" in url:
            return True

        return "HLP" in cookie_names

    def _open_admin_page(self, url: str, description: str) -> None:
        page = self._require_page()
        self.log(description)
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        if "/login" in page.url.lower():
            raise RuntimeError("Сессия истекла: сайт вернул страницу входа.")

    def open_profile(self) -> None:
        self._open_admin_page(PROFILE_PAGE, "Открываю профиль...")

    def open_news_list(self) -> None:
        self._open_admin_page(NEWS_LIST_PAGE, "Открываю список новостей...")

    def open_news_create(self) -> None:
        self._open_admin_page(NEWS_CREATE_PAGE, "Открываю форму добавления новости...")

    def open_news_edit(self, news_id: int | str) -> None:
        self._open_admin_page(
            news_edit_page(news_id),
            f"Открываю редактирование новости #{int(news_id)}...",
        )

    def _set_ckeditor(self, element_id: str, html: str) -> None:
        page = self._require_page()

        page.locator(f"#{element_id}").wait_for(state="attached", timeout=15_000)

        # CKEditor 4 replaces the textarea visually. If the instance is ready,
        # write through the editor API; otherwise fill the underlying textarea.
        has_editor = page.evaluate(
            """(id) => Boolean(window.CKEDITOR && CKEDITOR.instances && CKEDITOR.instances[id])""",
            element_id,
        )

        if has_editor:
            page.evaluate(
                """([id, value]) => {
                    const editor = CKEDITOR.instances[id];
                    editor.setData(value);
                    editor.updateElement();
                }""",
                [element_id, html],
            )
        else:
            page.locator(f"#{element_id}").fill(html)

    def publish_news(self, draft: NewsDraft) -> str:
        if not draft.title.strip():
            raise ValueError("Название новости не заполнено.")
        if not draft.ndate.strip():
            raise ValueError("Дата новости не заполнена.")

        page = self._require_page()
        self.open_news_create()

        self.log("Заполняю название, дату и источник...")
        page.locator("#news_title").fill(draft.title.strip())
        page.locator("#news_ndate").fill(draft.ndate.strip())
        page.locator("#news_source").fill(draft.source.strip())

        self.log("Заполняю лид и текст новости...")
        self._set_ckeditor("news_lead", draft.lead)
        self._set_ckeditor("news_text", draft.text)

        if draft.gallery_id:
            page.locator("#news_gallery_id").select_option(draft.gallery_id)

        if draft.videoteka_id:
            page.locator("#news_videoteka_id").select_option(draft.videoteka_id)

        region = page.locator("#news_trans_region")
        if region.count():
            region.set_checked(draft.trans_region)

        global_box = page.locator("#news_trans_global")
        if global_box.count():
            global_box.set_checked(draft.trans_global)

        # The school checkbox is disabled and checked by the site itself.
        self.log("Отправляю новость...")
        form = page.locator(
            f'form[action="/admin/page/news/edit?news_block_id={NEWS_BLOCK_ID}"]'
        ).first

        # Synchronize both CKEditor instances immediately before submit.
        page.evaluate(
            """() => {
                if (window.CKEDITOR && CKEDITOR.instances) {
                    Object.values(CKEDITOR.instances).forEach(editor => editor.updateElement());
                }
            }"""
        )

        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            form.locator('input[type="submit"][value="Сохранить"]').click()

        if "/login" in page.url.lower():
            raise RuntimeError("Во время сохранения истекла сессия.")

        self.log(f"Форма отправлена. Текущий URL: {page.url}")
        return page.url

    def wait_until_browser_closed(self) -> None:
        page = self._require_page()
        self.log("Браузер оставлен открытым. Закройте его для возврата в приложение.")
        try:
            while not page.is_closed():
                page.wait_for_timeout(500)
        except Exception:
            pass
