"""Keep the Streamlit Community Cloud deployment awake.

Community Cloud puts an app to sleep after 12 hours without traffic. A plain HTTP ping does not
count as traffic, because it never opens a Streamlit session. This opens the app in a real
headless browser, presses the wake-up button if the app is asleep, and waits until the app
itself has rendered. It exits non-zero if the app never comes up, so the scheduled GitHub
Action fails and GitHub emails the repo owner.

    APP_URL=https://<your-app>.streamlit.app python scripts/keep_awake.py
"""
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

APP_URL = os.environ.get("APP_URL", "").strip()
WAKE_BUTTON = re.compile(r"get this app back up", re.I)   # Streamlit's sleep page: "Yes, get this app back up!"
APP_MARKER = "Annie."                                     # sidebar brand, only present once the app has rendered
TIMEOUT_S = 300                                           # waking can mean a cold boot plus dependency install
SCREENSHOT = "keep-awake.png"


def app_rendered(page):
    """True once any frame (the app runs inside an iframe on *.streamlit.app) shows the app."""
    return any(frame.locator(f"text={APP_MARKER}").count() for frame in page.frames)


def main():
    if not APP_URL.startswith(("https://", "http://")):
        sys.exit("APP_URL is not set to the app's address")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=90_000)
        woke = False
        deadline = time.monotonic() + TIMEOUT_S
        while time.monotonic() < deadline:
            if app_rendered(page):
                break
            wake = page.get_by_role("button", name=WAKE_BUTTON)
            if not woke and wake.count():
                print("App was asleep - pressing the wake-up button")
                wake.first.click()
                woke = True
            page.wait_for_timeout(5_000)
        else:
            page.screenshot(path=SCREENSHOT, full_page=True)
            browser.close()
            sys.exit(f"App did not render within {TIMEOUT_S}s (screenshot saved to {SCREENSHOT})")
        page.wait_for_timeout(15_000)   # stay connected briefly so the visit registers as a session
        print(("Woke the app; " if woke else "") + f"app is up: {APP_URL}")
        browser.close()


if __name__ == "__main__":
    main()
