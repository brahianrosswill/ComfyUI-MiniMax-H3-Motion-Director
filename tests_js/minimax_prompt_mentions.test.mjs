import test from "node:test";
import assert from "node:assert/strict";

import {
    createTimelineShortcutHandler,
    createListenerRegistry,
    isEditableTarget,
    isPromptEditingKey,
    mentionQueryFromText,
    moveMentionActiveIndex,
    promptValueNeedsRender,
    referenceChipPresentation,
    shouldHandleTimelineShortcut,
    shouldCloseMentionForScroll,
} from "../web/js/minimax_prompt_mentions_core.mjs";


test("typing @ opens a query at the current prompt caret", () => {
    assert.deepEqual(mentionQueryFromText("scene @Pic", 10), { start: 6, query: "Pic" });
    assert.equal(mentionQueryFromText("scene without mention"), null);
});

test("capture handler receives real key events without firing editor shortcuts", () => {
    const rich = fakeElement({ contentEditable: true, classes: ["bd-prompt-editor"] });
    const timeline = fakeElement({ tagName: "CANVAS" });
    const calls = { deleted: 0, played: 0, stepped: 0 };
    let activeElement = rich;
    const handler = createTimelineShortcutHandler({
        timelineElement: timeline,
        getActiveElement: () => activeElement,
        hasSelectedSplit: () => false,
        canDelete: () => true,
        onDelete: () => { calls.deleted += 1; },
        onTogglePlay: () => { calls.played += 1; },
        onStepFrame: () => { calls.stepped += 1; },
    });
    for (const [key, code] of [["Backspace", ""], ["Delete", ""], [" ", "Space"], ["ArrowLeft", ""], ["ArrowRight", ""]]) {
        handler({ key, code, target: rich, preventDefault() {} });
    }
    assert.deepEqual(calls, { deleted: 0, played: 0, stepped: 0 });
    activeElement = timeline;
    handler({ key: "Delete", code: "", target: timeline, preventDefault() {} });
    assert.equal(calls.deleted, 1);
});

test("AAA/BBB segment switching refreshes stale rich prompt without rebuilding self-input", () => {
    assert.equal(promptValueNeedsRender("AAA", "AAA", "AAA"), false);
    assert.equal(promptValueNeedsRender("BBB", "AAA", "BBB"), true);
    assert.equal(promptValueNeedsRender("AAA edited", "AAA edited", "AAA edited"), false);
    assert.equal(promptValueNeedsRender("AAA edited", "AAA edited", "BBB"), true);
});

test("reference chip presentation uses effective tag without changing semantic identity", () => {
    const formatters = {
        formatDisabled: (name) => `已关闭 · ${name}`,
        formatMissing: (name) => `素材不存在 · ${name}`,
        formatDisabledTitle: (authoringTag, name) => `原始引用 ${authoringTag}\n素材：${name}`,
        formatMissingTitle: (name) => `找不到素材：${name}`,
    };
    assert.deepEqual(referenceChipPresentation({
        assetId: "C",
        status: "active",
        authoringTag: "<Picture 3>",
        effectiveTag: "<Picture 1>",
        name: "C.png",
    }, formatters), {
        state: "active",
        text: "<Picture 1>",
        title: "C.png",
    });
    assert.deepEqual(referenceChipPresentation({
        assetId: "C",
        status: "disabled",
        authoringTag: "<Picture 3>",
        effectiveTag: "",
        name: "C.png",
    }, formatters), {
        state: "disabled",
        text: "已关闭 · C.png",
        title: "原始引用 <Picture 3>\n素材：C.png",
    });
    assert.deepEqual(referenceChipPresentation({
        assetId: "gone",
        status: "missing",
        name: "gone",
    }, formatters), {
        state: "missing",
        text: "素材不存在 · gone",
        title: "找不到素材：gone",
    });
});

test("scrolling inside the mention menu does not close it", () => {
    const child = {};
    const menu = { contains: (target) => target === child };
    assert.equal(shouldCloseMentionForScroll(menu, child), false);
    assert.equal(shouldCloseMentionForScroll(menu, menu), false);
    assert.equal(shouldCloseMentionForScroll(menu, {}), true);
});

test("Arrow navigation wraps and can keep the active row visible", () => {
    assert.equal(moveMentionActiveIndex(0, 1, 3), 1);
    assert.equal(moveMentionActiveIndex(2, 1, 3), 0);
    assert.equal(moveMentionActiveIndex(0, -1, 3), 2);
});

test("Backspace/Delete are prompt editing keys and must not reach group shortcuts", () => {
    assert.equal(isPromptEditingKey("Backspace"), true);
    assert.equal(isPromptEditingKey("Delete"), true);
    assert.equal(isPromptEditingKey("Enter"), false);
});

function fakeElement({ tagName = "DIV", contentEditable = null, parent = null, classes = [] } = {}) {
    return {
        tagName,
        parentElement: parent,
        isContentEditable: contentEditable === true,
        getAttribute(name) {
            if (name !== "contenteditable") return null;
            if (contentEditable === null) return null;
            return contentEditable ? "true" : "false";
        },
        classList: { contains: (name) => classes.includes(name) },
        closest(selector) {
            let current = this;
            while (current) {
                if (selector.includes(".bd-prompt-editor") && current.classList?.contains("bd-prompt-editor")) return current;
                if (selector.includes("input") && ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(current.tagName)) return current;
                if (selector.includes("[contenteditable") && current.getAttribute?.("contenteditable") !== null) return current;
                current = current.parentElement;
            }
            return null;
        },
    };
}

test("real capture-boundary predicate protects contenteditable and nested prompt nodes", () => {
    const rich = fakeElement({ contentEditable: true, classes: ["bd-prompt-editor"] });
    const nested = fakeElement({ parent: rich });
    for (const target of [rich, nested]) {
        assert.equal(isEditableTarget(target), true);
        for (const key of ["Backspace", "Delete", " ", "ArrowLeft", "ArrowRight", "Home", "End", "a"]) {
            assert.equal(shouldHandleTimelineShortcut({ key, code: key === " " ? "Space" : "", target }, {
                activeElement: rich,
                timelineElement: fakeElement(),
            }), false, key);
        }
    }
});

test("Delete is destructive only when the timeline owns keyboard focus", () => {
    const timeline = fakeElement({ tagName: "CANVAS" });
    const control = fakeElement({ tagName: "BUTTON" });
    assert.equal(shouldHandleTimelineShortcut({ key: "Delete", target: timeline }, {
        activeElement: timeline,
        timelineElement: timeline,
    }), true);
    assert.equal(shouldHandleTimelineShortcut({ key: "Delete", target: control }, {
        activeElement: control,
        timelineElement: timeline,
    }), false);
    assert.equal(shouldHandleTimelineShortcut({ key: "Delete", target: {} }, {
        activeElement: {},
        timelineElement: timeline,
    }), false);
});

test("repeated mention-editor listener mount/destroy does not accumulate handlers", () => {
    const active = new Set();
    const target = {
        addEventListener(type, handler) { active.add(`${type}:${handler.name}`); },
        removeEventListener(type, handler) { active.delete(`${type}:${handler.name}`); },
    };
    for (let index = 0; index < 5; index += 1) {
        const registry = createListenerRegistry();
        function onInput() {}
        function onScroll() {}
        registry.add(target, "input", onInput);
        registry.add(target, "scroll", onScroll, true);
        assert.equal(registry.size, 2);
        registry.destroy();
        assert.equal(registry.size, 0);
        assert.equal(active.size, 0);
    }
});
