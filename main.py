from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# 단일 값이 아닌 리스트(list) 형태로 변경
signals_history = {
    "NAS": [],
    "BTC": [],
}


@app.post("/webhook")
async def receive_webhook(request: Request):
    body_bytes = await request.body()
    message = body_bytes.decode("utf-8").strip()

    print(f"[WEBHOOK RECEIVED] Raw Data: {message}")

    if not message:
        return {"status": "error", "reason": "empty body"}

    upper_message = message.upper()

    # 메시지 안에서 심볼 감지
    if "NAS" in upper_message:
        symbol = "NAS"
    elif "BTC" in upper_message:
        symbol = "BTC"
    else:
        print("[WEBHOOK IGNORED] No matching symbol (NAS/BTC)")
        return {"status": "ignored", "reason": "no matching symbol (NAS/BTC)"}

    # 수신 데이터 개별 객체 생성
    new_signal = {
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # 리스트 맨 위에 최신 신호 추가 (최신순 정렬)
    signals_history[symbol].insert(0, new_signal)

    # 개수가 너무 많아져 메모리가 낭비되지 않도록 최대 50개까지만 유지
    signals_history[symbol] = signals_history[symbol][:50]

    print(f"[SIGNAL ADDED] {symbol} (Total: {len(signals_history[symbol])})")

    return {
        "status": "received",
        "symbol": symbol,
        "total_count": len(signals_history[symbol]),
        "latest": new_signal,
    }


@app.get("/signal/{symbol}")
async def get_signal(symbol: str):
    symbol = symbol.upper()

    if symbol not in signals_history:
        return {"status": "unknown symbol"}

    history = signals_history[symbol]

    if not history:
        return {"status": "no signal yet", "history": []}

    # 해당 심볼의 전체 신호 내역 반환
    return {"status": "success", "count": len(history), "history": history}


# 정적 파일 연동
app.mount("/", StaticFiles(directory="public", html=True), name="static")
