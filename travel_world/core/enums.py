"""
travel_world.core.enums — all enumerated types used across the simulation.

Using str-based enums ensures values are human-readable in JSON serialisation
and compatible with FastAPI / Pydantic v2 schema generation.
"""

from enum import Enum


class TransportMode(str, Enum):
    """Modes of transport available on edges in the transport graph."""

    WALKING = "walking"
    CYCLING = "cycling"
    BUS = "bus"
    METRO = "metro"
    TAXI = "taxi"
    RIDESHARE = "rideshare"
    RENTAL_CAR = "rental_car"
    RAIL = "rail"
    FLIGHT = "flight"


class LocationType(str, Enum):
    """High-level category that classifies every Location entity."""

    HOTEL = "hotel"
    RESTAURANT = "restaurant"
    ATTRACTION = "attraction"
    EVENT_VENUE = "event_venue"
    TRANSPORT_HUB = "transport_hub"
    LANDMARK = "landmark"
    PARK = "park"
    SHOPPING = "shopping"
    NIGHTLIFE = "nightlife"
    MARKET = "market"
    TRANSIT_STOP = "transit_stop"
    PUBLIC_AMENITY = "public_amenity"
    SERVICE_VENUE = "service_venue"
    AREA_ATTRACTION = "area_attraction"


class DistrictType(str, Enum):
    """Primary character of a city district, used for filtering and scoring."""

    TOURISTIC = "touristic"
    RESIDENTIAL = "residential"
    NIGHTLIFE = "nightlife"
    BUSINESS = "business"
    CULTURAL = "cultural"
    HISTORIC = "historic"
    WATERFRONT = "waterfront"


class ClimateZone(str, Enum):
    """Broad climate classification for a city, used to seed weather generation."""

    TROPICAL = "tropical"
    SUBTROPICAL = "subtropical"
    TEMPERATE = "temperate"
    CONTINENTAL = "continental"
    ARID = "arid"
    POLAR = "polar"


class TravelStyle(str, Enum):
    """Spending style preference of a User, influences hotel and activity selection."""

    BUDGET = "budget"
    COMFORT = "comfort"
    LUXURY = "luxury"


class TravelPace(str, Enum):
    """Activity density preference of a User per day of travel."""

    RELAXED = "relaxed"
    MODERATE = "moderate"
    PACKED = "packed"


class WeatherCondition(str, Enum):
    """Discrete weather condition labels stored in WeatherSnapshot."""

    SUNNY = "sunny"
    PARTLY_CLOUDY = "partly_cloudy"
    OVERCAST = "overcast"
    RAINY = "rainy"
    STORMY = "stormy"
    SNOWY = "snowy"
    FOGGY = "foggy"


class CabinClass(str, Enum):
    """Cabin class for a Flight entity, used for price multiplier lookup."""

    ECONOMY = "economy"
    PREMIUM_ECONOMY = "premium_economy"
    BUSINESS = "business"
    FIRST = "first"


class AmenityType(str, Enum):
    """Amenity features available at a Hotel."""

    WIFI = "wifi"
    BREAKFAST = "breakfast"
    PARKING = "parking"
    GYM = "gym"
    POOL = "pool"
    ACCESSIBILITY = "accessibility"
    RESTAURANT = "restaurant"
    BAR = "bar"
    SPA = "spa"
    LAUNDRY = "laundry"
    ROOM_SERVICE = "room_service"
    PET_FRIENDLY = "pet_friendly"
    AIR_CONDITIONING = "air_conditioning"
    BUSINESS_CENTER = "business_center"
    EV_CHARGING = "ev_charging"
    CONCIERGE = "concierge"


class EventCategory(str, Enum):
    """Thematic category of an Event entity."""

    MUSIC = "music"
    SPORTS = "sports"
    CULTURE = "culture"
    FOOD = "food"
    FESTIVAL = "festival"
    EXHIBITION = "exhibition"
    THEATER = "theater"
    COMEDY = "comedy"
    MARKET = "market"
    ATTRACTION = "attraction"


class AttractionCategory(str, Enum):
    """Thematic category of an Attraction entity."""

    MUSEUM = "museum"
    PARK = "park"
    LANDMARK = "landmark"
    NIGHTLIFE = "nightlife"
    SHOPPING = "shopping"
    CULTURAL_SITE = "cultural_site"
    FOOD_MARKET = "food_market"
    BEACH = "beach"
    GALLERY = "gallery"
    HISTORIC_SITE = "historic_site"
    VIEWPOINT = "viewpoint"
    NATURE_RESERVE = "nature_reserve"
    THEME_PARK = "theme_park"
    AQUARIUM = "aquarium"
    ZOO = "zoo"


class CityArchetype(str, Enum):
    """High-level character of a city; drives district mix, attraction types, and event categories."""
    BEACH_RESORT = "beach_resort"
    CULTURAL_CAPITAL = "cultural_capital"
    TECH_HUB = "tech_hub"
    MOUNTAIN_RETREAT = "mountain_retreat"
    HISTORIC_CITY = "historic_city"
    NIGHTLIFE_CITY = "nightlife_city"
    NATURE_ESCAPE = "nature_escape"
    FOODIE_HAVEN = "foodie_haven"
    BUSINESS_CENTER = "business_center"
    ADVENTURE_DESTINATION = "adventure_destination"


class PublicAmenityType(str, Enum):
    """Type of public amenity."""
    HOSPITAL = "hospital"
    POLICE_STATION = "police_station"
    FIRE_STATION = "fire_station"
    PHARMACY = "pharmacy"
    CLINIC = "clinic"


class ServiceVenueCategory(str, Enum):
    """Category of a fixed-location service venue (open regular hours, not events)."""
    SPA = "spa"
    ARCADE = "arcade"
    CINEMA = "cinema"
    SHOPPING_MALL = "shopping_mall"
    BOWLING_ALLEY = "bowling_alley"
    ESCAPE_ROOM = "escape_room"
    FITNESS_CENTER = "fitness_center"
    KARAOKE = "karaoke"
    COMEDY_CLUB = "comedy_club"
    CASINO = "casino"
    THEME_PARK = "theme_park"
    AQUARIUM = "aquarium"
    ZOO = "zoo"
    BOTANICAL_GARDEN = "botanical_garden"
    WATER_PARK = "water_park"


class TransitLineType(str, Enum):
    """Type of public transit line."""
    METRO = "metro"
    BUS = "bus"
    TRAM = "tram"
    FERRY = "ferry"
