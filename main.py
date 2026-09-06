from fastapi import FastAPI, Request
from datetime import datetime, timezone, timedelta
import requests


# =========================================================
# [1] 기본 설정
# =========================================================

app = FastAPI()

KST = timezone(timedelta(hours=9))

# =========================================================
# 텔레그램
# =========================================================
BOT_TOKEN = "8899307951:AAHtgu2aW3ROCI-G7gwrp4glfaiD1vAycbY"
CHAT_ID = "2106941258"

# =========================================================
# 매매 대기시간
# =========================================================
WAIT_SECONDS = 20 * 60


# =========================================================
# [2] 매매시간
# =========================================================
# 신규 BUY / SELL
#   08:00 ~ 21:00
#   22:35 ~ 05:00
#
# 청산은 24시간 허용
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

# ---------------------------------------------------------
# NAS BUY 조건
#
# support = 지지구간 생성 OR 지지구간 진입
# up      = NAS100 상승
# ---------------------------------------------------------

nas_buy_waiting = {
    "support": None,
    "up": None
}


# ---------------------------------------------------------
# NAS SELL 조건
#
# resistance = 저항구간 생성 OR 저항구간 진입
# down       = NAS100 하락
# ---------------------------------------------------------

nas_sell_waiting = {
    "resistance": None,
    "down": None
}


# ---------------------------------------------------------
# BTC
# 기존 로직 그대로 유지
# ---------------------------------------------------------

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

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    now = datetime.now(KST).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # =====================================================
    # BUY
    # =====================================================

    if action == "BUY":

        text = (
            f"🟢 **{symbol} 매수 신호**\n\n"
            f"{symbol} 지지구간 확인\n"
            f"매수세 유입 발생\n\n"
            f"⏰ 시간: {now} KST"
        )

    # =====================================================
    # SELL
    # =====================================================

    elif action == "SELL":

        text = (
            f"🔴 **{symbol} 매도 신호**\n\n"
            f"{symbol} 저항구간 확인\n"
            f"매도세 유입 발생\n\n"
            f"⏰ 시간: {now} KST"
        )

    # =====================================================
    # BUY 청산
    # =====================================================

    elif action == "CLOSE_BUY":

        text = (
            f"⚪ **{symbol} 매수 포지션 청산**\n\n"
            f"{symbol} BUY 포지션 청산\n\n"
            f"⏰ 시간: {now} KST"
        )

    # =====================================================
    # SELL 청산
    # =====================================================

    elif action == "CLOSE_SELL":

        text = (
            f"⚪ **{symbol} 매도 포지션 청산**\n\n"
            f"{symbol} SELL 포지션 청산\n\n"
            f"⏰ 시간: {now} KST"
        )

    # 기존 전체 청산도 안전하게 유지
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
    # BUY / SELL은 매매시간 외 차단
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

    # =====================================================
    # 최종 신호 출력
    # =====================================================

    print(
        f"🔥 최종 신호 발생 → "
        f"{symbol} / {direction}"
    )

    # =====================================================
    # 포지션 상태
    # =====================================================

    if symbol == "NAS":

        if direction == "BUY":
            nas_position = "BUY"

        elif direction == "SELL":
            nas_position = "SELL"

    else:

        if direction == "BUY":
            btc_position = "BUY"

        elif direction == "SELL":
            btc_position = "SELL"

    # =====================================================
    # 신호 기록
    # =====================================================

    signals_history[symbol].append({
        "time": datetime.now(KST).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "direction": direction
    })

    # =====================================================
    # 텔레그램
    # =====================================================

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
# [8] NAS 대기 상태 전체 초기화
# =========================================================

def clear_nas_waiting():

    nas_buy_waiting["support"] = None
    nas_buy_waiting["up"] = None

    nas_sell_waiting["resistance"] = None
    nas_sell_waiting["down"] = None


# =========================================================
# [9] NAS BUY 조건 처리
# =========================================================
#
# BUY 조건:
#
#   (지지구간 생성 OR 지지구간 진입)
#                    +
#              NAS100 상승
#
# 두 신호의 순서는 관계없음.
#
# 어느 쪽이 먼저 와도 됨.
#
# 먼저 발생한 신호부터 20분.
# 두 번째 신호가 20분 안에 오면 BUY.
# =========================================================

