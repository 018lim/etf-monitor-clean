# -*- coding: utf-8 -*-
"""monitor.py"""

import requests
import os
import yfinance as yf
import time
import sys
from datetime import datetime, timedelta

# ✅ 텔레그램 알림 함수
def send_telegram_alert(message):
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    response = requests.post(url, data=payload)
    print(f"[텔레그램 응답] {response.status_code} / {response.text}")

# ✅ 한국 시간 반환
def get_kst_now():
    return datetime.utcnow() + timedelta(hours=9)

# ✅ 감시 대상
TICKERS = {
    "MOAT": "309230.KS",
    "나스닥100": "133690.KS",
    "코스피200 커버드콜": "498400.KS",
    "미배당커버드콜액티브": "441640.KS",
    "미국채30년커버드콜": "481060.KS",
    "리츠": "476800.KS",
    "AI 전력": "486450.KS",
    "글로벌원자력": "442320.KS"
}

INTERVAL_SECONDS = 300  # 5분 간격

# ✅ 평균, 표준편차 계산
def get_return_stats(ticker):
    df = yf.download(ticker, period="1250d", interval="1d")
    df['Return'] = df['Close'].pct_change()
    df = df.dropna()
    return float(df['Return'].mean()), float(df['Return'].std())

# ✅ 전일 종가 / 현재가
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

    # 시장 시간 확인 (09:00~15:30)
    if now.hour < 9 or (now.hour >= 15 and now.minute > 30) or now.hour >= 16:
        print("⏹️ 주식 시장 시간이 아닙니다. 감시 종료")
        send_telegram_alert("⏹️ 주식 시장 시간이 아닙니다. 감시 종료")
        sys.exit()

    send_telegram_alert("🚨 주식 시장 감시 시작합니다!")

    stats = {}
    notified = {code: False for code in TICKERS}
    summary_msg = "📋 감시 시작 요약\n"

    # 각 종목 기준 계산 및 요약 정리
    for code, yf_ticker in TICKERS.items():
        mean, std = get_return_stats(yf_ticker)
        stats[code] = (mean, std)

        daily = yf.download(yf_ticker, period="2d", interval="1d")
        if len(daily) < 2:
            summary_msg += f"{code}: ❌ 전일 종가 불러오기 실패\n"
            continue

        prev_close = daily['Close'].iloc[-2].item()
        buy_price = prev_close * (1 + mean - 2 * std)
        sell_price = prev_close * (1 + mean + 2 * std)

        summary_msg += (
            f"📌 {code}\n"
            f" - 전일 종가: {int(prev_close)}\n"
            f" - 매수 기준가: {int(buy_price)}\n"
            f" - 매도 기준가: {int(sell_price)}\n"
            f" - 매수 기준 등락률: {(mean - 2 * std)*100:.2f}%, "
            f"매도 기준: {(mean + 2 * std)*100:.2f}%\n\n"
        )

    send_telegram_alert(summary_msg)

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

                diff = (current_price - prev_close) / prev_close
                mean, std = stats[code]

                print(f"[{code}] 변화율: {diff:.2%} / 기준: ({mean:.2%} ± 2×{std:.2%})")

                if diff < mean - 2 * std:
                    msg = (
                        f"🚨 {code} 매수 타이밍\n"
                        f"전일종가: {int(prev_close)}\n"
                        f"매수 기준가: {int(prev_close * (1 + mean - 2 * std))}\n"
                        f"매수 기준 등락율: {(mean - 2 * std)*100:.2f}%\n"
                        f"현재가: {int(current_price)} (변화율: {diff:.2%})"
                    )
                    send_telegram_alert(msg)
                    notified[code] = True

                elif diff > mean + 2 * std:
                    msg = (
                        f"🚨 {code} 매도 타이밍\n"
                        f"전일종가: {int(prev_close)}\n"
                        f"매도 기준가: {int(prev_close * (1 + mean + 2 * std))}\n"
                        f"매도 기준 등락율: {(mean + 2 * std)*100:.2f}%\n"
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

# ✅ 실행
try:
    run_monitor()
except SystemExit:
    pass
