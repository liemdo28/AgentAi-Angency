"""
Weather Service — Open-Meteo API (free, no API key).
Used to factor weather into media buying decisions (e.g., retail traffic, outdoor ads).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"


class WeatherService:
    """
    Fetch current weather and forecasts for media planning decisions.

    No API key required. Uses Open-Meteo's free tier.

    Example use case:
        - Retail campaigns: rain -> indoor traffic spikes
        - Outdoor ads: sunny -> higher visibility
        - QSR: bad weather -> delivery channel push
    """

    def __init__(self, client: Optional[httpx.Client] = None) -> None:
        self._client = client or httpx.Client(timeout=10.0)

    def get_current(self, lat: float, lon: float) -> dict[str, Any]:
        """
        Fetch current weather conditions.

        Returns dict with keys: temperature_2m, relative_humidity_2m,
        precipitation, weather_code, wind_speed_10m
        """
        try:
            r = self._client.get(
                OPEN_METEO_BASE,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                    "timezone": "auto",
                },
            )
            r.raise_for_status()
            data = r.json()
            current = data.get("current", {})
            logger.debug("Weather fetched for (%s, %s): %s", lat, lon, current)
            return {
                "temperature_c": current.get("temperature_2m"),
                "humidity_pct": current.get("relative_humidity_2m"),
                "precipitation_mm": current.get("precipitation"),
                "weather_code": current.get("weather_code"),
                "wind_kmh": current.get("wind_speed_10m"),
                "timezone": data.get("timezone"),
                "fetched_at": data.get("current", {}).get("time"),
            }
        except Exception as exc:
            logger.warning("Weather fetch failed for (%s, %s): %s", lat, lon, exc)
            return {"error": str(exc)}

    def get_forecast(
        self,
        lat: float,
        lon: float,
        days: int = 7,
    ) -> dict[str, Any]:
        """
        Fetch daily forecast for campaign planning.

        Returns dict with 'daily' key containing list of daily summaries.
        """
        try:
            r = self._client.get(
                OPEN_METEO_BASE,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": (
                        "temperature_2m_max,temperature_2m_min,"
                        "precipitation_sum,weather_code,wind_speed_10m_max"
                    ),
                    "forecast_days": days,
                    "timezone": "auto",
                },
            )
            r.raise_for_status()
            data = r.json()
            daily = data.get("daily", {})
            forecasts = []
            for i in range(len(daily.get("time", []))):
                forecasts.append({
                    "date": daily["time"][i],
                    "temp_max_c": daily["temperature_2m_max"][i],
                    "temp_min_c": daily["temperature_2m_min"][i],
                    "precipitation_mm": daily["precipitation_sum"][i],
                    "weather_code": daily["weather_code"][i],
                    "wind_max_kmh": daily["wind_speed_10m_max"][i],
                })
            logger.debug("Forecast fetched: %d days", len(forecasts))
            return {
                "timezone": data.get("timezone"),
                "daily": forecasts,
            }
        except Exception as exc:
            logger.warning("Forecast fetch failed for (%s, %s): %s", lat, lon, exc)
            return {"error": str(exc), "daily": []}

    def weather_impact_summary(
        self,
        lat: float,
        lon: float,
        campaign_type: str = "general",
    ) -> str:
        """
        Return a human-readable weather impact note for media planning.

        campaign_type: "retail" | "outdoor" | "qsr" | "general"
        """
        current = self.get_current(lat, lon)
        if "error" in current:
            return f"Weather data unavailable: {current['error']}"

        temp = current.get("temperature_c")
        precip = current.get("precipitation_mm", 0)
        weather_code = current.get("weather_code", 0)

        notes = []
        if precip and precip > 1.0:
            notes.append("Precipitation detected - consider indoor/channel shift.")
        if weather_code >= 61:  # rainy codes
            notes.append("Rainy conditions - outdoor visibility reduced.")
        if campaign_type == "retail" and temp and temp > 30:
            notes.append("High temperature - expected higher indoor footfall.")
        if campaign_type == "outdoor" and precip and precip < 0.5 and weather_code < 50:
            notes.append("Clear weather - optimal for outdoor ad visibility.")
        if campaign_type == "qsr" and precip and precip > 0:
            notes.append("Wet weather - boost delivery/indoor dining channels.")

        if not notes:
            notes.append("Weather conditions are neutral for media planning.")

        return f"Current weather ({temp}C, precip={precip}mm, code={weather_code}): " + " ".join(notes)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "WeatherService":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
