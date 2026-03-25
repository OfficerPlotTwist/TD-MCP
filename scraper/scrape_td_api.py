"""
TouchDesigner Python API Scraper (v2)
=====================================
Scrapes the Derivative.ca documentation to build a JSON database of all
valid Python class members, methods, utility functions, and globals.

Covers:
  - All Operator Related Classes (OP, CHOP, COMP, DAT, SOP, MAT, TOP, etc.)
  - Helper Classes (UI, Panes, Undo, Connector, etc.)
  - td Module globals (me, op(), run(), debug(), etc.)
  - Utility Modules (TDFunctions, TDJSON, TDStoreTools, TDResources)
  - Standard Python imports (no import needed in TD scripts)

Usage:
    cd scraper
    python -Xutf8 scrape_td_api.py

Output:
    ../td_python_api.json
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

# Force UTF-8 on Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "https://docs.derivative.ca/"
INDEX_URL = BASE_URL + "Python_Classes_and_Modules"
REQUEST_DELAY = 0.5  # seconds between requests to be polite

# Create a session with browser-like headers
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
})

# Standard Python modules auto-imported by TD (never need import in scripts)
STANDARD_IMPORTS = [
    "collections", "enum", "inspect", "math", "re",
    "sys", "traceback", "warnings"
]

# Extra Helper Class pages to scrape (not discovered from Operator Related)
EXTRA_CLASS_URLS = {
    "UI":              BASE_URL + "UI_Class",
    "Panes":           BASE_URL + "Panes_Class",
    "Pane":            BASE_URL + "Pane_Class",
    "NetworkEditor":   BASE_URL + "NetworkEditor_Class",
    "Preferences":     BASE_URL + "Preferences_Class",
    "Undo":            BASE_URL + "Undo_Class",
    "Colors":          BASE_URL + "Colors_Class",
    "Options":         BASE_URL + "Options_Class",
    "Connector":       BASE_URL + "Connector_Class",
}

# Utility module pages to scrape
UTILITY_MODULE_URLS = {
    "TDFunctions":  BASE_URL + "TDFunctions",
    "TDJSON":       BASE_URL + "TDJSON",
    "TDStoreTools": BASE_URL + "TDStoreTools",
    "TDResources":  BASE_URL + "TDResources",
}

TD_MODULE_URL = BASE_URL + "Td_Module"


# ──────────────────────────────────────────────────────────────────────
# Shared HTML parsing helpers
# ──────────────────────────────────────────────────────────────────────

def _clean_text(el) -> str:
    """Extract clean text from an element, collapsing whitespace."""
    if el is None:
        return ""
    text = el.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\[edit\]", "", text).strip()
    return text


def _collect_siblings_until(start_el, stop_tags=None, stop_el=None):
    """Collect Tag siblings after start_el until a stop condition."""
    if stop_tags is None:
        stop_tags = {"h1"}
    elements = []
    current = start_el.next_sibling if start_el else None
    while current is not None:
        if current == stop_el:
            break
        if isinstance(current, Tag) and current.name in stop_tags:
            break
        elements.append(current)
        current = current.next_sibling
    return elements


def _parse_entries_from_elements(elements) -> list[dict]:
    """
    Parse member/method entries from a list of HTML elements.

    Each entry follows this HTML pattern:
      <div id="memberName" style="display:inline;"></div>
      <p><code class="python">name</code> → <code class="return">type</code> (Read Only):</p>
      <blockquote><p>Description text</p></blockquote>
    """
    entries = []
    i = 0
    while i < len(elements):
        el = elements[i]

        if isinstance(el, Tag) and el.name == "div":
            div_id = el.get("id", "")
            j = i + 1
            while j < len(elements):
                next_el = elements[j]
                if isinstance(next_el, Tag) and next_el.name == "p":
                    code_el = next_el.find("code", class_="python")
                    if code_el:
                        entry = _parse_entry_p(next_el, div_id)
                        entry["description"] = _find_description(elements, j + 1)
                        if entry["name"]:
                            entries.append(entry)
                        i = j
                        break
                    else:
                        break
                elif isinstance(next_el, NavigableString) and next_el.strip() == "":
                    j += 1
                    continue
                else:
                    break
                j += 1

        elif isinstance(el, Tag) and el.name == "p":
            code_el = el.find("code", class_="python")
            if code_el:
                prev = el.previous_sibling
                while prev and isinstance(prev, NavigableString) and prev.strip() == "":
                    prev = prev.previous_sibling
                div_id = ""
                if isinstance(prev, Tag) and prev.name == "div" and prev.get("id"):
                    div_id = prev.get("id", "")
                entry = _parse_entry_p(el, div_id)
                entry["description"] = _find_description(elements, i + 1)
                if entry["name"]:
                    entries.append(entry)
        i += 1
    return entries


def _find_description(elements, start_k) -> str:
    """Find the <blockquote> description after an entry's <p> tag."""
    k = start_k
    while k < len(elements):
        desc_el = elements[k]
        if isinstance(desc_el, Tag):
            if desc_el.name == "blockquote":
                return _clean_text(desc_el)[:500]
            if desc_el.name in ("h1", "h2", "h3", "h4"):
                break
            if desc_el.name == "div" and desc_el.get("id"):
                break
            if desc_el.name == "p" and desc_el.find("code", class_="python"):
                break
        k += 1
    return ""


