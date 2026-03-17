# My Travel World

A configurable simulated travel world for benchmarking and testing LLM-based travel-planning agents.

Generates a fully synthetic world — cities, airports, hotels, flights, and events — with realistic pricing, availability, and constraints, served through a REST API and a Streamlit UI. Agents can be evaluated on real planning tasks without touching live booking systems.

---

## Project Structure

```
travel_world/
  core/          # Domain entities, enums, exceptions, WorldState
  layers/        # Six JSON-serializable world layers (geo, weather, traffic,
                 #   accommodation, event, economics)
  generation/    # Seeded world generators (GeoGenerator, EventGenerator, etc.)
  manager/       # WorldManager — persistence and lifecycle
  services/      # Business logic (FlightService, HotelService, EventService, ...)
  api/           # FastAPI app, routes, and Pydantic schemas
  frontend/      # Streamlit UI (tabs, card components, API client)
  simulation/    # Simulation clock and tick engine
data/fixtures/   # Seeded review banks and event templates (JSON)
scripts/         # CLI tools: generate_world, run_api, inspect_world
```

---

## Quick Start

**1. Install**
```bash
pip install -e .
```

**2. Generate a world**
```bash
python scripts/generate_world.py --seed 42 --num-cities 3
```
This writes a world snapshot to `worlds/`.

**3. Start the API server**
```bash
python scripts/run_api.py
# Listening on http://localhost:8000
```

**4. Launch the Streamlit UI** (separate terminal)
```bash
streamlit run travel_world/frontend/app.py
```

Interactive API docs are available at `http://localhost:8000/docs`.

---

## Main Travel APIs

All endpoints are prefixed relative to the server root (default `http://localhost:8000`).

### World

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/world/` | List all generated worlds |
| `POST` | `/world/generate` | Generate and persist a new world (params: `seed`, `num_cities`) |
| `POST` | `/world/{world_id}/load` | Load a world as the active world state |
| `GET` | `/world/{world_id}/cities` | List all cities in a world |
| `GET` | `/world/{world_id}/layers` | Inspect layer summaries for a world |

### Flights

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/flights/search` | Search flights between two cities on a date. Params: `origin_city_id`, `destination_city_id`, `departure_date`, `passengers`, `cabin_class` |
| `GET` | `/flights/routes` | List all city-pair routes that have at least one flight edge |
| `GET` | `/flights/{flight_id}` | Full details for a specific flight edge |

**Example**
```
GET /flights/search?origin_city_id=city_42_0000&destination_city_id=city_42_0001&departure_date=2026-04-01&passengers=2
```

### Hotels

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/hotels/search` | Search available hotels in a city for a date range. Params: `city_id`, `check_in`, `check_out`, `guests`, `max_price_per_night`, `min_stars`, `amenities` |
| `GET` | `/hotels/{hotel_id}` | Full hotel details including upcoming availability |
| `GET` | `/hotels/{hotel_id}/availability` | Per-night availability and price for a date range |
| `POST` | `/hotels/{hotel_id}/book` | Book a hotel and record it in the session trip plan |
| `GET` | `/hotels/compare` | Side-by-side price/amenity comparison for a list of hotel IDs |

**Example**
```
GET /hotels/search?city_id=city_42_0001&check_in=2026-04-01&check_out=2026-04-05&min_stars=3
```

### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/events/search` | Search events in a city. Params: `city_id`, `start_date`, `end_date`, `category`, `max_price` |
| `GET` | `/events/calendar` | Events grouped by day for a given `city_id`, `year`, `month` |
| `GET` | `/events/{event_id}` | Full event details including venue and ticket availability |
| `POST` | `/events/book` | Book tickets for an event. Params: `event_id`, `quantity`, `session_id` |

**Example**
```
GET /events/search?city_id=city_42_0002&category=music
```

### Routing

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/routing/plan` | Find the shortest/fastest route between two cities. Params: `origin_city_id`, `destination_city_id`, `mode` |
| `GET` | `/routing/compare` | Compare all available transport modes for a city pair |
| `GET` | `/routing/time` | Estimated travel time between two cities for a given mode |

### Session

Sessions track an agent's (or user's) preferences and trip plan across multiple API calls.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/session/` | Create a new session. Returns a `session_id` |
| `GET` | `/session/{session_id}` | Get session state |
| `PUT` | `/session/{session_id}/preferences` | Update travel preferences (origin, destination, dates, group size) |
| `GET` | `/session/{session_id}/trip_plan` | Retrieve the current trip plan |
| `POST` | `/session/{session_id}/trip_plan/add` | Add a flight, hotel, or event item to the plan |
| `DELETE` | `/session/{session_id}/trip_plan/{item_id}` | Remove an item from the plan |
| `GET` | `/session/{session_id}/trip_plan/summary` | Cost breakdown and item count summary |
| `POST` | `/session/{session_id}/chat_message` | Log a chat message (for LLM agent interaction tracking) |
| `GET` | `/session/{session_id}/interaction_log` | Full interaction history for the session |

---

## Adding Custom Events

Event templates live in `data/fixtures/event_templates.json`. Add a new entry — no code changes needed:

```json
{
  "category": "music",
  "name": "Your Event Name",
  "description": "A short 1–2 sentence description of the event.",
  "rating": 4.5
}
```

Valid categories: `music`, `food`, `culture`, `sports`, `festival`, `exhibition`, `theater`, `comedy`, `market`.

After editing, regenerate the world with `scripts/generate_world.py` to see the new event appear.
