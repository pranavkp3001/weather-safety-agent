import pytest
from backend.app.services.geocoding import GeocodingService, GeocodingError
from backend.app.services.weather import WeatherService, WeatherServiceError, WeatherFacts


@pytest.mark.asyncio
async def test_geocoding_known_city():
    service = GeocodingService()
    location = await service.geocode("Bhopal")
    assert location is not None
    assert location.name.lower() == "bhopal"
    assert 22.0 <= location.latitude <= 24.5
    assert 76.5 <= location.longitude <= 78.5


@pytest.mark.asyncio
async def test_geocoding_unknown_city():
    service = GeocodingService()
    location = await service.geocode("NonExistentCityXYZ99999")
    assert location is None


@pytest.mark.asyncio
async def test_geocoding_service_error_handling():
    # Pass an unreachable URL to test graceful GeocodingError
    service = GeocodingService(base_url="https://invalid-non-existent-domain-12345.org/v1/search", timeout=1.0)
    with pytest.raises(GeocodingError):
        await service.geocode("Bhopal")


@pytest.mark.asyncio
async def test_weather_fetch_known_coords():
    service = WeatherService()
    # Bhopal coordinates
    facts = await service.fetch_weather(
        location_name="Bhopal",
        latitude=23.25,
        longitude=77.41
    )
    assert isinstance(facts, WeatherFacts)
    assert facts.location == "Bhopal"
    assert isinstance(facts.temperature_2m, float)
    assert isinstance(facts.wind_speed_10m, float)
    assert isinstance(facts.precipitation, float)
    assert isinstance(facts.precipitation_probability, float)
    assert isinstance(facts.uv_index, float)
    assert isinstance(facts.weather_code, int)


@pytest.mark.asyncio
async def test_weather_service_error_handling():
    # Pass an unreachable URL to test graceful WeatherServiceError
    service = WeatherService(base_url="https://invalid-weather-domain-xyz.org/v1/forecast", timeout=1.0)
    with pytest.raises(WeatherServiceError):
        await service.fetch_weather(
            location_name="Bhopal",
            latitude=23.25,
            longitude=77.41
        )
