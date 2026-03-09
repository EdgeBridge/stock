"""Tests for Korean tick size table."""

from data.kr_tick_size import get_tick_size, round_to_tick, is_valid_price


class TestGetTickSize:
    def test_under_2000(self):
        assert get_tick_size(1500) == 1

    def test_2000_to_5000(self):
        assert get_tick_size(3000) == 5

    def test_5000_to_20000(self):
        assert get_tick_size(10000) == 10

    def test_20000_to_50000(self):
        assert get_tick_size(30000) == 50

    def test_50000_to_200000(self):
        assert get_tick_size(72300) == 100

    def test_200000_to_500000(self):
        assert get_tick_size(350000) == 500

    def test_over_500000(self):
        assert get_tick_size(800000) == 1000

    def test_boundary_2000(self):
        assert get_tick_size(1999) == 1
        assert get_tick_size(2000) == 5

    def test_boundary_50000(self):
        assert get_tick_size(49999) == 50
        assert get_tick_size(50000) == 100


class TestRoundToTick:
    def test_round_down(self):
        assert round_to_tick(72350, "down") == 72300
        assert round_to_tick(72399, "down") == 72300

    def test_round_up(self):
        assert round_to_tick(72301, "up") == 72400

    def test_already_valid(self):
        assert round_to_tick(72300, "down") == 72300
        assert round_to_tick(72300, "up") == 72300

    def test_small_price(self):
        assert round_to_tick(1523, "down") == 1523  # tick=1
        assert round_to_tick(3007, "down") == 3005  # tick=5
        assert round_to_tick(3007, "up") == 3010

    def test_large_price(self):
        assert round_to_tick(510500, "down") == 510000  # tick=1000
        assert round_to_tick(510500, "up") == 511000


class TestIsValidPrice:
    def test_valid(self):
        assert is_valid_price(72300) is True  # 100 tick
        assert is_valid_price(3005) is True   # 5 tick
        assert is_valid_price(1523) is True   # 1 tick

    def test_invalid(self):
        assert is_valid_price(72350) is False  # not multiple of 100
        assert is_valid_price(3003) is False   # not multiple of 5
