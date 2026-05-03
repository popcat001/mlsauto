#!/usr/bin/env python3
"""Fill MLS Residential Search criteria for comparable sold properties."""

import argparse
import os
import sys
import time
from dataclasses import asdict, dataclass
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


@dataclass(frozen=True)
class PropertyFacts:
    address: str
    property_type: str
    beds: float
    baths: float
    sqft: float
    lot_size: float


@dataclass(frozen=True)
class SearchCriteria:
    address: str
    status: str
    sale_date_from: str
    sale_date_to: str
    property_type: str
    beds_min: str
    baths_min: str
    sqft_min: str
    lot_size_min: str
    within_miles: str


def normalize_type(raw: str) -> str:
    return PROPERTY_TYPE_MAP.get(raw.lower().strip(), raw)


def plus_number(value: float) -> str:
    if value == int(value):
        return f"{int(value)}+"
    return f"{value:g}+"


def build_criteria(facts: PropertyFacts, today: date = None) -> SearchCriteria:
    return SearchCriteria(
        address=facts.address,
        status="Sold",
        sale_date_from="01/01/2025",
        sale_date_to=(today or date.today()).strftime("%m/%d/%Y"),
        property_type=normalize_type(facts.property_type),
        beds_min=plus_number(max(0, facts.beds - 1)),
        baths_min=plus_number(max(0, facts.baths - 0.5)),
        sqft_min=plus_number(max(0, int(facts.sqft * 0.7))),
        lot_size_min=plus_number(max(0, int(facts.lot_size * 0.7))),
        within_miles="1",
    )


def fill_after_text(page: Page, label: str, value: str, *, contains: bool = False) -> None:
    ok = page.evaluate(
        """({ label, value, contains }) => {
            const visible = el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    rect.width > 0 &&
                    rect.height > 0;
            };
            const labelEl = [...document.querySelectorAll('body *')]
                .filter(visible)
                .filter(el => {
                    const text = (el.textContent || '').trim();
                    return contains ? text.includes(label) : text === label;
                })
                .sort((a, b) => a.textContent.trim().length - b.textContent.trim().length)[0];
            if (!labelEl) return false;

            const input = [...document.querySelectorAll('input:not([type=hidden]), textarea')]
                .filter(visible)
                .find(el => labelEl.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
            if (!input) return false;

            input.focus();
            input.value = value;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }""",
        {"label": label, "value": value, "contains": contains},
    )
    if not ok:
        raise RuntimeError(f"Could not find input after {label!r}")


def type_after_text(page: Page, label: str, value: str, *, contains: bool = False) -> None:
    ok = page.evaluate(
        """({ label, contains }) => {
            const visible = el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    rect.width > 0 &&
                    rect.height > 0;
            };
            document.querySelectorAll('[data-mls-auto-target]').forEach(el => {
                el.removeAttribute('data-mls-auto-target');
            });
            const labelEl = [...document.querySelectorAll('body *')]
                .filter(visible)
                .filter(el => {
                    const text = (el.textContent || '').trim();
                    return contains ? text.includes(label) : text === label;
                })
                .sort((a, b) => a.textContent.trim().length - b.textContent.trim().length)[0];
            if (!labelEl) return false;

            const input = [...document.querySelectorAll('input:not([type=hidden]), textarea')]
                .filter(visible)
                .find(el => labelEl.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
            if (!input) return false;
            input.setAttribute('data-mls-auto-target', '1');
            return true;
        }""",
        {"label": label, "contains": contains},
    )
    if not ok:
        raise RuntimeError(f"Could not find input after {label!r}")

    field = page.locator("[data-mls-auto-target='1']").first
    field.click()
    field.press("ControlOrMeta+A")
    field.type(value, delay=35)


