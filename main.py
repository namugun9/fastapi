from fastapi import FastAPI, Request
from datetime import datetime, timezone, timedelta
import requests


# =========================================================
# [1] 기본 설정
# =========================================================

app = FastAPI()

KST = timezone(timedelta(hours=9))

# 텔레그램
# 반드시 새로 발급받은 BOT_TOKEN 입력
BOT_TOKEN = "8899307951:AAHtgu2aW3ROCI-G7gwrp4glfaiD1vAycbY"
CHAT_ID = "2106941258"

# 매매 대기시간
WAIT_SECONDS = 20 * 60


# =========================================================
# [2] 매매시간
# =========================================================
# 08:00 ~ 21:00
# 22:35 ~ 05:00
#
# CLOSE(청산)는 24시간 허용
# =========================================================

def is_trade_time_kst():
    now = datetime.now(KST)

    current_minutes = now.hour * 60 + now.minute

    # 08:00 ~ 21:00
    if 8 * 60 <= current_minutes < 21 * 60:
        return True

    # 22:35 ~ 05:00
    if current_minutes >= 22 * 60 + 35 or current_minutes < 5 * 60:
        return True

    return False


def kst_now_text():
    return datetime.now(KST).strftime(
        "%Y-%m-%d %H:%M:%S KST"
    )


# =========================================================
# [3] NAS / BTC 대기 상태
# =========================================================

nas_buy_waiting = {
    "support": None,
    "up": None
}

nas_sell_waiting = {
    "resistance": None,
    "down": None
}

btc_waiting = {
    "active": False,
    "direction": None,
    "timestamp": None
}


# =========================================================
# [4] NAS / BTC 현재 포지션 상태
# =========================================================

nas_position = None
btc_position = None


# =========================================================
# [5] 최종 신호 기록
# =========================================================

signals_history = {
    "NAS": [],
    "BTC": []
}


# =========================================================
# [6] 텔레그램 전송
# =========================================================

def send_telegram_signal(action, symbol):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    now = datetime.now(KST).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    if action == "BUY":

        text = (
            f"🟢 **{symbol} 매수 신호**\n\n"
            f"{symbol} 지지구간 확인\n"
            f"매수세 유입 발생\n\n"
            f"⏰ 시간: {now} KST"
        )

    elif action == "SELL":

        text = (
            f"🔴 **{symbol} 매도 신호**\n\n"
            f"{symbol} 저항구간 확인\n"
            f"매도세 유입 발생\n\n"
            f"⏰ 시간: {now} KST"
        )

    elif action == "CLOSE":

        text = (
            f"⚪ **{symbol} 청산**\n\n"
            f"{symbol} 포지션 청산\n\n"
            f"⏰ 시간: {now} KST"
        )

    else:
        return

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

        print(
            f"Telegram: "
            f"{response.status_code}"
        )

    except Exception as e:

        print(
            f"Telegram Error: {e}"
        )


# =========================================================
# [7] 최종 매매 신호
# =========================================================

def create_final_signal(symbol, direction):

    global nas_position
    global btc_position

    # =====================================================
    # BUY / SELL은 매매시간 외 완전 차단
    # =====================================================

    if direction in ("BUY", "SELL"):

        if not is_trade_time_kst():

            print(
                f"🚫 매매시간 외 최종 {direction} 차단 "
                f"→ {symbol}"
            )

            return {
                "status": "ignored",
                "reason": "outside_trading_hours",
                "symbol": symbol,
                "direction": direction
            }

    print(
        f"🔥 최종 신호 발생 → "
        f"{symbol} / {direction}"
    )

    # 포지션 상태 저장
    if symbol == "NAS":
        nas_position = direction
    else:
        btc_position = direction

    # 신호 기록
    signals_history[symbol].append({
        "time": datetime.now(KST).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "direction": direction
    })

    # 텔레그램 전송
    send_telegram_signal(
        direction,
        "NAS100" if symbol == "NAS" else "BTC"
    )

    return {
        "status": "final_signal",
        "symbol": symbol,
        "direction": direction
    }


