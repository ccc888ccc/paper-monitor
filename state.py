"""
state.py — 去重狀態管理
負責讀寫 state.json，記錄「已處理過的論文 ID」，避免重複推送。
ID 格式：arXiv 用 arXiv paper id（如 2401.12345），期刊用 DOI。
"""

import json
import os
from typing import Set


def load_seen_ids(state_file: str) -> Set[str]:
    """讀取已處理的 ID 集合。檔案不存在時回傳空集合。"""
    if not os.path.exists(state_file):
        return set()
    with open(state_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("seen_ids", []))


def save_seen_ids(state_file: str, seen_ids: Set[str]) -> None:
    """將 ID 集合寫回 state.json。"""
    data = {"seen_ids": sorted(seen_ids)}
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def filter_new(papers: list, seen_ids: Set[str]) -> list:
    """從 papers 列表中過濾掉已處理過的，回傳新論文列表。"""
    new_papers = []
    for paper in papers:
        pid = paper.get("id", "")
        if pid and pid not in seen_ids:
            new_papers.append(paper)
    return new_papers


def mark_seen(papers: list, seen_ids: Set[str]) -> None:
    """把 papers 的 ID 加入 seen_ids（in-place 修改）。"""
    for paper in papers:
        pid = paper.get("id", "")
        if pid:
            seen_ids.add(pid)
