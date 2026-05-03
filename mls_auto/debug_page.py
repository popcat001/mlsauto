"""Debug script: logs in, navigates to search page, saves screenshot + HTML."""
import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(Path(__file__).parent / ".env")

LOGIN_URL = "https://search.mlslistings.com/Matrix/Account/Login"
SEARCH_URL = "https://search.mlslistings.com/Matrix/Search/Residential/ResidentialSearch"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    page.goto(LOGIN_URL, wait_until="networkidle")
    print("Login page URL:", page.url)
    page.fill("#UserId", os.environ["userid"])
    page.fill("#password", os.environ["pw"])
    page.click("button#next, button[type='submit'], input[type='submit']")
    # Wait for the full OAuth redirect chain back to mlslistings.com
    page.wait_for_url("**/search.mlslistings.com/**", timeout=30000)
    print("After login URL:", page.url)
    page.screenshot(path="/tmp/mls_after_login.png")

    page.goto(SEARCH_URL, wait_until="networkidle")
    page.wait_for_timeout(2000)
    print("Search page URL:", page.url)
    page.screenshot(path="/tmp/mls_search_page.png")

    html = page.content()
    with open("/tmp/mls_search_page.html", "w") as f:
        f.write(html)
    print("HTML saved to /tmp/mls_search_page.html")
    print("Screenshot saved to /tmp/mls_search_page.png")

    # Print all input/select element ids and names
    elements = page.evaluate("""() => {
        const els = [...document.querySelectorAll('input, select, textarea')];
        return els.map(e => ({tag: e.tagName, id: e.id, name: e.name, type: e.type, value: e.value}));
    }""")
    print(f"\nFound {len(elements)} form elements:")
    for el in elements[:60]:
        print(f"  <{el['tag'].lower()} id={el['id']!r} name={el['name']!r} type={el.get('type','')} value={el['value']!r}>")

    input("\nPress Enter to close...")
    browser.close()