# =========================================================
# [8] 청산 처리
# =========================================================
# 청산은 24시간 작동
# =========================================================

def process_close(symbol):

    global nas_position
    global btc_position

    if symbol == "NAS":
        position = nas_position
    else:
        position = btc_position

    print(
        f"⚪ {symbol} 청산 신호 수신 "
        f"(현재 포지션: {position})"
    )

    # 현재 포지션이 없으면 무시
    if position is None:

        print(
            f"⚪ {symbol} 청산 → "
            f"현재 포지션 없음. 무시"
        )

        return {
            "status": "ignored",
            "reason": "no_position"
        }

    # 청산은 시간과 관계없이 전송
    send_telegram_signal(
        "CLOSE",
        "NAS100" if symbol == "NAS" else "BTC"
    )

    # 포지션 초기화
    if symbol == "NAS":
        nas_position = None
    else:
        btc_position = None

    return {
        "status": "closed",
        "symbol": symbol,
        "previous_position": position
    }


# =========================================================
# [9] NAS100 지지/상승 또는 저항/하락 조합 처리
# =========================================================

def process_nas_pair(signal_type):

    # =====================================================
    # 매매시간 외에는 NAS 신호 자체를 받지 않음
    # =====================================================

    if not is_trade_time_kst():

        print(
            f"🚫 NAS100 {signal_type} "
            f"→ 매매시간 외. 완전 무시"
        )

        return {
            "status": "ignored",
            "reason": "outside_trading_hours",
            "symbol": "NAS",
            "signal": signal_type
        }

    now = datetime.now(KST)

    if signal_type in ("support", "up"):

        waiting = nas_buy_waiting
        pair_keys = ("support", "up")
        direction = "BUY"
        pair_name = "지지구간 + 상승"

    else:

        waiting = nas_sell_waiting
        pair_keys = ("resistance", "down")
        direction = "SELL"
        pair_name = "저항구간 + 하락"

    # =====================================================
    # 기존 대기시간 만료 확인
    # =====================================================

    for key in pair_keys:

        timestamp = waiting[key]

        if timestamp is not None:

            elapsed = (
                now - timestamp
            ).total_seconds()

            if elapsed >= WAIT_SECONDS:

                print(
                    f"⌛ NAS100 {key} 신호 → "
                    f"20분 초과. 만료 처리"
                )

                waiting[key] = None

    # =====================================================
    # 새로운 신호 기록
    # =====================================================

    if waiting[signal_type] is None:

        waiting[signal_type] = now

        print(
            f"⏳ NAS100 "
            f"{signal_type} 신호 기록"
        )

        print(
            f"⏰ 기준 시간: "
            f"{now.strftime('%H:%M:%S')} KST"
        )

    else:

        print(
            f"🔄 NAS100 {signal_type} 반복 → "
            f"기존 기준 시간 유지"
        )

    # =====================================================
    # 두 신호 조합 확인
    # =====================================================

    first_time = waiting[pair_keys[0]]
    second_time = waiting[pair_keys[1]]

    if (
        first_time is not None
        and
        second_time is not None
    ):

        gap = abs(
            (
                first_time - second_time
            ).total_seconds()
        )

        if gap <= WAIT_SECONDS:

            print(
                f"🔥 NAS100 {pair_name} "
                f"조건 완성 → {direction}"
            )

            result = create_final_signal(
                "NAS",
                direction
            )

            # 사용한 대기 신호 삭제
            waiting[pair_keys[0]] = None
            waiting[pair_keys[1]] = None

            print(
                f"✅ NAS100 최종 "
                f"{direction} 신호 완료"
            )

            return result

        # 조합시간 초과
        waiting[pair_keys[0]] = None
        waiting[pair_keys[1]] = None

    return {
        "status": "waiting",
        "symbol": "NAS",
        "condition": pair_name
    }


