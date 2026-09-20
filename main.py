import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import requests
from fastapi import FastAPI, Request

app = FastAPI(title="NAS100 Telegram Signal Server")

WAIT_SECONDS = 120 * 60

UTC = timezone.utc
KST = timezone(timedelta(hours=9))

BOT_TOKEN = os.getenv("BOT_TOKEN", "8899307951:AAHtgu2aW3ROCI-G7gwrp4glfaiD1vAycbY")
CHAT_ID = os.getenv("CHAT_ID", "2106941258,-1004483774716")

waiting = {
    "support": None,
    "resistance": None,
}


def now_utc():
    return datetime.now(UTC)


def kst_now_text():
    return now_utc().astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def send_telegram(direction: str):
    if direction not in ("BUY", "SELL"):
        return

    if not BOT_TOKEN or not CHAT_ID:
        print("[TELEGRAM] BOT_TOKEN 또는 CHAT_ID가 설정되지 않았습니다.")
        return

    if direction == "BUY":
        text = (
            "🟢 *NAS100 매수 진입 신호*\n\n"
            "NAS 지지구간 확인\n"
            "매수세력감지 확인\n\n"
            f"⏰ 시간: {kst_now_text()}"
        )
    else:
        text = (
            "🔴 *NAS100 매도 진입 신호*\n\n"
            "NAS 저항구간 확인\n"
            "매도세력감지 확인\n\n"
            f"⏰ 시간: {kst_now_text()}"
        )

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
        print(f"[TELEGRAM] {response.status_code}")
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")


def parse_message(message: str) -> Optional[Tuple[str, str]]:
    normalized = re.sub(
        r"[^A-Z0-9가-힣_]",
        "",
        message.upper(),
    )

    if normalized.startswith("BTC"):
        return None

    if "매수세력빠짐" in normalized:
        return None

    if "매도세력빠짐" in normalized:
        return None

    if "매수세력감지" in normalized:
        return "NAS", "buy_force"

    if "매도세력감지" in normalized:
        return "NAS", "sell_force"

    if normalized.startswith("NAS지지구간생성"):
        return "NAS", "support"

    if normalized.startswith("NAS지지구간진입"):
        return "NAS", "support"

    if normalized.startswith("NAS저항구간생성"):
        return "NAS", "resistance"

    if normalized.startswith("NAS저항구간진입"):
        return "NAS", "resistance"

    if normalized.startswith("NAS_지지구간"):
        return "NAS", "support"

    if normalized.startswith("NAS_저항구간"):
        return "NAS", "resistance"

    return None


def waiting_valid(timestamp):
    if timestamp is None:
        return False

    return now_utc() - timestamp <= timedelta(seconds=WAIT_SECONDS)


def cleanup_waiting():
    if waiting["support"] is not None:
        if not waiting_valid(waiting["support"]):
            waiting["support"] = None
            print("[WAIT EXPIRED] NAS BUY")

    if waiting["resistance"] is not None:
        if not waiting_valid(waiting["resistance"]):
            waiting["resistance"] = None
            print("[WAIT EXPIRED] NAS SELL")


@app.post("/webhook")
async def tradingview_webhook(request: Request):
    raw_body = await request.body()

    message = raw_body.decode(
        "utf-8",
        errors="replace",
    ).strip()

    print(f"\n[WEBHOOK RECEIVED] {message}")

    parsed = parse_message(message)

    if parsed is None:
        return {
            "status": "ignored",
            "message": message,
            "kst": kst_now_text(),
        }

    symbol, event = parsed

    if symbol != "NAS":
        return {
            "status": "ignored",
            "reason": "non_nas_symbol",
            "message": message,
            "kst": kst_now_text(),
        }

    cleanup_waiting()

    if event == "support":
        waiting["support"] = now_utc()

        print("[WAIT BUY] NAS 지지구간 → 120분 시작/갱신")

        return {
            "status": "waiting",
            "symbol": "NAS",
            "direction": "BUY",
            "wait_seconds": WAIT_SECONDS,
            "kst": kst_now_text(),
        }

    if event == "resistance":
        waiting["resistance"] = now_utc()

        print("[WAIT SELL] NAS 저항구간 → 120분 시작/갱신")

        return {
            "status": "waiting",
            "symbol": "NAS",
            "direction": "SELL",
            "wait_seconds": WAIT_SECONDS,
            "kst": kst_now_text(),
        }

    if event == "buy_force":
        if not waiting_valid(waiting["support"]):
            waiting["support"] = None

            print("[BUY IGNORED] NAS BUY 대기 없음 또는 120분 만료")

            return {
                "status": "ignored",
                "reason": "no_valid_buy_waiting",
                "symbol": "NAS",
                "kst": kst_now_text(),
            }

        waiting["support"] = None

        print("[BUY FINAL] NAS100")
        send_telegram("BUY")

        return {
            "status": "telegram_signal",
            "symbol": "NAS",
            "direction": "BUY",
            "reason": "support_then_buy_force",
            "kst": kst_now_text(),
        }

    if event == "sell_force":
        if not waiting_valid(waiting["resistance"]):
            waiting["resistance"] = None

            print("[SELL IGNORED] NAS SELL 대기 없음 또는 120분 만료")

            return {
                "status": "ignored",
                "reason": "no_valid_sell_waiting",
                "symbol": "NAS",
                "kst": kst_now_text(),
            }

        waiting["resistance"] = None

        print("[SELL FINAL] NAS100")
        send_telegram("SELL")

        return {
            "status": "telegram_signal",
            "symbol": "NAS",
            "direction": "SELL",
            "reason": "resistance_then_sell_force",
            "kst": kst_now_text(),
        }

    return {
        "status": "ignored",
        "reason": "unknown_event",
        "symbol": "NAS",
        "event": event,
        "kst": kst_now_text(),
    }


@app.get("/waiting")
def get_waiting():
    cleanup_waiting()

    buy_remaining = 0
    sell_remaining = 0

    if waiting["support"] is not None:
        buy_remaining = max(
            0,
            int(
                WAIT_SECONDS
                - (now_utc() - waiting["support"]).total_seconds()
            ),
        )

    if waiting["resistance"] is not None:
        sell_remaining = max(
            0,
            int(
                WAIT_SECONDS
                - (now_utc() - waiting["resistance"]).total_seconds()
            ),
        )

    return {
        "symbol": "NAS",
        "buy_waiting": waiting["support"] is not None,
        "buy_remaining_seconds": buy_remaining,
        "buy_remaining_minutes": round(buy_remaining / 60, 1),
        "sell_waiting": waiting["resistance"] is not None,
        "sell_remaining_seconds": sell_remaining,
        "sell_remaining_minutes": round(sell_remaining / 60, 1),
        "kst": kst_now_text(),
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "system": "NAS100 TELEGRAM ONLY",
        "wait_minutes": WAIT_SECONDS // 60,
        "telegram": bool(BOT_TOKEN and CHAT_ID),
        "kst": kst_now_text(),
    }
