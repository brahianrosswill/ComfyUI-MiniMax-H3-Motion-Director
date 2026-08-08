# Portions derived from ComfyUI-H3-Motion-Context
# Copyright (C) 2026 NikoDemon80 and contributors
# Modified for MiniMax H3 Motion Director, 2026-08-09
# Licensed under GNU GPL v3.0. See LICENSE and NOTICE.

"""Lift MiniMax H3's first/last-only keyframe anchor restriction.

Stock ComfyUI builds keyframe conditioning rows at one of two time
coordinates and rejects everything else:

    if pixel_index == 0:
        cond_t = float(text_len)
    elif frame_count is not None and pixel_index == frame_count - 1:
        cond_t = float(text_len) + sum(_video_t_spans(latent_t)) - FRAME_RESCALE
    else:
        raise ValueError("only first/last keyframe anchors are supported")

Both branches are the same expression. Each video token spans
FRAME_RESCALE * FRAME_PER_TOKEN[k % 5] and covers FRAME_PER_TOKEN[k % 5]
pixel frames, so the cumulative time at pixel frame p is exactly
FRAME_RESCALE * p, for every p. Substituting p = frame_count - 1
reproduces the second branch identically:

    text_len + FRAME_RESCALE * (frame_count - 1)
      == text_len + FRAME_RESCALE * frame_count - FRAME_RESCALE
      == text_len + sum(_video_t_spans(latent_t)) - FRAME_RESCALE

So the general position is:

    cond_t = text_len + FRAME_RESCALE * pixel_index

We do NOT rewrite the source of PackedLayout.__init__. Instead every
keyframe is handed to stock code with resolved_frame_index = 0, which is
always legal, and the real index rides along under MC_KEY. After the
stock constructor returns we rewrite the time column of each cond
segment's rows in position_ids. RoPE is built at forward time from
position_ids, so this lands before anything reads it.

That keeps the patch surface to one attribute we can verify rather than a
copy of a 90-line constructor that would rot on the next ComfyUI change.
"""

import logging

import torch

import comfy.ldm.minimax.model as mm

MC_KEY = "motion_context_index"
MC_AUDIO_KEY = "motion_context_audio_end_frame"
_LOG = logging.getLogger("h3_motion_context")

_orig_init = None
_applied = False
_failure_reason = None


def _ref_cursor_span(blk):
    """Return the exact amount one stock H3 ref advances the cursor."""
    kind = blk.get("kind")
    if kind == "image":
        return 1.0
    if kind == "audio":
        return float(blk.get("ref_audio_t", 0))
    if kind in ("video", "video_audio"):
        rt = float(blk.get("ref_audio_t", 0))
        vt = int(blk.get("latent_t", 0))
        return max(rt, sum(mm._video_t_spans(vt)))
    raise RuntimeError(
        "h3_motion_context: unknown ref kind %r; refusing cursor arithmetic."
        % kind
    )


def _ref_cursor_advance(refs):
    """How far ref blocks push the target origin past text_len.

    Refs are laid out sequentially from a cursor that starts at text_len,
    and the target audio and video rows use the cursor's final value as
    their origin. Keyframe coordinates are computed from text_len directly,
    so without this term adding any ref would slide the anchors backwards
    relative to the clip they are anchoring.
    """
    if not refs:
        return 0.0
    cursor = 0.0
    for blk in refs:
        cursor += _ref_cursor_span(blk)
    return cursor


def _marked_audio_cursor(refs):
    """Return (block, start, final cursor) for the one marked audio ref."""
    cursor = 0.0
    marked = []
    for index, blk in enumerate(refs or []):
        start = cursor
        cursor += _ref_cursor_span(blk)
        if blk.get(MC_AUDIO_KEY) is not None:
            marked.append((index, blk, start))
    if len(marked) != 1:
        raise RuntimeError(
            "h3_motion_context: expected exactly one marked Motion Audio "
            "Context ref, found %d among %d refs."
            % (len(marked), len(refs or []))
        )
    _, blk, start = marked[0]
    if blk.get("kind") != "audio":
        raise RuntimeError(
            "h3_motion_context: %s is set on a %r ref; only a standalone "
            "audio ref may be moved onto the target timeline."
            % (MC_AUDIO_KEY, blk.get("kind"))
        )
    return blk, start, cursor


def _cond_t(text_len, latent_t, frame_count, p):
    """Time coordinate for a keyframe anchored at pixel frame p.

    The endpoints reuse stock's exact expressions rather than the general
    formula. They are mathematically identical, but stock accumulates
    latent_t float additions where the general form does one multiply, and
    those differ in the last bits (about 7e-15). Matching stock bit for bit
    means an existing first/last graph builds byte-identical positions
    after this patch is applied, and lets the self-test stay strict.
    """
    if p == 0:
        return float(text_len)
    if frame_count is not None and p == frame_count - 1:
        return float(text_len) + sum(mm._video_t_spans(latent_t)) - mm.FRAME_RESCALE
    return float(text_len) + mm.FRAME_RESCALE * float(p)


