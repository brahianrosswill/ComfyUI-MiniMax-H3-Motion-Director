import test from "node:test";
import assert from "node:assert/strict";

import {
    SOURCE_BRIDGE_FIXED_FRAMES,
    normalizeSourceBridgeValue,
    notifyWidgetValueChange,
    resolveContinuityUiState,
    restoreDisabledWidgetValue,
    syncDisabledWidgetState,
} from "../web/js/minimax_continuity_ui.mjs";

const state = (overrides = {}) => resolveContinuityUiState({
    taskKey: "t2v",
    segmentCount: 3,
    motionContextEnabled: true,
    contextFrames: 22,
    sourceBridgeValue: 0,
    audioContextEnabled: true,
    audioMode: "generate",
    ...overrides,
});

test("Source Bridge facade serializes legacy and boolean values as INT 0 or fixed 5", () => {
    assert.equal(SOURCE_BRIDGE_FIXED_FRAMES, 5);
    assert.equal(normalizeSourceBridgeValue(0), 0);
    assert.equal(normalizeSourceBridgeValue(false), 0);
    assert.equal(normalizeSourceBridgeValue("off"), 0);
    assert.equal(normalizeSourceBridgeValue(5), 5);
    assert.equal(normalizeSourceBridgeValue(true), 5);
    assert.equal(normalizeSourceBridgeValue(3), 5);
    assert.equal(normalizeSourceBridgeValue("1"), 5);
});

test("a single segment disables every cross-segment control without changing stored values", () => {
    const actual = state({
        taskKey: "rv2v",
        segmentCount: 1,
        sourceBridgeValue: 5,
    });
    assert.equal(actual.strategy, "single");
    assert.equal(actual.motionContextControlEnabled, false);
    assert.equal(actual.contextFramesControlEnabled, false);
    assert.equal(actual.audioContextControlEnabled, false);
    assert.equal(actual.sourceBridgeControlEnabled, false);
    assert.equal(actual.motionContextValue, true);
    assert.equal(actual.sourceBridgeValue, 5);
});

for (const taskKey of ["t2v", "i2v", "r2v", "fl2v"]) {
    test(`${taskKey.toUpperCase()} multi-segment uses Motion Context and disables Source Bridge`, () => {
        const actual = state({ taskKey, sourceBridgeValue: 5 });
        assert.equal(actual.strategy, "motion_context");
        assert.equal(actual.motionContextControlEnabled, true);
        assert.equal(actual.contextFramesControlEnabled, true);
        assert.equal(actual.audioContextControlEnabled, true);
        assert.equal(actual.sourceBridgeControlEnabled, false);
        assert.equal(actual.sourceBridgeValue, 5);
    });
}

for (const taskKey of ["v2v", "rv2v"]) {
    test(`${taskKey.toUpperCase()} Bridge ON suppresses visual Motion Context without erasing it`, () => {
        const actual = state({ taskKey, sourceBridgeValue: 5 });
        assert.equal(actual.strategy, "source_bridge");
        assert.equal(actual.motionContextSuppressedByBridge, true);
        assert.equal(actual.motionContextControlEnabled, false);
        assert.equal(actual.contextFramesControlEnabled, false);
        assert.equal(actual.audioContextControlEnabled, false);
        assert.equal(actual.sourceBridgeControlEnabled, true);
        assert.equal(actual.motionContextValue, true);
    });

    test(`${taskKey.toUpperCase()} Bridge OFF restores experimental Motion Context fallback`, () => {
        const actual = state({ taskKey, sourceBridgeValue: 0 });
        assert.equal(actual.strategy, "motion_context");
        assert.equal(actual.motionContextSuppressedByBridge, false);
        assert.equal(actual.motionContextControlEnabled, true);
        assert.equal(actual.contextFramesControlEnabled, true);
        assert.equal(actual.audioContextControlEnabled, true);
    });
}

test("Motion Context OFF disables its dependent frame and audio controls", () => {
    const actual = state({ motionContextEnabled: false });
    assert.equal(actual.strategy, "none");
    assert.equal(actual.motionContextControlEnabled, true);
    assert.equal(actual.contextFramesControlEnabled, false);
    assert.equal(actual.audioContextControlEnabled, false);
});

test("non-video generation tasks do not expose video continuity controls", () => {
    const actual = state({ taskKey: "t2i", sourceBridgeValue: 5 });
    assert.equal(actual.strategy, "none");
    assert.equal(actual.motionContextControlEnabled, false);
    assert.equal(actual.contextFramesControlEnabled, false);
    assert.equal(actual.audioContextControlEnabled, false);
    assert.equal(actual.sourceBridgeControlEnabled, false);
});

test("Continue Generated Audio is additionally gated by generated-audio output mode", () => {
    assert.equal(state({ audioMode: "generate" }).audioContextControlEnabled, true);
    assert.equal(state({ audioMode: "source" }).audioContextControlEnabled, false);
    assert.equal(state({ audioMode: "mute" }).audioContextControlEnabled, false);
});

test("status payload identifies the active task, segment count, and context size", () => {
    assert.deepEqual(
        state({ taskKey: "t2v", segmentCount: 3, contextFrames: 22 }).status,
        { key: "motion", task: "T2V", segments: 3, frames: 22 },
    );
    assert.deepEqual(
        state({ taskKey: "rv2v", segmentCount: 2, sourceBridgeValue: 5 }).status,
        { key: "bridge", task: "RV2V", segments: 2, frames: 5 },
    );
});

test("disabled widget snapshot follows workflow values loaded after node creation", () => {
    const widget = { value: true };
    syncDisabledWidgetState(widget, false);
    assert.equal(widget._mmxContinuityStoredValue, true);

    // ComfyUI onConfigure applies the old workflow value after onCreated.
    widget.value = false;
    syncDisabledWidgetState(widget, false);
    assert.equal(widget._mmxContinuityStoredValue, false);

    // A disabled click must restore that loaded value, not the node default.
    widget.value = true;
    restoreDisabledWidgetValue(widget);
    assert.equal(widget.value, false);
});

test("Bridge facade reports a real source widget change for save, undo, and graph history", () => {
    const calls = [];
    const widget = {
        name: "source_overlap_frames",
        value: 0,
        callback(value) { calls.push(["callback", value]); },
    };
    const node = {
        graph: { incrementVersion() { calls.push(["version"]); } },
        onWidgetChanged(name, value, oldValue, changedWidget) {
            calls.push(["changed", name, value, oldValue, changedWidget]);
        },
        setDirtyCanvas(fg, bg) { calls.push(["dirty", fg, bg]); },
    };

    assert.equal(notifyWidgetValueChange(node, widget, 5), true);
    assert.equal(widget.value, 5);
    assert.deepEqual(calls[0], ["callback", 5]);
    assert.deepEqual(calls[1], ["changed", "source_overlap_frames", 5, 0, widget]);
    assert.deepEqual(calls[2], ["version"]);
    assert.deepEqual(calls[3], ["dirty", true, true]);
    assert.equal(notifyWidgetValueChange(node, widget, 5), false);
    assert.equal(calls.length, 4);
});
