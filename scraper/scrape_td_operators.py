"""
TouchDesigner Operator Catalog Scraper
======================================
Walks docs.derivative.ca category pages for the 6 operator families and emits
td_operators.json with the schema consumed by Brute Force Visuals'
KnowledgeGraph seeding (graph/__init__.py, graph/_db.py).

Schema:
    {
      "by_family": {
        "TOP":  [{"name", "family", "python_type", "slug", "url"}, ...],
        "CHOP": [...],
        "SOP":  [...],
        "DAT":  [...],
        "COMP": [...],
        "MAT":  [...]
      },
      "generated_at": "<ISO timestamp>",
      "source": "https://docs.derivative.ca/"
    }

Usage:
    cd scraper
    py -3.13 scrape_td_operators.py

Output:
    ../td_operators.json
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "https://docs.derivative.ca/"
REQUEST_DELAY = 0.4

FAMILIES = ["TOP", "CHOP", "SOP", "DAT", "COMP", "MAT"]
CATEGORY_URLS = {fam: BASE_URL + f"Category:{fam}s" for fam in FAMILIES}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
})


def fetch(url: str) -> BeautifulSoup:
    time.sleep(REQUEST_DELAY)
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def collect_category_pages(family: str) -> list[tuple[str, str]]:
    """Walk paginated MediaWiki category page; return list of (slug, url).

    Slugs come straight from href like '/Blur_TOP' → 'Blur_TOP'.
    Filters to entries whose slug ends with the family suffix.
    """
    suffix = "_" + family
    seen: dict[str, str] = {}
    next_url = CATEGORY_URLS[family]
    while next_url:
        soup = fetch(next_url)
        mw_pages = soup.find("div", id="mw-pages")
        if mw_pages is None:
            break
        for a in mw_pages.select("ul li a[href]"):
            href = a["href"]
            slug = unquote(href.lstrip("/"))
            if not slug.endswith(suffix):
                continue
            if slug in seen:
                continue
            seen[slug] = urljoin(BASE_URL, href)
        # Find "next page" link inside #mw-pages
        next_link = None
        for a in mw_pages.find_all("a"):
            if a.get_text(strip=True).lower().startswith("next page"):
                next_link = a
                break
        next_url = urljoin(BASE_URL, next_link["href"]) if next_link else None
    return sorted(seen.items())


_PYTHON_TYPE_OVERRIDES: dict[str, str] = {}


def derive_python_type(slug: str, family: str) -> str:
    """Convert 'Blur_TOP' → 'blurTOP', 'Audio_File_In_CHOP' → 'audiofileinCHOP'."""
    if slug in _PYTHON_TYPE_OVERRIDES:
        return _PYTHON_TYPE_OVERRIDES[slug]
    stem = slug[: -(len(family) + 1)]  # drop trailing '_FAM'
    lowered = re.sub(r"[^A-Za-z0-9]", "", stem).lower()
    return lowered + family


def slug_to_name(slug: str, family: str) -> str:
    """'Blur_TOP' → 'Blur', 'Audio_File_In_CHOP' → 'Audio File In'."""
    stem = slug[: -(len(family) + 1)]
    return stem.replace("_", " ")


def build_family_entries(family: str) -> list[dict]:
    print(f"  [{family}] fetching category index…", flush=True)
    pages = collect_category_pages(family)
    print(f"  [{family}] {len(pages)} entries", flush=True)
    entries = []
    for slug, url in pages:
        entries.append({
            "name": slug_to_name(slug, family),
            "family": family,
            "python_type": derive_python_type(slug, family),
            "slug": slug,
            "url": url,
        })
    return entries


def main() -> int:
    print("-- TouchDesigner Operator Scraper -----------------")
    by_family: dict[str, list[dict]] = {}
    total = 0
    for fam in FAMILIES:
        entries = build_family_entries(fam)
        by_family[fam] = entries
        total += len(entries)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": BASE_URL,
        "total": total,
        "by_family": by_family,
    }
    out_path = Path(__file__).resolve().parent.parent / "td_operators.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {total} operators -> {out_path}")
    for fam in FAMILIES:
        print(f"  {fam}: {len(by_family[fam])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
