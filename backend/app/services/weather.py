import httpx
import logging
from typing import Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field
from backend.app.config import settings

logger = logging.getLogger(__name__)


class AdvisorySignal(BaseModel):
    advisory_active: bool = False
    advisory_category: Optional[str] = None
    advisory_title: Optional[str] = None
    source: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "advisory_active": self.advisory_active,
            "advisory_category": self.advisory_category,
            "advisory_title": self.advisory_title,
            "source": self.source,
        }


class WeatherFacts(BaseModel):
    location: str
    latitude: float
    longitude: float
    timestamp: str
    temperature_2m: float
    wind_speed_10m: float
    wind_gusts_10m: float = 0.0
    precipitation: float = 0.0
    precipitation_probability: float = 0.0
    uv_index: float = 0.0
    weather_code: int = 0
    time_scope: str = "current"

    def to_facts_dict(self) -> dict[str, Any]:
        return {
            "temperature_2m": round(float(self.temperature_2m), 1),
            "wind_speed_10m": round(float(self.wind_speed_10m), 1),
            "wind_gusts_10m": round(float(self.wind_gusts_10m), 1),
            "precipitation": round(float(self.precipitation), 1),
            "precipitation_probability": round(float(self.precipitation_probability), 1),
            "uv_index": round(float(self.uv_index), 1),
            "weather_code": int(self.weather_code),
        }

    def summary_text(self) -> str:
        return (
            f"Temperature: {self.temperature_2m}°C, "
            f"Wind: {self.wind_speed_10m} km/h (gusts: {self.wind_gusts_10m} km/h), "
            f"Precipitation: {self.precipitation} mm ({self.precipitation_probability}%), "
            f"UV Index: {self.uv_index}, "
            f"WMO Code: {self.weather_code}"
        )


class WeatherServiceError(Exception):
    """Raised when weather API returns an error or fails."""
    pass


class WeatherService:
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self.base_url = base_url or settings.FORECAST_API_URL
        self.timeout = timeout or settings.WEATHER_REQUEST_TIMEOUT

    async def fetch_weather(
        self,
        location_name: str,
        latitude: float,
        longitude: float,
        time_reference: Optional[str] = None,
        advisory: Optional[AdvisorySignal] = None
    ) -> WeatherFacts:
        """
        Fetches current and hourly forecast from Open-Meteo for given coordinates.
        Explicitly requests required current and hourly fields.
        """
        current_fields = [
            "temperature_2m",
            "wind_speed_10m",
            "wind_gusts_10m",
            "precipitation",
            "precipitation_probability",
            "uv_index",
            "weather_code"
        ]
        hourly_fields = [
            "temperature_2m",
            "wind_speed_10m",
            "wind_gusts_10m",
            "precipitation",
            "precipitation_probability",
            "uv_index",
            "weather_code"
        ]

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(current_fields),
            "hourly": ",".join(hourly_fields),
            "timezone": "auto"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url, params=params)
                if response.status_code != 200:
                    logger.error(f"Open-Meteo Forecast HTTP {response.status_code}: {response.text}")
                    raise WeatherServiceError(f"Weather API returned HTTP {response.status_code}")

                data = response.json()
                current = data.get("current")
                if not current:
                    raise WeatherServiceError("Weather API response did not contain 'current' data block")

                # If a specific time reference like "evening", "tonight", "afternoon" was requested,
                # resolve from hourly forecast if available
                facts = self._extract_facts(
                    data=data,
                    location_name=location_name,
                    latitude=latitude,
                    longitude=longitude,
                    time_reference=time_reference
                )
                return facts

        except httpx.RequestError as exc:
            logger.error(f"Network error contacting Open-Meteo: {exc}")
            raise WeatherServiceError(f"Network error contacting weather service: {str(exc)}") from exc
        except (KeyError, ValueError) as exc:
            logger.error(f"Malformed Open-Meteo payload: {exc}")
            raise WeatherServiceError(f"Malformed weather data received: {str(exc)}") from exc

    def _extract_facts(
        self,
        data: dict[str, Any],
        location_name: str,
        latitude: float,
        longitude: float,
        time_reference: Optional[str]
    ) -> WeatherFacts:
        current = data.get("current", {})
        hourly = data.get("hourly", {})
        time_ref = (time_reference or "").strip().lower()

        # Check if time_reference targets evening/night/afternoon and hourly data is present
        target_index = None
        if hourly and "time" in hourly and time_ref in ["this evening", "evening", "tonight", "afternoon", "tomorrow morning"]:
            now_iso = current.get("time", "")
            times = hourly.get("time", [])
            for idx, t_str in enumerate(times):
                try:
                    dt = datetime.fromisoformat(t_str)
                    if "evening" in time_ref and 18 <= dt.hour <= 21:
                        target_index = idx
                        break
                    elif "tonight" in time_ref and 20 <= dt.hour <= 23:
                        target_index = idx
                        break
                    elif "afternoon" in time_ref and 13 <= dt.hour <= 16:
                        target_index = idx
                        break
                except Exception:
                    continue

        if target_index is not None and hourly:
            # Use hourly snapshot for requested time
            return WeatherFacts(
                location=location_name,
                latitude=latitude,
                longitude=longitude,
                timestamp=hourly["time"][target_index],
                temperature_2m=float(hourly["temperature_2m"][target_index]),
                wind_speed_10m=float(hourly["wind_speed_10m"][target_index]),
                wind_gusts_10m=float(hourly.get("wind_gusts_10m", [0.0])[target_index] or 0.0),
                precipitation=float(hourly["precipitation"][target_index]),
                precipitation_probability=float(hourly.get("precipitation_probability", [0.0])[target_index] or 0.0),
                uv_index=float(hourly.get("uv_index", [0.0])[target_index] or 0.0),
                weather_code=int(hourly.get("weather_code", [0])[target_index] or 0),
                time_scope=time_ref
            )

        # Default to current
        return WeatherFacts(
            location=location_name,
            latitude=latitude,
            longitude=longitude,
            timestamp=str(current.get("time", datetime.now().isoformat())),
            temperature_2m=float(current.get("temperature_2m", 0.0)),
            wind_speed_10m=float(current.get("wind_speed_10m", 0.0)),
            wind_gusts_10m=float(current.get("wind_gusts_10m", 0.0) or 0.0),
            precipitation=float(current.get("precipitation", 0.0) or 0.0),
            precipitation_probability=float(current.get("precipitation_probability", 0.0) or 0.0),
            uv_index=float(current.get("uv_index", 0.0) or 0.0),
            weather_code=int(current.get("weather_code", 0) or 0),
            time_scope="current"
        )
