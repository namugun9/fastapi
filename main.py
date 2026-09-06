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

# NAS100: 지지+상승 또는 저항+하락을 20분 이내 조합
# BTC: 마지막 SMR 신호를 기준으로 20분 동안 0선 돌파 대기
WAIT_SECONDS = 20 * 60


# =========================================================
# [2] NAS / BTC 대기 상태
# =========================================================

# NAS100 매수 조건: 지지구간 + 상승
nas_buy_waiting = {
    "support": None,
    "up": None
}

# NAS100 매도 조건: 저항구간 + 하락
nas_sell_waiting = {
    "resistance": None,
    "down": None
}

# BTC는 기존 방식 유지: SMR + 0선돌파
btc_waiting = {
    "active": False,
    "direction": None,
    "timestamp": None
}


# =========================================================
# [3] NAS / BTC 현재 포지션 상태
# =========================================================
# None = 포지션 없음
# BUY  = 매수 상태
# SELL = 매도 상태

nas_position = None
btc_position = None


# =========================================================
# [4] 최종 신호 기록
# =========================================================

signals_history = {
    "NAS": [],
    "BTC": []
}


# =========================================================
# [5] 텔레그램 전송
# =========================================================

def send_telegram_signal(action, symbol):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    # -----------------------------------------------------
    # 매수
    # -----------------------------------------------------

    if action == "BUY":

        text = (
            f"🟢 **{symbol} 매수 신호**\n\n"
            f"{symbol} 지지구간 확인\n"
            f"매수세 유입 발생\n\n"
            f"⏰ 시간: {now} KST"
        )

    # -----------------------------------------------------
    # 매도
    # -----------------------------------------------------

    elif action == "SELL":

        text = (
            f"🔴 **{symbol} 매도 신호**\n\n"
            f"{symbol} 저항구간 확인\n"
            f"매도세 유입 발생\n\n"
            f"⏰ 시간: {now} KST"
        )

    # -----------------------------------------------------
    # 청산
    # -----------------------------------------------------

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
            f"Telegram: {response.status_code}"
        )

    except Exception as e:

        print(
            f"Telegram Error: {e}"
        )


# =========================================================
# [6] 최종 매매 신호
# =========================================================

def create_final_signal(symbol, direction):

    global nas_position
    global btc_position

    print(
        f"🔥 최종 신호 발생 → "
        f"{symbol} / {direction}"
    )

    # -----------------------------------------------------
    # 포지션 상태 저장
    # -----------------------------------------------------

    if symbol == "NAS":

        nas_position = direction

    else:

        btc_position = direction

    # -----------------------------------------------------
    # 신호 기록
    # -----------------------------------------------------

    signals_history[symbol].append({
        "time": datetime.now(KST).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "direction": direction
    })

    # -----------------------------------------------------
    # 텔레그램
    # -----------------------------------------------------

    send_telegram_signal(
        direction,
        "NAS100" if symbol == "NAS" else "BTC"
    )


# =========================================================
# [7] 청산 처리
# =========================================================

def process_close(symbol):

    global nas_position
    global btc_position

    # 현재 포지션 확인
    if symbol == "NAS":

        position = nas_position

    else:

        position = btc_position

    print(
        f"⚪ {symbol} 청산 신호 수신 "
        f"(현재 포지션: {position})"
    )

    # -----------------------------------------------------
    # 포지션이 있을 때만 청산 알림
    # -----------------------------------------------------

    if position is None:

        print(
            f"⚪ {symbol} 청산 → "
            f"현재 포지션 없음. 무시"
        )

        return {
            "status": "ignored",
            "reason": "no_position"
        }

    # -----------------------------------------------------
    # 청산 알림
    # -----------------------------------------------------

    send_telegram_signal(
        "CLOSE",
        "NAS100" if symbol == "NAS" else "BTC"
    )

    # -----------------------------------------------------
    # 포지션 초기화
    # -----------------------------------------------------

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
# [8] NAS100 지지/상승 또는 저항/하락 조합 처리
# =========================================================

