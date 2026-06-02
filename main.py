"""
main.py — Pipeline 主程式
串起：偵測 → 去重 → LLM 判讀 → Telegram 推送 → 更新 state
執行方式：python main.py
"""

import logging
import os
import sys

import yaml

from sources import fetch_arxiv, fetch_crossref, fetch_rss
from state import load_seen_ids, save_seen_ids, filter_new, mark_seen
from summarize import summarize_papers
from notify import notify_papers

# ----------------------------------------------------------------
# 設定 logging
# ----------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    logger.info("=== paper-monitor 啟動 ===")

    # 1. 讀設定
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    config = load_config(config_path)
    state_file = config.get("state_file", "state.json")

    # 2. 讀已處理 ID
    seen_ids = load_seen_ids(state_file)
    logger.info(f"已知 {len(seen_ids)} 筆已處理 ID")

    # 3. 抓論文
    all_papers = []

    # arXiv
    arxiv_cfg = config.get("arxiv", {})
    arxiv_papers = fetch_arxiv(
        categories=arxiv_cfg.get("categories", ["math.OC"]),
        max_results=arxiv_cfg.get("max_results", 50),
    )
    all_papers.extend(arxiv_papers)

    # Crossref（正式期刊，主力）
    journals_cfg = config.get("journals", {})
    crossref_journals = journals_cfg.get("crossref", [])
    lookback = config.get("crossref_lookback_days", 3)
    crossref_papers = fetch_crossref(crossref_journals, lookback_days=lookback)
    all_papers.extend(crossref_papers)

    # RSS（補充）
    rss_journals = journals_cfg.get("rss", [])
    rss_papers = fetch_rss(rss_journals)
    all_papers.extend(rss_papers)

    logger.info(f"共抓到 {len(all_papers)} 篇（含重複）")

    # 4. 去重（跨來源 + 歷史）
    new_papers = filter_new(all_papers, seen_ids)
    logger.info(f"去重後：{len(new_papers)} 篇新論文")

    if not new_papers:
        logger.info("沒有新論文，結束。")
        return

    # 5. LLM 判讀
    papers_with_summary = summarize_papers(new_papers, config)

    # 6. Telegram 推送
    notify_papers(papers_with_summary, config)

    # 7. 更新 state（不論推送是否成功都記錄，避免重複處理）
    mark_seen(new_papers, seen_ids)
    save_seen_ids(state_file, seen_ids)
    logger.info(f"state.json 已更新，現有 {len(seen_ids)} 筆")

    logger.info("=== paper-monitor 完成 ===")


if __name__ == "__main__":
    main()
