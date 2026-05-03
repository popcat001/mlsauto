#!/usr/bin/env python3
"""MLS comparable sales search automation.

Usage:
    python3 search.py "<address>" "<property_type>"
    python3 search.py --dry-run "<address>" "<property_type>"
    python3 search.py --submit "<address>" "<property_type>"

property_type: "Single Family Home", "Townhouse", "Condominium"
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import Page, sync_playwright

load_dotenv(Path(__file__).parent / ".env")

LOGIN_URL = "https://search.mlslistings.com/Matrix/Account/Login"
SEARCH_URL = "https://search.mlslistings.com/Matrix/Search/Residential/ResidentialSearch"

PROPERTY_TYPE_MAP = {
    "single family home": "Single Family Home",
    "sfh": "Single Family Home",
    "townhouse": "Townhouse",
    "town house": "Townhouse",
    "condo": "Condominium",
    "condominium": "Condominium",
}

SFH_TYPES = {"single family home", "sfh"}


@dataclass(frozen=True)
class SearchCriteria:
    address: str
    property_type: str
    sale_date_from: str
    sale_date_to: str
    beds_min: str
    baths_min: str
    sqft_min: str
    lot_size_min: str
    within_miles: str


def normalize_type(raw: str) -> str:
    return PROPERTY_TYPE_MAP.get(raw.lower().strip(), raw)


def is_sfh(prop_type: str) -> bool:
    return prop_type.lower().strip() in SFH_TYPES or "single family" in prop_type.lower()


def build_criteria(address: str, property_type: str, today: date = None) -> SearchCriteria:
    prop_type_label = normalize_type(property_type)
    sfh = is_sfh(prop_type_label)
    sale_date_to = (today or date.today()).strftime("%m/%d/%Y")
    return SearchCriteria(
        address=address,
        property_type=prop_type_label,
        sale_date_from="01/01/2025",
        sale_date_to=sale_date_to,
        beds_min="2",
        baths_min="2",
        sqft_min="1300" if sfh else "",
        lot_size_min="5000" if sfh else "",
        within_miles="1",
    )


def fill_first(locator, value: str, label: str) -> None:
    if not locator.count():
        raise RuntimeError(f"Could not find field for {label}")
    field = locator.first
    field.click()
    field.fill(value)


def fill_visible_input_after_text(
    page: Page,
    label: str,
    value: str,
    *,
    occurrence: int = 0,
    contains: bool = False,
) -> None:
    filled = page.evaluate(
        """({ label, value, occurrence, contains }) => {
            const visible = el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== 'hidden' &&
                    style.display !== 'none' &&
                    rect.width > 0 &&
                    rect.height > 0;
            };
            const labels = [...document.querySelectorAll('body *')]
                .filter(visible)
                .filter(el => {
                    const text = (el.textContent || '').trim();
                    return contains ? text.includes(label) : text === label;
                })
                .sort((a, b) => a.textContent.trim().length - b.textContent.trim().length);
            const target = labels[occurrence];
            if (!target) return false;

            const candidates = [...document.querySelectorAll('input:not([type=hidden]), textarea')]
                .filter(visible)
                .filter(input => {
                    const pos = target.compareDocumentPosition(input);
                    return Boolean(pos & Node.DOCUMENT_POSITION_FOLLOWING);
                });
            const input = candidates[0];
            if (!input) return false;
            input.focus();
            input.value = value;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }""",
        {"label": label, "value": value, "occurrence": occurrence, "contains": contains},
    )
    if not filled:
        raise RuntimeError(f"Could not find visible input after {label!r}")


def select_list_option(page: Page, section_title: str, option_text: str, *, clear: bool = False) -> None:
    """Select an option in an MLS criteria listbox near a section heading."""
    selected = page.evaluate(
        """({ sectionTitle, optionText, clear }) => {
            const visible = el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== 'hidden' &&
                    style.display !== 'none' &&
                    rect.width > 0 &&
                    rect.height > 0;
            };
            const selects = [...document.querySelectorAll('select')].filter(visible);
            const section = [...document.querySelectorAll('body *')]
                .filter(visible)
                .filter(el => (el.textContent || '').trim() === sectionTitle)
                .sort((a, b) => a.textContent.trim().length - b.textContent.trim().length)[0];
            const candidates = section
                ? selects.filter(select => Boolean(section.compareDocumentPosition(select) & Node.DOCUMENT_POSITION_FOLLOWING))
                : selects;
            const select = candidates.find(sel =>
                [...sel.options].some(opt => opt.text.trim() === optionText)
            );
            if (!select) return false;
            if (clear) {
                [...select.options].forEach(opt => { opt.selected = false; });
            }
            const option = [...select.options].find(opt => opt.text.trim() === optionText);
            option.selected = true;
            select.dispatchEvent(new Event('input', { bubbles: true }));
            select.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }""",
        {"sectionTitle": section_title, "optionText": option_text, "clear": clear},
    )
    if selected:
        return

    option = page.locator(
        f"xpath=//*[normalize-space()={xpath_literal(section_title)}]"
        f"/ancestor::*[self::td or self::div][1]"
        f"//option[normalize-space()={xpath_literal(option_text)}]"
    ).first
    if not option.count():
        option = page.locator(f"option").filter(has_text=option_text).first
    if not option.count():
        raise RuntimeError(f"Could not find option {option_text!r} in {section_title!r}")

    select = option.locator("xpath=ancestor::select[1]")
    if not select.count():
        raise RuntimeError(f"Could not find select for option {option_text!r}")
    if clear:
        select.evaluate("el => Array.from(el.options).forEach(o => o.selected = false)")
    value = option.get_attribute("value")
    if value is not None:
        select.select_option(value=value)
    else:
        select.select_option(label=option_text)
    select.evaluate("el => el.dispatchEvent(new Event('change', { bubbles: true }))")


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in value.split("'")) + ")"


def fill_date_by_label(page: Page, label: str, start: str, end: str) -> None:
    try:
        fill_visible_input_after_text(page, label, f"{start}-{end}")
        return
    except RuntimeError:
        pass

    row_inputs = page.locator(
        f"xpath=//*[normalize-space()={xpath_literal(label)}]"
        "/ancestor::*[self::tr or self::div][1]//input[not(@type='hidden')]"
    )
    if row_inputs.count() >= 2:
        row_inputs.nth(0).fill(start)
        row_inputs.nth(1).fill(end)
        return
    if row_inputs.count() == 1:
        row_inputs.first.fill(f"{start}-{end}")
        return

    direct = page.locator(
        "input[id*='SaleDate'], input[name*='SaleDate'], "
        "input[id*='sale'], input[name*='sale']"
    )
    if direct.count() >= 2:
        direct.nth(0).fill(start)
        direct.nth(1).fill(end)
        return
    if direct.count() == 1:
        direct.first.fill(f"{start}-{end}")
        return
    raise RuntimeError("Could not find Sale Date input")


def fill_building_description(page: Page, criteria: SearchCriteria) -> None:
    rows = {
        "Beds": criteria.beds_min,
        "Full Baths": criteria.baths_min,
        "SqFt": criteria.sqft_min,
        "Lot Size": criteria.lot_size_min,
    }
    for label, value in rows.items():
        if not value:
            continue
        fill_visible_input_after_text(page, label, value)


def fill_map_search(page: Page, criteria: SearchCriteria) -> None:
    fill_visible_input_after_text(page, "Within", criteria.within_miles, contains=True)

    address_locator = None
    try:
        fill_visible_input_after_text(page, "miles of", criteria.address, contains=True)
    except RuntimeError:
        address_locator = page.locator(
            "input[id*='MapAddress'], input[name*='MapAddress'], "
            "input[aria-label*='address' i]"
        )
        fill_first(address_locator, criteria.address, "Map Search address")
    page.wait_for_timeout(1500)

    suggestion_clicked = click_map_suggestion(page, criteria.address)
    if suggestion_clicked:
        page.wait_for_timeout(1000)
        return

    suggestion = page.locator(".pac-item, .ui-autocomplete li, .autocomplete-suggestion").first
    if suggestion.count():
        suggestion.click()
        page.wait_for_timeout(1000)
        return

    if address_locator and address_locator.count():
        address_locator.first.press("ArrowDown")
        address_locator.first.press("Enter")
    else:
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")


def click_map_suggestion(page: Page, address: str) -> bool:
    words = [word for word in address.replace(",", " ").split() if word]
    if not words:
        return False
    address_key = " ".join(words[:2]).lower()
    debug = page.evaluate(
        """addressKey => {
            const visible = el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== 'hidden' &&
                    style.display !== 'none' &&
                    rect.width > 0 &&
                    rect.height > 0;
            };
            return [...document.querySelectorAll('body *')]
                .filter(visible)
                .map(el => {
                    const text = (el.textContent || '').trim().replace(/\\s+/g, ' ');
                    const rect = el.getBoundingClientRect();
                    const x = rect.left + rect.width / 2;
                    const y = rect.top + rect.height / 2;
                    const hit = document.elementFromPoint(x, y);
                    return {
                        tag: el.tagName,
                        className: String(el.className || ''),
                        text,
                        rect: [Math.round(rect.left), Math.round(rect.top), Math.round(rect.width), Math.round(rect.height)],
                        hitTag: hit ? hit.tagName : '',
                        hitClass: hit ? String(hit.className || '') : '',
                        cursor: hit ? window.getComputedStyle(hit).cursor : ''
                    };
                })
                .filter(row => row.text.toLowerCase().includes(addressKey))
                .slice(0, 12);
        }""",
        address_key,
    )
    print("Visible map suggestion candidates:")
    for row in debug:
        print(row)

    text_points = page.evaluate(
        """addressKey => {
            const visible = el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== 'hidden' &&
                    style.display !== 'none' &&
                    rect.width > 0 &&
                    rect.height > 0;
            };
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                {
                    acceptNode(node) {
                        const text = (node.nodeValue || '').trim().toLowerCase();
                        if (!text.includes(addressKey)) return NodeFilter.FILTER_REJECT;
                        const parent = node.parentElement;
                        if (!parent || !visible(parent)) return NodeFilter.FILTER_REJECT;
                        if (['SCRIPT', 'STYLE', 'TEXTAREA'].includes(parent.tagName)) {
                            return NodeFilter.FILTER_REJECT;
                        }
                        if (parent.tagName === 'INPUT') return NodeFilter.FILTER_REJECT;
                        return NodeFilter.FILTER_ACCEPT;
                    }
                }
            );

            const ranges = [];
            while (walker.nextNode()) {
                const range = document.createRange();
                range.selectNodeContents(walker.currentNode);
                for (const rect of range.getClientRects()) {
                    if (rect.width > 0 && rect.height > 0) {
                        ranges.push({
                            left: rect.left,
                            top: rect.top,
                            width: rect.width,
                            height: rect.height
                        });
                    }
                }
            }
            if (!ranges.length) return [];
            ranges.sort((a, b) => {
                const y = a.top - b.top;
                if (Math.abs(y) > 2) return y;
                return a.left - b.left;
            });
            return ranges.flatMap(rect => [
                { x: rect.left + Math.min(12, Math.max(4, rect.width * 0.08)), y: rect.top + rect.height / 2 },
                { x: rect.left + Math.min(40, Math.max(8, rect.width * 0.25)), y: rect.top + rect.height / 2 },
                { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
            ]);
        }""",
        address_key,
    )
    for point in text_points:
        print(f"Clicking map suggestion text at ({point['x']:.0f}, {point['y']:.0f})")
        page.mouse.move(point["x"], point["y"], steps=20)
        page.wait_for_timeout(1500)
        page.mouse.down()
        page.wait_for_timeout(100)
        page.mouse.up()
        page.wait_for_timeout(1200)
        if not page.locator("text=Did you mean:").count():
            return True

    did_you_mean_point = page.evaluate(
        """() => {
            const visible = el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== 'hidden' &&
                    style.display !== 'none' &&
                    rect.width > 0 &&
                    rect.height > 0;
            };
            const labels = [...document.querySelectorAll('body *')]
                .filter(visible)
                .filter(el => (el.textContent || '').trim() === 'Did you mean:')
                .sort((a, b) => {
                    const ar = a.getBoundingClientRect();
                    const br = b.getBoundingClientRect();
                    return (ar.width * ar.height) - (br.width * br.height);
                });
            const label = labels[0];
            if (!label) return false;
            const rect = label.getBoundingClientRect();
            return {
                x: rect.left + 24,
                y: rect.bottom + 18
            };
        }"""
    )
    if did_you_mean_point:
        print(f"Clicking map suggestion row at ({did_you_mean_point['x']:.0f}, {did_you_mean_point['y']:.0f})")
        page.mouse.click(did_you_mean_point["x"], did_you_mean_point["y"])
        page.wait_for_timeout(1000)
        if not page.locator("text=Did you mean:").count():
            return True
        page.mouse.dblclick(did_you_mean_point["x"], did_you_mean_point["y"])
        page.wait_for_timeout(1000)
        return not page.locator("text=Did you mean:").count()

    text_match = page.get_by_text(words[0], exact=False).filter(has_text=words[1]).last
    if text_match.count():
        print("Clicking map suggestion via Playwright text locator")
        text_match.hover()
        page.wait_for_timeout(1500)
        text_match.click()
        page.wait_for_timeout(1000)
        return not page.locator("text=Did you mean:").count()

    point = page.evaluate(
        """addressKey => {
            const visible = el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== 'hidden' &&
                    style.display !== 'none' &&
                    rect.width > 0 &&
                    rect.height > 0;
            };
            const candidates = [...document.querySelectorAll('body *')]
                .filter(visible)
                .filter(el => (el.textContent || '').toLowerCase().includes(addressKey))
                .filter(el => !['HTML', 'BODY', 'SCRIPT', 'STYLE', 'INPUT', 'TEXTAREA'].includes(el.tagName));
            if (!candidates.length) return false;

            candidates.sort((a, b) => {
                const ar = a.getBoundingClientRect();
                const br = b.getBoundingClientRect();
                const areaDelta = (ar.width * ar.height) - (br.width * br.height);
                if (areaDelta !== 0) return areaDelta;
                return ar.top - br.top;
            });
            const target = candidates[0];
            const rect = target.getBoundingClientRect();
            const text = (target.textContent || '').trim();
            const x = rect.left + Math.min(Math.max(10, rect.width / 4), rect.width - 5);
            const y = text.includes('Did you mean:')
                ? rect.bottom - Math.min(14, Math.max(6, rect.height / 4))
                : rect.top + rect.height / 2;
            return { x, y };
        }""",
        address_key,
    )
    if not point:
        return False
    print(f"Clicking map suggestion fallback at ({point['x']:.0f}, {point['y']:.0f})")
    page.mouse.click(point["x"], point["y"])
    page.wait_for_timeout(1000)
    return not page.locator("text=Did you mean:").count()


def wait_before_close(no_pause: bool) -> None:
    if no_pause:
        return
    if sys.stdin.isatty():
        input("\nPress Enter to close the browser...")
        return

    print("\nNo interactive stdin detected; keeping the browser open for 10 minutes.")
    time.sleep(600)


def run(
    address: str,
    property_type: str,
    *,
    headless: bool = False,
    dry_run: bool = False,
    no_pause: bool = False,
    submit: bool = False,
) -> None:
    criteria = build_criteria(address, property_type)
    if dry_run:
        for key, value in asdict(criteria).items():
            print(f"{key}: {value}")
        return

    userid = os.environ.get("userid", "")
    pw = os.environ.get("pw", "")
    if not userid or not pw:
        sys.exit("ERROR: userid and pw must be set in .env")

    print(f"Searching comps for: {criteria.address}")
    print(f"Property type: {criteria.property_type} ({'SFH rules' if criteria.sqft_min else 'Townhouse/Condo rules'})")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=0 if headless else 200)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        # --- Login ---
        page.goto(LOGIN_URL, wait_until="networkidle")
        page.fill("input#UserId, input#username, input[name='username'], input[type='text']", userid)
        page.fill("input#password, input[name='password'], input[type='password']", pw)
        page.click("button#next, input[type='submit'], button[type='submit']")
        page.wait_for_url("**/search.mlslistings.com/**", timeout=30000)
        print("Logged in.")

        # --- Navigate to search page ---
        page.goto(SEARCH_URL, wait_until="networkidle")
        page.wait_for_selector("select, input", state="attached", timeout=15000)

        # --- Status: Sold ---
        select_list_option(page, "Status", "Sold", clear=True)

        # --- Sale Date ---
        fill_date_by_label(page, "Sale Date", criteria.sale_date_from, criteria.sale_date_to)

        # --- Property Type ---
        select_list_option(page, "Property Type", criteria.property_type, clear=True)

        # --- Building Description ---
        fill_building_description(page, criteria)

        # --- Map Search ---
        fill_map_search(page, criteria)
        page.wait_for_timeout(500)

        if not submit:
            print("Search parameters filled. Review the open browser window; search was not submitted.")
            wait_before_close(no_pause)
            browser.close()
            return

        # --- Submit ---
        search_btn = page.locator("input[type='submit'][value*='Search'], button:has-text('Search')").first
        search_btn.click()
        page.wait_for_load_state("networkidle", timeout=20000)
        print("Search submitted, waiting for results...")

        # --- Extract results ---
        page.wait_for_timeout(2000)
        rows = page.locator("table.results-table tr, tr.result-row, .listing-row").all()

        if not rows:
            count = page.locator(".results-count, #resultsCount, .result-header").first
            count_text = count.text_content() if count.count() else "No result table detected"
            print(f"\nResult info: {count_text}")
            print("(Open the browser window to view full results)")
        else:
            print(f"\nFound {len(rows) - 1} comparable sales:\n")
            print(f"{'Address':<40} {'Type':<20} {'Sale $':>10} {'Beds':>4} {'Baths':>5} {'SqFt':>6} {'Sold Date':<12}")
            print("-" * 105)
            for row in rows[1:]:  # skip header
                cells = row.locator("td").all_text_contents()
                if cells:
                    print("  ".join(c.strip()[:38] for c in cells[:7]))

        wait_before_close(no_pause)
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MLS comparable sales search automation.")
    parser.add_argument("--dry-run", action="store_true", help="Print criteria without opening MLS.")
    parser.add_argument("--headless", action="store_true", help="Run browser headlessly.")
    parser.add_argument("--no-pause", action="store_true", help="Close the browser without waiting for Enter.")
    parser.add_argument("--submit", action="store_true", help="Submit the search after filling parameters.")
    parser.add_argument("address")
    parser.add_argument("property_type", choices=["Single Family Home", "Townhouse", "Condominium", "sfh", "townhouse", "condo"])
    args = parser.parse_args()

    run(
        args.address,
        args.property_type,
        headless=args.headless,
        dry_run=args.dry_run,
        no_pause=args.no_pause,
        submit=args.submit,
    )
