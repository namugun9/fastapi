from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

app = FastAPI()

latest_signals = {
    "NAS": None,
    "BTC": None,
}


@app.post("/webhook")
async def receive_webhook(request: Request):
    # 1. 트레이딩뷰에서 보낸 본문(Body)을 바이너리로 직접 읽기
    body_bytes = await request.body()
    message = body_bytes.decode("utf-8").strip()

    # 터미널/실행로그에서 웹훅 들어오는지 실시간 확인용
    print(f"[WEBHOOK RECEIVED] Raw Data: {message}")

    if not message:
        return {"status": "error", "reason": "empty body"}

    upper_message = message.upper()

    # 2. 메시지 안에서 심볼 감지
    if "NAS" in upper_message:
        symbol = "NAS"
    elif "BTC" in upper_message:
        symbol = "BTC"
    else:
        print("[WEBHOOK IGNORED] No symbol matching NAS or BTC")
        return {"status": "ignored", "reason": "no matching symbol (NAS/BTC)"}

    # 3. 신호 저장 (UTC 시간 기준)
    latest_signals[symbol] = {
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    print(f"[SIGNAL UPDATED] {symbol}: {latest_signals[symbol]}")

    return {"status": "received", "symbol": symbol, "message": message}


@app.get("/signal/{symbol}")
async def get_signal(symbol: str):
    symbol = symbol.upper()

    if symbol not in latest_signals:
        return {"status": "unknown symbol"}

    # 신호가 없으면 no signal yet, 있으면 최신 신호 반환
    return latest_signals[symbol] or {"status": "no signal yet"}


# 맨 마지막 위치 (정적 파일)
app.mount("/", StaticFiles(directory="public", html=True), name="static")
