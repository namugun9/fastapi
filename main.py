from datetime import datetime, timezone
from fastapi import Body, FastAPI, Request
from fastapi.staticfiles import StaticFiles

app = FastAPI()

latest_signals = {
    "NAS": None,
    "BTC": None,
}


@app.post("/webhook")
async def receive_webhook(
    request: Request,
    raw_message: str = Body(
        ..., media_type="text/plain", example="BUY NAS 18000"
    ),
):
    # Swagger 테스트 또는 실제 웹훅 요청에서 바이트 코드가 넘어올 경우 처리
    if isinstance(raw_message, bytes):
        message = raw_message.decode("utf-8").strip()
    else:
        message = str(raw_message).strip()

    upper_message = message.upper()

    # 메시지 어디에 NAS / BTC가 포함되어 있어도 인식
    if "NAS" in upper_message:
        symbol = "NAS"
    elif "BTC" in upper_message:
        symbol = "BTC"
    else:
        return {"status": "ignored", "reason": "no symbol tag"}

    latest_signals[symbol] = {
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {"status": "received", "symbol": symbol, "message": message}


@app.get("/signal/{symbol}")
async def get_signal(symbol: str):
    symbol = symbol.upper()

    if symbol not in latest_signals:
        return {"status": "unknown symbol"}

    return latest_signals[symbol] or {"status": "no signal yet"}


# 맨 마지막에 위치해야 함 (정적 파일 연결)
app.mount("/", StaticFiles(directory="public", html=True), name="static")