# =========================================================
# [10] BTC SMR 대기 시작 / 갱신
# =========================================================

def start_waiting(symbol, direction):

    # =====================================================
    # 매매시간 외에는 대기 자체를 시작하지 않음
    # =====================================================

    if not is_trade_time_kst():

        print(
            f"🚫 {symbol} {direction} "
            f"SMR → 매매시간 외. 무시"
        )

        return {
            "status": "ignored",
            "reason": "outside_trading_hours",
            "symbol": symbol,
            "direction": direction
        }

    check_timeout(symbol)

    now = datetime.now(KST)
    waiting = btc_waiting

    # 같은 방향 SMR 반복
    if (
        waiting["active"]
        and
        waiting["direction"] == direction
    ):

        waiting["timestamp"] = now

        print(
            f"🔄 {symbol} {direction} "
            f"SMR 추가 발생"
        )

        print(
            f"⏱ 마지막 신호 기준 "
            f"20분 대기 갱신"
        )

        return {
            "status": "waiting",
            "symbol": symbol,
            "direction": direction
        }

    # 새로운 대기 시작
    waiting["active"] = True
    waiting["direction"] = direction
    waiting["timestamp"] = now

    print(
        f"⏳ {symbol} {direction} "
        f"대기 시작"
    )

    print(
        f"⏰ 기준 시간: "
        f"{now.strftime('%H:%M:%S')} KST"
    )

    return {
        "status": "waiting",
        "symbol": symbol,
        "direction": direction
    }


# =========================================================
# [11] BTC 대기시간 초과 확인
# =========================================================

def check_timeout(symbol):

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
            f"{waiting['direction']} "
            f"대기시간 종료"
        )

        waiting["active"] = False
        waiting["direction"] = None
        waiting["timestamp"] = None

        return True

    return False


# =========================================================
# [12] BTC 0선 돌파 처리
# =========================================================

def process_zero_cross(symbol):

    waiting = btc_waiting

    # =====================================================
    # 매매시간 외에는 0선 돌파도 완전 무시
    # =====================================================

    if not is_trade_time_kst():

        print(
            f"🚫 {symbol} 0선 돌파 "
            f"→ 매매시간 외. 완전 무시"
        )

        # 혹시 기존 대기 상태가 있으면 폐기
        waiting["active"] = False
        waiting["direction"] = None
        waiting["timestamp"] = None

        return {
            "status": "ignored",
            "reason": "outside_trading_hours"
        }

    # =====================================================
    # SMR 대기 확인
    # =====================================================

    if not waiting["active"]:

        print(
            f"⚪ {symbol} 0선 돌파 → "
            f"SMR 대기 없음. 무시"
        )

        return {
            "status": "ignored",
            "reason": "no_smr_waiting"
        }

    # =====================================================
    # 대기시간 확인
    # =====================================================

    if check_timeout(symbol):

        print(
            f"⚪ {symbol} 0선 돌파 → "
            f"20분 초과. 무시"
        )

        return {
            "status": "ignored",
            "reason": "waiting_expired"
        }

    # =====================================================
    # 최종 방향
    # =====================================================

    direction = waiting["direction"]

    result = create_final_signal(
        symbol,
        direction
    )

    # 대기 초기화
    waiting["active"] = False
    waiting["direction"] = None
    waiting["timestamp"] = None

    print(
        f"✅ {symbol} 최종 "
        f"{direction} 신호 완료"
    )

    return result