def process_nas_buy(signal_type):

    now = datetime.now(KST)

    # =====================================================
    # 매매시간 외
    # =====================================================

    if not is_trade_time_kst():

        print(
            f"🚫 NAS BUY 조건 "
            f"{signal_type} → 매매시간 외. 무시"
        )

        return {
            "status": "ignored",
            "reason": "outside_trading_hours",
            "symbol": "NAS",
            "signal": signal_type
        }

    # =====================================================
    # BUY 조건이 들어오면 SELL 대기 폐기
    # =====================================================

    nas_sell_waiting["resistance"] = None
    nas_sell_waiting["down"] = None

    # =====================================================
    # support 또는 up 기록
    #
    # 반복 발생하면 마지막 신호 기준으로
    # 20분을 다시 시작
    # =====================================================

    nas_buy_waiting[signal_type] = now

    print(
        f"⏳ NAS BUY 조건 기록 → "
        f"{signal_type}"
    )

    print(
        f"⏰ 기준 시간: "
        f"{now.strftime('%H:%M:%S')} KST"
    )

    # =====================================================
    # 두 조건 존재 여부
    # =====================================================

    support_time = nas_buy_waiting["support"]
    up_time = nas_buy_waiting["up"]

    if support_time is None or up_time is None:

        return {
            "status": "waiting",
            "symbol": "NAS",
            "direction": "BUY",
            "condition": "지지구간 + 상승"
        }

    # =====================================================
    # 두 조건 시간 차이
    # =====================================================

    gap = abs(
        (
            support_time - up_time
        ).total_seconds()
    )

    # =====================================================
    # 20분 이내 → BUY
    # =====================================================

    if gap <= WAIT_SECONDS:

        print(
            f"🔥 NAS100 BUY 조건 완성"
        )

        print(
            f"지지구간 + 상승"
        )

        print(
            f"⏱ 조건 간격: "
            f"{gap:.1f}초"
        )

        result = create_final_signal(
            "NAS",
            "BUY"
        )

        clear_nas_waiting()

        return result

    # =====================================================
    # 20분 초과
    # =====================================================

    print(
        f"⌛ NAS BUY 조건 "
        f"20분 초과 → 폐기"
    )

    clear_nas_waiting()

    return {
        "status": "ignored",
        "reason": "pair_expired",
        "symbol": "NAS",
        "direction": "BUY"
    }


# =========================================================
# [10] NAS SELL 조건 처리
# =========================================================
#
# SELL 조건:
#
#   (저항구간 생성 OR 저항구간 진입)
#                    +
#              NAS100 하락
#
# 두 신호 순서 관계없음.
# =========================================================

def process_nas_sell(signal_type):

    now = datetime.now(KST)

    # =====================================================
    # 매매시간 외
    # =====================================================

    if not is_trade_time_kst():

        print(
            f"🚫 NAS SELL 조건 "
            f"{signal_type} → 매매시간 외. 무시"
        )

        return {
            "status": "ignored",
            "reason": "outside_trading_hours",
            "symbol": "NAS",
            "signal": signal_type
        }

    # =====================================================
    # SELL 조건이 들어오면 BUY 대기 폐기
    # =====================================================

    nas_buy_waiting["support"] = None
    nas_buy_waiting["up"] = None

    # =====================================================
    # resistance 또는 down 기록
    #
    # 반복 발생하면 마지막 신호 기준으로
    # 20분을 다시 시작
    # =====================================================

    nas_sell_waiting[signal_type] = now

    print(
        f"⏳ NAS SELL 조건 기록 → "
        f"{signal_type}"
    )

    print(
        f"⏰ 기준 시간: "
        f"{now.strftime('%H:%M:%S')} KST"
    )

    # =====================================================
    # 두 조건 존재 여부
    # =====================================================

    resistance_time = nas_sell_waiting["resistance"]
    down_time = nas_sell_waiting["down"]

    if (
        resistance_time is None
        or down_time is None
    ):

        return {
            "status": "waiting",
            "symbol": "NAS",
            "direction": "SELL",
            "condition": "저항구간 + 하락"
        }

    # =====================================================
    # 두 조건 시간 차이
    # =====================================================

    gap = abs(
        (
            resistance_time - down_time
        ).total_seconds()
    )

    # =====================================================
    # 20분 이내 → SELL
    # =====================================================

    if gap <= WAIT_SECONDS:

        print(
            f"🔥 NAS100 SELL 조건 완성"
        )

        print(
            f"저항구간 + 하락"
        )

        print(
            f"⏱ 조건 간격: "
            f"{gap:.1f}초"
        )

        result = create_final_signal(
            "NAS",
            "SELL"
        )

        clear_nas_waiting()

        return result

    # =====================================================
    # 20분 초과
    # =====================================================

    print(
        f"⌛ NAS SELL 조건 "
        f"20분 초과 → 폐기"
    )

    clear_nas_waiting()

    return {
        "status": "ignored",
        "reason": "pair_expired",
        "symbol": "NAS",
        "direction": "SELL"
    }


# =========================================================
# [11] BTC SMR 대기 시작 / 갱신
# =========================================================
#
# BTC 기존 로직 유지
# =========================================================

def start_waiting(symbol, direction):

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
# [12] BTC 대기시간 초과 확인
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
# [13] BTC 0선 돌파 처리
# =========================================================

