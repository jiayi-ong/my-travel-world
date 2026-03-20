"""
/session routes: user session state and trip plan management.

This is the primary integration point between the Streamlit UI and external LLM agents.
Both read and write session state through these endpoints.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from travel_world.api.dependencies import get_session_service, get_session
from travel_world.core.exceptions import SessionNotFoundError
from travel_world.core.itinerary import ItineraryManifest

router = APIRouter(prefix="/session", tags=["session"])


# --- Request Models ---

class UpdatePreferencesRequest(BaseModel):
    origin_city_id: Optional[str] = None
    destination_city_ids: Optional[list[str]] = None
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    budget_total: Optional[float] = None
    group_size: Optional[int] = None
    travel_style: Optional[str] = None
    pace: Optional[str] = None
    preferred_transport: Optional[list[str]] = None


class TripPlanItemRequest(BaseModel):
    item_type: str
    ref_id: str
    date: str = ""
    cost: float = 0.0
    metadata: dict = {}


class ChatMessageRequest(BaseModel):
    role: str   # "user" | "assistant"
    content: str


# --- Helpers ---

def _session_to_dict(session) -> dict:
    """Convert UserSession to a JSON-serialisable dict."""
    prefs = session.preferences
    return {
        "session_id": session.session_id,
        "created_at": session.created_at.isoformat(),
        "world_id": session.world_id,
        "llm_connected": session.llm_connected,
        "preferences": {
            "origin_city_id": prefs.origin_city_id,
            "destination_city_ids": prefs.destination_city_ids,
            "departure_date": prefs.departure_date,
            "return_date": prefs.return_date,
            "budget_total": prefs.budget_total,
            "group_size": prefs.group_size,
            "travel_style": prefs.travel_style,
            "pace": prefs.pace,
            "preferred_transport": prefs.preferred_transport,
        },
        "trip_plan": _plan_to_dict(session.trip_plan),
        "chat_history": session.chat_history,
    }


def _plan_to_dict(plan) -> dict:
    return {
        "items": [
            {
                "item_id": i.item_id,
                "item_type": i.item_type,
                "ref_id": i.ref_id,
                "date": i.date,
                "cost": i.cost,
                "metadata": i.metadata,
            }
            for i in plan.items
        ],
        "total_cost": plan.total_cost,
    }


# --- Routes ---

@router.post("/")
def create_session(world_id: str, session_service=Depends(get_session_service)):
    """Create a new session. Returns session_id for use in all subsequent calls."""
    session = session_service.create_session(world_id)
    return {"session_id": session.session_id, "world_id": session.world_id}


@router.get("/{session_id}")
def get_session_route(session_id: str, session_service=Depends(get_session_service)):
    """Get full session state including preferences and trip plan. Primary LLM bootstrap endpoint."""
    try:
        session = session_service.get_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return _session_to_dict(session)


@router.put("/{session_id}/preferences")
def update_preferences(
    session_id: str,
    preferences: UpdatePreferencesRequest,
    session_service=Depends(get_session_service),
):
    """Update trip parameters. Called by UI when user changes dates/budget/etc."""
    try:
        session = session_service.update_preferences(
            session_id, preferences.model_dump(exclude_none=True)
        )
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return {"session_id": session_id, "preferences": _session_to_dict(session)["preferences"]}


@router.get("/{session_id}/trip_plan")
def get_trip_plan(session_id: str, session_service=Depends(get_session_service)):
    """Get the current trip plan items and total cost."""
    try:
        session = session_service.get_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return _plan_to_dict(session.trip_plan)


@router.get("/{session_id}/trip_plan/summary")
def get_trip_plan_summary(session_id: str, session_service=Depends(get_session_service)):
    """Budget summary: total spent, remaining, breakdown by category."""
    try:
        session = session_service.get_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    plan = session.trip_plan
    budget = session.preferences.budget_total
    return {
        "total_cost": plan.total_cost,
        "budget_total": budget,
        "budget_remaining": plan.budget_remaining(budget),
        "cost_by_category": plan.cost_by_category(),
        "item_count": len(plan.items),
    }


@router.post("/{session_id}/trip_plan/add")
def add_trip_item(
    session_id: str,
    item: TripPlanItemRequest,
    session_service=Depends(get_session_service),
):
    """Add a selected item to the trip plan. Called by LLM agent after selecting flights/hotels."""
    try:
        plan = session_service.add_trip_item(session_id, item.model_dump())
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return _plan_to_dict(plan)


@router.delete("/{session_id}/trip_plan/{item_id}")
def remove_trip_item(
    session_id: str,
    item_id: str,
    session_service=Depends(get_session_service),
):
    """Remove an item from the trip plan by item_id."""
    try:
        plan = session_service.remove_trip_item(session_id, item_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return _plan_to_dict(plan)


@router.post("/{session_id}/chat_message")
def post_chat_message(
    session_id: str,
    message: ChatMessageRequest,
    session_service=Depends(get_session_service),
):
    """Post a chat message (user or assistant). Displayed in the AI Assistant tab."""
    try:
        msg = session_service.add_chat_message(session_id, message.role, message.content)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return msg


@router.get("/{session_id}/interaction_log")
def get_interaction_log(session_id: str, session_service=Depends(get_session_service)):
    """Export the full interaction log for agent evaluation."""
    try:
        return session_service.get_interaction_log(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")


@router.get("/{session_id}/llm_status")
def get_llm_status(session_id: str, session_service=Depends(get_session_service)):
    """Poll endpoint for Streamlit UI to check if an LLM agent is connected."""
    try:
        session = session_service.get_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return {
        "llm_connected": session.llm_connected,
        "last_message_at": session.chat_history[-1]["timestamp"] if session.chat_history else None,
    }


@router.post("/{session_id}/reset")
def reset_session(session_id: str, session_service=Depends(get_session_service)):
    """Clear trip plan while keeping preferences."""
    try:
        session = session_service.reset_trip_plan(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return {"session_id": session_id, "message": "Trip plan cleared.", "world_id": session.world_id}


@router.post("/{session_id}/itinerary")
def submit_itinerary(
    session_id: str,
    manifest: ItineraryManifest,
    session_service=Depends(get_session_service),
):
    """
    Submit a completed itinerary manifest for a session.

    The agent calls this endpoint once — after full planning is complete —
    to submit the self-contained ItineraryManifest. The travel world stores
    it for retrieval by the evaluator. This replaces the incremental
    trip_plan/add pattern as the primary itinerary submission mechanism.
    """
    try:
        session = session_service.get_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    # Store the manifest on the session (serialized as dict)
    setattr(session, "submitted_itinerary", manifest.model_dump(mode="json"))
    return {
        "status": "accepted",
        "manifest_id": manifest.manifest_id,
        "session_id": session_id,
        "item_count": len(manifest.items),
        "total_cost": manifest.total_cost,
    }


@router.get("/{session_id}/itinerary/manifest")
def get_submitted_itinerary(
    session_id: str,
    session_service=Depends(get_session_service),
):
    """
    Retrieve the submitted ItineraryManifest for a session.

    Intended for the evaluator to retrieve the agent's final plan.
    """
    try:
        session = session_service.get_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    manifest = getattr(session, "submitted_itinerary", None)
    if manifest is None:
        raise HTTPException(status_code=404, detail="No itinerary has been submitted for this session yet.")
    return manifest
