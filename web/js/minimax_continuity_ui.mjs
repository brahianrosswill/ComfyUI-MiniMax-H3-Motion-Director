// Pure state rules for the Director node's cross-segment continuity controls.
// Kept DOM-free so workflow compatibility rules can be tested with Node.js.

export const SOURCE_BRIDGE_FIXED_FRAMES = 5;

const BRIDGE_TASKS = new Set(["v2v", "rv2v"]);
const MOTION_CONTEXT_TASKS = new Set(["t2v", "i2v", "r2v", "fl2v", "v2v", "rv2v"]);

function boolValue(value) {
    if (value === false || value === 0 || value == null) return false;
    const text = String(value).trim().toLowerCase();
    return text !== "" && text !== "0" && text !== "false" && text !== "off";
}

export function normalizeSourceBridgeValue(value) {
    return boolValue(value) ? SOURCE_BRIDGE_FIXED_FRAMES : 0;
}

export function syncDisabledWidgetState(widget, enabled) {
    if (!widget) return;
    if (!enabled) widget._mmxContinuityStoredValue = widget.value;
    widget._mmxContinuityDisabled = !enabled;
    widget.disabled = !enabled;
}

export function restoreDisabledWidgetValue(widget) {
    if (!widget || widget._mmxContinuityStoredValue === undefined) return;
    widget.value = widget._mmxContinuityStoredValue;
}

export function notifyWidgetValueChange(node, widget, nextValue, callbackArgs = []) {
    if (!widget || Object.is(widget.value, nextValue)) return false;
    const oldValue = widget.value;
    widget.value = nextValue;
    widget.callback?.call(widget, nextValue, ...callbackArgs);
    node?.onWidgetChanged?.(widget.name, nextValue, oldValue, widget);
    node?.graph?.incrementVersion?.();
    node?.setDirtyCanvas?.(true, true);
    return true;
}

export function resolveContinuityUiState({
    taskKey,
    segmentCount,
    motionContextEnabled,
    contextFrames,
    sourceBridgeValue,
    audioContextEnabled,
    audioMode,
} = {}) {
    const task = String(taskKey || "").trim().toLowerCase();
    const segments = Math.max(0, Math.trunc(Number(segmentCount) || 0));
    const multiSegment = segments > 1;
    const bridgeTask = BRIDGE_TASKS.has(task);
    const motionTask = MOTION_CONTEXT_TASKS.has(task);
    const normalizedBridge = normalizeSourceBridgeValue(sourceBridgeValue);
    const bridgeOn = normalizedBridge > 0;
    const motionOn = boolValue(motionContextEnabled);
    const audioOn = boolValue(audioContextEnabled);
    const bridgeActive = multiSegment && bridgeTask && bridgeOn;
    const motionControlEnabled = multiSegment && motionTask && !bridgeActive;
    const motionActive = motionControlEnabled && motionOn;
    const context = Math.max(1, Math.trunc(Number(contextFrames) || 1));

    let strategy = "none";
    let status = { key: "none", task: task.toUpperCase(), segments };
    if (!multiSegment) {
        strategy = "single";
        status = { key: "single", task: task.toUpperCase(), segments };
    } else if (bridgeActive) {
        strategy = "source_bridge";
        status = {
            key: "bridge",
            task: task.toUpperCase(),
            segments,
            frames: SOURCE_BRIDGE_FIXED_FRAMES,
        };
    } else if (motionActive) {
        strategy = "motion_context";
        status = { key: "motion", task: task.toUpperCase(), segments, frames: context };
    }

    return {
        taskKey: task,
        segmentCount: segments,
        multiSegment,
        strategy,
        status,
        motionContextValue: motionOn,
        audioContextValue: audioOn,
        sourceBridgeValue: normalizedBridge,
        sourceBridgeChecked: bridgeOn,
        sourceBridgeControlEnabled: multiSegment && bridgeTask,
        motionContextSuppressedByBridge: bridgeActive,
        motionContextControlEnabled: motionControlEnabled,
        contextFramesControlEnabled: motionActive,
        audioContextControlEnabled: motionActive && String(audioMode || "generate").toLowerCase() === "generate",
    };
}