def _fixup(layout, text_len, latent_t, frame_count, keyframes, refs=None):
    """Rewrite cond-row time coordinates to the general position formula."""
    offset = _ref_cursor_advance(refs)
    if offset and any(kf.get(MC_KEY) is None for kf in keyframes):
        # keyframes without MC_KEY are left exactly as stock built them,
        # which means they do NOT get the ref cursor compensation. Mixing
        # them with MC keyframes under a ref would slide the stock anchors
        # relative to ours and to the target. Nothing produces this today;
        # refuse loudly in case something ever does.
        raise RuntimeError(
            "h3_motion_context: stock and motion-context keyframes mixed in "
            "one graph alongside a ref; their coordinates would disagree. "
            "Give every keyframe a %s entry or remove the refs." % MC_KEY)
    cond_spans = [(a, b) for a, b, kind in layout.segments if kind == "cond"]
    if len(cond_spans) != len(keyframes):
        raise RuntimeError(
            "h3_motion_context: expected %d cond segments, layout has %d. "
            "Refusing to rewrite positions."
            % (len(keyframes), len(cond_spans)))
    for (a, b), kf in zip(cond_spans, keyframes):
        p = kf.get(MC_KEY)
        if p is None:
            continue
        layout.position_ids[a:b, 0] = _cond_t(text_len, latent_t, frame_count, p) + offset


def _fixup_audio(layout, text_len, refs):
    """Move the audio ref rows' time coordinates onto the target timeline.

    Refs and keyframes carry identical row machinery; what makes the model
    read a ref as "a separate clip to imitate" rather than "this clip,
    continued" is that its coordinates sit in a span before the target.
    That distinction decided continuation vs reproduction for video, and
    seam analysis showed the audio ref producing phase-unlocked imitation.
    So: keep the audio on the ref path for construction and payload (rows
    built, latents filled, all stock code untouched) and TRANSLATE its
    time coordinates so the window END lands at target frame
    MC_AUDIO_KEY -- the same instant the pinned video ends.

    Translation, not per-row assignment: new = old + shift preserves
    whatever intra-block structure stock built (row order, the rows-per-
    step factor, fractional offsets), so nothing about the block's
    internals is assumed.

    The ref still advances the layout cursor, so its old coordinate slot
    [text_len, text_len + rt) is left VACANT after the move. An audio
    window longer than the video window therefore spills backwards into
    empty coordinate space rather than onto the text rows -- the collision
    that made `before` mode fail for video does not arise here.

    Row selection is by coordinate range (the vacated slot), excluding
    cond segments explicitly so a stock first-frame keyframe sitting at
    text_len can never be swept up regardless of fixup order.
    """
    blk, marked_start, final_cursor = _marked_audio_cursor(refs)
    rt = int(blk.get("ref_audio_t", 0))
    if rt <= 0:
        raise RuntimeError(
            "h3_motion_context: marked Motion Audio Context has no latent steps."
        )
    end_frame = float(blk[MC_AUDIO_KEY])
    old_start = float(text_len) + marked_start
    old_end = old_start + float(rt)
    target_origin = float(text_len) + final_cursor

    t = layout.position_ids[:, 0]
    sel = (t >= old_start - 1e-4) & (t < old_end - 1e-4)
    for a, b, kind in layout.segments:
        if kind == "cond":
            sel[a:b] = False
    count = int(sel.sum())
    expected_rows = rt * 2
    if count != expected_rows:
        raise RuntimeError(
            "h3_motion_context: found %d rows in the audio ref's coordinate "
            "slot for %d latent steps, expected exactly %d. Upstream layout "
            "change or overlapping ref coordinates; refusing to move rows."
            % (count, rt, expected_rows)
        )
    # window end at target time FRAME_RESCALE * end_frame, width rt steps
    shift = (target_origin + mm.FRAME_RESCALE * end_frame - rt) - old_start
    layout.position_ids[sel, 0] = t[sel] + shift