def select_option_after_heading(page: Page, heading: str, option_text: str) -> None:
    ok = page.evaluate(
        """({ heading, optionText }) => {
            const visible = el => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    rect.width > 0 &&
                    rect.height > 0;
            };
            const headingEl = [...document.querySelectorAll('body *')]
                .filter(visible)
                .filter(el => (el.textContent || '').trim() === heading)
                .sort((a, b) => a.textContent.trim().length - b.textContent.trim().length)[0];
            const selects = [...document.querySelectorAll('select')].filter(visible);
            const candidates = headingEl
                ? selects.filter(sel => headingEl.compareDocumentPosition(sel) & Node.DOCUMENT_POSITION_FOLLOWING)
                : selects;
            const select = candidates.find(sel =>
                [...sel.options].some(opt => opt.text.trim() === optionText)
            );
            if (!select) return false;

            [...select.options].forEach(opt => { opt.selected = false; });
            [...select.options].find(opt => opt.text.trim() === optionText).selected = true;
            select.dispatchEvent(new Event('input', { bubbles: true }));
            select.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }""",
        {"heading": heading, "optionText": option_text},
    )
    if not ok:
        raise RuntimeError(f"Could not select {option_text!r} under {heading!r}")


def fill_form(page: Page, criteria: SearchCriteria) -> None:
    select_option_after_heading(page, "Status", criteria.status)
    fill_after_text(page, "Sale Date", f"{criteria.sale_date_from}-{criteria.sale_date_to}")
    select_option_after_heading(page, "Property Type", criteria.property_type)
    fill_after_text(page, "Beds", criteria.beds_min)
    fill_after_text(page, "Tot Baths", criteria.baths_min)
    fill_after_text(page, "SqFt", criteria.sqft_min)
    fill_after_text(page, "Lot Size", criteria.lot_size_min)
    fill_after_text(page, "Within", criteria.within_miles, contains=True)
    type_after_text(page, "miles of", criteria.address, contains=True)


def wait_before_close(no_pause: bool) -> None:
    if no_pause:
        return
    if sys.stdin.isatty():
        input("\nPress Enter to close the browser...")
    else:
        print("\nNo interactive stdin detected; keeping the browser open for 10 minutes.")
        time.sleep(600)


def run(facts: PropertyFacts, *, dry_run: bool = False, headless: bool = False, no_pause: bool = False) -> None:
    criteria = build_criteria(facts)
    if dry_run:
        for key, value in asdict(criteria).items():
            print(f"{key}: {value}")
        return

    userid = os.environ.get("userid", "")
    pw = os.environ.get("pw", "")
    if not userid or not pw:
        sys.exit("ERROR: userid and pw must be set in mls_auto/.env")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=0 if headless else 200)
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        page.goto(LOGIN_URL, wait_until="networkidle")
        page.fill("input#UserId, input#username, input[name='username'], input[type='text']", userid)
        page.fill("input#password, input[name='password'], input[type='password']", pw)
        page.click("button#next, input[type='submit'], button[type='submit']")
        page.wait_for_url("**/search.mlslistings.com/**", timeout=30000)

        page.goto(SEARCH_URL, wait_until="networkidle")
        page.wait_for_selector("select, input", state="attached", timeout=15000)
        fill_form(page, criteria)

        print("Search parameters filled. Address suggestion was not clicked; search was not submitted.")
        wait_before_close(no_pause)
        browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill MLS Residential Search criteria.")
    parser.add_argument("address")
    parser.add_argument("property_type", choices=["Single Family Home", "Townhouse", "Condominium", "sfh", "townhouse", "condo"])
    parser.add_argument("--beds", type=float, required=True, help="Subject property's bed count from Zillow/Redfin.")
    parser.add_argument("--baths", type=float, required=True, help="Subject property's bath count from Zillow/Redfin.")
    parser.add_argument("--sqft", type=float, required=True, help="Subject property's interior square feet.")
    parser.add_argument("--lot-size", type=float, required=True, help="Subject property's lot size in square feet.")
    parser.add_argument("--dry-run", action="store_true", help="Print criteria without opening MLS.")
    parser.add_argument("--headless", action="store_true", help="Run browser without a visible window.")
    parser.add_argument("--no-pause", action="store_true", help="Close browser immediately after filling.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        PropertyFacts(
            address=args.address,
            property_type=args.property_type,
            beds=args.beds,
            baths=args.baths,
            sqft=args.sqft,
            lot_size=args.lot_size,
        ),
        dry_run=args.dry_run,
        headless=args.headless,
        no_pause=args.no_pause,
    )
