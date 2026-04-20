"""Phase 1: Website crawl with structured data extraction.

Fetches known domains, discovers sub-pages from navigation, and extracts
both structured data (JSON-LD, OpenGraph, meta tags) and clean text.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_client: httpx.Client | None = None

_BLOCKED_HOSTS = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0", "[::1]",
    "metadata.google.internal", "169.254.169.254",
})


def _is_safe_url(url: str) -> bool:
    """Reject URLs targeting internal/metadata endpoints."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host in _BLOCKED_HOSTS:
        return False
    if host.endswith(".internal") or host.endswith(".local"):
        return False
    parts = host.split(".")
    if len(parts) == 4:
        try:
            octets = [int(p) for p in parts]
            if octets[0] == 10:
                return False
            if octets[0] == 172 and 16 <= octets[1] <= 31:
                return False
            if octets[0] == 192 and octets[1] == 168:
                return False
        except (ValueError, IndexError):
            pass
    return True


PRIORITY_PATHS = [
    "", "/about", "/about-us", "/company", "/team", "/leadership",
    "/pricing", "/products", "/services", "/solutions",
    "/careers", "/jobs", "/press", "/newsroom", "/blog",
    "/investors", "/partners", "/customers", "/case-studies",
    "/contact", "/integrations", "/platform",
]

MAX_PAGES_PER_DOMAIN = 20
PAGE_TEXT_LIMIT = 6000
NAV_LINK_LIMIT = 30


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "ArcflareBot/1.0 (org-research)"},
        )
    return _client


@dataclass
class StructuredData:
    json_ld: list[dict] = field(default_factory=list)
    og_tags: dict = field(default_factory=dict)
    meta_description: str = ""
    meta_keywords: str = ""
    social_links: dict = field(default_factory=dict)


@dataclass
class CrawledPage:
    url: str
    title: str
    text: str
    structured_data: StructuredData
    page_type: str
    status_code: int = 200


def _extract_structured_data(soup: BeautifulSoup, url: str) -> StructuredData:
    """Extract JSON-LD, OpenGraph, meta tags, and social links."""
    data = StructuredData()

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            parsed = json.loads(script.string or "")
            if isinstance(parsed, list):
                data.json_ld.extend(parsed)
            elif isinstance(parsed, dict):
                data.json_ld.append(parsed)
        except (json.JSONDecodeError, TypeError):
            continue

    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        content = meta.get("content", "")
        if not content:
            continue
        if prop.startswith("og:"):
            data.og_tags[prop[3:]] = content
        elif prop == "description":
            data.meta_description = content
        elif prop == "keywords":
            data.meta_keywords = content
        elif prop in ("twitter:site", "twitter:creator"):
            data.social_links["twitter"] = content

    social_patterns = {
        "linkedin": re.compile(r"linkedin\.com/(company|in)/[\w-]+", re.I),
        "twitter": re.compile(r"(twitter|x)\.com/\w+", re.I),
        "facebook": re.compile(r"facebook\.com/[\w.]+", re.I),
        "github": re.compile(r"github\.com/[\w-]+", re.I),
        "youtube": re.compile(r"youtube\.com/(c|channel|@)[\w-]+", re.I),
    }
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        for platform, pattern in social_patterns.items():
            if platform not in data.social_links and pattern.search(href):
                data.social_links[platform] = href
                break

    return data


def _classify_page(path: str, title: str) -> str:
    """Classify a page by its path and title."""
    path_lower = path.lower().rstrip("/")
    title_lower = title.lower()

    mapping = {
        "about": ("about", "company", "who-we-are", "our-story"),
        "team": ("team", "leadership", "management", "people", "executives"),
        "pricing": ("pricing", "plans", "packages"),
        "products": ("products", "services", "solutions", "platform", "features"),
        "careers": ("careers", "jobs", "hiring", "work-with-us"),
        "press": ("press", "news", "newsroom", "media"),
        "blog": ("blog", "articles", "resources", "insights"),
        "investors": ("investors", "investor-relations", "ir"),
        "partners": ("partners", "partnerships", "integrations"),
        "customers": ("customers", "case-studies", "testimonials", "success-stories"),
        "contact": ("contact", "get-in-touch"),
    }
    for page_type, keywords in mapping.items():
        for kw in keywords:
            if kw in path_lower or kw in title_lower:
                return page_type

    return "homepage" if path_lower in ("", "/") else "other"


def _clean_text(soup: BeautifulSoup) -> str:
    """Extract readable text, stripping boilerplate."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                     "form", "noscript", "iframe", "svg"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    clean = "\n".join(lines)
    return clean[:PAGE_TEXT_LIMIT]


def _discover_nav_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Find internal links from navigation elements and main content."""
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc
    links: list[str] = []
    seen: set[str] = set()

    nav_elements = soup.find_all(["nav"]) or []
    containers = nav_elements + [soup.find("main") or soup.find("body") or soup]

    for container in containers[:3]:
        for a_tag in container.find_all("a", href=True):
            href = a_tag["href"]
            if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
                continue

            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)

            if parsed.netloc != base_domain:
                continue

            path = parsed.path.rstrip("/")
            if path in seen or not path:
                continue

            skip_extensions = (".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg",
                               ".css", ".js", ".xml", ".zip", ".doc", ".docx")
            if any(path.lower().endswith(ext) for ext in skip_extensions):
                continue

            seen.add(path)
            links.append(full_url)

            if len(links) >= NAV_LINK_LIMIT:
                break

    return links