def _parse_entry_p(p_el, div_id: str) -> dict:
    """Parse a <p> element containing a member/method signature."""
    entry = {
        "name": "", "signature": "", "returns": "",
        "read_only": False, "description": "", "is_method": False,
    }
    code_python = p_el.find("code", class_="python")
    if code_python:
        sig = code_python.get_text(strip=True)
        entry["signature"] = sig
        name_match = re.match(r"([a-zA-Z_]\w*)", sig)
        if name_match:
            entry["name"] = name_match.group(1)
        elif div_id:
            entry["name"] = div_id
        entry["is_method"] = "(" in sig

    code_return = p_el.find("code", class_="return")
    if code_return:
        entry["returns"] = code_return.get_text(strip=True)

    if "Read Only" in p_el.get_text():
        entry["read_only"] = True
    return entry


# ──────────────────────────────────────────────────────────────────────
# Step 1 – Discover all Operator Related Class URLs from the index
# ──────────────────────────────────────────────────────────────────────

def get_class_urls() -> dict[str, str]:
    """Return {ClassName: URL} for every *_Class link on the index page."""
    print(f"[*] Fetching index page: {INDEX_URL}")
    resp = SESSION.get(INDEX_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    class_urls: dict[str, str] = {}
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        m = re.search(r"/([A-Za-z]+_Class)$", href)
        if m:
            class_page = m.group(1)
            class_name = class_page.replace("_Class", "")
            full_url = urljoin(BASE_URL, href)
            class_urls[class_name] = full_url

    # Merge in extra helper class URLs
    for name, url in EXTRA_CLASS_URLS.items():
        if name not in class_urls:
            class_urls[name] = url

    print(f"    Found {len(class_urls)} unique class URLs")
    return class_urls


# ──────────────────────────────────────────────────────────────────────
# Step 2 – Parse a single class page
# ──────────────────────────────────────────────────────────────────────

def _find_own_section_range(content, class_name: str):
    """Return (members_h2, methods_h2, end_element, inherited_classes)."""
    all_h2 = content.find_all("h2")
    all_h1 = content.find_all("h1")

    members_h2 = None
    methods_h2 = None
    for h2 in all_h2:
        headline = h2.find("span", class_="mw-headline")
        if not headline:
            continue
        text = headline.get_text(strip=True)
        if text == "Members" and members_h2 is None:
            members_h2 = h2
        elif text == "Methods" and methods_h2 is None:
            methods_h2 = h2

    inherited_classes = []
    end_element = None
    for h1 in all_h1:
        headline = h1.find("span", class_="mw-headline")
        if not headline:
            continue
        text = headline.get_text(strip=True)
        hid = headline.get("id", "")
        if hid.endswith("_Class") or text.endswith("Class"):
            inherited_name = text.replace(" Class", "").strip()
            if inherited_name and inherited_name != class_name:
                inherited_classes.append(inherited_name)
                if end_element is None:
                    end_element = h1

    return members_h2, methods_h2, end_element, inherited_classes


def parse_class_page(url: str, class_name: str) -> dict:
    """Parse a single class documentation page."""
    print(f"  [>] Scraping {class_name} from {url}")
    resp = SESSION.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    result = {
        "url": url, "description": "", "inherits": [],
        "members": {}, "methods": {},
    }

    content = soup.find("div", {"id": "mw-content-text"})
    if not content:
        print(f"    [!] No content found for {class_name}")
        return result

    first_p = content.find("p")
    if first_p:
        desc = _clean_text(first_p)
        result["description"] = desc[:300] + "..." if len(desc) > 300 else desc

    members_h2, methods_h2, end_element, inherited_classes = (
        _find_own_section_range(content, class_name)
    )
    result["inherits"] = inherited_classes

    if members_h2:
        stop = methods_h2 or end_element
        elements = _collect_siblings_until(members_h2, stop_tags={"h1", "h2"}, stop_el=stop)
        for entry in _parse_entries_from_elements(elements):
            result["members"][entry["name"]] = {
                "type": entry["returns"] or "unknown",
                "read_only": entry["read_only"],
                "description": entry["description"],
            }

    if methods_h2:
        elements = _collect_siblings_until(methods_h2, stop_tags={"h1", "h2"}, stop_el=end_element)
        for entry in _parse_entries_from_elements(elements):
            result["methods"][entry["name"]] = {
                "signature": entry["signature"],
                "returns": entry["returns"] or "unknown",
                "description": entry["description"],
            }

    return result


# ──────────────────────────────────────────────────────────────────────
# Step 3 – Parse the td Module page
# ──────────────────────────────────────────────────────────────────────

def parse_td_module() -> dict:
    """Parse the td Module page for global members and methods."""
    print(f"\n[*] Scraping td Module from {TD_MODULE_URL}")
    resp = SESSION.get(TD_MODULE_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    result = {
        "url": TD_MODULE_URL,
        "description": "The td module is automatically imported and provides "
                       "global access to TouchDesigner objects (me, op, ext, mod, etc.).",
        "members": {},
        "methods": {},
    }

    content = soup.find("div", {"id": "mw-content-text"})
    if not content:
        return result

    members_h2 = None
    methods_h2 = None
    for h2 in content.find_all("h2"):
        headline = h2.find("span", class_="mw-headline")
        if not headline:
            continue
        text = headline.get_text(strip=True)
        if text == "Members" and members_h2 is None:
            members_h2 = h2
        elif text == "Methods" and methods_h2 is None:
            methods_h2 = h2

    # Find the "Python Classes and Modules" h2 as end boundary
    end_el = None
    for h2 in content.find_all("h2"):
        headline = h2.find("span", class_="mw-headline")
        if headline and "Python Classes" in headline.get_text(strip=True):
            end_el = h2
            break

    if members_h2:
        stop = methods_h2 or end_el
        elements = _collect_siblings_until(members_h2, stop_tags={"h1"}, stop_el=stop)
        for entry in _parse_entries_from_elements(elements):
            if entry["is_method"]:
                result["methods"][entry["name"]] = {
                    "signature": entry["signature"],
                    "returns": entry["returns"] or "unknown",
                    "description": entry["description"],
                }
            else:
                result["members"][entry["name"]] = {
                    "type": entry["returns"] or "unknown",
                    "read_only": entry["read_only"],
                    "description": entry["description"],
                }

    if methods_h2:
        elements = _collect_siblings_until(methods_h2, stop_tags={"h1", "h2"}, stop_el=end_el)
        for entry in _parse_entries_from_elements(elements):
            result["methods"][entry["name"]] = {
                "signature": entry["signature"],
                "returns": entry["returns"] or "unknown",
                "description": entry["description"],
            }

    print(f"    ✓ Members: {len(result['members'])}, Methods: {len(result['methods'])}")
    return result


# ──────────────────────────────────────────────────────────────────────
# Step 4 – Parse utility module pages (TDFunctions, TDJSON, etc.)
# ──────────────────────────────────────────────────────────────────────

def parse_utility_module(name: str, url: str) -> dict:
    """Parse a utility module page for its functions.
    
    These pages use two different HTML patterns:
    1. Same as class pages: <code class="python"> + <code class="return">
    2. Classless: <p><code>funcName(args)</code> → <code>returnType</code>:</p>
    """
    print(f"  [>] Scraping {name} from {url}")
    resp = SESSION.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    result = {
        "url": url,
        "description": "",
        "functions": {},
    }

    content = soup.find("div", {"id": "mw-content-text"})
    if not content:
        return result

    # Get first paragraph as description
    first_p = content.find("p")
    if first_p:
        desc = _clean_text(first_p)
        result["description"] = desc[:300] + "..." if len(desc) > 300 else desc

    # Strategy: find all <p> tags that contain → (arrow) and have <code> children
    # This works for both class="python" and classless code elements
    seen_names = set()
    for p_tag in content.find_all("p"):
        p_text = p_tag.get_text()
        if "→" not in p_text and "\u2192" not in p_text:
            continue
        
        # Get the first <code> element (function signature)
        codes = p_tag.find_all("code")
        if not codes:
            continue
        
        sig_code = codes[0]
        sig = sig_code.get_text(strip=True)
        
        # Extract bare function name
        name_match = re.match(r"([a-zA-Z_]\w*)", sig)
        if not name_match:
            continue
        func_name = name_match.group(1)
        if func_name in seen_names:
            continue
        seen_names.add(func_name)
        
        # Try to get return type from the second <code> or from code.return
        returns = "unknown"
        ret_code = p_tag.find("code", class_="return")
        if ret_code:
            returns = ret_code.get_text(strip=True)
        elif len(codes) >= 2:
            returns = codes[1].get_text(strip=True)
        
        is_method = "(" in sig
        
        # Look for description in following <blockquote> or <ul>
        desc = ""
        next_el = p_tag.next_sibling
        while next_el:
            if isinstance(next_el, Tag):
                if next_el.name == "blockquote":
                    desc = _clean_text(next_el)[:500]
                    break
                if next_el.name == "ul":
                    desc = _clean_text(next_el)[:500]
                    break
                if next_el.name == "p" and ("→" in next_el.get_text() or "\u2192" in next_el.get_text()):
                    break  # next function entry
                if next_el.name in ("h1", "h2", "h3", "h4"):
                    break
            next_el = next_el.next_sibling
        
        result["functions"][func_name] = {
            "signature": sig,
            "returns": returns,
            "description": desc,
        }

    print(f"    ✓ Functions: {len(result['functions'])}")
    return result


# ──────────────────────────────────────────────────────────────────────
# Step 5 – Main pipeline
# ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("TouchDesigner Python API Scraper v2")
    print("=" * 60)

    # 1. Discover class URLs (operator + helper classes)
    class_urls = get_class_urls()

    # 2. Scrape each class
    classes = {}
    total = len(class_urls)
    for i, (class_name, url) in enumerate(sorted(class_urls.items()), 1):
        print(f"\n[{i}/{total}] {class_name}")
        try:
            class_data = parse_class_page(url, class_name)
            mc = len(class_data["members"])
            fc = len(class_data["methods"])
            inh = " → ".join(class_data["inherits"]) if class_data["inherits"] else "(base)"
            print(f"    ✓ Members: {mc}, Methods: {fc}, Inherits: {inh}")
            classes[class_name] = class_data
        except Exception as e:
            print(f"    ✗ ERROR: {e}")
            classes[class_name] = {
                "url": url, "description": "", "inherits": [],
                "members": {}, "methods": {}, "error": str(e),
            }
        if i < total:
            time.sleep(REQUEST_DELAY)

    # 3. Scrape td Module
    time.sleep(REQUEST_DELAY)
    td_module = parse_td_module()

    # 4. Scrape utility modules
    utility_modules = {}
    for name, url in sorted(UTILITY_MODULE_URLS.items()):
        time.sleep(REQUEST_DELAY)
        try:
            utility_modules[name] = parse_utility_module(name, url)
        except Exception as e:
            print(f"    ✗ ERROR: {e}")
            utility_modules[name] = {
                "url": url, "description": "", "functions": {},
                "error": str(e),
            }

    # 5. Build output
    output = {
        "metadata": {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "source": INDEX_URL,
            "class_count": len(classes),
            "total_members": sum(len(c["members"]) for c in classes.values()),
            "total_methods": sum(len(c["methods"]) for c in classes.values()),
            "utility_module_count": len(utility_modules),
            "total_utility_functions": sum(
                len(m["functions"]) for m in utility_modules.values()
            ),
            "td_module_members": len(td_module["members"]),
            "td_module_methods": len(td_module["methods"]),
        },
        "standard_imports": STANDARD_IMPORTS,
        "td_module": td_module,
        "utility_modules": utility_modules,
        "classes": classes,
    }

    # 6. Write JSON (to parent directory)
    output_path = os.path.join(os.path.dirname(__file__), "..", "td_python_api.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    m = output["metadata"]
    print("\n" + "=" * 60)
    print(f"Done! Wrote {output_path}")
    print(f"  Classes:            {m['class_count']}")
    print(f"  Total members:      {m['total_members']}")
    print(f"  Total methods:      {m['total_methods']}")
    print(f"  Utility modules:    {m['utility_module_count']}")
    print(f"  Utility functions:  {m['total_utility_functions']}")
    print(f"  td module members:  {m['td_module_members']}")
    print(f"  td module methods:  {m['td_module_methods']}")
    print(f"  Standard imports:   {', '.join(STANDARD_IMPORTS)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
