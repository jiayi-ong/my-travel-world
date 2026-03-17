"""
travel_world.layers.geo_layer — geographic foundation layer.

Must be loaded before any other layer. Defines the full geographic hierarchy
and the multi-modal transport graph.
"""

from __future__ import annotations

import networkx as nx

from travel_world.core.entities import (
    Attraction,
    City,
    District,
    EventVenue,
    Hotel,
    Location,
    Region,
    Restaurant,
    TransportEdge,
    TransportHub,
)
from travel_world.core.enums import LocationType, TransportMode
from travel_world.core.exceptions import EntityNotFoundError
from travel_world.layers.base import BaseLayer, LayerMeta

# Mapping from LocationType value to the correct entity subclass.
_LOCATION_TYPE_MAP: dict[str, type[Location]] = {
    LocationType.HOTEL.value: Hotel,
    LocationType.ATTRACTION.value: Attraction,
    LocationType.RESTAURANT.value: Restaurant,
    LocationType.EVENT_VENUE.value: EventVenue,
    LocationType.TRANSPORT_HUB.value: TransportHub,
}


class GeoLayer(BaseLayer):
    """
    The geographic foundation layer. All other layers reference entity IDs defined here.

    Must be loaded before any other layer. Contains:
    - The full geographic hierarchy (regions -> cities -> districts -> locations)
    - The multi-modal transport graph (NetworkX MultiDiGraph)

    Design: geographic hierarchy is built as a graph FIRST (nodes with coordinates and
    connectivity), then detailed attributes are mapped onto nodes in a second pass.
    This matches the real-world process: topology before semantics.

    Graph structure:
        Nodes: transport hub location_ids (airports, stations, bus terminals)
        Edges: TransportEdge objects keyed by edge_id
        Multiple edges between the same pair of nodes are allowed (MultiDiGraph)
        to represent different transport modes.
    """

    LAYER_ID = "geo"

    def __init__(
        self,
        meta: LayerMeta,
        regions: dict[str, Region],
        cities: dict[str, City],
        districts: dict[str, District],
        locations: dict[str, Location],
        transport_edges: dict[str, TransportEdge],
    ) -> None:
        super().__init__(meta)
        self.regions: dict[str, Region] = regions
        self.cities: dict[str, City] = cities
        self.districts: dict[str, District] = districts
        self.locations: dict[str, Location] = locations
        self.transport_edges: dict[str, TransportEdge] = transport_edges
        self._graph: nx.MultiDiGraph = self._build_graph()

    def _build_graph(self) -> nx.MultiDiGraph:
        """Build the NetworkX transport graph from stored TransportEdge objects."""
        graph = nx.MultiDiGraph()
        for loc in self.locations.values():
            if loc.location_type == LocationType.TRANSPORT_HUB:
                graph.add_node(
                    loc.location_id,
                    lat=loc.coordinates.lat,
                    lon=loc.coordinates.lon,
                )
        for edge in self.transport_edges.values():
            graph.add_edge(
                edge.origin_node_id,
                edge.destination_node_id,
                key=edge.edge_id,
                **edge.model_dump(),
            )
        return graph

    def get_city(self, city_id: str) -> City:
        if city_id not in self.cities:
            raise EntityNotFoundError(city_id, "City")
        return self.cities[city_id]

    def get_district(self, district_id: str) -> District:
        if district_id not in self.districts:
            raise EntityNotFoundError(district_id, "District")
        return self.districts[district_id]

    def get_location(self, location_id: str) -> Location:
        if location_id not in self.locations:
            raise EntityNotFoundError(location_id, "Location")
        return self.locations[location_id]

    def get_locations_in_district(self, district_id: str) -> list[Location]:
        return [loc for loc in self.locations.values() if loc.district_id == district_id]

    def get_locations_in_city(self, city_id: str) -> list[Location]:
        return [loc for loc in self.locations.values() if loc.city_id == city_id]

    def get_locations_by_type(
        self, city_id: str, location_type: LocationType
    ) -> list[Location]:
        return [
            loc
            for loc in self.locations.values()
            if loc.city_id == city_id and loc.location_type == location_type
        ]

    def get_transport_hubs(self, city_id: str) -> list[TransportHub]:
        return [
            loc  # type: ignore[return-value]
            for loc in self.locations.values()
            if loc.city_id == city_id and loc.location_type == LocationType.TRANSPORT_HUB
        ]

    def get_edges_between(
        self,
        origin_id: str,
        dest_id: str,
        mode: TransportMode | None = None,
    ) -> list[TransportEdge]:
        if not self._graph.has_node(origin_id) or not self._graph.has_node(dest_id):
            return []
        edges_data = self._graph.get_edge_data(origin_id, dest_id)
        if not edges_data:
            return []
        result: list[TransportEdge] = []
        for edge_attrs in edges_data.values():
            edge = self.transport_edges.get(edge_attrs.get("edge_id", ""))
            if edge is None:
                continue
            if mode is not None and edge.mode != mode:
                continue
            result.append(edge)
        return result

    def get_graph(self) -> nx.MultiDiGraph:
        """Return the underlying NetworkX transport graph."""
        return self._graph

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def _location_to_dict(self, loc: Location) -> dict:
        d = loc.model_dump(mode="json")
        d["_type"] = loc.location_type.value
        return d

    def to_dict(self) -> dict:
        return {
            "regions": {k: v.model_dump(mode="json") for k, v in self.regions.items()},
            "cities": {k: v.model_dump(mode="json") for k, v in self.cities.items()},
            "districts": {k: v.model_dump(mode="json") for k, v in self.districts.items()},
            "locations": {k: self._location_to_dict(v) for k, v in self.locations.items()},
            "transport_edges": {
                k: v.model_dump(mode="json") for k, v in self.transport_edges.items()
            },
        }

    @classmethod
    def from_dict(cls, meta: LayerMeta, data: dict) -> "GeoLayer":
        regions: dict[str, Region] = {
            k: Region.model_validate(v) for k, v in data["regions"].items()
        }
        cities: dict[str, City] = {
            k: City.model_validate(v) for k, v in data["cities"].items()
        }
        districts: dict[str, District] = {
            k: District.model_validate(v) for k, v in data["districts"].items()
        }
        locations: dict[str, Location] = {}
        for k, v in data["locations"].items():
            type_tag = v.get("_type", "")
            loc_class = _LOCATION_TYPE_MAP.get(type_tag, Location)
            # Remove the synthetic tag before validation so Pydantic doesn't choke on it.
            v_clean = {key: val for key, val in v.items() if key != "_type"}
            locations[k] = loc_class.model_validate(v_clean)
        transport_edges: dict[str, TransportEdge] = {
            k: TransportEdge.model_validate(v) for k, v in data["transport_edges"].items()
        }
        return cls(meta, regions, cities, districts, locations, transport_edges)

    # ------------------------------------------------------------------
    # Validation & summary
    # ------------------------------------------------------------------

    def validate_internal_consistency(self) -> list[str]:
        violations: list[str] = []
        for district_id, district in self.districts.items():
            if district.city_id not in self.cities:
                violations.append(
                    f"District '{district_id}' references unknown city_id '{district.city_id}'"
                )
        for location_id, location in self.locations.items():
            if location.district_id not in self.districts:
                violations.append(
                    f"Location '{location_id}' references unknown district_id '{location.district_id}'"
                )
            if location.city_id not in self.cities:
                violations.append(
                    f"Location '{location_id}' references unknown city_id '{location.city_id}'"
                )
        for edge_id, edge in self.transport_edges.items():
            if edge.origin_node_id not in self.locations:
                violations.append(
                    f"TransportEdge '{edge_id}' origin_node_id '{edge.origin_node_id}' not found in locations"
                )
            if edge.destination_node_id not in self.locations:
                violations.append(
                    f"TransportEdge '{edge_id}' destination_node_id '{edge.destination_node_id}' not found in locations"
                )
        return violations

    def summary(self) -> dict:
        locations_by_type: dict[str, int] = {}
        for loc in self.locations.values():
            key = loc.location_type.value
            locations_by_type[key] = locations_by_type.get(key, 0) + 1

        edges_by_mode: dict[str, int] = {}
        for edge in self.transport_edges.values():
            key = edge.mode.value
            edges_by_mode[key] = edges_by_mode.get(key, 0) + 1

        return {
            "layer_id": self.layer_id,
            "num_regions": len(self.regions),
            "num_cities": len(self.cities),
            "num_districts": len(self.districts),
            "num_locations": len(self.locations),
            "locations_by_type": locations_by_type,
            "num_transport_edges": len(self.transport_edges),
            "edges_by_mode": edges_by_mode,
            "num_graph_nodes": self._graph.number_of_nodes(),
            "num_graph_edges": self._graph.number_of_edges(),
        }
