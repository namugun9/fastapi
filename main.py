```python
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone, timedelta
import requests


# =========================================================
# [1] 기본 설정
# =========================================================

app = FastAPI()

KST = timezone(timedelta(hours=9))

# 텔레그램
BOT_TOKEN = "8899307951:AAGg39IiF-CvYj6w3065UcspJxtJU1wKng0"
CHAT_ID = "2106941258"

# SMR 신호가 계속 들어올 때
# 마지막 신호를 기준으로 10분 동안 0선 돌파 대기
WAIT_SECONDS = 10 * 60


# =========================================================
# [2] NAS / BTC 대기 상태
# =========================================================

nas_waiting = {
    "active": False,
    "direction": None,      # BUY / SELL
    "timestamp": None       # 마지막 SMR 신호 시간
}

btc_waiting = {
    "active": False,
    "direction": None,
    "timestamp": None
}


# =========================================================
# [3] 신호 기록
# =========================================================

signals_history = {
    "NAS": [],
    "BTC": []
}


# =========================================================
# [4] 텔레그램 전송
# =========================================================

def send_telegram_signal(action, symbol):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    if action == "BUY":
        emoji = "🟢"
        action_text = "매수"
    else:
        emoji = "🔴"
        action_text = "매도"

    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    text = (
        f"{emoji} **[{symbol} {action_text} 신호]**\n\n"
        f"SMR 확인\n"
        f"0선 돌파 발생\n\n"
        f"⏰ 시간: {now} KST"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        print("Telegram:", response.status_code)

    except Exception as e:
        print("Telegram Error:", e)


# =========================================================
# [5] 최종 매매 신호
# =========================================================

def create_final_signal(symbol, direction):

    print(
        f"🔥 최종 신호 발생 → "
        f"{symbol} / {direction}"
    )

    signals_history[symbol].append({
        "time": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "direction": direction
    })

    send_telegram_signal(
        direction,
        "NAS100" if symbol == "NAS" else "BTC"
    )


# =========================================================
# [6] SMR 대기 시작 / 갱신
# =========================================================

def start_waiting(symbol, direction):

    # 기존 대기 상태가 10분을 넘었으면 먼저 만료 처리
    check_timeout(symbol)

    now = datetime.now(KST)

    if symbol == "NAS":
        waiting = nas_waiting
    else:
        waiting = btc_waiting

    # -----------------------------------------------------
    # 같은 종목 + 같은 방향의 SMR
    # → 마지막 신호 시간으로 10분을 다시 시작
    # -----------------------------------------------------

    if waiting["active"] and waiting["direction"] == direction:

        waiting["timestamp"] = now

        print(
            f"🔄 {symbol} {direction} SMR 추가 발생"
        )

        print(
            f"⏱ 마지막 신호 기준 10분 대기 갱신"
        )

        return

    # -----------------------------------------------------
    # 새로운 방향의 SMR
    # -----------------------------------------------------

    waiting["active"] = True
    waiting["direction"] = direction
    waiting["timestamp"] = now

    print(
        f"⏳ {symbol} {direction} 대기 시작"
    )

    print(
        f"⏰ 기준 시간: "
        f"{now.strftime('%H:%M:%S')} KST"
    )


# =========================================================
# [7] 10분 시간 초과 확인
# =========================================================

def check_timeout(symbol):

    if symbol == "NAS":
        waiting = nas_waiting
    else:
        waiting = btc_waiting

    if not waiting["active"]:
        return False

    now = datetime.now(KST)

    elapsed = (
        now - waiting["timestamp"]
    ).total_seconds()

    if elapsed >= WAIT_SECONDS:

        print(
            f"⌛ {symbol} "
            f"{waiting['direction']} 대기시간 종료"
        )

        waiting["active"] = False
        waiting["direction"] = None
        waiting["timestamp"] = None

        return True

    return False


# =========================================================
# [8] 0선 돌파 처리
# =========================================================

def process_zero_cross(symbol):

    if symbol == "NAS":
        waiting = nas_waiting
    else:
        waiting = btc_waiting

    # SMR이 먼저 발생하지 않았다면 무시
    if not waiting["active"]:

        print(
            f"⚪ {symbol} 0선 돌파 → "
            f"SMR 대기 없음. 무시"
        )

        return {
            "status": "ignored",
            "reason": "no_smr_waiting"
        }

    # 10분 초과 여부 확인
    if check_timeout(symbol):

        print(
            f"⚪ {symbol} 0선 돌파 → "
            f"10분 초과. 무시"
        )

        return {
            "status": "ignored",
            "reason": "waiting_expired"
        }

    # 현재 방향 저장
    direction = waiting["direction"]

    # 최종 신호 발생
    create_final_signal(
        symbol,
        direction
    )

    # 대기 상태 초기화
    waiting["active"] = False
    waiting["direction"] = None
    waiting["timestamp"] = None

    print(
        f"✅ {symbol} 최종 {direction} 신호 완료"
    )

    return {
        "status": "final_signal",
        "symbol": symbol,
        "direction": direction
    }


# =========================================================
# [9] TradingView 웹훅
# =========================================================

@app.post("/webhook")
async def webhook(request: Request):

    body = await request.body()

    message = body.decode(
        "utf-8",
        errors="ignore"
    ).strip()

    print("\n==============================")
    print("📩 TradingView 수신")
    print(message)
    print("==============================")

    upper_message = message.upper()


    # =====================================================
    # NAS
    # =====================================================

    if "NAS" in upper_message:

        # NAS 0선 돌파
        if "NAS100 0선 돌파" in message:

            result = process_zero_cross("NAS")

            return result

        # NAS 지지 → BUY 대기
        if (
            "지지구간 생성" in message
            or
            "지지구간 진입" in message
        ):

            start_waiting("NAS", "BUY")

            return {
                "status": "waiting",
                "symbol": "NAS",
                "direction": "BUY"
            }

        # NAS 저항 → SELL 대기
        if (
            "저항구간 생성" in message
            or
            "저항구간 진입" in message
        ):

            start_waiting("NAS", "SELL")

            return {
                "status": "waiting",
                "symbol": "NAS",
                "direction": "SELL"
            }

        return {
            "status": "ignored",
            "reason": "NAS_unknown_signal"
        }


    # =====================================================
    # BTC
    # =====================================================

    if "BTC" in upper_message:

        # BTC 0선 돌파
        if "BTC 0선 돌파" in message:

            result = process_zero_cross("BTC")

            return result

        # BTC 지지 → BUY 대기
        if (
            "지지구간 생성" in message
            or
            "지지구간 진입" in message
        ):

            start_waiting("BTC", "BUY")

            return {
                "status": "waiting",
                "symbol": "BTC",
                "direction": "BUY"
            }

        # BTC 저항 → SELL 대기
        if (
            "저항구간 생성" in message
            or
            "저항구간 진입" in message
        ):

            start_waiting("BTC", "SELL")

            return {
                "status": "waiting",
                "symbol": "BTC",
                "direction": "SELL"
            }

        return {
            "status": "ignored",
            "reason": "BTC_unknown_signal"
        }


    # =====================================================
    # 종목 태그 없음
    # =====================================================

    return {
        "status": "ignored",
        "reason": "no_symbol_tag"
    }


# =========================================================
# [10] 현재 대기 상태 확인
# =========================================================

@app.get("/waiting/{symbol}")
def get_waiting(symbol: str):

    symbol = symbol.upper()

    if symbol == "NAS":
        waiting = nas_waiting

    elif symbol == "BTC":
        waiting = btc_waiting

    else:
        return {
            "status": "error",
            "reason": "unknown_symbol"
        }

    return {
        "symbol": symbol,
        "active": waiting["active"],
        "direction": waiting["direction"],
        "timestamp": (
            waiting["timestamp"].strftime(
                "%Y-%m-%d %H:%M:%S KST"
            )
            if waiting["timestamp"]
            else None
        )
    }


# =========================================================
# [11] 신호 기록 확인
# =========================================================

@app.get("/signal/{symbol}")
def get_signal(symbol: str):

    symbol = symbol.upper()

    if symbol not in signals_history:

        return {
            "status": "error",
            "reason": "unknown_symbol"
        }

    return {
        "symbol": symbol,
        "signals": signals_history[symbol]
    }


# =========================================================
# [12] 정적 파일
# =========================================================

try:

    app.mount(
        "/",
        StaticFiles(
            directory="static",
            html=True
        ),
        name="static"
    )

except Exception:

    pass
```