def _patched_init(self, text_len, latent_t, latent_h, latent_w, audio_t,
                  keyframes=None, refs=None, frame_count=None):
    _orig_init(self, text_len, latent_t, latent_h, latent_w, audio_t,
               keyframes=keyframes, refs=refs, frame_count=frame_count)
    has_mc_kf = bool(keyframes) and any(
        kf.get(MC_KEY) is not None for kf in keyframes)
    has_mc_audio = bool(refs) and any(
        r.get(MC_AUDIO_KEY) is not None for r in refs)
    if has_mc_kf:
        _fixup(self, text_len, latent_t, frame_count, keyframes, refs)
    if has_mc_audio:
        _fixup_audio(self, text_len, refs)
    # neither marked: stock graph, leave it exactly as built


def _self_test():
    """Prove the rewrite reproduces stock positions before committing.

    Builds the two anchors stock code already supports, once the stock way
    and once through our mechanism, and requires the position tensors to
    match exactly. If ComfyUI changes the position maths underneath us this
    fails and the patch is not applied.
    """
    text_len, latent_t, lh, lw, audio_t = 7, 7, 22, 38, 16
    frame_count = sum(mm.FRAME_PER_TOKEN[k % 5] for k in range(latent_t))

    stock_kf = [{"resolved_frame_index": 0},
                {"resolved_frame_index": frame_count - 1}]
    ours_kf = [{"resolved_frame_index": 0, MC_KEY: 0},
               {"resolved_frame_index": 0, MC_KEY: frame_count - 1}]

    a = mm.PackedLayout.__new__(mm.PackedLayout)
    _orig_init(a, text_len, latent_t, lh, lw, audio_t,
               keyframes=stock_kf, frame_count=frame_count)

    b = mm.PackedLayout.__new__(mm.PackedLayout)
    _orig_init(b, text_len, latent_t, lh, lw, audio_t,
               keyframes=ours_kf, frame_count=frame_count)
    _fixup(b, text_len, latent_t, frame_count, ours_kf)

    if a.position_ids.shape != b.position_ids.shape:
        raise RuntimeError("position_ids shape mismatch in self-test")
    if not torch.equal(a.position_ids, b.position_ids):
        bad = (a.position_ids != b.position_ids).any(dim=1).nonzero().flatten()
        raise RuntimeError("position mismatch at rows %s" % bad[:8].tolist())

    # a consecutive run must land on strictly increasing coordinates inside
    # the span the two endpoints define
    run = [{"resolved_frame_index": 0, MC_KEY: i} for i in range(4)]
    c = mm.PackedLayout.__new__(mm.PackedLayout)
    _orig_init(c, text_len, latent_t, lh, lw, audio_t,
               keyframes=run, frame_count=frame_count)
    _fixup(c, text_len, latent_t, frame_count, run)
    ts = [float(c.position_ids[s, 0]) for s, _, k in c.segments if k == "cond"]
    if len(ts) != len(run):
        raise RuntimeError("expected %d cond segments, got %d" % (len(run), len(ts)))
    if any(ts[i] >= ts[i + 1] for i in range(len(ts) - 1)):
        raise RuntimeError("consecutive anchors not strictly increasing: %s" % ts)
    t_last = float(text_len) + mm.FRAME_RESCALE * (frame_count - 1)
    if not (ts[0] == float(text_len) and ts[-1] < t_last):
        raise RuntimeError("run %s escapes the [%.4f, %.4f] span"
                           % (ts, float(text_len), t_last))

    # adding a ref must not move the anchors relative to the target. Stock
    # cond rows cannot be the reference here: stock computes them from
    # text_len and never compensates for refs, which is the very bug
    # _ref_cursor_advance exists to fix. The ground truth is the target
    # rows themselves. Ref rows are laid out BEFORE the target, so the
    # largest time coordinate in position_ids belongs to the end of the
    # target in both layouts, and the anchor-to-end gap must be identical
    # with and without the ref. This exercises _ref_cursor_advance against
    # stock's real cursor arithmetic, so if upstream changes how refs
    # advance the cursor, this fails and the patch is not applied.
    ref = [{"kind": "audio", "ref_audio_t": 8}]
    d = mm.PackedLayout.__new__(mm.PackedLayout)
    _orig_init(d, text_len, latent_t, lh, lw, audio_t,
               keyframes=run, refs=ref, frame_count=frame_count)
    _fixup(d, text_len, latent_t, frame_count, run, refs=ref)
    ts_ref = [float(d.position_ids[s, 0]) for s, _, k in d.segments if k == "cond"]
    if len(ts_ref) != len(ts):
        raise RuntimeError("cond segment count changed when a ref was added")
    # a semantic failure here is a shift of whole rows (the 8.0 of the ref,
    # or FRAME_RESCALE multiples), while legitimate noise is float
    # accumulation from a different origin, orders of magnitude below 1e-3
    # even at float32. Strict equality stays reserved for the endpoint test.
    tol = 1e-3
    gap = float(c.position_ids[:, 0].max()) - ts[0]
    gap_ref = float(d.position_ids[:, 0].max()) - ts_ref[0]
    if abs(gap - gap_ref) > tol:
        raise RuntimeError(
            "ref compensation off by %.6f: anchor-to-target gap %.6f without "
            "ref, %.6f with. _ref_cursor_advance no longer matches the "
            "layout's cursor arithmetic." % (gap_ref - gap, gap, gap_ref))
    shifts = [b - a for a, b in zip(ts, ts_ref)]
    if any(abs(s - shifts[0]) > tol for s in shifts):
        raise RuntimeError("ref shifted anchors unevenly: %s" % shifts)

    # Multi-ref audio placement: Picture, Video, Motion Audio, user Audio.
    # Only the marked block may move, and target origin must include the user
    # audio that follows it. This proves both actual-cursor discovery and the
    # final-cursor calculation rather than relying on refs == 1.
    end_frame = 4
    rt = 8
    refs_plain = [
        {"kind": "image", "latent_h": 8, "latent_w": 12},
        {"kind": "video", "latent_t": 2, "latent_h": 8, "latent_w": 12,
         "ref_audio_t": 0},
        {"kind": "audio", "ref_audio_t": rt},
        {"kind": "audio", "ref_audio_t": 5},
    ]
    ref_mc = [dict(r) for r in refs_plain]
    ref_mc[2][MC_AUDIO_KEY] = end_frame
    d_audio = mm.PackedLayout.__new__(mm.PackedLayout)
    _orig_init(d_audio, text_len, latent_t, lh, lw, audio_t,
               keyframes=run, refs=refs_plain, frame_count=frame_count)
    _fixup(d_audio, text_len, latent_t, frame_count, run, refs=refs_plain)
    e = mm.PackedLayout.__new__(mm.PackedLayout)
    _orig_init(e, text_len, latent_t, lh, lw, audio_t,
               keyframes=run, refs=ref_mc, frame_count=frame_count)
    _fixup(e, text_len, latent_t, frame_count, run, refs=ref_mc)
    _fixup_audio(e, text_len, ref_mc)
    if e.position_ids.shape != d_audio.position_ids.shape:
        raise RuntimeError("audio move changed the layout shape")
    if not torch.equal(d_audio.position_ids[:, 1:], e.position_ids[:, 1:]):
        raise RuntimeError("audio move touched a non-time coordinate column")
    td, te = d_audio.position_ids[:, 0], e.position_ids[:, 0]
    cond_rows = set()
    for a, b, kind in d_audio.segments:
        if kind == "cond":
            cond_rows.update(range(a, b))
    marked_start = float(text_len) + sum(_ref_cursor_span(r) for r in refs_plain[:2])
    expect_moved = set(i for i in range(len(td))
                       if marked_start - 1e-4 <= float(td[i]) < marked_start + rt - 1e-4
                       and i not in cond_rows)
    moved = set(i for i in range(len(td)) if float(td[i]) != float(te[i]))
    if moved != expect_moved:
        raise RuntimeError(
            "audio move touched the wrong rows: %d moved, %d expected, "
            "e.g. %s" % (len(moved), len(expect_moved),
                         sorted(moved ^ expect_moved)[:8]))
    if not moved:
        raise RuntimeError("audio move moved no rows")
    trailing = _ref_cursor_span(refs_plain[3])
    want_shift = trailing + mm.FRAME_RESCALE * end_frame
    deltas = [float(te[i]) - float(td[i]) for i in sorted(moved)]
    if any(abs(dd - want_shift) > 1e-5 for dd in deltas):
        raise RuntimeError("audio rows shifted non-uniformly or by the wrong "
                           "amount: %s vs %.6f" % (deltas[:4], want_shift))


def apply_patch():
    global _orig_init, _applied, _failure_reason
    if _applied:
        return True
    if not hasattr(mm, "PackedLayout") or not hasattr(mm, "FRAME_RESCALE"):
        _failure_reason = "MiniMax H3 model module is missing PackedLayout/FRAME_RESCALE"
        _LOG.warning("h3_motion_context: %s; patch not applied", _failure_reason)
        return False
    _orig_init = mm.PackedLayout.__init__
    try:
        _self_test()
    except Exception as exc:
        _orig_init = None
        _failure_reason = str(exc)
        _LOG.warning("h3_motion_context: self-test failed (%s), patch not applied. "
                     "Interior keyframe anchors unavailable.", exc)
        return False
    mm.PackedLayout.__init__ = _patched_init
    _applied = True
    _failure_reason = None
    _LOG.info("h3_motion_context: interior keyframe anchors enabled")
    return True


def is_applied():
    return _applied


def failure_reason():
    return _failure_reason
