from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from datetime import datetime

app = FastAPI()

latest_signals = {
    "NAS": None,
    "BTC": None,
}

@app.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.body()
    message = body.decode("utf-8").strip()

    if message.startswith("NAS_"):
        symbol = "NAS"
    elif message.startswith("BTC_"):
        symbol = "BTC"
    else:
        return {"status": "ignored", "reason": "no symbol tag"}

    latest_signals[symbol] = {
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }
    return {"status": "received", "symbol": symbol}


@app.get("/signal/{symbol}")
async def get_signal(symbol: str):
    symbol = symbol.upper()
    if symbol not in latest_signals:
        return {"status": "unknown symbol"}
    return latest_signals[symbol] or {"status": "no signal yet"}


app.mount("/", StaticFiles(directory="public", html=True), name="static")
