"""
Geographic hierarchy and transport graph generator.

Two-pass design:
    Pass 1 — Topology: generate the graph skeleton (nodes = hub locations,
             edges = transport connections) with coordinates and connectivity only.
    Pass 2 — Attributes: enrich each node with semantic metadata (city tier,
             district type, location category, etc.) and assign reviews/ratings
             from the fixture database.

This two-pass approach mirrors real geographic data pipelines where topology
(road networks, airport connections) is available separately from semantic
metadata and can be updated independently.
"""
import json
import math
import random
from pathlib import Path

from travel_world.core.entities import (
    Attraction,
    City,
    Coordinates,
    District,
    EventVenue,
    Hotel,
    Location,
    RatingsSummary,
    Region,
    Restaurant,
    Review,
    TransportEdge,
    TransportHub,
)
from travel_world.core.enums import (
    AmenityType,
    AttractionCategory,
    ClimateZone,
    DistrictType,
    LocationType,
    TransportMode,
)
from travel_world.generation.fixture_loader import FixtureLoader
from travel_world.layers.base import LayerMeta
from travel_world.layers.geo_layer import GeoLayer


class GeoGenerator:
    """
    Generates the full geographic hierarchy and transport graph for a world.

    Attributes:
        rng: Seeded random.Random instance (isolated from other generators).
        config: World configuration dict.
        fixture_loader: Loads review/rating fixtures for random assignment.
    """

    # ── Constants (used in generation) ───────────────────────────────────────
    REGION_NAMES = [
        "Northern Europe", "Southern Europe", "East Asia", "Southeast Asia",
        "North America", "South America", "Middle East", "Sub-Saharan Africa",
    ]
    CITY_NAMES = [
        "Aeloria", "Brindor", "Caelum", "Duskport", "Embervale", "Frostholm",
        "Goldenhaven", "Harrowgate", "Ironmere", "Jadebury", "Kestrelford", "Lumina",
        "Mistholm", "Navara", "Oakhaven", "Porthaven", "Queensmere", "Ravenspire",
        "Stormwatch", "Thaloria", "Ulverton", "Velmoor", "Whitmore", "Xandria",
    ]
    DISTRICT_NAME_TEMPLATES = [
        "Old Town", "Marina District", "Arts Quarter", "Financial District",
        "University District", "Riverside", "Hilltop", "Central Market",
        "Harbor View", "Cultural Mile", "East End", "West Quarter", "Northgate",
        "Southbank", "Greenfields",
    ]
    COUNTRY_CODES = ["US", "GB", "FR", "DE", "JP", "AU", "BR", "IN", "ES", "IT",
                     "CA", "MX", "KR", "NL", "SE", "NO", "DK", "CH", "NZ", "ZA"]
    AIRLINE_NAMES = ["SkyLink", "AeroWorld", "GlobalAir", "StarFly", "CloudJet",
                     "HorizonAir", "ZenithAir", "ApexFlight"]
    CUISINE_TYPES = [
        "Italian", "French", "Japanese", "Chinese", "Mexican", "Indian",
        "Mediterranean", "American", "Thai", "Spanish", "Greek", "Vietnamese",
    ]
    FLIGHT_SPEED_KMH = 850
    HAVERSINE_EARTH_RADIUS_KM = 6371
    _DENSITY_PROFILES_PATH = (
        Path(__file__).resolve().parents[2] / "data" / "config" / "district_density_profiles.json"
    )

    def __init__(self, seed: int, config: dict):
        self.rng = random.Random(seed)
        self.config = config
        self.fixture_loader = FixtureLoader(self.rng)
        self._density_profiles = self._load_density_profiles()

    @classmethod
    def _load_density_profiles(cls) -> dict:
        with open(cls._DENSITY_PROFILES_PATH, encoding="utf-8") as fh:
            raw = json.load(fh)
        # Strip the metadata comment keys
        return {k: v for k, v in raw.items() if not k.startswith("_")}

    def _density(self, district, field: str) -> int:
        """Return the count for `field` for this district's type, with default fallback."""
        key = district.district_type.value if hasattr(district.district_type, "value") else str(district.district_type)
        profile = self._density_profiles.get(key, self._density_profiles.get("default", {}))
        default_profile = self._density_profiles.get("default", {})
        value = profile.get(field, default_profile.get(field, 3))
        if isinstance(value, list):
            # [min, max] range
            return self.rng.randint(value[0], value[1])
        return int(value)

    # ── Public entry point ────────────────────────────────────────────────────

    def generate(self, world_id: str, meta: LayerMeta) -> GeoLayer:
        """
        Run both passes and return a complete GeoLayer.

        Pass 1: _generate_topology() — coordinates and graph structure
        Pass 2: _enrich_attributes() — semantic metadata and reviews
        """
        skeleton = self._generate_topology(world_id)
        enriched = self._enrich_attributes(world_id, skeleton)

        # Merge hub locations with enriched locations into one dict
        all_locations: dict[str, Location] = {}
        all_locations.update(skeleton["hub_locations"])
        all_locations.update(enriched["locations"])

        return GeoLayer(
            meta,
            regions=skeleton["regions"],
            cities=skeleton["cities"],
            districts=skeleton["districts"],
            locations=all_locations,
            transport_edges=skeleton["transport_edges"],
        )

    # ── Pass 1: Topology ─────────────────────────────────────────────────────

    def _generate_topology(self, world_id: str) -> dict:
        """
        Generate the graph skeleton: nodes with coordinates, edges with distances.

        Returns a dict with keys: regions, cities, districts, hub_locations,
        transport_edges.
        """
        regions: dict[str, Region] = {}
        cities: dict[str, City] = {}
        districts: dict[str, District] = {}
        hub_locations: dict[str, TransportHub] = {}
        transport_edges: dict[str, TransportEdge] = {}

        num_regions = self.config.get("num_regions", 1)
        num_cities_per_region = self.config.get("num_cities_per_region", 1)
        num_districts_per_city = self.config.get("num_districts_per_city", 5)
        num_hubs_per_city = self.config.get("num_transport_hubs_per_city", 2)

        city_global_idx = 0
        district_global_idx = 0
        hub_global_idx = 0
        edge_global_idx = 0

        # city_id -> list[hub_location_id] for edge generation
        city_hub_map: dict[str, list[str]] = {}

        for region_idx in range(num_regions):
            region = self._generate_region(world_id, region_idx)
            regions[region.region_id] = region

            for city_local_idx in range(num_cities_per_region):
                city = self._generate_city(world_id, region, city_global_idx)
                cities[city.city_id] = city
                city_hub_map[city.city_id] = []

                # Districts
                for d_local_idx in range(num_districts_per_city):
                    district = self._generate_district(
                        world_id, city, district_global_idx
                    )
                    districts[district.district_id] = district
                    district_global_idx += 1

                # Transport hubs — use first district of the city as their district
                # (districts were generated just above, so we can look up the first one)
                first_district_id = next(
                    (d.district_id for d in districts.values() if d.city_id == city.city_id),
                    None,
                )
                for hub_local_idx in range(num_hubs_per_city):
                    hub_type = "airport" if hub_local_idx == 0 else "train_station"
                    hub = self._generate_transport_hub(
                        world_id, city, hub_type, hub_global_idx,
                        district_id=first_district_id or f"district_{world_id}_0000",
                    )
                    hub_locations[hub.location_id] = hub
                    city_hub_map[city.city_id].append(hub.location_id)
                    hub_global_idx += 1

                # Intra-city walking/bus edges between all hub pairs
                city_hubs = city_hub_map[city.city_id]
                for i in range(len(city_hubs)):
                    for j in range(len(city_hubs)):
                        if i == j:
                            continue
                        hub_a = hub_locations[city_hubs[i]]
                        hub_b = hub_locations[city_hubs[j]]
                        dist = self._haversine(
                            hub_a.coordinates.lat, hub_a.coordinates.lon,
                            hub_b.coordinates.lat, hub_b.coordinates.lon,
                        )
                        mode = TransportMode.BUS
                        travel_time = (dist / 50.0) * 60  # 50 km/h bus speed
                        edge_id = f"edge_{world_id}_{edge_global_idx:04d}"
                        edge = TransportEdge(
                            edge_id=edge_id,
                            origin_node_id=hub_a.location_id,
                            destination_node_id=hub_b.location_id,
                            mode=mode,
                            distance_km=round(dist, 2),
                            base_travel_time_min=round(travel_time, 1),
                            base_cost=round(dist * 0.5, 2),
                            carrier=None,
                            frequency_per_day=24,
                        )
                        transport_edges[edge_id] = edge
                        edge_global_idx += 1

                city_global_idx += 1

        # Inter-city flight edges between all airport pairs
        all_city_ids = list(cities.keys())
        for i in range(len(all_city_ids)):
            for j in range(len(all_city_ids)):
                if i == j:
                    continue
                city_a_id = all_city_ids[i]
                city_b_id = all_city_ids[j]
                # First hub of each city is the airport
                hubs_a = city_hub_map.get(city_a_id, [])
                hubs_b = city_hub_map.get(city_b_id, [])
                if not hubs_a or not hubs_b:
                    continue
                airport_a = hub_locations[hubs_a[0]]
                airport_b = hub_locations[hubs_b[0]]
                dist = self._haversine(
                    airport_a.coordinates.lat, airport_a.coordinates.lon,
                    airport_b.coordinates.lat, airport_b.coordinates.lon,
                )
                # Minimum flight distance 100 km
                if dist < 100:
                    dist = 100.0
                # Add 45 min overhead (taxi, boarding, climb, descent, landing)
                travel_time = (dist / self.FLIGHT_SPEED_KMH) * 60 + 45
                airline = self.rng.choice(self.AIRLINE_NAMES)
                num_flights = self.config.get("num_flights_per_route", 10)
                # 10 departure slots; early morning and red-eye carry a premium,
                # mid-afternoon off-peak flights are cheapest.
                DEPARTURE_TIMES = [
                    "05:00", "07:00", "09:00", "11:00", "13:00",
                    "15:00", "17:00", "19:00", "21:00", "23:00",
                ]
                # Price multipliers correlated with departure time inconvenience:
                # 05:00 very early (+20%), 23:00 red-eye (+25%), 15:00 cheapest (-15%).
                PRICE_MULTS = [1.20, 1.00, 0.90, 0.95, 1.05,
                               0.85, 1.10, 1.05, 1.15, 1.25]
                for flight_num in range(num_flights):
                    dep_idx = flight_num % len(DEPARTURE_TIMES)
                    base_cost = round(
                        (50.0 + dist * 0.12) * PRICE_MULTS[dep_idx], 2
                    )
                    edge_id = f"edge_{world_id}_{edge_global_idx:04d}"
                    edge = TransportEdge(
                        edge_id=edge_id,
                        origin_node_id=airport_a.location_id,
                        destination_node_id=airport_b.location_id,
                        mode=TransportMode.FLIGHT,
                        distance_km=round(dist, 2),
                        base_travel_time_min=round(travel_time, 1),
                        base_cost=base_cost,
                        carrier=airline,
                        frequency_per_day=num_flights,
                        metadata={
                            "origin_city_id": city_a_id,
                            "destination_city_id": city_b_id,
                            "departure_time": DEPARTURE_TIMES[dep_idx],
                            "flight_number": f"{airline[:2].upper()}{100 + flight_num + i*10 + j*100}",
                            "airline": airline,
                            "price_multiplier": PRICE_MULTS[dep_idx],
                        },
                    )
                    transport_edges[edge_id] = edge
                    edge_global_idx += 1

        return {
            "regions": regions,
            "cities": cities,
            "districts": districts,
            "hub_locations": hub_locations,
            "transport_edges": transport_edges,
            "city_hub_map": city_hub_map,
        }

    def _generate_region(self, world_id: str, idx: int) -> Region:
        """Generate a Region entity with random coordinates."""
        name = self.REGION_NAMES[idx % len(self.REGION_NAMES)]
        lat = self.rng.uniform(-40, 60)
        lon = self.rng.uniform(-150, 150)
        country_code = self.rng.choice(self.COUNTRY_CODES)
        region_id = f"region_{world_id}_{idx:04d}"
        return Region(
            region_id=region_id,
            name=name,
            coordinates=Coordinates(lat=round(lat, 5), lon=round(lon, 5)),
            country_code=country_code,
            description=f"The {name} region.",
        )

    def _generate_city(self, world_id: str, region: Region, idx: int) -> City:
        """Generate a City entity near its region center."""
        name = self.CITY_NAMES[idx % len(self.CITY_NAMES)]
        lat = region.coordinates.lat + self.rng.uniform(-15, 15)
        lon = region.coordinates.lon + self.rng.uniform(-15, 15)
        lat = max(-85.0, min(85.0, lat))
        lon = max(-180.0, min(180.0, lon))
        city_id = f"city_{world_id}_{idx:04d}"
        population = self.rng.randint(100_000, 10_000_000)
        economic_tier = self.rng.randint(1, 5)
        tourism_density = round(self.rng.uniform(0.1, 1.0), 3)
        safety_score = round(self.rng.uniform(0.3, 1.0), 3)
        climate_zone = self.rng.choice(list(ClimateZone))
        transport_quality = round(self.rng.uniform(0.3, 1.0), 3)
        return City(
            city_id=city_id,
            name=name,
            region_id=region.region_id,
            coordinates=Coordinates(lat=round(lat, 5), lon=round(lon, 5)),
            population=population,
            economic_tier=economic_tier,
            tourism_density=tourism_density,
            safety_score=safety_score,
            climate_zone=climate_zone,
            transport_quality=transport_quality,
            description=f"{name} is a city in the {region.name} region.",
            timezone="UTC",
        )

    def _generate_district(self, world_id: str, city: City, idx: int) -> District:
        """Generate a District entity near its city center."""
        name = self.DISTRICT_NAME_TEMPLATES[idx % len(self.DISTRICT_NAME_TEMPLATES)]
        lat = city.coordinates.lat + self.rng.uniform(-0.05, 0.05)
        lon = city.coordinates.lon + self.rng.uniform(-0.05, 0.05)
        district_id = f"district_{world_id}_{idx:04d}"
        district_type = self.rng.choice(list(DistrictType))
        safety_score = round(self.rng.uniform(0.2, 1.0), 3)
        walkability_score = round(self.rng.uniform(0.2, 1.0), 3)
        noise_level = round(self.rng.uniform(0.0, 1.0), 3)
        cost_index = round(self.rng.uniform(0.5, 2.5), 3)
        return District(
            district_id=district_id,
            city_id=city.city_id,
            name=name,
            coordinates=Coordinates(lat=round(lat, 6), lon=round(lon, 6)),
            district_type=district_type,
            safety_score=safety_score,
            walkability_score=walkability_score,
            noise_level=noise_level,
            cost_index=cost_index,
            description=f"{name} district in {city.name}.",
        )

    def _generate_transport_hub(
        self, world_id: str, city: City, hub_type: str, idx: int,
        district_id: str = "",
    ) -> TransportHub:
        """Generate a TransportHub (airport or train station) for a city."""
        lat = city.coordinates.lat + self.rng.uniform(-0.05, 0.05)
        lon = city.coordinates.lon + self.rng.uniform(-0.05, 0.05)
        location_id = f"hub_{world_id}_{idx:04d}"
        iata_code = city.name[:3].upper() if hub_type == "airport" else None
        name = (
            f"{city.name} International Airport"
            if hub_type == "airport"
            else f"{city.name} Central Station"
        )
        return TransportHub(
            location_id=location_id,
            name=name,
            district_id=district_id,
            city_id=city.city_id,
            coordinates=Coordinates(lat=round(lat, 6), lon=round(lon, 6)),
            location_type=LocationType.TRANSPORT_HUB,
            opening_hours={d: "00:00-23:59" for d in
                           ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
            capacity=self.rng.randint(500, 50_000),
            popularity_score=round(self.rng.uniform(0.5, 1.0), 3),
            hub_type=hub_type,
            iata_code=iata_code,
            connections=[],
            description=f"{name}.",
        )

    # ── Pass 2: Attribute enrichment ─────────────────────────────────────────

    def _enrich_attributes(self, world_id: str, skeleton: dict) -> dict:
        """
        Second pass: generate non-hub locations (hotels, attractions, restaurants,
        event venues) and assign reviews/ratings from fixture database to all locations.
        """
        locations: dict[str, Location] = {}
        loc_idx = 0

        districts: dict[str, District] = skeleton["districts"]
        cities: dict[str, City] = skeleton["cities"]

        for district_id, district in districts.items():
            city = cities[district.city_id]

            # Hotels
            hotels = self._generate_hotels_in_district(world_id, district, city, loc_idx)
            for hotel in hotels:
                locations[hotel.location_id] = hotel
            loc_idx += len(hotels)

            # Attractions
            attractions = self._generate_attractions_in_district(world_id, district, city, loc_idx)
            for attraction in attractions:
                locations[attraction.location_id] = attraction
            loc_idx += len(attractions)

            # Restaurants
            restaurants = self._generate_restaurants_in_district(world_id, district, city, loc_idx)
            for restaurant in restaurants:
                locations[restaurant.location_id] = restaurant
            loc_idx += len(restaurants)

            # Event venues (1-2 per district)
            venues = self._generate_event_venues_in_district(world_id, district, city, loc_idx)
            for venue in venues:
                locations[venue.location_id] = venue
            loc_idx += len(venues)

        return {"locations": locations}

    def _generate_hotels_in_district(
        self, world_id: str, district: District, city: City, start_idx: int
    ) -> list[Hotel]:
        """Generate Hotel entities for one district."""
        n = self._density(district, "hotels")
        hotels: list[Hotel] = []
        star_weights = [0.1, 0.1, 0.4, 0.3, 0.1]
        star_choices = [1, 2, 3, 4, 5]
        for i in range(n):
            location_id = f"hotel_{world_id}_{start_idx + i:04d}"
            lat = district.coordinates.lat + self.rng.uniform(-0.01, 0.01)
            lon = district.coordinates.lon + self.rng.uniform(-0.01, 0.01)
            star_rating = self.rng.choices(star_choices, weights=star_weights, k=1)[0]
            price_per_night = round(
                star_rating * 50 + self.rng.uniform(-20, 40) * district.cost_index, 2
            )
            price_per_night = max(20.0, price_per_night)
            amenities = [AmenityType.WIFI]
            if star_rating >= 2:
                amenities.append(AmenityType.PARKING)
            if star_rating >= 3:
                amenities.extend([AmenityType.BREAKFAST, AmenityType.PET_FRIENDLY])
            if star_rating >= 4:
                amenities.extend([AmenityType.GYM, AmenityType.POOL])
            if star_rating >= 5:
                amenities.extend([AmenityType.SPA])
            total_rooms = self.rng.randint(20, 200)
            neighborhood_score = round(
                district.safety_score * 0.6 + district.walkability_score * 0.4, 3
            )
            popularity = round(self.rng.uniform(0.2, 1.0), 3)
            reviews, ratings = self._assign_reviews("hotel", self.rng.randint(5, 15))
            hotel_names = [
                f"The {district.name} Hotel", f"{city.name} Grand",
                f"Hotel {city.name[:3]}{i + 1}", f"{city.name} Suites",
                f"The {star_rating}-Star Inn",
            ]
            name = self.rng.choice(hotel_names)
            hotels.append(
                Hotel(
                    location_id=location_id,
                    name=name,
                    district_id=district.district_id,
                    city_id=city.city_id,
                    coordinates=Coordinates(lat=round(lat, 6), lon=round(lon, 6)),
                    location_type=LocationType.HOTEL,
                    opening_hours={d: "00:00-23:59" for d in
                                   ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
                    capacity=total_rooms * 2,
                    popularity_score=popularity,
                    ratings=ratings,
                    reviews=reviews,
                    description=f"A {star_rating}-star hotel in {district.name}.",
                    tags=["hotel", f"{star_rating}_star"],
                    star_rating=star_rating,
                    price_per_night=price_per_night,
                    amenities=amenities,
                    room_types={"Standard": 1.0, "Deluxe": 1.4, "Suite": 2.2},
                    total_rooms=total_rooms,
                    neighborhood_score=neighborhood_score,
                )
            )
        return hotels

    def _generate_attractions_in_district(
        self, world_id: str, district: District, city: City, start_idx: int
    ) -> list[Attraction]:
        """Generate Attraction entities for one district."""
        n = self._density(district, "attractions")
        attractions: list[Attraction] = []
        outdoor_categories = {
            AttractionCategory.PARK, AttractionCategory.BEACH,
        }
        museum_categories = {
            AttractionCategory.MUSEUM, AttractionCategory.GALLERY,
        }
        for i in range(n):
            location_id = f"attraction_{world_id}_{start_idx + i:04d}"
            lat = district.coordinates.lat + self.rng.uniform(-0.01, 0.01)
            lon = district.coordinates.lon + self.rng.uniform(-0.01, 0.01)
            category = self.rng.choice(list(AttractionCategory))
            duration_hours = round(self.rng.uniform(0.5, 4.0), 1)
            ticket_price = round(self.rng.uniform(0, 50), 2)
            free_entry = ticket_price < 5
            if category in outdoor_categories:
                weather_sensitivity = round(self.rng.uniform(0.6, 1.0), 3)
            elif category in museum_categories:
                weather_sensitivity = round(self.rng.uniform(0.0, 0.2), 3)
            else:
                weather_sensitivity = round(self.rng.uniform(0.2, 0.6), 3)
            popularity = round(self.rng.uniform(0.2, 1.0), 3)
            crowding_base = round(popularity * self.rng.uniform(0.5, 1.0), 3)
            reviews, ratings = self._assign_reviews(
                "attraction", self.rng.randint(5, 15)
            )
            attraction_names = [
                f"{city.name} {category.value.replace('_', ' ').title()}",
                f"{district.name} {category.value.replace('_', ' ').title()}",
                f"The Great {category.value.replace('_', ' ').title()} of {city.name}",
            ]
            name = self.rng.choice(attraction_names)
            attractions.append(
                Attraction(
                    location_id=location_id,
                    name=name,
                    district_id=district.district_id,
                    city_id=city.city_id,
                    coordinates=Coordinates(lat=round(lat, 6), lon=round(lon, 6)),
                    location_type=LocationType.ATTRACTION,
                    opening_hours=self._attraction_opening_hours(),
                    capacity=self.rng.randint(50, 5000),
                    popularity_score=popularity,
                    ratings=ratings,
                    reviews=reviews,
                    description=f"A {category.value} attraction in {district.name}.",
                    tags=["attraction", category.value],
                    category=category,
                    duration_hours=duration_hours,
                    ticket_price=ticket_price,
                    weather_sensitivity=weather_sensitivity,
                    crowding_base=crowding_base,
                    free_entry=free_entry,
                )
            )
        return attractions

    def _generate_restaurants_in_district(
        self, world_id: str, district: District, city: City, start_idx: int
    ) -> list[Restaurant]:
        """Generate Restaurant entities for one district."""
        n = self._density(district, "restaurants")
        restaurants: list[Restaurant] = []
        days_all = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i in range(n):
            location_id = f"restaurant_{world_id}_{start_idx + i:04d}"
            lat = district.coordinates.lat + self.rng.uniform(-0.01, 0.01)
            lon = district.coordinates.lon + self.rng.uniform(-0.01, 0.01)
            # 1-2 cuisine types
            num_cuisines = self.rng.randint(1, 2)
            cuisine_types = self.rng.sample(self.CUISINE_TYPES, num_cuisines)
            average_spend = round(
                self.rng.uniform(10, 120) * (0.5 + district.cost_index * 0.5), 2
            )
            popularity = round(self.rng.uniform(0.2, 1.0), 3)
            reservation_required = self.rng.random() < 0.3
            michelin_stars = 0
            if self.rng.random() < 0.05:
                michelin_stars = self.rng.randint(1, 3)
            reviews, ratings = self._assign_reviews(
                "restaurant", self.rng.randint(3, 10)
            )
            # Some restaurants closed Monday
            closed_monday = self.rng.random() < 0.25
            opening_hours: dict[str, str] = {}
            for day in days_all:
                if closed_monday and day == "Mon":
                    opening_hours[day] = ""
                else:
                    opening_hours[day] = "11:00-22:00"
            name = f"{self.rng.choice(cuisine_types)} Kitchen {city.name[:3]}{i + 1}"
            restaurants.append(
                Restaurant(
                    location_id=location_id,
                    name=name,
                    district_id=district.district_id,
                    city_id=city.city_id,
                    coordinates=Coordinates(lat=round(lat, 6), lon=round(lon, 6)),
                    location_type=LocationType.RESTAURANT,
                    opening_hours=opening_hours,
                    capacity=self.rng.randint(20, 200),
                    popularity_score=popularity,
                    ratings=ratings,
                    reviews=reviews,
                    description=(
                        f"A {' & '.join(cuisine_types)} restaurant in {district.name}."
                    ),
                    tags=["restaurant"] + [c.lower() for c in cuisine_types],
                    cuisine_types=cuisine_types,
                    average_spend=average_spend,
                    michelin_stars=michelin_stars,
                    reservation_required=reservation_required,
                )
            )
        return restaurants

    def _generate_event_venues_in_district(
        self, world_id: str, district: District, city: City, start_idx: int
    ) -> list[EventVenue]:
        """Generate EventVenue entities for one district (count from density profile)."""
        n = self._density(district, "event_venues")
        venues: list[EventVenue] = []
        venue_type_choices = [
            "Concert Hall", "Stadium", "Theater", "Park Stage", "Conference Center",
        ]
        outdoor_types = {"Park Stage", "Stadium"}
        for i in range(n):
            location_id = f"venue_{world_id}_{start_idx + i:04d}"
            lat = district.coordinates.lat + self.rng.uniform(-0.01, 0.01)
            lon = district.coordinates.lon + self.rng.uniform(-0.01, 0.01)
            venue_type = self.rng.choice(venue_type_choices)
            max_capacity = self.rng.randint(100, 10_000)
            indoor = venue_type not in outdoor_types
            popularity = round(self.rng.uniform(0.3, 1.0), 3)
            name = f"{district.name} {venue_type}"
            venues.append(
                EventVenue(
                    location_id=location_id,
                    name=name,
                    district_id=district.district_id,
                    city_id=city.city_id,
                    coordinates=Coordinates(lat=round(lat, 6), lon=round(lon, 6)),
                    location_type=LocationType.EVENT_VENUE,
                    opening_hours={d: "18:00-23:00" for d in
                                   ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
                    capacity=max_capacity,
                    popularity_score=popularity,
                    description=f"A {venue_type} in {district.name}, {city.name}.",
                    tags=["venue", venue_type.lower().replace(" ", "_")],
                    venue_type=venue_type,
                    max_capacity=max_capacity,
                    indoor=indoor,
                )
            )
        return venues

    def _assign_reviews(
        self, location_type: str, n: int
    ) -> tuple[list[Review], RatingsSummary]:
        """Draw n random reviews from the fixture database and compute summary."""
        raw = self.fixture_loader.get_reviews(location_type, n)
        reviews = [Review(**r) for r in raw]
        summary = RatingsSummary.from_reviews(reviews)
        return reviews, summary

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Return great-circle distance in km between two WGS-84 coordinates."""
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.asin(math.sqrt(a))

    @staticmethod
    def _attraction_opening_hours() -> dict[str, str]:
        """Return standard opening hours for an attraction."""
        return {
            "Mon": "09:00-18:00",
            "Tue": "09:00-18:00",
            "Wed": "09:00-18:00",
            "Thu": "09:00-18:00",
            "Fri": "09:00-18:00",
            "Sat": "09:00-18:00",
            "Sun": "10:00-17:00",
        }
