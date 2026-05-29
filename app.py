import requests
import pandas as pd
import streamlit as st
from datetime import datetime

# ── 1. 실시간 가격 가져오기 ──────────────────────────────
def get_prices():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": "tether,usd-coin,dai",
        "vs_currencies": "usd"
    }
    response = requests.get(url, params=params)
    data = response.json()
    return {
        "USDT": data["tether"]["usd"],
        "USDC": data["usd-coin"]["usd"],
        "DAI":  data["dai"]["usd"]
    }

# ── 2. 디페그 감지 ───────────────────────────────────────
def check_depeg(prices):
    alerts = []
    for coin, price in prices.items():
        if price < 0.99 or price > 1.01:
            alerts.append(f"⚠️ {coin} 디페그! 현재 가격: ${price}")
    return alerts

# ── 🆕 3. 뉴스 가져오기 ──────────────────────────────────
def get_news(coin_name):
    url = "https://api.coingecko.com/api/v3/news"
    params = {"query": coin_name}
    response = requests.get(url, params=params)
    data = response.json()
    news_list = data.get("news", [])[:3]  # 상위 3개만
    return [news["title"] for news in news_list]

# ── 4. 화면 구성 ─────────────────────────────────────────
st.title("🛡️ 스테이블코인 디페그 모니터")
st.caption(f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 가격 가져오기
prices = get_prices()

# 상단 카드 3개
col1, col2, col3 = st.columns(3)

with col1:
    delta = round(prices["USDT"] - 1.0, 4)
    st.metric(label="USDT", value=f"${prices['USDT']}", delta=delta)

with col2:
    delta = round(prices["USDC"] - 1.0, 4)
    st.metric(label="USDC", value=f"${prices['USDC']}", delta=delta)

with col3:
    delta = round(prices["DAI"] - 1.0, 4)
    st.metric(label="DAI", value=f"${prices['DAI']}", delta=delta)

st.divider()

# 디페그 알림 + 뉴스
alerts = check_depeg(prices)
if alerts:
    for alert in alerts:
        st.error(alert)
    
    # 🆕 디페그 감지되면 뉴스 표시
    st.subheader("📰 관련 뉴스")
    for coin in prices.keys():
        if prices[coin] < 0.99 or prices[coin] > 1.01:
            news = get_news(coin)
            st.write(f"**{coin} 관련 뉴스:**")
            for article in news:
                st.write(f"- {article}")
else:
    st.success("✅ 현재 디페그 없음 — 세 코인 모두 정상입니다")

st.divider()

# 30일치 과거 데이터 그래프
st.subheader("📈 30일 가격 추이")

@st.cache_data(ttl=3600)
def get_history(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": 30}
    response = requests.get(url, params=params)
    data = response.json()
    prices = data["prices"]
    df = pd.DataFrame(prices, columns=["timestamp", coin_id])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp")
    return df

# 세 코인 데이터 합치기
df_usdt = get_history("tether")
df_usdc = get_history("usd-coin")
df_dai  = get_history("dai")
df_all  = pd.concat([df_usdt, df_usdc, df_dai], axis=1)
df_all.columns = ["USDT", "USDC", "DAI"]

st.line_chart(df_all)

st.divider()

# 새로고침 버튼
if st.button("🔄 지금 다시 확인"):
    st.rerun()