"""
User session management: stores trip preferences, trip plan, and interaction log.

Sessions are the primary integration point between the Streamlit UI and external
LLM agents. Both can read and write session state via the /session API endpoints.
"""
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

from travel_world.core.exceptions import SessionNotFoundError


@dataclass
class TripPlanItem:
    """A single item (flight, hotel, event, attraction) in a session's trip plan."""

    item_id: str
    item_type: str          # "flight" | "hotel" | "event" | "attraction"
    ref_id: str             # flight_id / hotel_id / event_id
    date: str
    cost: float
    metadata: dict = field(default_factory=dict)  # item-specific summary for display


@dataclass
class TripPreferences:
    """User-supplied trip parameters. Written by UI, read by LLM agent."""

    origin_city_id: Optional[str] = None
    destination_city_ids: list = field(default_factory=list)
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    budget_total: Optional[float] = None
    group_size: int = 1
    travel_style: Optional[str] = None
    pace: Optional[str] = None
    preferred_transport: list = field(default_factory=list)


@dataclass
class TripPlan:
    """Assembled trip plan for a session."""

    items: list = field(default_factory=list)
    total_cost: float = 0.0

    def budget_remaining(self, budget_total: Optional[float]) -> Optional[float]:
        """Return budget_total - total_cost if budget_total is set, else None."""
        if budget_total is None:
            return None
        return budget_total - self.total_cost

    def cost_by_category(self) -> dict:
        """Group items by item_type and sum costs per category."""
        result: dict = {}
        for item in self.items:
            result[item.item_type] = result.get(item.item_type, 0.0) + item.cost
        return result


@dataclass
class SessionEvent:
    """A timestamped record of one API interaction within a session."""

    event_id: str
    timestamp: datetime
    endpoint: str
    request_summary: dict
    response_status: int


@dataclass
class UserSession:
    """Full session state for one user interaction."""

    session_id: str
    created_at: datetime
    world_id: str
    preferences: TripPreferences = field(default_factory=TripPreferences)
    trip_plan: TripPlan = field(default_factory=TripPlan)
    interaction_log: list = field(default_factory=list)  # list[SessionEvent]
    chat_history: list = field(default_factory=list)     # [{role, content, timestamp}]
    llm_connected: bool = False


class SessionService:
    """
    In-memory session store. Manages creation, reading, and writing of UserSession objects.

    Design: Service Locator for sessions — FastAPI dependencies call get_session()
    to retrieve the active session for a request.

    Note: In-memory store is intentional for MVP. Sessions are not persisted across
    server restarts. A future version can replace the dict with Redis or a database
    without changing the interface.

    Attributes:
        _sessions: dict[session_id, UserSession]
    """

    def __init__(self):
        self._sessions: dict[str, UserSession] = {}

    def create_session(self, world_id: str) -> UserSession:
        """Create and store a new empty session. Returns the new UserSession."""
        session_id = str(uuid.uuid4())
        session = UserSession(
            session_id=session_id,
            created_at=datetime.utcnow(),
            world_id=world_id,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> UserSession:
        """Retrieve session by ID. Raises SessionNotFoundError if not found."""
        if session_id not in self._sessions:
            raise SessionNotFoundError(session_id)
        return self._sessions[session_id]

    def update_preferences(self, session_id: str, preferences: dict) -> UserSession:
        """Update trip preferences for a session (partial update: only provided fields change)."""
        session = self.get_session(session_id)
        prefs = session.preferences
        for key, val in preferences.items():
            if hasattr(prefs, key):
                setattr(prefs, key, val)
        return session

    def add_trip_item(self, session_id: str, item_data: dict) -> TripPlan:
        """Add a planned item (flight/hotel/event) to the session trip plan."""
        session = self.get_session(session_id)
        item = TripPlanItem(
            item_id=str(uuid.uuid4()),
            item_type=item_data["item_type"],
            ref_id=item_data["ref_id"],
            date=item_data.get("date", ""),
            cost=float(item_data.get("cost", 0.0)),
            metadata=item_data.get("metadata", {}),
        )
        session.trip_plan.items.append(item)
        session.trip_plan.total_cost = sum(i.cost for i in session.trip_plan.items)
        return session.trip_plan

    def remove_trip_item(self, session_id: str, item_id: str) -> TripPlan:
        """Remove an item from the trip plan by item_id."""
        session = self.get_session(session_id)
        session.trip_plan.items = [
            i for i in session.trip_plan.items if i.item_id != item_id
        ]
        session.trip_plan.total_cost = sum(i.cost for i in session.trip_plan.items)
        return session.trip_plan

    def add_chat_message(self, session_id: str, role: str, content: str) -> dict:
        """Append a chat message to the session's chat history."""
        session = self.get_session(session_id)
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }
        session.chat_history.append(msg)
        return msg

    def log_interaction(
        self,
        session_id: str,
        endpoint: str,
        request_summary: dict,
        response_status: int,
    ) -> None:
        """Log an API call to the session's interaction log (for agent evaluation)."""
        try:
            session = self.get_session(session_id)
        except SessionNotFoundError:
            return
        event = SessionEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            endpoint=endpoint,
            request_summary=request_summary,
            response_status=response_status,
        )
        session.interaction_log.append(event)

    def reset_trip_plan(self, session_id: str) -> UserSession:
        """Clear the trip plan while keeping preferences intact."""
        session = self.get_session(session_id)
        session.trip_plan = TripPlan()
        return session

    def get_interaction_log(self, session_id: str) -> list[dict]:
        """Export full interaction log as list of dicts (for evaluation framework)."""
        session = self.get_session(session_id)
        return [
            {
                "event_id": e.event_id,
                "timestamp": e.timestamp.isoformat(),
                "endpoint": e.endpoint,
                "request_summary": e.request_summary,
                "response_status": e.response_status,
            }
            for e in session.interaction_log
        ]

    def list_sessions(self) -> list[dict]:
        """Return summary of all active sessions (id, world_id, created_at, item_count)."""
        return [
            {
                "session_id": s.session_id,
                "world_id": s.world_id,
                "created_at": s.created_at.isoformat(),
                "item_count": len(s.trip_plan.items),
            }
            for s in self._sessions.values()
        ]
