"""
summarize.py — LLM 判讀
呼叫 Google Gemini API，對每篇論文的 title + abstract 產生快速判讀。
API key 由環境變數 GEMINI_API_KEY 傳入。
免費方案：gemini-1.5-flash 每天 1500 次請求，對本 pipeline 完全夠用。
取得 API key：https://aistudio.google.com/app/apikey
"""

import os
import logging
import time
from typing import Dict

import requests

logger = logging.getLogger(__name__)

_MIN_ABSTRACT_LEN = 50
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def summarize_paper(paper: Dict, config: Dict) -> str:
    """
    對單篇論文呼叫 Gemini API，回傳判讀文字。
    paper:  包含 title / abstract 的 dict
    config: config.yaml 中的 llm 區塊
    回傳：判讀字串，或錯誤訊息字串。
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return "⚠️ 未設定 GEMINI_API_KEY，跳過 LLM 判讀。"

    title = paper.get("title", "(無標題)")
    abstract = paper.get("abstract", "").strip()

    if len(abstract) < _MIN_ABSTRACT_LEN:
        return "（摘要過短或不可用，無法判讀。請至原文確認。）"

    prompt_template = config.get("prompt", "請判讀以下論文：\n標題：{title}\n摘要：{abstract}")
    prompt = prompt_template.format(title=title, abstract=abstract)

    model = config.get("model", "gemini-1.5-flash")
    url = _GEMINI_URL.format(model=model) + f"?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": config.get("max_tokens", 400)},
    }

    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        logger.info(f"LLM summarized: {title[:50]}...")
        return result
    except requests.HTTPError as e:
        logger.error(f"Gemini API HTTP error: {e.response.status_code} {e.response.text}")
        return f"⚠️ LLM API 錯誤（{e.response.status_code}），跳過判讀。"
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return f"⚠️ LLM 發生錯誤：{e}"


def summarize_papers(papers: list, config: Dict, delay_seconds: float = 1.0) -> list:
    """
    批次對所有論文做判讀，回傳每個 paper dict 加上 "summary" 欄位。
    delay_seconds: 每次 API 呼叫間隔（避免超過 rate limit）
    """
    llm_config = config.get("llm", {})
    results = []
    for i, paper in enumerate(papers):
        logger.info(f"Summarizing {i+1}/{len(papers)}: {paper.get('title','')[:60]}")
        summary = summarize_paper(paper, llm_config)
        paper_with_summary = {**paper, "summary": summary}
        results.append(paper_with_summary)
        if i < len(papers) - 1:
            time.sleep(delay_seconds)
    return results
