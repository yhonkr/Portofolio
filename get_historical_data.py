import requests
import json
from datetime import datetime

# API de CoinGecko para datos históricos
url = "https://api.coingecko.com/api/v3/coins/tether/market_chart"

# Configuración de la solicitud
params = {
    "vs_currency": "usd",        # Precio en dólares
    "days": "30",                # Datos de 30 días
    "interval": "daily"          # Un dato por día
}

# Enviar la solicitud
response = requests.get(url, params=params)
data = response.json()

# Ver la estructura de los datos recibidos
print("Claves en los datos recibidos:", data.keys())
# Resultado: dict_keys(['prices', 'market_caps', 'volumes'])

# Extraer solo los datos de precios (formato: [[tiempo en ms, precio], ...])
prices = data['prices']

print(f"\nTotal de {len(prices)} puntos de datos\n")

# Mostrar solo los primeros 5
print("Primeros 5 datos:")
for i, (timestamp, price) in enumerate(prices[:5]):
    # Convertir milisegundos a fecha legible
    date = datetime.fromtimestamp(timestamp / 1000)
    print(f"{date.strftime('%Y-%m-%d %H:%M')}: ${price:.4f}")