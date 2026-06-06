"""Open-Meteo weather tools — scoped to Hong Kong (22.3193° N, 114.1694° E).

get_weather_forecast  – hourly / daily forecast + current conditions
get_air_quality       – PM2.5, PM10, ozone, NO2 and AQI index
get_elevation         – terrain elevation at HK coordinates
"""

import requests
from langchain_core.tools import tool

from context import RunContext

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"

_HK_LAT = 22.3193
_HK_LON = 114.1694
_HK_TZ = "Asia/Hong_Kong"

_TIMEOUT = 15


def _get(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def weather_tools(ctx: RunContext) -> list:  # noqa: ARG001
    @tool
    def get_weather_forecast(
        forecast_days: int = 7,
        temperature_unit: str = "celsius",
    ) -> dict:
        """Fetch weather forecast and current conditions for Hong Kong.

        Returns current weather (temperature, wind speed, weather code) plus
        hourly (temperature_2m, precipitation, windspeed_10m, weathercode) and
        daily (temperature_2m_max/min, precipitation_sum, sunrise/sunset) arrays.
        `forecast_days`: 1–16 (default 7).
        `temperature_unit`: "celsius" or "fahrenheit".
        """
        params = {
            "latitude": _HK_LAT,
            "longitude": _HK_LON,
            "forecast_days": max(1, min(16, forecast_days)),
            "timezone": _HK_TZ,
            "temperature_unit": temperature_unit,
            "current_weather": True,
            "hourly": "temperature_2m,precipitation,windspeed_10m,weathercode",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,sunrise,sunset",
        }
        return _get(_FORECAST_URL, params)

    @tool
    def get_air_quality(forecast_days: int = 3) -> dict:
        """Fetch air quality forecast for Hong Kong.

        Returns hourly arrays for pm2_5, pm10, ozone, nitrogen_dioxide,
        sulphur_dioxide, carbon_monoxide, and european_aqi / us_aqi indices.
        `forecast_days`: 1–7 (default 3).
        """
        params = {
            "latitude": _HK_LAT,
            "longitude": _HK_LON,
            "forecast_days": max(1, min(7, forecast_days)),
            "timezone": _HK_TZ,
            "hourly": (
                "pm2_5,pm10,ozone,nitrogen_dioxide,"
                "sulphur_dioxide,carbon_monoxide,"
                "european_aqi,us_aqi"
            ),
        }
        return _get(_AIR_QUALITY_URL, params)

    @tool
    def get_elevation() -> dict:
        """Return terrain elevation (metres above sea level) for Hong Kong.

        Uses the Open-Meteo digital elevation model (90 m resolution).
        Returns {"latitude": ..., "longitude": ..., "elevation": [<metres>]}.
        """
        params = {"latitude": _HK_LAT, "longitude": _HK_LON}
        return _get(_ELEVATION_URL, params)

    return [get_weather_forecast, get_air_quality, get_elevation]