def _fetch_page(url: str) -> CrawledPage | None:
    """Fetch a single page and return structured + text content."""
    if not _is_safe_url(url):
        logger.debug("crawl_blocked_unsafe url=%s", url[:80])
        return None
    try:
        resp = _get_client().get(url)
        if resp.status_code >= 400:
            logger.debug("crawl_skip url=%s status=%d", url[:80], resp.status_code)
            return None
    except Exception as e:
        logger.warning("crawl_fetch_failed url=%s error=%s", url[:80], e)
        return None

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    path = urlparse(url).path

    structured = _extract_structured_data(soup, url)
    text = _clean_text(soup)

    if len(text) < 50:
        return None

    return CrawledPage(
        url=url,
        title=title,
        text=text,
        structured_data=structured,
        page_type=_classify_page(path, title),
        status_code=resp.status_code,
    )


def crawl_domains(domains: list[str]) -> list[CrawledPage]:
    """Crawl all provided domains. Returns deduplicated pages sorted by relevance.

    Strategy:
    1. For each domain, fetch the homepage first
    2. Try priority paths (about, team, pricing, etc.)
    3. Discover additional pages from navigation links
    4. Deduplicate by URL
    """
    all_pages: list[CrawledPage] = []
    seen_urls: set[str] = set()

    for domain in domains:
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        base = domain.rstrip("/")
        domain_pages: list[CrawledPage] = []

        if not _is_safe_url(base):
            logger.warning("crawl_blocked_unsafe domain=%s", base)
            continue

        try:
            resp = _get_client().get(base)
        except Exception as e:
            logger.warning("crawl_homepage_failed domain=%s error=%s", base, e)
            continue

        if resp.status_code >= 400:
            logger.warning("crawl_homepage_failed domain=%s status=%d", base, resp.status_code)
            continue

        homepage_soup = BeautifulSoup(resp.text, "lxml")
        title_tag = homepage_soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""
        structured = _extract_structured_data(homepage_soup, base)
        text = _clean_text(homepage_soup)

        if text and len(text) >= 50:
            homepage = CrawledPage(
                url=base, title=title, text=text,
                structured_data=structured,
                page_type="homepage", status_code=resp.status_code,
            )
            seen_urls.add(base)
            domain_pages.append(homepage)

        nav_links = _discover_nav_links(homepage_soup, base)

        for path in PRIORITY_PATHS[1:]:
            if len(domain_pages) >= MAX_PAGES_PER_DOMAIN:
                break
            url = f"{base}{path}"
            if url in seen_urls:
                continue
            page = _fetch_page(url)
            if page:
                seen_urls.add(url)
                domain_pages.append(page)

        for link_url in nav_links:
            if len(domain_pages) >= MAX_PAGES_PER_DOMAIN:
                break
            normalized = link_url.split("?")[0].split("#")[0]
            if normalized in seen_urls:
                continue
            page = _fetch_page(link_url)
            if page:
                seen_urls.add(normalized)
                domain_pages.append(page)

        logger.info(
            "crawl_complete domain=%s pages=%d",
            base, len(domain_pages),
        )
        all_pages.extend(domain_pages)

    return all_pages


def extract_structured_profile_hints(pages: list[CrawledPage]) -> dict:
    """Extract quick-win profile data from structured data across all pages.

    This pulls facts from JSON-LD, OpenGraph, and meta tags without any LLM cost.
    Returns a dict of hints that can seed the profile assembly.
    """
    hints: dict = {
        "names": set(),
        "descriptions": [],
        "social_links": {},
        "logos": [],
        "emails": set(),
        "phones": set(),
    }

    for page in pages:
        sd = page.structured_data

        for ld in sd.json_ld:
            ld_type = ld.get("@type", "")
            types = ld_type if isinstance(ld_type, list) else [ld_type]

            if any(t in ("Organization", "Corporation", "LocalBusiness",
                         "WebSite", "Company") for t in types):
                if ld.get("name"):
                    hints["names"].add(ld["name"])
                if ld.get("description"):
                    hints["descriptions"].append(ld["description"])
                if ld.get("logo"):
                    logo = ld["logo"]
                    if isinstance(logo, dict):
                        logo = logo.get("url", "")
                    if logo:
                        hints["logos"].append(logo)
                if ld.get("email"):
                    hints["emails"].add(ld["email"])
                if ld.get("telephone"):
                    hints["phones"].add(ld["telephone"])
                if ld.get("sameAs"):
                    same_as = ld["sameAs"]
                    if isinstance(same_as, str):
                        same_as = [same_as]
                    for link in same_as:
                        for platform in ("linkedin", "twitter", "facebook", "github"):
                            if platform in link.lower():
                                hints["social_links"][platform] = link

        hints["social_links"].update(sd.social_links)

        if sd.og_tags.get("site_name"):
            hints["names"].add(sd.og_tags["site_name"])
        if sd.og_tags.get("description"):
            hints["descriptions"].append(sd.og_tags["description"])

        if sd.meta_description:
            hints["descriptions"].append(sd.meta_description)

    hints["names"] = list(hints["names"])
    hints["emails"] = list(hints["emails"])
    hints["phones"] = list(hints["phones"])

    return hints
