"""
Orchestrates all layer generators in dependency order.

Design: Facade pattern — provides a single generate_all() entry point
that handles generator sequencing and seed derivation internally.
Callers (WorldManager) do not need to know the order or dependencies.
"""
from datetime import datetime

from travel_world.layers.base import LayerMeta
from travel_world.layers.economics_layer import EconomicsLayer
from travel_world.generation.geo_generator import GeoGenerator
from travel_world.generation.weather_generator import WeatherGenerator
from travel_world.generation.traffic_generator import TrafficGenerator
from travel_world.generation.accommodation_generator import AccommodationGenerator
from travel_world.generation.event_generator import EventGenerator
from travel_world.generation.economics_generator import EconomicsGenerator


class WorldGenerator:
    """
    Orchestrates seeded generation of all world layers.

    Generator isolation:
        Each sub-generator gets its own random.Random instance seeded with
        a deterministic value derived from the world seed and the generator name.
        This means changing one generator's implementation does not affect the
        random sequences consumed by other generators.

        Seed derivation: sub_seed = hash((world_seed, generator_name)) % (2**32)

    Args:
        seed: Master world seed.
        config: Optional configuration dict controlling world parameters
                (num_cities, date_range_days, hotels_per_district, etc.)
    """

    DEFAULT_CONFIG = {
        "num_regions": 1,
        "num_cities_per_region": 1,
        "num_districts_per_city": 5,
        "num_hotels_per_district": 3,
        "num_attractions_per_district": 4,
        "num_restaurants_per_district": 5,
        "num_transport_hubs_per_city": 2,
        "date_range_days": 90,
        "num_events_per_city": 60,
        "num_flights_per_route": 10,
    }

    def __init__(self, seed: int, config: dict | None = None):
        self.seed = seed
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}

    def generate_all(self, world_id: str) -> dict:
        """
        Run all generators in dependency order and return dict of layer_id -> BaseLayer.

        Order: geo → weather → traffic → accommodation → event → economics
        """
        now = datetime.utcnow()

        def meta(layer_id: str) -> LayerMeta:
            return LayerMeta(
                layer_id=layer_id,
                world_id=world_id,
                seed=self._derive_seed(layer_id),
                generated_at=now,
            )

        # Pass 1: geography (foundation for all other layers)
        geo = GeoGenerator(self._derive_seed("geo"), self.config).generate(
            world_id, meta("geo")
        )

        # Pass 2: weather and traffic (depend only on geo)
        weather = WeatherGenerator(self._derive_seed("weather"), self.config).generate(
            world_id, meta("weather"), geo
        )
        traffic = TrafficGenerator(self._derive_seed("traffic"), self.config).generate(
            world_id, meta("traffic"), geo
        )

        # Pass 3: accommodation (needs geo; economics not yet available — bootstrap empty)
        empty_econ = EconomicsLayer(meta("economics"), {}, {})
        accommodation = AccommodationGenerator(
            self._derive_seed("accommodation"), self.config
        ).generate(world_id, meta("accommodation"), geo, empty_econ)

        # Pass 4: events (needs geo)
        events = EventGenerator(self._derive_seed("event"), self.config).generate(
            world_id, meta("event"), geo
        )

        # Pass 5: full economics (needs geo, accommodation, events)
        economics = EconomicsGenerator(
            self._derive_seed("economics"), self.config
        ).generate(world_id, meta("economics"), geo, accommodation, events)

        return {
            "geo": geo,
            "weather": weather,
            "traffic": traffic,
            "accommodation": accommodation,
            "event": events,
            "economics": economics,
        }

    def _derive_seed(self, generator_name: str) -> int:
        """Derive a deterministic sub-seed for a named generator from the master seed."""
        return hash((self.seed, generator_name)) % (2**32)
