"""
travel_world.core.itinerary — Self-contained itinerary artifact schema.

An ItineraryManifest is the output contract between the agent and the evaluator.
It is designed to be self-contained: an external evaluator module can perform
all Tier 1 (deterministic) feasibility checks using only this document,
without re-querying the travel world API.

Design principles:
- Every item carries full datetime stamps (not just dates or times).
- Every item carries location_id + coordinates so spatial checks are possible.
- Confirmed prices are snapshotted at planning time (not live prices).
- Explicit TransitSegment objects sit between every pair of consecutive activity items.
- The manifest references world_id so a Tier 3 evaluator can load the same world.
"""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field
from travel_world.core.enums import TransportMode


class ItineraryTransitSegment(BaseModel):
    """
    An explicit transit leg between two consecutive itinerary items.

    The evaluator can check:
    - Whether the duration fits in the buffer between item N and item N+1.
    - Whether the mode was available (via routing API oracle).
    - Whether the cost was correctly budgeted.
    """
    segment_id: str
    from_item_id: str          # ItineraryItem.item_id of the preceding activity
    to_item_id: str            # ItineraryItem.item_id of the following activity
    from_location_id: str
    to_location_id: str
    transport_mode: TransportMode
    departure_datetime: datetime
    arrival_datetime: datetime
    estimated_duration_min: float
    estimated_cost: float
    buffer_min: float          # slack: (to_item.start - arrival_datetime).total_seconds()/60
    route_source: str = "agent_planned"  # "agent_planned" | "routing_api" | "manual"


class ItineraryItem(BaseModel):
    """
    A single item in the planned itinerary.

    item_type distinguishes the planning entity:
    - "flight"        → entity_id is a flight edge_id or flight_id
    - "hotel"         → entity_id is a hotel location_id; spans check_in to check_out
    - "attraction"    → entity_id is an attraction location_id
    - "event"         → entity_id is an event_id
    - "restaurant"    → entity_id is a restaurant location_id
    - "service_venue" → entity_id is a service venue location_id
    - "free_time"     → unstructured block; entity_id may be empty
    """
    item_id: str
    item_type: str             # see docstring for valid values
    entity_id: str
    title: str                 # human-readable label
    start_datetime: datetime
    end_datetime: datetime
    location_id: str           # primary location (use entrance_id for AreaAttractions)
    coordinates: dict          # {"lat": float, "lon": float}
    city_id: str
    district_id: str = ""
    confirmed_price: float = 0.0  # price at time of planning (snapshotted)
    currency: str = "USD"
    booking_reference: Optional[str] = None
    notes: str = ""
    metadata: dict = {}        # item-type-specific extras (cabin_class, num_guests, etc.)


class ItineraryManifest(BaseModel):
    """
    The complete, self-contained itinerary artifact emitted by the agent.

    This is the contract between the agent and the evaluator. The evaluator
    receives this document and can perform:
    - Tier 1: deterministic checks (budget, temporal feasibility, overlap)
    - Tier 2: rubric-based evaluation (using user_preferences + items)
    - Tier 3: world-aware evaluation (using world_id to load oracle context)

    The agent emits this as a single POSTed document to the session endpoint.
    The travel world does not build this up incrementally.
    """
    manifest_id: str
    world_id: str
    world_snapshot_timestamp: Optional[datetime] = None  # when world was generated
    session_id: Optional[str] = None
    planning_datetime: datetime = Field(default_factory=datetime.utcnow)

    # Trip scope
    trip_date_range: tuple[date, date]       # (departure_date, return_date)
    origin_city_id: str
    destination_city_ids: list[str]          # cities visited

    # User context (snapshotted at planning time)
    user_preferences: dict = {}              # full User profile or subset
    constraints_declared: list[str] = []    # explicit hard constraints stated by user

    # Itinerary content
    items: list[ItineraryItem] = []
    transit_segments: list[ItineraryTransitSegment] = []

    # Financial summary
    total_cost: float = 0.0
    total_cost_by_category: dict[str, float] = {}  # e.g. {"flights": 450, "hotels": 300}
    budget_declared: Optional[float] = None  # user's stated total budget

    # Evaluation metadata
    tool_calls_log_ref: Optional[str] = None  # session_id for interaction log replay
    agent_notes: str = ""                    # agent's own summary of the plan
