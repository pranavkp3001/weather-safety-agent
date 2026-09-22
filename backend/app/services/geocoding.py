import httpx
import logging
from typing import Optional
from pydantic import BaseModel
from backend.app.config import settings

logger = logging.getLogger(__name__)


class LocationInfo(BaseModel):
    name: str
    latitude: float
    longitude: float
    country: Optional[str] = None
    admin1: Optional[str] = None  # State / Province

    @property
    def display_name(self) -> str:
        parts = [self.name]
        if self.admin1:
            parts.append(self.admin1)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)


class GeocodingError(Exception):
    """Raised when geocoding network or service fails."""
    pass


class GeocodingService:
    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        self.base_url = base_url or settings.GEOCODING_API_URL
        self.timeout = timeout or settings.WEATHER_REQUEST_TIMEOUT

    async def geocode(self, city_name: str) -> Optional[LocationInfo]:
        cleaned_name = city_name.strip()
        if not cleaned_name:
            return None

        params = {
            "name": cleaned_name,
            "count": 5,
            "language": "en",
            "format": "json"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url, params=params)
                if response.status_code != 200:
                    logger.error(f"Geocoding API error: HTTP {response.status_code} - {response.text}")
                    raise GeocodingError(f"Geocoding service returned HTTP {response.status_code}")

                data = response.json()
                results = data.get("results")
                if not results or len(results) == 0:
                    logger.info(f"Geocoding returned no results for query: '{cleaned_name}'")
                    return None

                first_match = results[0]
                return LocationInfo(
                    name=first_match.get("name", cleaned_name),
                    latitude=float(first_match["latitude"]),
                    longitude=float(first_match["longitude"]),
                    country=first_match.get("country"),
                    admin1=first_match.get("admin1")
                )

        except httpx.RequestError as exc:
            logger.error(f"Network error during geocoding request: {exc}")
            raise GeocodingError(f"Network error contacting geocoding service: {str(exc)}") from exc
        except (KeyError, ValueError) as exc:
            logger.error(f"Malformed geocoding payload: {exc}")
            raise GeocodingError(f"Malformed geocoding response data: {str(exc)}") from exc
