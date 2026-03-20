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
    CityArchetype,
    ClimateZone,
    DistrictType,
    EventCategory,
    LocationType,
    PublicAmenityType,
    ServiceVenueCategory,
    TransitLineType,
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
    positivity: float = Field(default=0.5, ge=0.0, le=1.0)  # 0=very negative, 1=very positive
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
    travel_advisory: str = ""  # Official tiered advisory text
    dominant_cuisines: list[str] = []
    dominant_event_categories: list[str] = []
    vibe_summary: str = ""
    city_archetype: CityArchetype = CityArchetype.CULTURAL_CAPITAL
    dominant_attraction_categories: list[str] = []


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
    reviews: list[Review] = []  # Visitor reviews including subjective safety observations


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
    check_in_time: str = "13:00"
    check_out_time: str = "11:00"
    num_beds: int = 1
    airport_shuttle: bool = False


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


class TransitStop(Location):
    """
    A public transit stop (metro station, bus stop, tram stop).

    Layer: GeoLayer. TransitStop entities are placed near attraction clusters
    and connected via METRO/BUS edges in the transport graph. Each stop
    belongs to one or more transit lines.
    """
    line_ids: list[str] = []          # transit line IDs this stop serves
    stop_number: int = 0              # sequential position on the primary line
    is_interchange: bool = False      # True if served by 2+ lines
    accessible: bool = True


class PublicAmenity(Location):
    """
    A public safety or health amenity (hospital, police station, pharmacy, etc.).

    Layer: GeoLayer. Included so agents can answer questions about safety and
    emergency services near a location. Not bookable.
    """
    amenity_type: PublicAmenityType
    is_24_hours: bool = False
    phone_number: str = ""
    emergency_services: bool = False


class ServiceVenue(Location):
    """
    A fixed-location entertainment or lifestyle service open on regular hours.

    Unlike Event entities (one-time occurrences) and Attraction entities (static
    landmarks), ServiceVenue represents recurring commercial services such as
    spas, cinemas, and shopping malls. Follows the same open/close hour pattern
    as Restaurant.

    Layer: GeoLayer.
    """
    category: ServiceVenueCategory
    opening_time: str = "09:00"       # "HH:MM"
    closing_time: str = "22:00"       # "HH:MM"
    average_spend_per_person: float = 20.0
    min_duration_hours: float = 1.0
    max_duration_hours: float = 3.0
    requires_reservation: bool = False
    age_restriction: int | None = None   # minimum age, None = no restriction
    indoor: bool = True
    dress_code: str = ""


class AreaEntrance(BaseModel):
    """
    A named entry/exit point for an AreaAttraction.

    Entrances are used as routing targets — an agent navigating to a large park
    should route to a specific entrance, not the centroid of the area.
    """
    entrance_id: str
    name: str                         # e.g. "North Gate", "Main Entrance"
    coordinates: Coordinates
    is_main_entrance: bool = False
    accessible: bool = True
    notes: str = ""                   # e.g. "Closes at sunset", "Parking available"


class AreaAttraction(Attraction):
    """
    A tourist attraction that spans a geographic area rather than a point.

    Examples: large national parks, sprawling palace grounds, botanical gardens,
    historic city centres, beachfronts.

    The boundary_polygon gives map renderers the area shape. Agents should use
    entrances (not the centroid) as routing targets. sub_areas lists named
    zones within the area for itinerary specificity.

    Layer: GeoLayer — stored in locations dict alongside point Attractions.
    """
    boundary_polygon: list[Coordinates] = []   # simplified polygon (4-12 vertices)
    area_sqkm: float = 0.0
    entrances: list[AreaEntrance] = []
    sub_areas: list[str] = []                  # named zones within the area
    internal_walking_paths: bool = True
    estimated_visit_hours: float = 2.0         # typical visit duration


class TransitLine(BaseModel):
    """
    A public transit route composed of an ordered sequence of TransitStop IDs.

    Layer: GeoLayer — stored in a separate transit_lines dict in GeoLayer.
    TransitLine is not a Location (it has no single coordinate); it is a
    route entity that links a sequence of TransitStop locations.
    """
    line_id: str
    name: str                         # e.g. "Red Line", "Bus 42"
    line_type: TransitLineType
    city_id: str
    color: str = "#0000FF"            # hex color for map rendering
    stop_ids: list[str] = []          # ordered list of TransitStop location_ids
    frequency_per_hour: int = 6       # departures per hour
    operating_hours: str = "06:00-23:00"
    fare: float = 2.50


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
    requires_booking: bool = True   # False for free-entry attractions (parks, beaches, etc.)
    is_all_day_entry: bool = False  # True for attractions open all day with no fixed show time
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
