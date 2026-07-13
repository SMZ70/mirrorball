"""Saving and recalling shows."""

from __future__ import annotations

import json

from mirrorball.core import store
from mirrorball.core.show import Show, Track


def test_solo_is_never_saved_or_loaded(tmp_path):
    """A solo is monitoring state, not part of the show.

    Saving it meant a show could be recalled with one track soloed and every
    other track silenced -- which looks exactly like "my groups stopped
    playing", because the engine is right and nothing on screen says why.
    """
    show = Show(name="x", tracks=[
        Track(id="t0", targets=["l0"]),
        Track(id="t1", targets=["l1"], solo=True, mute=True),
    ])
    store.save(show, tmp_path)

    # not in the file at all
    written = json.loads((tmp_path / "x.json").read_text())
    assert [t["solo"] for t in written["tracks"]] == [False, False]
    # mute survives: muting is a decision about the show, soloing is not
    assert [t["mute"] for t in written["tracks"]] == [False, True]

    back = store.load("x", tmp_path)
    assert [t.solo for t in back.tracks] == [False, False]
    assert len(back.active_tracks()) == 1          # t1 muted, t0 plays


def test_a_show_saved_with_a_latched_solo_is_healed_on_load(tmp_path):
    """Shows written before the fix still have a solo in them. They are the
    user's work -- heal them, rather than send them hunting for the one track
    with an S on it."""
    (tmp_path / "old.json").write_text(json.dumps({
        "name": "old",
        "tracks": [
            {"id": "t0", "targets": ["l0", "l1", "l2"]},          # a group
            {"id": "t1", "targets": ["l3"], "solo": True},        # the culprit
        ],
    }))
    show = store.load("old", tmp_path)
    assert [t.solo for t in show.tracks] == [False, False]
    assert len(show.active_tracks()) == 2         # the group plays again