# =========================================================
# [13] TradingView 웹훅
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

    clean_message = (
        message
        .replace(" ", "")
        .upper()
    )

    # =====================================================
    # NAS
    # =====================================================

    if "NAS" in clean_message:

        # -------------------------------------------------
        # 청산
        # 청산은 24시간 허용
        # -------------------------------------------------

        if "NAS100청산" in clean_message:

            return process_close("NAS")

        # -------------------------------------------------
        # 상승
        # -------------------------------------------------

        if "NAS100상승" in clean_message:

            return process_nas_pair("up")

        # -------------------------------------------------
        # 하락
        # -------------------------------------------------

        if "NAS100하락" in clean_message:

            return process_nas_pair("down")

        # -------------------------------------------------
        # 지지구간
        # -------------------------------------------------

        if "지지구간" in clean_message:

            return process_nas_pair("support")

        # -------------------------------------------------
        # 저항구간
        # -------------------------------------------------

        if "저항구간" in clean_message:

            return process_nas_pair("resistance")

        return {
            "status": "ignored",
            "reason": "NAS_unknown_signal"
        }

    # =====================================================
    # BTC
    # =====================================================

    if "BTC" in clean_message:

        # -------------------------------------------------
        # 청산
        # 청산은 24시간 허용
        # -------------------------------------------------

        if "BTC청산" in clean_message:

            return process_close("BTC")

        # -------------------------------------------------
        # 0선 돌파
        # -------------------------------------------------

        if "BTC0선돌파" in clean_message:

            return process_zero_cross("BTC")

        # -------------------------------------------------
        # 지지구간
        # -------------------------------------------------

        if "지지구간" in clean_message:

            return start_waiting(
                "BTC",
                "BUY"
            )

        # -------------------------------------------------
        # 저항구간
        # -------------------------------------------------

        if "저항구간" in clean_message:

            return start_waiting(
                "BTC",
                "SELL"
            )

        return {
            "status": "ignored",
            "reason": "BTC_unknown_signal"
        }

    # =====================================================
    # 알 수 없는 신호
    # =====================================================

    return {
        "status": "ignored",
        "reason": "no_symbol_tag"
    }


# =========================================================
# [14] 현재 대기 상태 확인
# =========================================================

@app.get("/waiting/{symbol}")
def get_waiting(symbol: str):

    symbol = symbol.upper()

    # =====================================================
    # NAS
    # =====================================================

    if symbol == "NAS":

        return {
            "symbol": symbol,

            "buy_support": (
                nas_buy_waiting["support"].strftime(
                    "%Y-%m-%d %H:%M:%S KST"
                )
                if nas_buy_waiting["support"]
                else None
            ),

            "buy_up": (
                nas_buy_waiting["up"].strftime(
                    "%Y-%m-%d %H:%M:%S KST"
                )
                if nas_buy_waiting["up"]
                else None
            ),

            "sell_resistance": (
                nas_sell_waiting["resistance"].strftime(
                    "%Y-%m-%d %H:%M:%S KST"
                )
                if nas_sell_waiting["resistance"]
                else None
            ),

            "sell_down": (
                nas_sell_waiting["down"].strftime(
                    "%Y-%m-%d %H:%M:%S KST"
                )
                if nas_sell_waiting["down"]
                else None
            )
        }

    # =====================================================
    # BTC
    # =====================================================

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
# [15] 현재 포지션 상태 확인
# =========================================================

@app.get("/position/{symbol}")
def get_position(symbol: str):

    symbol = symbol.upper()

    if symbol == "NAS":

        position = nas_position

    elif symbol == "BTC":

        position = btc_position

    else:

        return {
            "status": "error",
            "reason": "unknown_symbol"
        }

    return {
        "symbol": symbol,
        "position": position
    }


# =========================================================
# [16] 신호 기록 확인
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
# [17] 현재 매매시간 확인
# =========================================================

@app.get("/trading-time")
def trading_time():

    return {
        "kst": kst_now_text(),

        "trading_allowed": (
            is_trade_time_kst()
        ),

        "schedule": [
            "08:00-21:00 KST",
            "22:35-05:00 KST"
        ],

        "close_allowed_24h": True
    }
