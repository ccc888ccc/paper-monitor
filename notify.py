"""
notify.py — Telegram 推送
用 Telegram Bot API 推送每篇新論文的判讀結果。
環境變數：
  TELEGRAM_BOT_TOKEN  — BotFather 給的 token
  TELEGRAM_CHAT_ID    — 接收訊息的 chat id（個人或群組）
"""

import os
import logging
from typing import Dict, List

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _get_priority_emoji(summary: str, config: Dict) -> str:
    """根據判讀結果中的「值得細讀」欄位判斷 emoji。"""
    tg_cfg = config.get("telegram", {})
    summary_lower = summary.lower()
    if "值得細讀】高" in summary or "值得細讀】 高" in summary:
        return tg_cfg.get("high_priority_emoji", "🔥")
    elif "值得細讀】低" in summary or "值得細讀】 低" in summary:
        return tg_cfg.get("low_priority_emoji", "💤")
    else:
        return tg_cfg.get("medium_priority_emoji", "📄")


def _format_message(paper: Dict, config: Dict) -> str:
    """將一篇論文格式化成 Telegram 訊息（MarkdownV2）。"""
    emoji = _get_priority_emoji(paper.get("summary", ""), config)
    title = paper.get("title", "(無標題)")
    source = paper.get("source", "")
    journal = paper.get("journal", "")
    url = paper.get("url", "")
    summary = paper.get("summary", "(無判讀)")

    source_label = journal if journal else source.upper()

    # Telegram MarkdownV2 需要 escape 特殊字元，這裡用純文字模式（parse_mode 不傳）
    msg = (
        f"{emoji} [{source_label}]\n"
        f"📌 {title}\n"
        f"🔗 {url}\n"
        f"\n{summary}"
    )
    return msg


def send_message(token: str, chat_id: str, text: str) -> bool:
    """發送一則 Telegram 訊息，回傳是否成功。"""
    url = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        # 不用 MarkdownV2 以避免 escape 問題，純文字最穩
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except requests.HTTPError as e:
        logger.error(f"Telegram HTTP error: {e.response.status_code} {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False


def notify_heartbeat(config: Dict, note: str = "") -> bool:
    """
    沒有新論文時，仍推一則簡短回報，讓使用者每天都能確認排程正常運作。
    回傳是否成功。
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("未設定 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，跳過 heartbeat。")
        return False

    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    msg = f"✅ {today} 已檢查，今日無新論文。"
    if note:
        msg += f"\n{note}"
    return send_message(token, chat_id, msg)


def notify_papers(papers: List[Dict], config: Dict) -> int:
    """
    推送所有論文到 Telegram。
    回傳成功推送的數量。
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("未設定 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，跳過推送。")
        return 0

    tg_cfg = config.get("telegram", {})
    max_msgs = tg_cfg.get("max_messages_per_run", 20)

    papers_to_send = papers[:max_msgs]
    if len(papers) > max_msgs:
        logger.warning(f"本次新論文 {len(papers)} 篇，超過上限 {max_msgs}，只推送前 {max_msgs} 篇。")

    # 先發送一則摘要訊息
    if papers_to_send:
        summary_msg = f"📚 今日新論文：共 {len(papers)} 篇（推送 {len(papers_to_send)} 篇）"
        send_message(token, chat_id, summary_msg)

    sent = 0
    for paper in papers_to_send:
        msg = _format_message(paper, config)
        if send_message(token, chat_id, msg):
            sent += 1
        import time; time.sleep(0.3)  # 避免 Telegram rate limit（30 msg/sec）

    logger.info(f"Telegram: 推送 {sent}/{len(papers_to_send)} 則成功")
    return sent
