import requests
import feedparser
import pandas as pd
import streamlit as st
import altair as alt
import urllib.parse
from datetime import datetime

feedparser.USER_AGENT = "Mozilla/5.0 (compatible; StablecoinNewsApp/1.0)"

# ── 1. 실시간 가격 가져오기
def get_prices():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "tether,usd-coin,dai", "vs_currencies": "usd"}
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return {
            "USDT": data.get("tether", {}).get("usd", 1.0),
            "USDC": data.get("usd-coin", {}).get("usd", 1.0),
            "DAI":  data.get("dai", {}).get("usd", 1.0)
        }
    except Exception:
        return {"USDT": 1.0, "USDC": 1.0, "DAI": 1.0}

# ── 2. 디페그 감지
def check_depeg(prices):
    alerts = []
    for coin, price in prices.items():
        if price < 0.99 or price > 1.01:
            alerts.append(f":warning: {coin} 디페그! 현재 가격: ${price}")
    return alerts

# ── 3. 30일 과거 데이터
@st.cache_data(ttl=3600)
def get_history(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": 30}
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        df = pd.DataFrame(data["prices"], columns=["timestamp", coin_id])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("timestamp")
        return df
    except Exception:
        return pd.DataFrame()

# ── 4. 뉴스 가져오기 (Google News RSS)
@st.cache_data(ttl=900)
def get_news():
    query = "stablecoin OR USDC OR USDT OR Tether OR DAI"
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries:
        items.append({
            "title":     e.get("title", ""),
            "link":      e.get("link", "#"),
            "published": e.get("published", "")[:16],
            "source":    e.get("source", {}).get("title", ""),
        })
    return items

# ── 5. Yield Optimizer (DefiLlama API — 무료, API 키 불필요)
@st.cache_data(ttl=1800)
def get_yield_data():
    url = "https://yields.llama.fi/pools"
    try:
        response = requests.get(url, timeout=15)
        data = response.json()

        TARGET_SYMBOLS = ["USDT", "USDC", "DAI"]
        SAFE_PROTOCOLS = [
            "aave-v3", "aave-v2", "compound-v3", "compound",
            "curve-dex", "curve", "makerdao", "sparklend",
            "morpho", "fluid-lending", "fluid-lite",
            "sky", "sky-savings-rate", "dsr"
        ]

        results = []
        for pool in data["data"]:
            symbol    = pool.get("symbol", "")
            apy       = pool.get("apy")
            tvl       = pool.get("tvlUsd", 0)
            project   = pool.get("project", "")
            chain     = pool.get("chain", "")
            is_stable = pool.get("stablecoin", False)

            if (is_stable
                    and symbol in TARGET_SYMBOLS
                    and apy is not None
                    and 0 < apy < 50
                    and tvl > 10_000_000):

                risk = 50
                if tvl > 1_000_000_000:
                    risk -= 25
                elif tvl > 500_000_000:
                    risk -= 20
                elif tvl > 100_000_000:
                    risk -= 15
                elif tvl > 50_000_000:
                    risk -= 5
                else:
                    risk += 10

                if project in SAFE_PROTOCOLS:
                    risk -= 25
                else:
                    risk += 20

                if apy > 20:
                    risk += 30
                elif apy > 12:
                    risk += 15
                elif apy > 8:
                    risk += 5

                risk = max(0, min(100, risk))

                if risk <= 35:
                    nivel = "🟢 안전"
                elif risk <= 65:
                    nivel = "🟡 보통"
                else:
                    nivel = "🔴 위험"

                results.append({
                    "프로토콜":  project,
                    "체인":     chain,
                    "풀":       symbol,
                    "APY (%)":  round(apy, 2),
                    "TVL ($M)": round(tvl / 1_000_000, 1),
                    "리스크":   nivel,
                    "점수":     risk
                })

        results.sort(key=lambda x: (x["점수"], -x["APY (%)"]))
        return results[:10]

    except Exception:
        return []

# ── 6. 텔레그램 알림 보내기
def send_telegram(message):
    try:
        token   = st.secrets["TELEGRAM_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(
            url,
            data={"chat_id": chat_id, "text": message},
            timeout=10
        )
        return True
    except Exception:
        return False

# ════════════════════════════════════════
# 화면 구성
# ════════════════════════════════════════
st.title(":shield: 스테이블코인 디페그 모니터")
st.caption(f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

prices = get_prices()

# ── 상단 카드 3개
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("USDT", f"${prices['USDT']}", round(prices['USDT'] - 1.0, 4))
with col2:
    st.metric("USDC", f"${prices['USDC']}", round(prices['USDC'] - 1.0, 4))
with col3:
    st.metric("DAI",  f"${prices['DAI']}",  round(prices['DAI']  - 1.0, 4))

st.divider()

# ── 디페그 알림 + 텔레그램 연동
alerts = check_depeg(prices)
if alerts:
    for alert in alerts:
        st.error(alert)

    # 세션당 1번만 전송
    if "telegram_sent" not in st.session_state:
        st.session_state.telegram_sent = False

    if not st.session_state.telegram_sent:
        news = get_news()
        news_line = ""
        if news:
            news_line = f"\n📰 관련 뉴스: {news[0]['title']}"

        mensaje = "🚨 디페그 감지!\n"
        for coin, price in prices.items():
            if price < 0.99 or price > 1.01:
                pct = round((price - 1.0) * 100, 2)
                mensaje += f"\n🪙 {coin} 현재 가격: ${price}"
                mensaje += f"\n📉 $1 기준 {pct}% 이탈"

        # Yield Optimizer 추천 포함
        yield_data = get_yield_data()
        safe = [p for p in yield_data if "🟢" in p["리스크"]]
        if safe:
            best = safe[0]
            mensaje += (
                f"\n\n💰 추천 이동처:"
                f"\n→ {best['프로토콜'].upper()} ({best['체인']})"
                f"\n→ {best['풀']} APY {best['APY (%)']}%"
            )

        mensaje += news_line

        if send_telegram(mensaje):
            st.toast("📱 텔레그램 알림 전송 완료!")
            st.session_state.telegram_sent = True
else:
    st.success(":white_check_mark: 현재 디페그 없음 — 세 코인 모두 정상입니다")
    st.session_state.telegram_sent = False

st.divider()

# ── 30일 그래프
st.subheader(":chart_with_upwards_trend: 30일 가격 추이")

df_usdt = get_history("tether")
df_usdc = get_history("usd-coin")
df_dai  = get_history("dai")

if not df_usdt.empty and not df_usdc.empty and not df_dai.empty:
    df_all = pd.concat([df_usdt, df_usdc, df_dai], axis=1, sort=False)
    df_all.columns = ["USDT", "USDC", "DAI"]

    df_reset = df_all.reset_index()
    df_melt  = df_reset.melt("timestamp", var_name="코인", value_name="가격")

    chart = alt.Chart(df_melt).mark_line().encode(
        x="timestamp:T",
        y=alt.Y("가격:Q", scale=alt.Scale(domain=[0.98, 1.02])),
        color="코인:N"
    ).properties(height=300)

    st.altair_chart(chart, use_container_width=True)
else:
    st.warning("⏳ CoinGecko API 요청 제한 — 1분 후 다시 시도하세요")

st.divider()

# ── Yield Optimizer 화면
st.subheader("💰 수익률 TOP 10 — Yield Optimizer")
st.caption("출처: DefiLlama API · 순수 스테이블코인 풀만 · 30분마다 갱신")

yield_data = get_yield_data()

if yield_data:
    if alerts:
        st.warning("⚠️ 디페그 감지됨 — 아래 안전한 풀로 이동을 고려하세요")

    df_yield = pd.DataFrame(yield_data)

    st.dataframe(
        df_yield.drop(columns=["점수"]),
        column_config={
            "APY (%)":  st.column_config.NumberColumn(
                            "APY (%)", format="%.2f%%"),
            "TVL ($M)": st.column_config.NumberColumn(
                            "TVL ($M)", format="$%.0fM"),
        },
        hide_index=True,
        use_container_width=True
    )

    safe = [p for p in yield_data if "🟢" in p["리스크"]]
    if safe:
        best = safe[0]
        st.success(
            f"✅ 추천: **{best['프로토콜'].upper()}** ({best['체인']}) — "
            f"{best['풀']} — APY {best['APY (%)']}% — "
            f"TVL ${best['TVL ($M)']}M"
        )
else:
    st.info("수익률 데이터를 불러오는 중입니다...")

st.divider()

# ── 최신 뉴스
st.subheader(":newspaper: 스테이블코인 관련 뉴스")
news_list = get_news()

if news_list:
    for item in news_list[:10]:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"**{item['title']}**")
            st.caption(f":clock1: {item['published']}  |  {item['source']}")
        with col2:
            st.markdown(f"[기사 보기]({item['link']})")
        st.divider()
else:
    st.info("뉴스를 불러오는 중입니다...")

st.divider()

# ── 텔레그램 테스트 버튼
if st.button("📱 텔레그램 테스트 메시지 보내기"):
    test_msg = (
        "✅ StableGuard 테스트\n\n"
        f"🪙 USDT: ${prices['USDT']}\n"
        f"🪙 USDC: ${prices['USDC']}\n"
        f"🪙 DAI:  ${prices['DAI']}\n\n"
        "봇이 정상 작동 중입니다! 🚀"
    )
    if send_telegram(test_msg):
        st.success("✅ 전송 완료! 텔레그램을 확인하세요 📱")
    else:
        st.error("❌ 전송 실패 — secrets.toml의 토큰을 확인하세요")

# ── 새로고침 버튼
if st.button(":arrows_counterclockwise: 지금 다시 확인"):
    st.cache_data.clear()
    st.rerun()