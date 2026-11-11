from clipengine.highlights import per_second_scores, pick_windows


def test_scores_peak_where_loud():
    loud = [(t / 10, -30.0 if 40 <= t / 10 < 45 else -45.0) for t in range(1200)]
    scores = per_second_scores(loud, scenes=[41.0, 42.0], duration_s=120)
    assert len(scores) == 120
    assert max(range(120), key=lambda i: scores[i]) in range(40, 45)


def test_pick_windows_non_overlapping_and_preroll():
    scores = [0.0] * 300
    scores[100] = 10.0
    scores[200] = 8.0
    wins = pick_windows(scores, target_len_s=30, max_windows=5, pre_roll_s=4)
    assert len(wins) == 2
    assert wins[0].start_s == 96 and wins[0].end_s == 126
    for a in wins:
        for b in wins:
            if a is not b:
                assert a.end_s <= b.start_s or b.end_s <= a.start_s


def test_pick_windows_empty():
    assert pick_windows([], 30) == []
    assert pick_windows([0.0] * 50, 30) == []
