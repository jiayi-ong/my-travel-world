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
    EventCategory,
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

        # 10 departure slots with time-of-day price multipliers
        DEPARTURE_TIMES = [
            "05:00", "07:00", "09:00", "11:00", "13:00",
            "15:00", "17:00", "19:00", "21:00", "23:00",
        ]
        PRICE_MULTS = [1.20, 1.00, 0.90, 0.95, 1.05, 0.85, 1.10, 1.05, 1.15, 1.25]
        num_flights = self.config.get("num_flights_per_route", 10)

        # Pre-compute airport distances for layover generation
        _ap_dist: dict[tuple, float] = {}
        _ap_travel_time: dict[tuple, float] = {}
        for i in range(len(all_city_ids)):
            for j in range(len(all_city_ids)):
                if i == j:
                    continue
                ca, cb = all_city_ids[i], all_city_ids[j]
                ha = city_hub_map.get(ca, [])
                hb = city_hub_map.get(cb, [])
                if not ha or not hb:
                    continue
                ap_a = hub_locations[ha[0]]
                ap_b = hub_locations[hb[0]]
                d = self._haversine(
                    ap_a.coordinates.lat, ap_a.coordinates.lon,
                    ap_b.coordinates.lat, ap_b.coordinates.lon,
                )
                if d < 100:
                    d = 100.0
                _ap_dist[(ca, cb)] = d
                _ap_travel_time[(ca, cb)] = (d / self.FLIGHT_SPEED_KMH) * 60 + 45

        # ── Direct flights ────────────────────────────────────────────────
        for i in range(len(all_city_ids)):
            for j in range(len(all_city_ids)):
                if i == j:
                    continue
                city_a_id = all_city_ids[i]
                city_b_id = all_city_ids[j]
                if (city_a_id, city_b_id) not in _ap_dist:
                    continue
                dist = _ap_dist[(city_a_id, city_b_id)]
                travel_time = _ap_travel_time[(city_a_id, city_b_id)]
                airport_a = hub_locations[city_hub_map[city_a_id][0]]
                airport_b = hub_locations[city_hub_map[city_b_id][0]]
                airline = self.rng.choice(self.AIRLINE_NAMES)
                for flight_num in range(num_flights):
                    dep_idx = flight_num % len(DEPARTURE_TIMES)
                    base_cost = round((50.0 + dist * 0.12) * PRICE_MULTS[dep_idx], 2)
                    # ±30 min variability in 5-min increments
                    variation_steps = self.rng.randint(-6, 6)
                    duration_min = max(30, round(travel_time / 5) * 5 + variation_steps * 5)
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
                            "duration_min": duration_min,
                            "is_direct": True,
                        },
                    )
                    transport_edges[edge_id] = edge
                    edge_global_idx += 1

        # ── Connecting (layover) flights ──────────────────────────────────
        # For each A→C pair, find the best intermediate city B where
        # dist(A,B) + dist(B,C) < 1.5 * dist(A,C). Generate 2-3 departure
        # options so the connecting option appears alongside direct flights.
        for i in range(len(all_city_ids)):
            for j in range(len(all_city_ids)):
                if i == j:
                    continue
                city_a_id = all_city_ids[i]
                city_c_id = all_city_ids[j]
                dist_ac = _ap_dist.get((city_a_id, city_c_id))
                if dist_ac is None:
                    continue
                airport_a = hub_locations[city_hub_map[city_a_id][0]]
                airport_c = hub_locations[city_hub_map[city_c_id][0]]

                # Find best intermediate city (smallest total detour)
                best_b_id = None
                best_extra = float("inf")
                for b_idx in range(len(all_city_ids)):
                    if b_idx == i or b_idx == j:
                        continue
                    city_b_id = all_city_ids[b_idx]
                    dist_ab = _ap_dist.get((city_a_id, city_b_id))
                    dist_bc = _ap_dist.get((city_b_id, city_c_id))
                    if dist_ab is None or dist_bc is None:
                        continue
                    extra = (dist_ab + dist_bc) - dist_ac
                    if extra < best_extra:
                        best_extra = extra
                        best_b_id = city_b_id

                if best_b_id is None:
                    continue

                dist_ab = _ap_dist[(city_a_id, best_b_id)]
                dist_bc = _ap_dist[(best_b_id, city_c_id)]
                tt_ab = _ap_travel_time[(city_a_id, best_b_id)]
                tt_bc = _ap_travel_time[(best_b_id, city_c_id)]
                layover_min = self.rng.choice([60, 75, 90, 105, 120])
                total_duration = round(tt_ab + tt_bc + layover_min)
                airport_b = hub_locations[city_hub_map[best_b_id][0]]
                airline = self.rng.choice(self.AIRLINE_NAMES)
                # Generate 3 departure slots for the connecting option
                layover_slots = self.rng.sample(range(len(DEPARTURE_TIMES)), min(3, len(DEPARTURE_TIMES)))
                for k, dep_idx in enumerate(layover_slots):
                    base_cost = round((50.0 + (dist_ab + dist_bc) * 0.10) * PRICE_MULTS[dep_idx], 2)
                    fn1 = f"{airline[:2].upper()}{200 + k + i*10 + j*100}"
                    fn2 = f"{airline[:2].upper()}{201 + k + i*10 + j*100}"
                    edge_id = f"edge_{world_id}_{edge_global_idx:04d}"
                    edge = TransportEdge(
                        edge_id=edge_id,
                        origin_node_id=airport_a.location_id,
                        destination_node_id=airport_c.location_id,
                        mode=TransportMode.FLIGHT,
                        distance_km=round(dist_ab + dist_bc, 2),
                        base_travel_time_min=float(total_duration),
                        base_cost=base_cost,
                        carrier=airline,
                        frequency_per_day=len(layover_slots),
                        metadata={
                            "origin_city_id": city_a_id,
                            "destination_city_id": city_c_id,
                            "departure_time": DEPARTURE_TIMES[dep_idx],
                            "flight_number": fn1,
                            "airline": airline,
                            "price_multiplier": PRICE_MULTS[dep_idx],
                            "duration_min": total_duration,
                            "is_direct": False,
                            "layover_city_id": best_b_id,
                            "layover_city_name": cities[best_b_id].name,
                            "layover_airport_id": airport_b.location_id,
                            "layover_duration_min": layover_min,
                            "connecting_flight_numbers": [fn1, fn2],
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
        travel_advisory = self._generate_travel_advisory(safety_score)
        # Dominant cuisines: 2-3 drawn with mild bias toward richer cuisines for high-tier cities
        high_tier_cuisines = ["French", "Japanese", "Mediterranean", "Spanish", "Italian"]
        low_tier_cuisines = ["Indian", "Mexican", "Thai", "Vietnamese", "Chinese"]
        if economic_tier >= 4:
            cuisine_pool = high_tier_cuisines + self.CUISINE_TYPES
        elif economic_tier <= 2:
            cuisine_pool = low_tier_cuisines + self.CUISINE_TYPES
        else:
            cuisine_pool = self.CUISINE_TYPES
        n_dominant_cuisines = self.rng.randint(2, 3)
        dominant_cuisines = list(dict.fromkeys(self.rng.choices(cuisine_pool, k=n_dominant_cuisines * 3)))[:n_dominant_cuisines]
        # Dominant event categories: 2-3 random draws from EventCategory
        all_event_cats = [c.value for c in EventCategory]
        n_dominant_events = self.rng.randint(2, 3)
        dominant_event_categories = self.rng.sample(all_event_cats, n_dominant_events)
        vibe_summary = self._generate_vibe_summary(
            name, region.name, economic_tier, tourism_density,
            safety_score, climate_zone, dominant_cuisines, dominant_event_categories,
        )
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
            travel_advisory=travel_advisory,
            dominant_cuisines=dominant_cuisines,
            dominant_event_categories=dominant_event_categories,
            vibe_summary=vibe_summary,
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
        # Assign district visitor reviews; weight sampling towards reviews that match safety level
        # (low safety_score → more negative reviews drawn from the pool)
        n_reviews = self.rng.randint(3, 7)
        district_reviews, _ = self._assign_reviews("district", n_reviews)
        description = self._generate_district_description(name, city.name, district_type, safety_score, walkability_score, cost_index)
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
            description=description,
            reviews=district_reviews,
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
            _STAR_BASE_PRICE = {1: 35, 2: 80, 3: 150, 4: 270, 5: 460}
            base = _STAR_BASE_PRICE[star_rating]
            noise = self.rng.uniform(0.88, 1.12)
            district_factor = 0.75 + district.cost_index * 0.35  # range ~0.88 to 1.63
            price_per_night = round(base * noise * district_factor, 2)
            price_per_night = max(20.0, price_per_night)
            amenities = [AmenityType.WIFI, AmenityType.AIR_CONDITIONING]  # always included

            # Parking: 90% for 2+, 50% for 1-star
            if self.rng.random() < (0.9 if star_rating >= 2 else 0.5):
                amenities.append(AmenityType.PARKING)

            # Breakfast: 85% for 3+, 50% for 2, 20% for 1
            breakfast_prob = 0.85 if star_rating >= 3 else (0.5 if star_rating == 2 else 0.2)
            if self.rng.random() < breakfast_prob:
                amenities.append(AmenityType.BREAKFAST)

            # Pet friendly: 60% for 3+, 30% for 1-2
            if self.rng.random() < (0.6 if star_rating >= 3 else 0.3):
                amenities.append(AmenityType.PET_FRIENDLY)

            # Gym: 90% for 4+, 50% for 3, 15% for 1-2
            gym_prob = 0.9 if star_rating >= 4 else (0.5 if star_rating == 3 else 0.15)
            if self.rng.random() < gym_prob:
                amenities.append(AmenityType.GYM)

            # Pool: 80% for 4+, 35% for 3, 10% for 1-2
            pool_prob = 0.8 if star_rating >= 4 else (0.35 if star_rating == 3 else 0.1)
            if self.rng.random() < pool_prob:
                amenities.append(AmenityType.POOL)

            # Spa: 90% for 5, 50% for 4, 15% for 3, 5% for 1-2
            spa_prob = 0.9 if star_rating == 5 else (0.5 if star_rating == 4 else (0.15 if star_rating == 3 else 0.05))
            if self.rng.random() < spa_prob:
                amenities.append(AmenityType.SPA)

            # Restaurant on-site: 80% for 4+, 45% for 3, 15% for 1-2
            rest_prob = 0.8 if star_rating >= 4 else (0.45 if star_rating == 3 else 0.15)
            if self.rng.random() < rest_prob:
                amenities.append(AmenityType.RESTAURANT)

            # Bar: 75% for 4+, 40% for 3, 15% for 1-2
            bar_prob = 0.75 if star_rating >= 4 else (0.4 if star_rating == 3 else 0.15)
            if self.rng.random() < bar_prob:
                amenities.append(AmenityType.BAR)

            # Laundry: 70% for all 2+, 30% for 1
            if self.rng.random() < (0.7 if star_rating >= 2 else 0.3):
                amenities.append(AmenityType.LAUNDRY)

            # Room service: 95% for 5, 80% for 4, 50% for 3, 15% for 1-2
            rs_prob = 0.95 if star_rating == 5 else (0.8 if star_rating == 4 else (0.5 if star_rating == 3 else 0.15))
            if self.rng.random() < rs_prob:
                amenities.append(AmenityType.ROOM_SERVICE)

            # Business center: 85% for 4+, 50% for 3, 20% for 1-2
            biz_prob = 0.85 if star_rating >= 4 else (0.5 if star_rating == 3 else 0.2)
            if self.rng.random() < biz_prob:
                amenities.append(AmenityType.BUSINESS_CENTER)

            # Concierge: 95% for 5, 70% for 4, 30% for 3, 5% for 1-2
            con_prob = 0.95 if star_rating == 5 else (0.7 if star_rating == 4 else (0.3 if star_rating == 3 else 0.05))
            if self.rng.random() < con_prob:
                amenities.append(AmenityType.CONCIERGE)

            # EV charging: 60% for 4+, 25% for 3, 10% for 1-2
            ev_prob = 0.6 if star_rating >= 4 else (0.25 if star_rating == 3 else 0.1)
            if self.rng.random() < ev_prob:
                amenities.append(AmenityType.EV_CHARGING)

            # Airport shuttle: probability-based by star (60/45/20/8/3% for 5/4/3/2/1)
            _SHUTTLE_PROBS = {5: 0.60, 4: 0.45, 3: 0.20, 2: 0.08, 1: 0.03}
            airport_shuttle = self.rng.random() < _SHUTTLE_PROBS[star_rating]

            total_rooms = self.rng.randint(20, 200)
            neighborhood_score = round(
                district.safety_score * 0.6 + district.walkability_score * 0.4, 3
            )
            popularity = round(self.rng.uniform(0.2, 1.0), 3)
            reviews, ratings = self._assign_reviews("hotel", self.rng.randint(5, 15))
            hotel_name_templates = [
                f"The {district.name} Hotel", f"{city.name} Grand",
                f"Hotel {city.name[:3]}{i + 1}", f"{city.name} Suites",
                f"The {district.name} Inn", f"{city.name} Residences",
                f"Grand {district.name}", f"The {city.name} Plaza",
            ]
            name = self.rng.choice(hotel_name_templates)
            # num_beds scales with star rating (1-star: 1 bed, 5-star: up to 4)
            num_beds = min(4, max(1, star_rating - 1 + self.rng.randint(0, 2)))
            # Check-in time: random ±2 hours around 1 pm (11:00–15:00)
            checkin_slots = [
                "11:00", "11:30", "12:00", "12:30", "13:00",
                "13:30", "14:00", "14:30", "15:00",
            ]
            check_in_time = self.rng.choice(checkin_slots)
            description = self._generate_hotel_description(
                name, star_rating, district, city, amenities, airport_shuttle
            )
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
                    description=description,
                    tags=["hotel", f"{star_rating}_star"],
                    star_rating=star_rating,
                    price_per_night=price_per_night,
                    amenities=amenities,
                    room_types={"Standard": 1.0, "Deluxe": 1.4, "Suite": 2.2},
                    total_rooms=total_rooms,
                    neighborhood_score=neighborhood_score,
                    num_beds=num_beds,
                    check_in_time=check_in_time,
                    airport_shuttle=airport_shuttle,
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
        """Generate Restaurant entities for one district, weighted toward city dominant cuisines."""
        n = self._density(district, "restaurants")
        restaurants: list[Restaurant] = []
        days_all = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        # Build cuisine pool with 3× weight for dominant city cuisines
        dominant = getattr(city, "dominant_cuisines", [])
        cuisine_pool = dominant * 3 + self.CUISINE_TYPES if dominant else self.CUISINE_TYPES
        for i in range(n):
            location_id = f"restaurant_{world_id}_{start_idx + i:04d}"
            lat = district.coordinates.lat + self.rng.uniform(-0.01, 0.01)
            lon = district.coordinates.lon + self.rng.uniform(-0.01, 0.01)
            # 1-2 cuisine types, drawn from weighted pool
            num_cuisines = self.rng.randint(1, 2)
            cuisine_types = list(dict.fromkeys(self.rng.choices(cuisine_pool, k=num_cuisines * 2)))[:num_cuisines]
            if not cuisine_types:
                cuisine_types = self.rng.sample(self.CUISINE_TYPES, 1)
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
            opening_hours = self._restaurant_opening_hours()
            name = self._generate_restaurant_name(cuisine_types, city, district, i)
            description = self._generate_restaurant_description(cuisine_types, district, city, average_spend, michelin_stars)
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
                    description=description,
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

    def _generate_vibe_summary(
        self, name: str, region: str, economic_tier: int, tourism_density: float,
        safety_score: float, climate_zone, dominant_cuisines: list[str],
        dominant_event_categories: list[str],
    ) -> str:
        """Generate a 2-3 sentence prose vibe summary for a city."""
        tier_adj = {1: "budget-conscious", 2: "emerging", 3: "mid-tier", 4: "prosperous", 5: "affluent"}[economic_tier]
        tourism_adj = "highly popular" if tourism_density >= 0.7 else ("moderately visited" if tourism_density >= 0.4 else "off-the-beaten-path")
        climate_desc = {
            "tropical": "warm and humid year-round",
            "subtropical": "mild winters and hot summers",
            "temperate": "four distinct seasons",
            "continental": "cold winters and warm summers",
            "arid": "dry and sunny with little rainfall",
            "polar": "cold with long winters",
        }.get(climate_zone.value if hasattr(climate_zone, "value") else str(climate_zone), "varied")
        safety_desc = (
            "considered very safe for travellers" if safety_score >= 0.75
            else "generally safe with the usual urban precautions"
            if safety_score >= 0.55
            else "requiring a degree of caution, especially after dark"
            if safety_score >= 0.35
            else "presenting elevated safety concerns — plan carefully"
        )
        cuisine_str = " and ".join(dominant_cuisines[:2]) if dominant_cuisines else "diverse"
        event_str = " and ".join(dominant_event_categories[:2]) if dominant_event_categories else "varied"
        return (
            f"{name} is a {tier_adj} city in {region}, {tourism_adj} by international visitors. "
            f"The climate is {climate_desc}, making it {safety_desc}. "
            f"The food scene leans toward {cuisine_str} cuisine, and the city is known for its vibrant {event_str} scene."
        )

    def _generate_district_description(
        self, name: str, city_name: str, district_type, safety_score: float,
        walkability_score: float, cost_index: float,
    ) -> str:
        """Generate a richer district description from its type and scores."""
        type_desc = {
            "touristic": "a lively tourist hub packed with attractions, souvenir shops, and guided tours",
            "residential": "a quiet residential neighbourhood favoured by locals and long-term visitors",
            "nightlife": "the city's prime entertainment strip, buzzing with bars, clubs, and late-night dining",
            "business": "a dense commercial district dominated by office towers, conference venues, and corporate hotels",
            "cultural": "a culturally rich quarter home to galleries, theatres, and heritage institutions",
            "historic": "a preserved historic core with cobbled streets, colonial-era architecture, and landmark monuments",
            "waterfront": "a scenic waterfront district with promenades, seafood restaurants, and marina views",
        }.get(district_type.value if hasattr(district_type, "value") else str(district_type),
              "a diverse urban district")
        safety_note = (
            "widely regarded as one of the safer parts of the city" if safety_score >= 0.75
            else "considered reasonably safe during daylight hours"
            if safety_score >= 0.5
            else "best navigated with caution, particularly at night"
        )
        walk_note = (
            "and highly walkable" if walkability_score >= 0.7
            else "with moderate walkability"
            if walkability_score >= 0.45
            else "though transit is advisable for longer journeys"
        )
        cost_note = (
            "Prices here are above the city average." if cost_index > 1.4
            else "Costs are broadly in line with the rest of the city."
            if cost_index > 0.8
            else "It is one of the more affordable parts of the city."
        )
        return f"{name} is {type_desc}, {safety_note} {walk_note}. {cost_note}"

    def _generate_hotel_description(
        self, name: str, star_rating: int, district, city, amenities: list, airport_shuttle: bool
    ) -> str:
        """Generate a richer hotel description."""
        tier = {1: "budget", 2: "economy", 3: "comfortable mid-range", 4: "upscale", 5: "luxury five-star"}[star_rating]
        highlight_amenities = []
        if AmenityType.SPA in amenities:
            highlight_amenities.append("a full-service spa")
        if AmenityType.POOL in amenities:
            highlight_amenities.append("an outdoor pool")
        if AmenityType.BAR in amenities:
            highlight_amenities.append("a bar")
        if AmenityType.BREAKFAST in amenities:
            highlight_amenities.append("daily breakfast")
        if AmenityType.GYM in amenities:
            highlight_amenities.append("a fitness centre")
        amenity_str = (", ".join(highlight_amenities[:3]) + " ") if highlight_amenities else ""
        shuttle_note = " Airport shuttle service is available." if airport_shuttle else ""
        return (
            f"{name} is a {tier} hotel located in {district.name}, {city.name}. "
            f"Facilities include {amenity_str}and the property scores well for neighbourhood access.{shuttle_note}"
        )

    def _generate_restaurant_name(
        self, cuisine_types: list[str], city, district, idx: int
    ) -> str:
        """Generate a realistic restaurant name."""
        cuisine = cuisine_types[0]
        templates = [
            f"The {cuisine} Table", f"{cuisine} Kitchen {city.name[:3]}{idx + 1}",
            f"{district.name} {cuisine} Bistro", f"Maison {city.name[:4]}",
            f"Casa {city.name[:4]}", f"The {district.name} Brasserie",
            f"{cuisine} House {idx + 1}", f"Chez {district.name}",
        ]
        return self.rng.choice(templates)

    def _generate_restaurant_description(
        self, cuisine_types: list[str], district, city, average_spend: float, michelin_stars: int
    ) -> str:
        """Generate a richer restaurant description."""
        cuisine_str = " and ".join(cuisine_types)
        spend_tier = "budget-friendly" if average_spend < 25 else ("mid-range" if average_spend < 60 else "upscale")
        michelin_note = f" Awarded {michelin_stars} Michelin star{'s' if michelin_stars > 1 else ''}." if michelin_stars else ""
        return (
            f"A {spend_tier} {cuisine_str} restaurant set in the {district.name} area of {city.name}.{michelin_note} "
            f"Known for fresh ingredients and a welcoming atmosphere."
        )

    def _restaurant_opening_hours(self) -> dict[str, str]:
        """Return varied restaurant opening hours based on a randomly chosen pattern."""
        days_all = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        pattern = self.rng.choice([
            "full_day", "full_day", "full_day",   # most common
            "dinner_only", "dinner_only",
            "lunch_only",
            "breakfast_brunch",
            "late_night",
        ])
        hours: dict[str, str] = {}
        if pattern == "full_day":
            closed_day = "Mon" if self.rng.random() < 0.25 else None
            for day in days_all:
                hours[day] = "" if day == closed_day else "11:00-22:00"
        elif pattern == "dinner_only":
            for day in days_all:
                hours[day] = "" if day == "Mon" else "17:00-23:00"
        elif pattern == "lunch_only":
            for day in days_all:
                hours[day] = "11:30-15:30" if day not in ("Sat", "Sun") else "11:00-16:00"
        elif pattern == "breakfast_brunch":
            for day in days_all:
                hours[day] = "07:00-15:00"
        elif pattern == "late_night":
            for day in days_all:
                hours[day] = "" if day in ("Mon", "Tue") else "20:00-02:00"
        return hours

    def _generate_travel_advisory(self, safety_score: float) -> str:
        """Generate a formal tiered travel advisory based on a city's safety score."""
        if safety_score >= 0.75:
            return (
                "Level 1 – Exercise Normal Precautions: This destination presents a low overall "
                "risk to travellers. Standard personal vigilance is sufficient. Keep copies of "
                "important documents and remain aware of your surroundings in crowded areas."
            )
        elif safety_score >= 0.55:
            return (
                "Level 2 – Exercise Increased Caution: Be alert in crowded public spaces, "
                "transport hubs, and tourist areas. Petty crime, including pickpocketing and "
                "bag snatching, occurs. Keep valuables secure and out of sight, and avoid "
                "displaying expensive items in public."
            )
        elif safety_score >= 0.35:
            return (
                "Level 3 – Reconsider Travel: There is an elevated risk from petty crime and "
                "occasional civil unrest. Avoid demonstrations and poorly lit areas, especially "
                "at night. Use only licensed taxis or pre-booked transport. Register your travel "
                "plans with your embassy or consulate."
            )
        else:
            return (
                "Level 4 – Do Not Travel: Significant safety and security threats exist. "
                "Avoid all non-essential travel to this destination. If present, maintain a low "
                "profile, avoid public gatherings, and ensure you have a clear evacuation plan. "
                "Contact your embassy immediately upon arrival."
            )

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
