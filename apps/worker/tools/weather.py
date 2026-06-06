"""Open-Meteo weather tools.

get_weather_forecast  – hourly / daily forecast + current conditions
get_air_quality       – PM2.5, PM10, ozone, NO2 and AQI index
get_elevation         – terrain elevation at a coordinate
get_geocoding         – resolve a place name to latitude / longitude
"""

import json
from typing import Optional

import requests
from langchain_core.tools import tool

from context import RunContext

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

_TIMEOUT = 15


def _get(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def weather_tools(ctx: RunContext) -> list:  # noqa: ARG001
    @tool
    def get_weather_forecast(
        latitude: float,
        longitude: float,
        forecast_days: int = 7,
        timezone: str = "auto",
        temperature_unit: str = "celsius",
    ) -> dict:
        """Fetch weather forecast and current conditions for a coordinate.

        Returns current weather (temperature, wind speed, weather code) plus
        hourly (temperature_2m, precipitation, windspeed_10m) and daily
        (temperature_2m_max/min, precipitation_sum, sunrise/sunset) arrays.
        `forecast_days`: 1–16 (default 7).
        `timezone`: IANA timezone string or "auto" to detect from coordinates.
        `temperature_unit`: "celsius" or "fahrenheit".
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "forecast_days": max(1, min(16, forecast_days)),
            "timezone": timezone,
            "temperature_unit": temperature_unit,
            "current_weather": True,
            "hourly": "temperature_2m,precipitation,windspeed_10m,weathercode",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,sunrise,sunset",
        }
        return _get(_FORECAST_URL, params)

    @tool
    def get_air_quality(
        latitude: float,
        longitude: float,
        forecast_days: int = 3,
        timezone: str = "auto",
    ) -> dict:
        """Fetch air quality forecast for a coordinate.

        Returns hourly arrays for pm2_5, pm10, ozone, nitrogen_dioxide,
        sulphur_dioxide, carbon_monoxide, and european_aqi / us_aqi indices.
        `forecast_days`: 1–7 (default 3).
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "forecast_days": max(1, min(7, forecast_days)),
            "timezone": timezone,
            "hourly": (
                "pm2_5,pm10,ozone,nitrogen_dioxide,"
                "sulphur_dioxide,carbon_monoxide,"
                "european_aqi,us_aqi"
            ),
        }
        return _get(_AIR_QUALITY_URL, params)

    @tool
    def get_elevation(latitude: float, longitude: float) -> dict:
        """Return terrain elevation (metres above sea level) for a coordinate.

        Uses the Open-Meteo digital elevation model (90 m resolution).
        Returns {"latitude": ..., "longitude": ..., "elevation": [<metres>]}.
        """
        params = {"latitude": latitude, "longitude": longitude}
        return _get(_ELEVATION_URL, params)

    @tool
    def get_geocoding(
        name: str,
        count: int = 5,
        language: str = "en",
        country_code: Optional[str] = None,
    ) -> dict:
        """Resolve a place name to geographic coordinates.

        Returns up to `count` (1–100) matching locations with latitude,
        longitude, country, admin1 (state/province), population, and timezone.
        Use the returned latitude/longitude in the other weather tools.
        `country_code`: optional ISO-3166-1 alpha-2 filter (e.g. "HK", "US").
        """
        params: dict = {
            "name": name,
            "count": max(1, min(100, count)),
            "language": language,
            "format": "json",
        }
        if country_code:
            params["countryCode"] = country_code.upper()
        return _get(_GEOCODING_URL, params)

    return [get_weather_forecast, get_air_quality, get_elevation, get_geocoding]
