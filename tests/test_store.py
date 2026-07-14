"""Saving and recalling shows."""

from __future__ import annotations

import json

from mirrorball.core import store
from mirrorball.core.show import Link, Show, Track


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


def test_empty_tracks_do_not_survive_a_round_trip(tmp_path):
    """An empty track renders nothing and is not a thing in the room. They piled
    up because taking the last light out of a track left the husk behind."""
    show = Show(name="x", tracks=[
        Track(id="t0", targets=["l0", "l1"]),
        Track(id="t1", targets=[]),                      # a husk
        Track(id="t2", targets=["l2"], link=Link(follow="t1")),   # following one
    ])
    store.save(show, tmp_path)
    back = store.load("x", tmp_path)

    assert [t.id for t in back.tracks] == ["t0", "t2"]
    assert back.tracks[1].link is None, "a link to a track that is gone must go too"


def test_a_show_saved_with_husks_is_healed_on_load(tmp_path):
    (tmp_path / "old.json").write_text(json.dumps({
        "name": "old",
        "tracks": [
            {"id": "t0", "targets": ["l0"]},
            {"id": "t1", "targets": []},
            {"id": "t2", "targets": []},
        ],
    }))
    show = store.load("old", tmp_path)
    assert [t.id for t in show.tracks] == ["t0"]
