"""
sources.py — 論文來源抓取
支援三種來源：
  1. arXiv Atom feed（官方 API）
  2. Crossref API（用 ISSN 查近期新 DOI）
  3. 期刊 RSS feed（補充，即時性較好）
每篇論文統一回傳 dict：
  {
    "id":       str,   # arXiv id 或 DOI（去重用）
    "title":    str,
    "abstract": str,
    "authors":  str,   # 逗號分隔
    "url":      str,   # 論文連結
    "source":   str,   # "arxiv" / "crossref" / "rss"
    "journal":  str,   # 期刊名稱（arXiv 為空字串）
  }
"""

import time
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict

import feedparser
import requests

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# arXiv
# ----------------------------------------------------------------

def fetch_arxiv(categories: List[str], max_results: int = 50) -> List[Dict]:
    """
    用 arXiv Atom feed API 抓最新論文。
    categories: 如 ["math.OC", "cs.LG"]
    """
    papers = []
    search_query = " OR ".join(f"cat:{c}" for c in categories)
    url = (
        "https://export.arxiv.org/api/query"
        f"?search_query={search_query}"
        f"&sortBy=submittedDate&sortOrder=descending"
        f"&max_results={max_results}"
    )
    logger.info(f"Fetching arXiv: {url}")
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            arxiv_id = entry.get("id", "").split("/abs/")[-1].strip()
            abstract = entry.get("summary", "").replace("\n", " ").strip()
            authors = ", ".join(
                a.get("name", "") for a in entry.get("authors", [])
            )
            papers.append({
                "id": arxiv_id,
                "title": entry.get("title", "").replace("\n", " ").strip(),
                "abstract": abstract,
                "authors": authors,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "source": "arxiv",
                "journal": "",
            })
        logger.info(f"arXiv: got {len(papers)} papers")
    except Exception as e:
        logger.error(f"arXiv fetch error: {e}")
    return papers


# ----------------------------------------------------------------
# Crossref
# ----------------------------------------------------------------

def fetch_crossref(journals: List[Dict], lookback_days: int = 3) -> List[Dict]:
    """
    用 Crossref API 查各期刊近 lookback_days 天的新 DOI。
    journals: [{"name": ..., "issn": ...}, ...]
    Crossref 只提供 metadata（無 abstract），abstract 欄位設為空字串。
    注意：Crossref 的 abstract 覆蓋率低，有時會是空的。
    """
    papers = []
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    for journal in journals:
        issn = journal.get("issn", "").strip()
        name = journal.get("name", "")
        if not issn:
            continue
        url = (
            f"https://api.crossref.org/journals/{issn}/works"
            f"?filter=from-pub-date:{since}"
            f"&sort=published&order=desc&rows=50"
            f"&select=DOI,title,author,abstract,URL,published"
        )
        headers = {"User-Agent": "paper-monitor/1.0 (mailto:your-email@example.com)"}
        logger.info(f"Fetching Crossref for {name} (ISSN {issn})")
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            items = resp.json().get("message", {}).get("items", [])
            for item in items:
                doi = item.get("DOI", "").strip()
                if not doi:
                    continue
                title_list = item.get("title", [])
                title = title_list[0] if title_list else ""
                abstract = item.get("abstract", "")
                # Crossref abstract 有時包含 <jats:p> HTML 標籤，做簡單清理
                abstract = _strip_jats(abstract)
                authors_raw = item.get("author", [])
                authors = ", ".join(
                    f"{a.get('given','')} {a.get('family','')}".strip()
                    for a in authors_raw
                )
                paper_url = item.get("URL", f"https://doi.org/{doi}")
                papers.append({
                    "id": doi,
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "url": paper_url,
                    "source": "crossref",
                    "journal": name,
                })
            logger.info(f"Crossref {name}: got {len(items)} papers")
            time.sleep(0.5)  # 對 Crossref 友善，避免 rate limit
        except Exception as e:
            logger.error(f"Crossref fetch error ({name}): {e}")
    return papers


def _strip_jats(text: str) -> str:
    """移除 Crossref abstract 裡的 JATS XML 標籤。"""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


# ----------------------------------------------------------------
# RSS
# ----------------------------------------------------------------

def fetch_rss(journals: List[Dict]) -> List[Dict]:
    """
    用期刊官方 RSS feed 抓新論文（補充 Crossref）。
    journals: [{"name": ..., "url": ...}, ...]
    url 為空字串時跳過。
    """
    papers = []
    for journal in journals:
        rss_url = journal.get("url", "").strip()
        name = journal.get("name", "")
        if not rss_url:
            continue
        logger.info(f"Fetching RSS for {name}: {rss_url}")
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                # 盡量取 DOI 當 id，沒有就用連結
                doi = entry.get("prism_doi", "") or entry.get("dc_identifier", "")
                entry_id = doi.strip() if doi else entry.get("link", "").strip()
                if not entry_id:
                    continue
                abstract = entry.get("summary", "").replace("\n", " ").strip()
                papers.append({
                    "id": entry_id,
                    "title": entry.get("title", "").strip(),
                    "abstract": abstract,
                    "authors": "",
                    "url": entry.get("link", ""),
                    "source": "rss",
                    "journal": name,
                })
            logger.info(f"RSS {name}: got {len(feed.entries)} entries")
        except Exception as e:
            logger.error(f"RSS fetch error ({name}): {e}")
    return papers
