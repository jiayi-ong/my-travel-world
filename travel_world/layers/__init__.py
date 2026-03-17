"""
travel_world.layers — world state layer implementations.

Each layer is an independent, serialisable slice of world state. Layers are
assembled at runtime into a WorldState by WorldManager. They are persisted
individually as JSON files under worlds/<world_id>/.
"""
