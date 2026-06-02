"""
main.py — Pipeline 主程式
串起：偵測 → 去重 → LLM 判讀 → Telegram 推送 → 更新 state
執行方式：python main.py
"""

import logging
import os
import sys
from datetime import datetime, timezone

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


def _journals_by_tier(journal_list, tier):
    """從 crossref / rss 設定清單中，挑出指定 tier 的期刊。"""
    return [j for j in journal_list if j.get("tier", "daily") == tier]


def _relevance_score(summary: str) -> int:
    """依判讀結果的【值得細讀】欄位給分，用於排序：高=3、中=2、低=1。"""
    if "值得細讀】高" in summary or "值得細讀】 高" in summary:
        return 3
    if "值得細讀】低" in summary or "值得細讀】 低" in summary:
        return 1
    return 2


def _select_top(papers, limit):
    """依相關度由高到低排序，取前 limit 篇（sorted 穩定，平手者維持原順序）。"""
    ranked = sorted(papers, key=lambda p: _relevance_score(p.get("summary", "")), reverse=True)
    return ranked[:limit]


def main():
    logger.info("=== paper-monitor 啟動 ===")

    # 1. 讀設定
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    config = load_config(config_path)
    state_file = config.get("state_file", "state.json")

    # 2. 讀已處理 ID
    seen_ids = load_seen_ids(state_file)
    logger.info(f"已知 {len(seen_ids)} 筆已處理 ID")

    # 判斷今天是否為「每週期刊」處理日
    selection = config.get("selection", {})
    weekly_weekday = selection.get("weekly_run_weekday", 0)
    is_weekly_day = datetime.now(timezone.utc).weekday() == weekly_weekday
    logger.info(f"今天 weekday={datetime.now(timezone.utc).weekday()}，每週期刊處理日={'是' if is_weekly_day else '否'}")

    # 3. 抓論文
    all_papers = []

    # arXiv（每天）
    arxiv_cfg = config.get("arxiv", {})
    arxiv_papers = fetch_arxiv(
        categories=arxiv_cfg.get("categories", ["math.OC"]),
        max_results=arxiv_cfg.get("max_results", 50),
    )
    all_papers.extend(arxiv_papers)

    # 期刊：依 tier 拆成每日 / 每週
    journals_cfg = config.get("journals", {})
    crossref_all = journals_cfg.get("crossref", [])
    rss_all = journals_cfg.get("rss", [])

    daily_lookback = config.get("crossref_lookback_days", 3)
    weekly_lookback = config.get("crossref_weekly_lookback_days", 7)

    # 每日期刊（每天抓）
    all_papers.extend(fetch_crossref(_journals_by_tier(crossref_all, "daily"), lookback_days=daily_lookback))
    all_papers.extend(fetch_rss(_journals_by_tier(rss_all, "daily")))

    # 每週期刊（只在每週指定那天抓，往前看一整週）
    weekly_journal_names = {j.get("name", "") for j in crossref_all if j.get("tier") == "weekly"}
    weekly_journal_names |= {j.get("name", "") for j in rss_all if j.get("tier") == "weekly"}
    if is_weekly_day:
        all_papers.extend(fetch_crossref(_journals_by_tier(crossref_all, "weekly"), lookback_days=weekly_lookback))
        all_papers.extend(fetch_rss(_journals_by_tier(rss_all, "weekly")))
    else:
        logger.info("今天非每週處理日，略過每週期刊。")

    logger.info(f"共抓到 {len(all_papers)} 篇（含重複）")

    # 4. 去重（跨來源 + 歷史）
    new_papers = filter_new(all_papers, seen_ids)
    logger.info(f"去重後：{len(new_papers)} 篇新論文")

    if not new_papers:
        logger.info("沒有新論文，結束。")
        return

    # 5. LLM 判讀（全部判讀，之後再分桶挑選）
    papers_with_summary = summarize_papers(new_papers, config, delay_seconds=0.5)

    # 6. 分桶 + 依相關度挑選
    #    桶一：arXiv；桶二：每日期刊；桶三：每週期刊
    arxiv_bucket, daily_bucket, weekly_bucket = [], [], []
    for p in papers_with_summary:
        if p.get("source") == "arxiv":
            arxiv_bucket.append(p)
        elif p.get("journal", "") in weekly_journal_names:
            weekly_bucket.append(p)
        else:
            daily_bucket.append(p)

    selected = []
    selected += _select_top(arxiv_bucket, selection.get("arxiv_daily_limit", 10))
    selected += _select_top(daily_bucket, selection.get("daily_journal_limit", 10))
    if is_weekly_day:
        selected += _select_top(weekly_bucket, selection.get("weekly_journal_limit", 10))
    logger.info(
        f"選取結果：arXiv {min(len(arxiv_bucket), selection.get('arxiv_daily_limit',10))} / "
        f"每日期刊 {min(len(daily_bucket), selection.get('daily_journal_limit',10))} / "
        f"每週期刊 {min(len(weekly_bucket), selection.get('weekly_journal_limit',10)) if is_weekly_day else 0} 篇"
    )

    # 7. Telegram 推送（只推送挑選出來的）
    notify_papers(selected, config)

    # 8. 更新 state（所有已判讀的新論文都記錄，避免明天重複判讀燒 token）
    mark_seen(new_papers, seen_ids)
    save_seen_ids(state_file, seen_ids)
    logger.info(f"state.json 已更新，現有 {len(seen_ids)} 筆")

    logger.info("=== paper-monitor 完成 ===")


if __name__ == "__main__":
    main()