def process_zero_cross(symbol):

    waiting = btc_waiting

    if not is_trade_time_kst():

        print(
            f"🚫 {symbol} 0선 돌파 "
            f"→ 매매시간 외. 완전 무시"
        )

        waiting["active"] = False
        waiting["direction"] = None
        waiting["timestamp"] = None

        return {
            "status": "ignored",
            "reason": "outside_trading_hours"
        }

    if not waiting["active"]:

        print(
            f"⚪ {symbol} 0선 돌파 → "
            f"SMR 대기 없음. 무시"
        )

        return {
            "status": "ignored",
            "reason": "no_smr_waiting"
        }

    if check_timeout(symbol):

        print(
            f"⚪ {symbol} 0선 돌파 → "
            f"20분 초과. 무시"
        )

        return {
            "status": "ignored",
            "reason": "waiting_expired"
        }

    direction = waiting["direction"]

    result = create_final_signal(
        symbol,
        direction
    )

    waiting["active"] = False
    waiting["direction"] = None
    waiting["timestamp"] = None

    print(
        f"✅ {symbol} 최종 "
        f"{direction} 신호 완료"
    )

    return result


# =========================================================
# [14] NAS 방향별 청산
# =========================================================
#
# NAS100 상승청산
#   → BUY 포지션만 청산
#
# NAS100 하락청산
#   → SELL 포지션만 청산
#
# 청산은 24시간
# =========================================================

def process_nas_close(close_direction):

    global nas_position

    print(
        f"⚪ NAS100 청산 신호 → "
        f"{close_direction}"
    )

    # =====================================================
    # BUY 청산
    # =====================================================

    if close_direction == "CLOSE_BUY":

        if nas_position != "BUY":

            print(
                f"⚪ NAS100 BUY 청산 → "
                f"현재 BUY 포지션 없음. 무시"
            )

            return {
                "status": "ignored",
                "reason": "no_buy_position",
                "symbol": "NAS",
                "direction": "CLOSE_BUY"
            }

        send_telegram_signal(
            "CLOSE_BUY",
            "NAS100"
        )

        nas_position = None

        return {
            "status": "closed",
            "symbol": "NAS",
            "direction": "CLOSE_BUY"
        }

    # =====================================================
    # SELL 청산
    # =====================================================

    if close_direction == "CLOSE_SELL":

        if nas_position != "SELL":

            print(
                f"⚪ NAS100 SELL 청산 → "
                f"현재 SELL 포지션 없음. 무시"
            )

            return {
                "status": "ignored",
                "reason": "no_sell_position",
                "symbol": "NAS",
                "direction": "CLOSE_SELL"
            }

        send_telegram_signal(
            "CLOSE_SELL",
            "NAS100"
        )

        nas_position = None

        return {
            "status": "closed",
            "symbol": "NAS",
            "direction": "CLOSE_SELL"
        }


# =========================================================
# [15] BTC 전체 청산
# =========================================================
#
# BTC 기존 로직 유지
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

    if position is None:

        print(
            f"⚪ {symbol} 청산 → "
            f"현재 포지션 없음. 무시"
        )

        return {
            "status": "ignored",
            "reason": "no_position"
        }

    send_telegram_signal(
        "CLOSE",
        "NAS100" if symbol == "NAS" else "BTC"
    )

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
# [16] TradingView 웹훅
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
        # BUY 청산
        #
        # NAS100 상승청산
        # -------------------------------------------------

        if "NAS100상승청산" in clean_message:

            clear_nas_waiting()

            return process_nas_close(
                "CLOSE_BUY"
            )

        # -------------------------------------------------
        # SELL 청산
        #
        # NAS100 하락청산
        # -------------------------------------------------

        if "NAS100하락청산" in clean_message:

            clear_nas_waiting()

            return process_nas_close(
                "CLOSE_SELL"
            )

        # -------------------------------------------------
        # 상승
        # -------------------------------------------------

        if "NAS100상승" in clean_message:

            return process_nas_buy("up")

        # -------------------------------------------------
        # 하락
        # -------------------------------------------------

        if "NAS100하락" in clean_message:

            return process_nas_sell("down")

        # -------------------------------------------------
        # 지지구간
        #
        # 생성 / 진입 둘 다 BUY 조건
        # -------------------------------------------------

        if "지지구간" in clean_message:

            return process_nas_buy("support")

        # -------------------------------------------------
        # 저항구간
        #
        # 생성 / 진입 둘 다 SELL 조건
        # -------------------------------------------------

        if "저항구간" in clean_message:

            return process_nas_sell("resistance")

        return {
            "status": "ignored",
            "reason": "NAS_unknown_signal"
        }

    # =====================================================
    # BTC
    # =====================================================

    if "BTC" in clean_message:

        # -------------------------------------------------
        # 기존 BTC 청산
        # -------------------------------------------------

        if "BTC청산" in clean_message:

            return process_close("BTC")

        # -------------------------------------------------
        # 기존 BTC 0선 돌파
        # -------------------------------------------------

        if "BTC0선돌파" in clean_message:

            return process_zero_cross("BTC")

        # -------------------------------------------------
        # 기존 BTC 지지구간
        # -------------------------------------------------

        if "지지구간" in clean_message:

            return start_waiting(
                "BTC",
                "BUY"
            )

        # -------------------------------------------------
        # 기존 BTC 저항구간
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
# [17] 현재 대기 상태 확인
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
# [18] 현재 포지션 상태 확인
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
# [19] 신호 기록 확인
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
# [20] 현재 매매시간 확인
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

        "close_allowed_24h": True,

        "wait_seconds": WAIT_SECONDS
    }
