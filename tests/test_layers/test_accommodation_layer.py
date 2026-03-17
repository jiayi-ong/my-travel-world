"""Tests for AccommodationLayer booking and availability logic."""
import pytest

class TestAccommodationAvailability:

    def test_is_available_returns_true_for_fresh_hotel(self, seeded_world):
        """A newly generated hotel should have rooms available."""
        # TODO: get accommodation_layer and first hotel
        # TODO: assert accommodation_layer.is_available(hotel_id, check_in, check_out, guests=1)
        pass

    def test_record_booking_decrements_rooms(self, seeded_world):
        """Recording a booking should decrease rooms_available by 1."""
        # TODO: get initial rooms_available for a date
        # TODO: record_booking for one night
        # TODO: get rooms_available again and assert decreased by 1
        pass

    def test_frozen_layer_ignores_booking(self, seeded_world):
        """Bookings on a frozen AccommodationLayer should have no effect."""
        # TODO: freeze accommodation_layer
        # TODO: record_booking
        # TODO: assert rooms_available unchanged
        pass