def process_nas_pair(signal_type):
    """
    NAS100은 순서와 관계없이 두 신호가 20분 안에 모두 발생하면
    최종 매수/매도 신호를 만든다.

    BUY  = 지지구간 + 상승
    SELL = 저항구간 + 하락
    """

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

    # -----------------------------------------------------
    # 20분이 지난 신호는 만료
    # -----------------------------------------------------

    for key in pair_keys:
        timestamp = waiting[key]

        if timestamp is not None:
            elapsed = (now - timestamp).total_seconds()

            if elapsed >= WAIT_SECONDS:
                print(
                    f"⌛ NAS100 {key} 신호 → "
                    f"20분 초과. 만료 처리"
                )
                waiting[key] = None

    # -----------------------------------------------------
    # 현재 신호 기록
    # 같은 신호가 반복되어도 최초 신호 시간을 유지
    # -----------------------------------------------------

    if waiting[signal_type] is None:
        waiting[signal_type] = now

        print(
            f"⏳ NAS100 {signal_type} 신호 기록"
        )
        print(
            f"⏰ 기준 시간: "
            f"{now.strftime('%H:%M:%S')} KST"
        )
    else:
        print(
            f"🔄 NAS100 {signal_type} 신호 반복 → "
            f"기존 기준 시간 유지"
        )

    # -----------------------------------------------------
    # 두 신호가 모두 있고 20분 이내인지 확인
    # -----------------------------------------------------

    first_time = waiting[pair_keys[0]]
    second_time = waiting[pair_keys[1]]

    if first_time is not None and second_time is not None:

        gap = abs(
            (first_time - second_time).total_seconds()
        )

        if gap <= WAIT_SECONDS:

            print(
                f"🔥 NAS100 {pair_name} 조건 완성 "
                f"→ {direction}"
            )

            create_final_signal(
                "NAS",
                direction
            )

            # 최종 신호 후 두 조건 초기화
            waiting[pair_keys[0]] = None
            waiting[pair_keys[1]] = None

            print(
                f"✅ NAS100 최종 {direction} 신호 완료"
            )

            return {
                "status": "final_signal",
                "symbol": "NAS",
                "direction": direction
            }

        # 안전 처리
        waiting[pair_keys[0]] = None
        waiting[pair_keys[1]] = None

    return {
        "status": "waiting",
        "symbol": "NAS",
        "condition": pair_name
    }


# =========================================================
# [9] BTC 기존 SMR 대기 / 갱신
# =========================================================

def start_waiting(symbol, direction):

    # 기존 대기가 20분을 넘었으면 먼저 초기화
    check_timeout(symbol)

    now = datetime.now(KST)
    waiting = btc_waiting

    # -----------------------------------------------------
    # 같은 종목 + 같은 방향
    # → 마지막 SMR 기준 20분 다시 시작
    # -----------------------------------------------------

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

        return

    # -----------------------------------------------------
    # 새로운 대기 시작
    # -----------------------------------------------------

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


# =========================================================
# [10] BTC 20분 시간 초과 + 0선 돌파 처리
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


def process_zero_cross(symbol):

    waiting = btc_waiting

    # -----------------------------------------------------
    # SMR이 먼저 발생하지 않았다면 무시
    # -----------------------------------------------------

    if not waiting["active"]:

        print(
            f"⚪ {symbol} 0선 돌파 → "
            f"SMR 대기 없음. 무시"
        )

        return {
            "status": "ignored",
            "reason": "no_smr_waiting"
        }

    # -----------------------------------------------------
    # 20분 초과 여부 확인
    # -----------------------------------------------------

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

    create_final_signal(
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

    return {
        "status": "final_signal",
        "symbol": symbol,
        "direction": direction
    }


# =========================================================
# [11] TradingView 웹훅
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

    # 공백 제거 + 대문자 변환
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
        # NAS100 청산
        # -------------------------------------------------

        if "NAS100청산" in clean_message:

            return process_close("NAS")


        # -------------------------------------------------
        # NAS100 상승
        # -------------------------------------------------

        if "NAS100상승" in clean_message:

            return process_nas_pair("up")


        # -------------------------------------------------
        # NAS100 하락
        # -------------------------------------------------

        if "NAS100하락" in clean_message:

            return process_nas_pair("down")


        # -------------------------------------------------
        # NAS 지지
        # -------------------------------------------------

        if "지지구간" in clean_message:

            return process_nas_pair("support")


        # -------------------------------------------------
        # NAS 저항
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
        # BTC 청산
        # -------------------------------------------------

        if "BTC청산" in clean_message:

            return process_close("BTC")


        # -------------------------------------------------
        # BTC 0선 돌파
        # -------------------------------------------------

        if "BTC0선돌파" in clean_message:

            return process_zero_cross("BTC")


        # -------------------------------------------------
        # BTC 지지
        # -------------------------------------------------

        if "지지구간" in clean_message:

            start_waiting(
                "BTC",
                "BUY"
            )

            return {
                "status": "waiting",
                "symbol": "BTC",
                "direction": "BUY"
            }


        # -------------------------------------------------
        # BTC 저항
        # -------------------------------------------------

        if "저항구간" in clean_message:

            start_waiting(
                "BTC",
                "SELL"
            )

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
# [12] 현재 대기 상태 확인
# =========================================================

@app.get("/waiting/{symbol}")
def get_waiting(symbol: str):

    symbol = symbol.upper()

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
# [13] 현재 포지션 상태 확인
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
# [14] 신호 기록 확인
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
