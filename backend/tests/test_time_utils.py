def test_minutes_between_treats_wrapped_end_as_next_day():
    from app.utils.time_utils import minutes_between

    assert minutes_between("13:00", "02:11") == 791


def test_minutes_between_keeps_same_day_ranges():
    from app.utils.time_utils import minutes_between

    assert minutes_between("14:00", "20:00") == 360
