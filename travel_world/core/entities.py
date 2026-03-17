"""
travel_world.core.entities — Pydantic v2 domain entity definitions.

Layer: Core domain model (no layer or service dependencies).

All entities are pure data containers (Pydantic BaseModel). Business logic
lives in services; layer-level logic lives in layer classes. Entities are
serialised to / from JSON as part of layer persistence.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from travel_world.core.enums import (
    AmenityType,
    AttractionCategory,
    CabinClass,
    ClimateZone,
    DistrictType,
    EventCategory,
    LocationType,
    TransportMode,
    TravelPace,
    TravelStyle,
)


# ---------------------------------------------------------------------------
# Geographic primitives
# ---------------------------------------------------------------------------


class Coordinates(BaseModel):
    """
    A WGS-84 geographic coordinate pair.

    Layer: Core / shared primitive used by all geographic entities.
    """

    lat: float
    lon: float


# ---------------------------------------------------------------------------
# Reviews & ratings
# ---------------------------------------------------------------------------


class Review(BaseModel):
    """
    A single user review attached to a Location or Event.

    Layer: Core domain model. Reviews are loaded from a shared fixture file at
    world-generation time and randomly assigned to entities; they are not
    hard-coded per entity.
    """

    reviewer_id: str
    rating: float = Field(ge=1.0, le=5.0)
    text: str
    date: str  # ISO date string "YYYY-MM-DD"
    tags: list[str] = []


class RatingsSummary(BaseModel):
    """
    Aggregate statistics computed from a list of Review objects.

    Layer: Core domain model. Stored alongside each reviewable entity so that
    services can surface ratings without iterating the full review list.
    """

    average_rating: float
    review_count: int
    rating_distribution: dict[str, int]  # keys: "1", "2", "3", "4", "5"

    @classmethod
    def from_reviews(cls, reviews: list[Review]) -> "RatingsSummary":
        """
        Compute a RatingsSummary from a list of Review objects.

        Counts are bucketed by floor(rating) into keys "1" through "5".
        Returns a zero-state summary when the list is empty.
        """
        # Zero-state summary for an empty review list
        if not reviews:
            return cls(
                average_rating=0.0,
                review_count=0,
                rating_distribution={"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
            )

        # Compute average across all reviews
        total = sum(r.rating for r in reviews)
        average_rating = total / len(reviews)

        # Bucket by floor(rating), clamped to 1-5
        distribution: dict[str, int] = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
        for r in reviews:
            bucket = max(1, min(5, int(r.rating)))  # floor + clamp for ratings like 5.0
            distribution[str(bucket)] += 1

        return cls(
            average_rating=round(average_rating, 4),
            review_count=len(reviews),
            rating_distribution=distribution,
        )


# ---------------------------------------------------------------------------
# Geographic hierarchy
# ---------------------------------------------------------------------------


class Region(BaseModel):
    """
    A broad geographic region (e.g. country sub-region or island group).

    Layer: GeoLayer — the top level of the geographic hierarchy.
    """

    region_id: str
    name: str
    coordinates: Coordinates
    country_code: str
    description: str = ""


class City(BaseModel):
    """
    A city within a Region.

    Layer: GeoLayer — second level of the geographic hierarchy. Cities anchor
    all districts, locations, weather forecasts, and economics data.
    """

    city_id: str
    name: str
    region_id: str
    coordinates: Coordinates
    population: int
    economic_tier: int = Field(ge=1, le=5)
    tourism_density: float = Field(ge=0.0, le=1.0)
    safety_score: float = Field(ge=0.0, le=1.0)
    climate_zone: ClimateZone
    transport_quality: float = Field(ge=0.0, le=1.0)
    description: str = ""
    timezone: str = "UTC"


class District(BaseModel):
    """
    A neighbourhood or district within a City.

    Layer: GeoLayer — third level of the geographic hierarchy. Districts carry
    walkability, safety, noise, and cost context used by recommendation services.
    """

    district_id: str
    city_id: str
    name: str
    coordinates: Coordinates
    district_type: DistrictType
    safety_score: float
    walkability_score: float
    noise_level: float = Field(ge=0.0, le=1.0)
    cost_index: float = Field(ge=0.0)  # relative; 1.0 = city average
    description: str = ""


# ---------------------------------------------------------------------------
# Locations — base and specialisations
# ---------------------------------------------------------------------------


class Location(BaseModel):
    """
    Base entity for every visitable place in the world.

    Layer: GeoLayer — all Location subclasses are stored in the locations dict.

    Specialisations (Hotel, Attraction, Restaurant, EventVenue, TransportHub)
    extend this class via Pydantic model inheritance to add domain-specific
    fields while sharing the common geographic and operational attributes.
    """

    location_id: str
    name: str
    district_id: str
    city_id: str
    coordinates: Coordinates
    location_type: LocationType
    opening_hours: dict[str, str] = {}  # day -> "HH:MM-HH:MM"; empty string = closed
    capacity: int
    popularity_score: float = Field(ge=0.0, le=1.0)
    ratings: RatingsSummary | None = None
    reviews: list[Review] = []
    description: str = ""
    tags: list[str] = []


class Hotel(Location):
    """
    A hotel or accommodation property.

    Layer: GeoLayer (location data) + AccommodationLayer (availability calendar).

    Inherits Location rather than composing it so that hotel entities can be
    stored uniformly in the locations dict alongside other location types,
    enabling single-pass geographic queries.
    """

    star_rating: int = Field(ge=1, le=5)
    price_per_night: float
    amenities: list[AmenityType] = []
    room_types: dict[str, float] = {}  # room_name -> price_multiplier
    total_rooms: int
    neighborhood_score: float
    check_in_time: str = "15:00"
    check_out_time: str = "11:00"


class Attraction(Location):
    """
    A tourist attraction, landmark, park, museum, or activity site.

    Layer: GeoLayer. Attraction-specific fields inform scheduling and scoring
    in the itinerary planning service (duration, weather sensitivity, crowding).
    """

    category: AttractionCategory
    duration_hours: float
    ticket_price: float
    weather_sensitivity: float = Field(ge=0.0, le=1.0)
    crowding_base: float = Field(ge=0.0, le=1.0)
    free_entry: bool = False


class Restaurant(Location):
    """
    A dining establishment.

    Layer: GeoLayer. Cuisine types and spend level are used by preference
    matching in the recommendation service.
    """

    cuisine_types: list[str]
    average_spend: float
    michelin_stars: int = 0
    reservation_required: bool = False


class EventVenue(Location):
    """
    A venue that hosts events (concert hall, stadium, theatre, etc.).

    Layer: GeoLayer. EventVenue is the physical container; Event entities
    (in EventLayer) reference venue_id to link to a specific EventVenue.
    """

    venue_type: str
    max_capacity: int
    indoor: bool = True


class TransportHub(Location):
    """
    An airport, train station, bus terminal, or port.

    Layer: GeoLayer. TransportHub nodes form the vertices of the transport
    graph; TransportEdge objects define the directed connections between them.
    """

    hub_type: str  # "airport" | "station" | "port" | "bus_terminal"
    iata_code: str | None = None
    connections: list[str] = []  # list of connected hub location_ids


# ---------------------------------------------------------------------------
# Transport graph edge
# ---------------------------------------------------------------------------


class TransportEdge(BaseModel):
    """
    A directed edge in the multi-modal transport graph.

    Layer: GeoLayer — edges are stored in transport_edges and loaded into the
    NetworkX MultiDiGraph. Multiple edges between the same node pair are
    allowed to represent different transport modes.
    """

    edge_id: str
    origin_node_id: str
    destination_node_id: str
    mode: TransportMode
    distance_km: float
    base_travel_time_min: float
    base_cost: float
    carrier: str | None = None
    frequency_per_day: int = 0
    metadata: dict = {}


# ---------------------------------------------------------------------------
# Flights
# ---------------------------------------------------------------------------


class Flight(BaseModel):
    """
    A scheduled flight service between two transport hubs.

    Layer: GeoLayer (static schedule) + EconomicsLayer (dynamic pricing).

    Delay parameters (mean_delay_min, std_delay_min) are used by the
    simulation engine to sample realised arrival times during a rollout.
    """

    flight_id: str
    route_id: str
    origin_hub_id: str
    destination_hub_id: str
    origin_city_id: str
    destination_city_id: str
    departure_time: str  # "HH:MM"
    arrival_time: str    # "HH:MM"
    duration_min: int
    airline: str
    flight_number: str
    base_price: float
    cabin_class: CabinClass = CabinClass.ECONOMY
    baggage_included: bool = True
    baggage_allowance_kg: float = 23.0
    cancellation_probability: float = 0.02
    mean_delay_min: float = 15.0
    std_delay_min: float = 20.0


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class Event(BaseModel):
    """
    A time-bound event at an EventVenue (concert, festival, sports match, etc.).

    Layer: EventLayer — events are managed separately from the geographic layer
    because their availability (tickets) is dynamic and independent of geography.
    """

    event_id: str
    name: str
    venue_id: str
    city_id: str
    category: EventCategory
    start_datetime: str  # ISO 8601 datetime string
    end_datetime: str    # ISO 8601 datetime string
    capacity: int
    base_ticket_price: float
    popularity: float = Field(ge=0.0, le=1.0)
    description: str = ""
    tags: list[str] = []
    ratings: RatingsSummary | None = None
    reviews: list[Review] = []


# ---------------------------------------------------------------------------
# User / agent profile
# ---------------------------------------------------------------------------


class User(BaseModel):
    """
    A traveller profile that parameterises agent behaviour.

    Layer: Session / agent state — not persisted in any world layer. Injected
    into services via the session store.

    hidden_preferences stores partially-revealed preference signals gathered
    during conversational interaction; services may update this dict in-place
    as the agent learns more about the user.
    """

    user_id: str
    name: str = "Traveler"
    budget_total: float | None = None
    travel_style: TravelStyle = TravelStyle.COMFORT
    pace: TravelPace = TravelPace.MODERATE
    group_size: int = 1
    risk_tolerance: float = 0.5
    safety_sensitivity: float = 0.5
    weather_tolerance: float = 0.5
    preferred_transport: list[TransportMode] = []
    cuisine_preferences: list[str] = []
    activity_preferences: list[AttractionCategory] = []
    accessibility_needs: bool = False
    hidden_preferences: dict = {}  # partially revealed during conversation
