"""src.context package — Layer 3 real-time context aggregation."""
from src.context.aggregator import ContextAggregator
from src.context.weather import WeatherService
from src.context.market_trends import MarketTrendsService

__all__ = ["ContextAggregator", "WeatherService", "MarketTrendsService"]
