"""
Restaurant search and detail service.
"""
from travel_world.core.enums import LocationType
from travel_world.core.exceptions import EntityNotFoundError


def _price_tier(avg_spend: float) -> int:
    """Map average spend per person to a 1–4 price tier."""
    if avg_spend < 20:
        return 1
    elif avg_spend < 50:
        return 2
    elif avg_spend < 80:
        return 3
    return 4


_TIER_LABEL = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}


class RestaurantService:
    """Handles restaurant queries from the geo layer."""

    def __init__(self, world_state):
        self._world_state = world_state
        self._geo = world_state.get_layer("geo")

    def search(
        self,
        city_id: str,
        cuisine: str | None = None,
        max_avg_spend: float | None = None,
        reservation_required: bool | None = None,
        district_id: str | None = None,
        session_id: str | None = None,
    ) -> list[dict]:
        """Search restaurants with optional filters."""
        from travel_world.core.entities import Restaurant

        locations = self._geo.get_locations_by_type(city_id, LocationType.RESTAURANT)
        restaurants = [loc for loc in locations if isinstance(loc, Restaurant)]

        results = []
        for r in restaurants:
            if cuisine and cuisine.lower() not in [c.lower() for c in r.cuisine_types]:
                continue
            if max_avg_spend is not None and r.average_spend > max_avg_spend:
                continue
            if reservation_required is not None and r.reservation_required != reservation_required:
                continue
            if district_id and r.district_id != district_id:
                continue

            district_name = ""
            district = self._geo.districts.get(r.district_id)
            if district:
                district_name = district.name

            tier = _price_tier(r.average_spend)
            results.append({
                "restaurant_id": r.location_id,
                "name": r.name,
                "city_id": r.city_id,
                "district_id": r.district_id,
                "district_name": district_name,
                "cuisine_types": r.cuisine_types,
                "average_spend": r.average_spend,
                "price_tier": tier,
                "price_tier_label": _TIER_LABEL[tier],
                "michelin_stars": r.michelin_stars,
                "reservation_required": r.reservation_required,
                "opening_hours": r.opening_hours,
                "capacity": r.capacity,
                "popularity_score": r.popularity_score,
                "average_rating": r.ratings.average_rating if r.ratings else None,
                "review_count": r.ratings.review_count if r.ratings else 0,
                "description": r.description,
                "tags": r.tags,
                "reviews": [
                    {"reviewer_id": rv.reviewer_id, "rating": rv.rating,
                     "positivity": rv.positivity, "text": rv.text,
                     "date": rv.date, "tags": rv.tags}
                    for rv in r.reviews
                ],
                "coordinates": {"lat": r.coordinates.lat, "lon": r.coordinates.lon},
            })

        results.sort(key=lambda x: x["popularity_score"], reverse=True)
        return results

    def get_detail(self, restaurant_id: str) -> dict:
        """Return full restaurant record."""
        from travel_world.core.entities import Restaurant

        loc = self._geo.get_location(restaurant_id)
        if not isinstance(loc, Restaurant):
            raise EntityNotFoundError(restaurant_id, "Restaurant")
        r = loc

        district_name = ""
        district = self._geo.districts.get(r.district_id)
        if district:
            district_name = district.name

        tier = _price_tier(r.average_spend)
        return {
            "restaurant_id": r.location_id,
            "name": r.name,
            "city_id": r.city_id,
            "district_id": r.district_id,
            "district_name": district_name,
            "cuisine_types": r.cuisine_types,
            "average_spend": r.average_spend,
            "price_tier": tier,
            "price_tier_label": _TIER_LABEL[tier],
            "michelin_stars": r.michelin_stars,
            "reservation_required": r.reservation_required,
            "opening_hours": r.opening_hours,
            "capacity": r.capacity,
            "popularity_score": r.popularity_score,
            "average_rating": r.ratings.average_rating if r.ratings else None,
            "review_count": r.ratings.review_count if r.ratings else 0,
            "rating_distribution": r.ratings.rating_distribution if r.ratings else {},
            "description": r.description,
            "tags": r.tags,
            "reviews": [
                {"reviewer_id": rv.reviewer_id, "rating": rv.rating,
                 "positivity": rv.positivity, "text": rv.text,
                 "date": rv.date, "tags": rv.tags}
                for rv in r.reviews
            ],
            "coordinates": {"lat": r.coordinates.lat, "lon": r.coordinates.lon},
        }
