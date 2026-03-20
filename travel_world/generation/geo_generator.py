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
    AreaAttraction,
    AreaEntrance,
    Attraction,
    City,
    Coordinates,
    District,
    EventVenue,
    Hotel,
    Location,
    PublicAmenity,
    RatingsSummary,
    Region,
    Restaurant,
    Review,
    ServiceVenue,
    TransitLine,
    TransitStop,
    TransportEdge,
    TransportHub,
)
from travel_world.core.enums import (
    AmenityType,
    AttractionCategory,
    CityArchetype,
    ClimateZone,
    DistrictType,
    EventCategory,
    LocationType,
    PublicAmenityType,
    ServiceVenueCategory,
    TransitLineType,
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
        "Seafood",
    ]
    FLIGHT_SPEED_KMH = 850
    HAVERSINE_EARTH_RADIUS_KM = 6371

    # Maps each archetype to its weighted district type distribution.
    ARCHETYPE_DISTRICT_WEIGHTS: dict[str, dict[str, int]] = {
        "beach_resort":       {"touristic": 4, "waterfront": 4, "nightlife": 2, "residential": 2, "business": 1, "cultural": 1, "historic": 1},
        "cultural_capital":   {"cultural": 4, "historic": 3, "touristic": 3, "residential": 2, "business": 1, "nightlife": 1, "waterfront": 1},
        "tech_hub":           {"business": 5, "residential": 3, "cultural": 2, "touristic": 1, "nightlife": 1, "historic": 1, "waterfront": 1},
        "mountain_retreat":   {"touristic": 3, "residential": 3, "cultural": 2, "historic": 2, "nightlife": 1, "business": 1, "waterfront": 0},
        "historic_city":      {"historic": 5, "cultural": 3, "touristic": 3, "residential": 2, "business": 1, "nightlife": 1, "waterfront": 0},
        "nightlife_city":     {"nightlife": 5, "touristic": 3, "residential": 2, "business": 2, "waterfront": 1, "cultural": 1, "historic": 1},
        "nature_escape":      {"touristic": 3, "residential": 3, "waterfront": 2, "cultural": 2, "historic": 1, "business": 1, "nightlife": 1},
        "foodie_haven":       {"touristic": 3, "cultural": 3, "nightlife": 2, "residential": 2, "business": 2, "waterfront": 1, "historic": 1},
        "business_center":    {"business": 5, "residential": 3, "cultural": 1, "touristic": 1, "nightlife": 2, "historic": 1, "waterfront": 1},
        "adventure_destination": {"touristic": 4, "residential": 2, "waterfront": 2, "cultural": 1, "historic": 1, "nightlife": 1, "business": 1},
    }

    ARCHETYPE_ATTRACTION_CATEGORIES: dict[str, list[str]] = {
        "beach_resort":         ["beach", "park", "nightlife", "food_market"],
        "cultural_capital":     ["museum", "gallery", "cultural_site", "landmark"],
        "tech_hub":             ["museum", "landmark", "shopping", "gallery"],
        "mountain_retreat":     ["nature_reserve", "viewpoint", "park", "historic_site"],
        "historic_city":        ["historic_site", "landmark", "cultural_site", "museum"],
        "nightlife_city":       ["nightlife", "food_market", "shopping", "landmark"],
        "nature_escape":        ["nature_reserve", "park", "viewpoint", "beach"],
        "foodie_haven":         ["food_market", "cultural_site", "landmark", "shopping"],
        "business_center":      ["landmark", "museum", "shopping", "gallery"],
        "adventure_destination": ["nature_reserve", "park", "viewpoint", "beach"],
    }

    ARCHETYPE_EVENT_CATEGORIES: dict[str, list[str]] = {
        "beach_resort":         ["festival", "music", "sports"],
        "cultural_capital":     ["culture", "theater", "exhibition"],
        "tech_hub":             ["exhibition", "culture", "comedy"],
        "mountain_retreat":     ["festival", "sports", "market"],
        "historic_city":        ["culture", "exhibition", "theater"],
        "nightlife_city":       ["music", "comedy", "festival"],
        "nature_escape":        ["festival", "sports", "market"],
        "foodie_haven":         ["food", "market", "festival"],
        "business_center":      ["exhibition", "culture", "comedy"],
        "adventure_destination": ["sports", "festival", "music"],
    }

    ARCHETYPE_CUISINES: dict[str, list[str]] = {
        "beach_resort":         ["Mediterranean", "Seafood", "American"],
        "cultural_capital":     ["French", "Italian", "Mediterranean"],
        "tech_hub":             ["Japanese", "American", "Indian"],
        "mountain_retreat":     ["American", "Italian", "Greek"],
        "historic_city":        ["French", "Mediterranean", "Spanish"],
        "nightlife_city":       ["Mexican", "American", "Vietnamese"],
        "nature_escape":        ["American", "Mediterranean", "Thai"],
        "foodie_haven":         ["French", "Japanese", "Italian"],
        "business_center":      ["Japanese", "French", "American"],
        "adventure_destination": ["American", "Mexican", "Thai"],
    }

    TRANSIT_LINE_NAMES = ["Red Line", "Blue Line", "Green Line", "Yellow Line", "Orange Line", "Purple Line", "Silver Line", "Gold Line"]
    TRANSIT_COLORS = {"Red Line": "#E53E3E", "Blue Line": "#3182CE", "Green Line": "#38A169", "Yellow Line": "#D69E2E", "Orange Line": "#DD6B20", "Purple Line": "#805AD5", "Silver Line": "#718096", "Gold Line": "#B7791F"}

    SERVICE_VENUE_HOURS: dict[str, tuple[str, str]] = {
        "spa":               ("09:00", "21:00"),
        "arcade":            ("10:00", "23:00"),
        "cinema":            ("10:00", "24:00"),
        "shopping_mall":     ("10:00", "22:00"),
        "bowling_alley":     ("11:00", "24:00"),
        "escape_room":       ("10:00", "22:00"),
        "fitness_center":    ("06:00", "22:00"),
        "karaoke":           ("12:00", "03:00"),
        "comedy_club":       ("18:00", "02:00"),
        "casino":            ("00:00", "23:59"),
        "theme_park":        ("09:00", "20:00"),
        "aquarium":          ("09:00", "18:00"),
        "zoo":               ("09:00", "17:00"),
        "botanical_garden":  ("08:00", "18:00"),
        "water_park":        ("10:00", "19:00"),
    }
    SERVICE_VENUE_SPEND: dict[str, tuple[float, float]] = {
        "spa": (60, 200), "arcade": (10, 30), "cinema": (12, 25),
        "shopping_mall": (30, 150), "bowling_alley": (15, 40), "escape_room": (25, 50),
        "fitness_center": (10, 30), "karaoke": (20, 60), "comedy_club": (25, 60),
        "casino": (50, 500), "theme_park": (50, 120), "aquarium": (20, 40),
        "zoo": (20, 40), "botanical_garden": (10, 25), "water_park": (30, 70),
    }
    SERVICE_VENUE_DURATION: dict[str, tuple[float, float]] = {
        "spa": (1.5, 4.0), "arcade": (1.0, 3.0), "cinema": (1.5, 3.0),
        "shopping_mall": (1.5, 4.0), "bowling_alley": (1.5, 3.0), "escape_room": (1.0, 1.5),
        "fitness_center": (1.0, 2.0), "karaoke": (2.0, 4.0), "comedy_club": (1.5, 2.5),
        "casino": (2.0, 6.0), "theme_park": (4.0, 10.0), "aquarium": (1.5, 3.0),
        "zoo": (2.0, 4.0), "botanical_garden": (1.0, 2.5), "water_park": (3.0, 6.0),
    }
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
            transit_lines=enriched["transit_lines"],
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
        # Assign city archetype
        archetype = self.rng.choice(list(CityArchetype))
        # Dominant cuisines: derive from archetype, with possible random addition
        archetype_cuisines = self.ARCHETYPE_CUISINES[archetype.value]
        n_dominant_cuisines = self.rng.randint(2, 3)
        cuisine_pool = list(archetype_cuisines)
        if self.rng.random() < 0.4:
            extra = self.rng.choice(self.CUISINE_TYPES)
            cuisine_pool.append(extra)
        self.rng.shuffle(cuisine_pool)
        dominant_cuisines = list(dict.fromkeys(cuisine_pool))[:n_dominant_cuisines]
        # Dominant event categories from archetype
        archetype_events = self.ARCHETYPE_EVENT_CATEGORIES[archetype.value]
        n_dominant_events = self.rng.randint(2, 3)
        dominant_event_categories = list(archetype_events[:n_dominant_events])
        # Dominant attraction categories from archetype
        archetype_attractions = self.ARCHETYPE_ATTRACTION_CATEGORIES[archetype.value]
        n_dominant_attractions = self.rng.randint(2, 3)
        dominant_attraction_categories = list(archetype_attractions[:n_dominant_attractions])
        vibe_summary = self._generate_vibe_summary(
            name, region.name, economic_tier, tourism_density,
            safety_score, climate_zone, dominant_cuisines, dominant_event_categories,
            archetype=archetype,
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
            city_archetype=archetype,
            dominant_attraction_categories=dominant_attraction_categories,
        )

    def _generate_district(self, world_id: str, city: City, idx: int) -> District:
        """Generate a District entity near its city center."""
        name = self.DISTRICT_NAME_TEMPLATES[idx % len(self.DISTRICT_NAME_TEMPLATES)]
        lat = city.coordinates.lat + self.rng.uniform(-0.05, 0.05)
        lon = city.coordinates.lon + self.rng.uniform(-0.05, 0.05)
        district_id = f"district_{world_id}_{idx:04d}"
        # Use archetype-weighted district type selection
        weights_dict = self.ARCHETYPE_DISTRICT_WEIGHTS.get(city.city_archetype.value, {})
        district_types = list(DistrictType)
        weights = [weights_dict.get(dt.value, 1) for dt in district_types]
        district_type = self.rng.choices(district_types, weights=weights, k=1)[0]
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
        event venues, service venues, public amenities, area attractions, transit
        stops) and assign reviews/ratings from fixture database to all locations.
        """
        locations: dict[str, Location] = {}
        transit_lines: dict[str, TransitLine] = {}
        loc_idx = 0

        districts: dict[str, District] = skeleton["districts"]
        cities: dict[str, City] = skeleton["cities"]

        # Track per-city districts for city-level generation later
        city_districts: dict[str, list[District]] = {}
        for district in districts.values():
            city_districts.setdefault(district.city_id, []).append(district)

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

            # Service venues per district
            service_venues = self._generate_service_venues_in_district(world_id, district, city, loc_idx)
            for sv in service_venues:
                locations[sv.location_id] = sv
            loc_idx += len(service_venues)

        # City-level generation: public amenities, area attractions, transit
        transit_stop_idx = 0
        transit_line_idx = 0
        area_attraction_idx = 0
        public_amenity_idx = 0

        for city_id, city in cities.items():
            city_dist_list = city_districts.get(city_id, [])

            # Public amenities (1-2 hospitals + 1-2 police stations per city)
            amenities = self._generate_public_amenities_for_city(
                world_id, city, city_dist_list, public_amenity_idx
            )
            for am in amenities:
                locations[am.location_id] = am
            public_amenity_idx += len(amenities)

            # AreaAttractions: 1-2 per city (large parks/reserves)
            city_attractions = [
                loc for loc in locations.values()
                if loc.city_id == city_id and loc.location_type == LocationType.ATTRACTION
            ]
            area_attrs = self._generate_area_attractions_for_city(
                world_id, city, city_dist_list, city_attractions, area_attraction_idx
            )
            for aa in area_attrs:
                locations[aa.location_id] = aa
            area_attraction_idx += len(area_attrs)

            # Transit lines + stops per city
            city_all_attractions = [
                loc for loc in locations.values()
                if loc.city_id == city_id and loc.location_type in (
                    LocationType.ATTRACTION, LocationType.AREA_ATTRACTION
                )
            ]
            new_stops, new_lines, new_edges = self._generate_transit_for_city(
                world_id, city, city_dist_list, city_all_attractions,
                transit_stop_idx, transit_line_idx,
            )
            for stop in new_stops:
                locations[stop.location_id] = stop
            transit_stop_idx += len(new_stops)
            for line in new_lines:
                transit_lines[line.line_id] = line
            transit_line_idx += len(new_lines)
            # new_edges are TransportEdge objects; add to skeleton
            for edge in new_edges:
                skeleton["transport_edges"][edge.edge_id] = edge

        return {"locations": locations, "transit_lines": transit_lines}

    # ── Service venue generation ───────────────────────────────────────────────

    _SERVICE_VENUE_NAMES: dict[str, list[str]] = {
        "spa": ["Zen Spa", "Serenity Wellness", "The Retreat", "Pure Bliss Spa"],
        "arcade": ["Game Zone", "Pixel Palace", "Retro Arcade", "Fun World"],
        "cinema": ["StarPlex Cinema", "Cinepolis", "The Reel", "Grand Cinema"],
        "shopping_mall": ["City Mall", "Grand Bazaar", "The Plaza", "Metro Mall"],
        "bowling_alley": ["Strike Zone", "Bowl-O-Rama", "Lucky Lanes"],
        "escape_room": ["Escape Masters", "The Puzzle Room", "Breakout"],
        "fitness_center": ["FitLife", "IronWorks Gym", "Urban Fitness"],
        "karaoke": ["Sing Star", "Karaoke Night", "The Mic Room"],
        "comedy_club": ["Laugh Factory", "The Punchline", "Comedy Corner"],
        "casino": ["Royal Casino", "The Golden Deck", "Lucky Star Casino"],
        "theme_park": ["Adventure World", "Fun Kingdom", "Thrill Park"],
        "aquarium": ["Ocean World", "Sea Life Center", "The Aquarium"],
        "zoo": ["City Zoo", "Wildlife Park", "Animal Kingdom"],
        "botanical_garden": ["Botanical Gardens", "The Garden", "Green Paradise"],
        "water_park": ["Splash Zone", "AquaFun", "Wave World"],
    }

    _DISTRICT_SERVICE_VENUE_WEIGHTS: dict[str, list[str]] = {
        "nightlife": ["karaoke", "comedy_club", "casino", "cinema"],
        "touristic": ["spa", "shopping_mall", "theme_park", "aquarium"],
        "cultural": ["botanical_garden", "zoo", "aquarium"],
        "business": ["fitness_center", "spa", "cinema"],
        "residential": ["cinema", "bowling_alley", "fitness_center"],
        "historic": ["botanical_garden", "spa", "cinema"],
        "waterfront": ["spa", "aquarium", "water_park"],
    }

    def _generate_service_venues_in_district(
        self, world_id: str, district: District, city: City, start_idx: int
    ) -> list[ServiceVenue]:
        """Generate ServiceVenue entities for one district."""
        n = self._density(district, "service_venues")
        if n == 0:
            return []
        district_type_val = district.district_type.value
        preferred_cats = self._DISTRICT_SERVICE_VENUE_WEIGHTS.get(district_type_val, list(self._SERVICE_VENUE_NAMES.keys()))
        # Build weighted pool
        all_cat_vals = list(self._SERVICE_VENUE_NAMES.keys())
        weights = [3 if c in preferred_cats else 1 for c in all_cat_vals]

        service_venues: list[ServiceVenue] = []
        for i in range(n):
            cat_val = self.rng.choices(all_cat_vals, weights=weights, k=1)[0]
            category = ServiceVenueCategory(cat_val)
            location_id = f"sv_{world_id}_{start_idx + i:04d}"
            lat = district.coordinates.lat + self.rng.uniform(-0.01, 0.01)
            lon = district.coordinates.lon + self.rng.uniform(-0.01, 0.01)
            name_opts = self._SERVICE_VENUE_NAMES.get(cat_val, [f"{cat_val.replace('_',' ').title()}"])
            name = self.rng.choice(name_opts)
            hours = self.SERVICE_VENUE_HOURS.get(cat_val, ("09:00", "22:00"))
            spend_range = self.SERVICE_VENUE_SPEND.get(cat_val, (10.0, 50.0))
            dur_range = self.SERVICE_VENUE_DURATION.get(cat_val, (1.0, 3.0))
            avg_spend = round(self.rng.uniform(*spend_range), 2)
            min_dur = dur_range[0]
            max_dur = dur_range[1]
            service_venues.append(ServiceVenue(
                location_id=location_id,
                name=name,
                district_id=district.district_id,
                city_id=city.city_id,
                coordinates=Coordinates(lat=round(lat, 6), lon=round(lon, 6)),
                location_type=LocationType.SERVICE_VENUE,
                opening_hours={d: f"{hours[0]}-{hours[1]}" for d in
                               ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
                capacity=self.rng.randint(20, 500),
                popularity_score=round(self.rng.uniform(0.2, 1.0), 3),
                description=f"A {cat_val.replace('_', ' ')} in {district.name}, {city.name}.",
                tags=["service_venue", cat_val],
                category=category,
                opening_time=hours[0],
                closing_time=hours[1],
                average_spend_per_person=avg_spend,
                min_duration_hours=min_dur,
                max_duration_hours=max_dur,
                requires_reservation=self.rng.random() < 0.2,
                indoor=cat_val not in ("water_park", "zoo", "botanical_garden"),
            ))
        return service_venues

    # ── Public amenity generation ──────────────────────────────────────────────

    _PUBLIC_AMENITY_NAMES: dict[str, list[str]] = {
        "hospital": ["{city} General Hospital", "{city} Medical Center", "St. {city} Hospital", "City Hospital"],
        "police_station": ["{city} Police Department", "Central Police Station", "{district} Police Post"],
        "pharmacy": ["PharmaCare", "MediCare Pharmacy", "Health Plus"],
        "clinic": ["{city} Clinic", "Community Health Center", "Wellness Clinic"],
    }

    def _generate_public_amenities_for_city(
        self, world_id: str, city: City, districts: list[District], start_idx: int
    ) -> list[PublicAmenity]:
        """Generate public amenities (hospitals, police stations) for a city."""
        if not districts:
            return []
        amenities: list[PublicAmenity] = []
        # 1-2 hospitals
        n_hospitals = self.rng.randint(1, 2)
        for i in range(n_hospitals):
            district = self.rng.choice(districts)
            name_template = self.rng.choice(self._PUBLIC_AMENITY_NAMES["hospital"])
            name = name_template.format(city=city.name, district=district.name)
            lat = district.coordinates.lat + self.rng.uniform(-0.01, 0.01)
            lon = district.coordinates.lon + self.rng.uniform(-0.01, 0.01)
            location_id = f"amenity_{world_id}_{start_idx:04d}"
            start_idx += 1
            amenities.append(PublicAmenity(
                location_id=location_id,
                name=name,
                district_id=district.district_id,
                city_id=city.city_id,
                coordinates=Coordinates(lat=round(lat, 6), lon=round(lon, 6)),
                location_type=LocationType.PUBLIC_AMENITY,
                opening_hours={d: "00:00-23:59" for d in
                               ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
                capacity=self.rng.randint(50, 500),
                popularity_score=0.5,
                description=f"Public hospital serving {city.name}.",
                tags=["public_amenity", "hospital"],
                amenity_type=PublicAmenityType.HOSPITAL,
                is_24_hours=True,
                emergency_services=True,
            ))
        # 1-2 police stations
        n_police = self.rng.randint(1, 2)
        for i in range(n_police):
            district = self.rng.choice(districts)
            name_template = self.rng.choice(self._PUBLIC_AMENITY_NAMES["police_station"])
            name = name_template.format(city=city.name, district=district.name)
            lat = district.coordinates.lat + self.rng.uniform(-0.01, 0.01)
            lon = district.coordinates.lon + self.rng.uniform(-0.01, 0.01)
            location_id = f"amenity_{world_id}_{start_idx:04d}"
            start_idx += 1
            amenities.append(PublicAmenity(
                location_id=location_id,
                name=name,
                district_id=district.district_id,
                city_id=city.city_id,
                coordinates=Coordinates(lat=round(lat, 6), lon=round(lon, 6)),
                location_type=LocationType.PUBLIC_AMENITY,
                opening_hours={d: "00:00-23:59" for d in
                               ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
                capacity=50,
                popularity_score=0.3,
                description=f"Police station serving {district.name}, {city.name}.",
                tags=["public_amenity", "police_station"],
                amenity_type=PublicAmenityType.POLICE_STATION,
                is_24_hours=True,
                emergency_services=True,
            ))
        return amenities

    # ── Area attraction generation ─────────────────────────────────────────────

    _AREA_SUB_AREAS = [
        "Rose Garden", "Lake Area", "Children's Playground", "Picnic Grounds",
        "Sports Fields", "Nature Trail", "Sculpture Garden", "Fountain Plaza",
        "Wilderness Zone", "Botanical Section",
    ]
    _AREA_ENTRANCE_NAMES = ["Main Entrance", "North Gate", "South Gate", "East Gate", "West Gate"]

    def _generate_area_attractions_for_city(
        self, world_id: str, city: City, districts: list[District],
        existing_attractions: list, start_idx: int
    ) -> list[AreaAttraction]:
        """Generate 1-2 AreaAttractions for a city."""
        if not districts:
            return []
        n = self.rng.randint(1, 2)
        area_attractions: list[AreaAttraction] = []
        for i in range(n):
            district = self.rng.choice(districts)
            lat = district.coordinates.lat + self.rng.uniform(-0.008, 0.008)
            lon = district.coordinates.lon + self.rng.uniform(-0.008, 0.008)
            location_id = f"area_attr_{world_id}_{start_idx + i:04d}"
            # Category: park or nature_reserve
            category = self.rng.choice([AttractionCategory.PARK, AttractionCategory.NATURE_RESERVE])
            area_sqkm = round(self.rng.uniform(0.5, 5.0), 2)
            # Build boundary polygon: 6 points at 60° intervals
            polygon: list[Coordinates] = []
            for angle_deg in range(0, 360, 60):
                angle_rad = math.radians(angle_deg)
                radius = self.rng.uniform(0.005, 0.02)
                p_lat = lat + radius * math.cos(angle_rad)
                p_lon = lon + radius * math.sin(angle_rad)
                polygon.append(Coordinates(lat=round(p_lat, 6), lon=round(p_lon, 6)))
            # Entrances at a subset of polygon points
            entrance_names = self.rng.sample(self._AREA_ENTRANCE_NAMES, min(4, len(self._AREA_ENTRANCE_NAMES)))
            entrances: list[AreaEntrance] = []
            for j, ename in enumerate(entrance_names):
                e_coords = polygon[j % len(polygon)]
                entrances.append(AreaEntrance(
                    entrance_id=f"{location_id}_entrance_{j}",
                    name=ename,
                    coordinates=e_coords,
                    is_main_entrance=(j == 0),
                    accessible=True,
                ))
            # Sub areas
            n_sub = self.rng.randint(3, 5)
            sub_areas = self.rng.sample(self._AREA_SUB_AREAS, min(n_sub, len(self._AREA_SUB_AREAS)))
            cat_label = category.value.replace("_", " ").title()
            name = self.rng.choice([
                f"{city.name} {cat_label}",
                f"{district.name} {cat_label}",
                f"Great {cat_label} of {city.name}",
            ])
            reviews, ratings = self._assign_reviews("attraction", self.rng.randint(5, 15))
            area_attractions.append(AreaAttraction(
                location_id=location_id,
                name=name,
                district_id=district.district_id,
                city_id=city.city_id,
                coordinates=Coordinates(lat=round(lat, 6), lon=round(lon, 6)),
                location_type=LocationType.AREA_ATTRACTION,
                opening_hours=self._attraction_opening_hours(),
                capacity=self.rng.randint(500, 10_000),
                popularity_score=round(self.rng.uniform(0.5, 1.0), 3),
                ratings=ratings,
                reviews=reviews,
                description=f"A large {category.value.replace('_', ' ')} area in {city.name}.",
                tags=["area_attraction", category.value],
                category=category,
                duration_hours=round(self.rng.uniform(1.5, 4.0), 1),
                ticket_price=round(self.rng.uniform(0, 20), 2),
                weather_sensitivity=round(self.rng.uniform(0.4, 0.9), 3),
                crowding_base=round(self.rng.uniform(0.3, 0.8), 3),
                free_entry=self.rng.random() < 0.4,
                boundary_polygon=polygon,
                area_sqkm=area_sqkm,
                entrances=entrances,
                sub_areas=sub_areas,
                internal_walking_paths=True,
                estimated_visit_hours=round(self.rng.uniform(1.5, 4.0), 1),
            ))
        return area_attractions

    # ── Transit generation ─────────────────────────────────────────────────────

    def _generate_transit_for_city(
        self,
        world_id: str,
        city: City,
        districts: list[District],
        attractions: list,
        stop_start_idx: int,
        line_start_idx: int,
    ) -> tuple[list[TransitStop], list[TransitLine], list[TransportEdge]]:
        """Generate 2-3 transit lines with stops for a city."""
        if not districts:
            return [], [], []

        stops: list[TransitStop] = []
        lines: list[TransitLine] = []
        edges: list[TransportEdge] = []

        n_lines = self.rng.randint(2, 3)
        line_names = self.rng.sample(self.TRANSIT_LINE_NAMES, min(n_lines, len(self.TRANSIT_LINE_NAMES)))
        all_stop_ids_by_line: list[list[str]] = []

        edge_idx = 99000 + stop_start_idx  # high offset to avoid collision

        for line_i in range(n_lines):
            line_name = line_names[line_i]
            color = self.TRANSIT_COLORS.get(line_name, "#0000FF")
            line_type = TransitLineType.METRO if line_i == 0 else TransitLineType.BUS
            n_stops = self.rng.randint(8, 12)

            # Anchor stops near attractions, or at random city offsets
            if len(attractions) >= n_stops:
                anchors = self.rng.sample(attractions, n_stops)
                anchor_coords = [(a.coordinates.lat, a.coordinates.lon) for a in anchors]
            else:
                anchor_coords = []
                for _ in range(n_stops):
                    alat = city.coordinates.lat + self.rng.uniform(-0.04, 0.04)
                    alon = city.coordinates.lon + self.rng.uniform(-0.04, 0.04)
                    anchor_coords.append((alat, alon))
                if attractions:
                    # Supplement with available attractions
                    for idx2, a in enumerate(attractions[:n_stops - len(anchor_coords)]):
                        anchor_coords[idx2] = (a.coordinates.lat, a.coordinates.lon)

            line_stop_ids: list[str] = []
            line_stops: list[TransitStop] = []

            for s_i, (alat, alon) in enumerate(anchor_coords):
                offset_lat = self.rng.uniform(-0.003, 0.003)
                offset_lon = self.rng.uniform(-0.003, 0.003)
                slat = round(alat + offset_lat, 6)
                slon = round(alon + offset_lon, 6)
                stop_id = f"stop_{world_id}_{stop_start_idx:04d}"
                stop_start_idx += 1
                district = self.rng.choice(districts)
                stop = TransitStop(
                    location_id=stop_id,
                    name=f"{line_name} — Stop {s_i + 1}",
                    district_id=district.district_id,
                    city_id=city.city_id,
                    coordinates=Coordinates(lat=slat, lon=slon),
                    location_type=LocationType.TRANSIT_STOP,
                    opening_hours={d: "06:00-23:00" for d in
                                   ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
                    capacity=200,
                    popularity_score=round(self.rng.uniform(0.3, 0.8), 3),
                    description=f"Transit stop on the {line_name}.",
                    tags=["transit_stop", line_type.value],
                    stop_number=s_i,
                    is_interchange=False,
                    accessible=self.rng.random() < 0.9,
                )
                line_stops.append(stop)
                line_stop_ids.append(stop_id)

            # Mark interchange stops (appear in 2+ lines)
            for existing_stop_ids in all_stop_ids_by_line:
                # (no actual ID overlap since we generate fresh stops, but we mark based on proximity)
                pass

            stops.extend(line_stops)
            all_stop_ids_by_line.append(line_stop_ids)

            # Edges between consecutive stops
            mode = TransportMode.METRO if line_type == TransitLineType.METRO else TransportMode.BUS
            for s_i in range(len(line_stops) - 1):
                stop_a = line_stops[s_i]
                stop_b = line_stops[s_i + 1]
                dist = self._haversine(
                    stop_a.coordinates.lat, stop_a.coordinates.lon,
                    stop_b.coordinates.lat, stop_b.coordinates.lon,
                )
                travel_time = max(2.0, (dist / (40.0 if mode == TransportMode.METRO else 25.0)) * 60)
                edge_id = f"transit_edge_{world_id}_{edge_idx:05d}"
                edge_idx += 1
                edges.append(TransportEdge(
                    edge_id=edge_id,
                    origin_node_id=stop_a.location_id,
                    destination_node_id=stop_b.location_id,
                    mode=mode,
                    distance_km=round(dist, 3),
                    base_travel_time_min=round(travel_time, 1),
                    base_cost=2.50,
                    frequency_per_day=6 * 17,  # ~6/hour for 17 hours
                    metadata={"line_id": f"line_{world_id}_{line_start_idx:04d}", "line_name": line_name},
                ))

            line_id = f"line_{world_id}_{line_start_idx:04d}"
            line_start_idx += 1
            lines.append(TransitLine(
                line_id=line_id,
                name=line_name,
                line_type=line_type,
                city_id=city.city_id,
                color=color,
                stop_ids=line_stop_ids,
                frequency_per_hour=6,
                operating_hours="06:00-23:00",
                fare=2.50,
            ))

            # Update stop line_ids
            for stop in line_stops:
                stop.line_ids.append(line_id)

        return stops, lines, edges

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
            all_cats = list(AttractionCategory)
            dominant_cats = getattr(city, "dominant_attraction_categories", [])
            cat_weights = [3 if cat.value in dominant_cats else 1 for cat in all_cats]
            category = self.rng.choices(all_cats, weights=cat_weights, k=1)[0]
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
        archetype=None,
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
        archetype_str = ""
        if archetype is not None:
            archetype_label = archetype.value.replace("_", " ")
            archetype_str = f" As a {archetype_label}, it offers a distinctive character shaped by its primary identity."
        return (
            f"{name} is a {tier_adj} city in {region}, {tourism_adj} by international visitors.{archetype_str} "
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
