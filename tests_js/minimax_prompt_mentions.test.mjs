import test from "node:test";
import assert from "node:assert/strict";

import {
    isPromptEditingKey,
    mentionQueryFromText,
    moveMentionActiveIndex,
    shouldCloseMentionForScroll,
} from "../web/js/minimax_prompt_mentions_core.mjs";


test("typing @ opens a query at the current prompt caret", () => {
    assert.deepEqual(mentionQueryFromText("scene @Pic", 10), { start: 6, query: "Pic" });
    assert.equal(mentionQueryFromText("scene without mention"), null);
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
