import time
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

# ── 2. 디페그 감지 (0.998부터 감지 — 매우 민감)
def check_depeg(prices):
    alerts = []
    for coin, price in prices.items():
        if price < 0.998 or price > 1.002:
            # 심각도 레벨
            if price < 0.990 or price > 1.010:
                nivel = "🚨 위험"
            elif price < 0.995 or price > 1.005:
                nivel = "🔴 경고"
            else:
                nivel = "⚠️ 주의"
            pct = round((price - 1.0) * 100, 3)
            alerts.append({
                "coin":   coin,
                "price":  price,
                "pct":    pct,
                "nivel":  nivel
            })
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

# ── 5. Yield Optimizer (DefiLlama API)
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
                if tvl > 1_000_000_000:    risk -= 25
                elif tvl > 500_000_000:    risk -= 20
                elif tvl > 100_000_000:    risk -= 15
                elif tvl > 50_000_000:     risk -= 5
                else:                      risk += 10

                if project in SAFE_PROTOCOLS: risk -= 25
                else:                         risk += 20

                if apy > 20:    risk += 30
                elif apy > 12:  risk += 15
                elif apy > 8:   risk += 5

                risk = max(0, min(100, risk))

                if risk <= 35:    nivel = "🟢 안전"
                elif risk <= 65:  nivel = "🟡 보통"
                else:             nivel = "🔴 위험"

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

# ── 6. 텔레그램 알림
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

# ── 7. 텔레그램 메시지 생성
def build_telegram_message(alerts, prices, yield_data, news):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"⚠️ 스테이블코인 이상 감지!\n🕐 {now}\n"
    msg += "─────────────────────\n"

    for a in alerts:
        msg += f"\n{a['nivel']} {a['coin']}"
        msg += f"\n💵 현재가: ${a['price']}"
        msg += f"\n📉 변동: {a['pct']}%\n"

    # 안전 풀 추천
    safe = [p for p in yield_data if "🟢" in p["리스크"]]
    if safe:
        best = safe[0]
        msg += "\n─────────────────────"
        msg += "\n💰 추천 이동처:"
        msg += f"\n→ {best['프로토콜'].upper()} ({best['체인']})"
        msg += f"\n→ {best['풀']} APY {best['APY (%)']}%"

    # 관련 뉴스 1개
    if news:
        msg += "\n─────────────────────"
        msg += f"\n📰 {news[0]['title']}"

    return msg

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

# ── 디페그 알림 + 텔레그램 자동 전송
alerts = check_depeg(prices)

# session_state 초기화
if "telegram_sent" not in st.session_state:
    st.session_state.telegram_sent = set()  # 이미 알림 보낸 코인 집합

if alerts:
    for a in alerts:
        if a["nivel"] == "🚨 위험":
            st.error(f"{a['nivel']} {a['coin']} — ${a['price']} ({a['pct']}%)")
        elif a["nivel"] == "🔴 경고":
            st.warning(f"{a['nivel']} {a['coin']} — ${a['price']} ({a['pct']}%)")
        else:
            st.info(f"{a['nivel']} {a['coin']} — ${a['price']} ({a['pct']}%)")

        # 코인별로 1번만 전송
        if a["coin"] not in st.session_state.telegram_sent:
            yield_data_tg = get_yield_data()
            news_tg       = get_news()
            msg = build_telegram_message(alerts, prices, yield_data_tg, news_tg)
            if send_telegram(msg):
                st.session_state.telegram_sent.add(a["coin"])
                st.toast(f"📱 {a['coin']} 텔레그램 알림 전송!")
else:
    st.success(":white_check_mark: 현재 이상 없음 — 세 코인 모두 정상입니다")
    # 정상으로 돌아오면 해당 코인 초기화 (다음 디페그에 다시 알림 가능)
    for coin in list(st.session_state.telegram_sent):
        if prices.get(coin, 1.0) >= 0.998:
            st.session_state.telegram_sent.discard(coin)

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

# ── Yield Optimizer
st.subheader("💰 수익률 TOP 10 — Yield Optimizer")
st.caption("출처: DefiLlama API · 순수 스테이블코인 풀만 · 30분마다 갱신")

yield_data = get_yield_data()

if yield_data:
    if alerts:
        st.warning("⚠️ 이상 감지됨 — 아래 안전한 풀로 이동을 고려하세요")

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

# ── 자동 모니터링 설정
st.subheader("⚙️ 자동 모니터링 설정")

col1, col2 = st.columns([3, 1])
with col1:
    intervalo = st.slider(
        "새로고침 간격 (초)",
        min_value=30,
        max_value=300,
        value=60,
        step=30
    )
with col2:
    auto_on = st.toggle("자동 실행", value=True)

if auto_on:
    st.caption(f"🟢 자동 모니터링 중 — {intervalo}초마다 확인 · 감지 기준: $0.998")
else:
    st.caption("🔴 자동 모니터링 꺼짐")

if st.button(":arrows_counterclockwise: 지금 바로 확인"):
    st.cache_data.clear()
    st.rerun()

# ── 자동 루프
if auto_on:
    time.sleep(intervalo)
    st.cache_data.clear()
    st.rerun()