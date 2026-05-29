import requests

url = "https://api.coingecko.com/api/v3/simple/price"
params = {
    "ids": "tether,usd-coin,dai",
    "vs_currencies": "usd"
}

response = requests.get(url, params=params)
data = response.json()

# Organizar y mostrar los datos de forma más clara
print("=" * 40)
print("🪙 Precios actuales de monedas estables")
print("=" * 40)

nombres_monedas = {
    "tether": "USDT (Tether)",
    "usd-coin": "USDC (USD Coin)",
    "dai": "DAI"
}

for coin_id, coin_name in nombres_monedas.items():
    price = data[coin_id]['usd']
    
    # Detectar desvinculación (si se desvía ±1% de $1)
    if price < 0.99:
        status = "🔴 ¡Desvinculación detectada!"
    elif price > 1.01:
        status = "🔴 Aumento"
    else:
        status = "🟢 Normal"
    
    print(f"{coin_name}: ${price:.4f} {status}")

print("=" * 40)