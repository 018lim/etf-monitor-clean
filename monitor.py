# -*- coding: utf-8 -*-
"""monitor.py"""

import requests
import os
import yfinance as yf
import time
import sys
from datetime import datetime, timedelta

# ✅ 텔레그램 알림 함수 (보안 적용)
def send_telegram_alert(message):
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    response = requests.post(url, data=payload)
    print(f"[텔레그램 응답] {response.status_code} / {response.text}")

# ✅ 한국 시간 반환 함수
def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)

# ✅ 감시 대상
TICKERS = {
    "MOAT": "309230.KS",
    "나스닥100": "133690.KS",
    "코스피200 커버드콜": "498400.KS",
    "미배당커버드콜액티브": "441640.KS",
    "전력": "486450.KS",
    "소프트웨어": "481180.KS"
}

INTERVAL_SECONDS = 60  # 1분 간격 감시

# ✅ 일일 등락률의 표준편차 계산
def get_return_std(ticker):
    df = yf.download(ticker, period="1250d", interval="1d")
    df['Return'] = df['Close'].pct_change()
    df = df.dropna()
    return float(df['Return'].std())

# ✅ 전일 종가 / 현재가 가져오기
def get_prev_close_and_current_price(ticker):
    daily = yf.download(ticker, period="2d", interval="1d")
    if len(daily) < 2:
        return None, None
    prev_close = daily['Close'].iloc[-2].item()

    intraday = yf.download(ticker, period="1d", interval="1m")
    if intraday.empty:
        return None, None
    current_price = intraday['Close'].iloc[-1].item()

    return prev_close, current_price

# ✅ 감시 루프
def run_monitor():
    now = get_kst_now()
    if now.weekday() >= 5:
        print("🛑 주말입니다. 감시 종료")
        send_telegram_alert("🛑 주말이라 감시 종료합니다.")
        sys.exit()

    # ✅ 시장시간이 아니면 종료
    if now.hour < 9 or (now.hour >= 15 and now.minute > 30) or now.hour >= 16:
        print("⏹️ 주식 시장 시간이 아닙니다. 감시 종료")
        send_telegram_alert("⏹️ 주식 시장 시간이 아닙니다. 감시 종료")
        sys.exit()

    send_telegram_alert("🚨 주식 시장 감시 시작합니다!")
    thresholds = {}
    notified = {code: False for code in TICKERS}

    for code, yf_ticker in TICKERS.items():
        std = get_return_std(yf_ticker)
        threshold = 2 * std
        thresholds[code] = threshold
        print(f"[{code}] 기준 등락폭 (2σ): {threshold:.2%}")

    while True:
        now = get_kst_now()
        if now.hour > 15 or (now.hour == 15 and now.minute >= 30):
            send_telegram_alert("⏹️ 감시 종료: 장 마감 (KST)")
            sys.exit()

        for code, yf_ticker in TICKERS.items():
            if notified[code]:
                print(f"[{code}] ✅ 감시 완료 → 제외")
                continue

            try:
                prev_close, current_price = get_prev_close_and_current_price(yf_ticker)
                if prev_close is None or current_price is None:
                    print(f"[{code}] 가격 수신 실패")
                    continue

                change_pct = abs((current_price - prev_close) / prev_close)
                diff = (current_price - prev_close) / prev_close
                threshold = thresholds[code]

                print(f"[{code}] 현재 등락률 변화: {change_pct:.2%} / 기준: {threshold:.2%}")

                if diff < -threshold:
                    msg = (
                        f"🚨 {code} 타이밍 \n"
                        f"전일종가: {int(prev_close)}\n"
                        f"매수 기준가: {int(prev_close * (1 - threshold))}\n"
                        f"매수 기준 등락율: -{threshold:.2%}\n"
                        f"현재가: {int(current_price)} (변화율: {diff:.2%})"
                    )
                    send_telegram_alert(msg)
                    notified[code] = True

                elif diff > threshold:
                    msg = (
                        f"🚨 {code} 타이밍 \n"
                        f"전일종가: {int(prev_close)}\n"
                        f"매도 기준가: {int(prev_close * (1 + threshold))}\n"
                        f"매도 기준 등락율: +{threshold:.2%}\n"
                        f"현재가: {int(current_price)} (변화율: {diff:.2%})"
                    )
                    send_telegram_alert(msg)
                    notified[code] = True

                else:
                    print(f"[{code}] 변화율 정상 범위")

                if all(notified.values()):
                    print("✅ 모든 종목 감시 완료. 프로그램 종료.")
                    send_telegram_alert("✅ 모든 종목 감시 완료. 프로그램 종료.")
                    sys.exit()

            except Exception as e:
                print(f"[{code}] 오류: {e}")
                send_telegram_alert(f"❌ {code} 오류: {e}")

        time.sleep(INTERVAL_SECONDS)

# ✅ 노트북 환경에서도 에러 없이 종료
try:
    run_monitor()
except SystemExit:
    pass
