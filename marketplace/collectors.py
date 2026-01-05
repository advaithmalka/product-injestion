from __future__ import annotations

from pathlib import Path
from typing import Protocol


class PageCollector(Protocol):
    def collect(self, url: str, html_path: str | None = None) -> str: ...


class FixturePageCollector:
    def collect(self, url: str, html_path: str | None = None) -> str:
        if not html_path:
            raise ValueError(f"Fixture collection requires html_path for {url}")
        return Path(html_path).read_text(encoding="utf-8")


class SeleniumPageCollector:
    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    def collect(self, url: str, html_path: str | None = None) -> str:
        if html_path:
            return FixturePageCollector().collect(url, html_path)

        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=options)
        try:
            driver.set_page_load_timeout(self.timeout_seconds)
            driver.get(url)
            return driver.page_source
        finally:
            driver.quit()
