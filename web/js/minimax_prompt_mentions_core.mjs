/** DOM-independent prompt mention behavior used by Node regression tests. */

export function moveMentionActiveIndex(current, delta, length) {
    if (!length) return 0;
    return (Number(current || 0) + Number(delta || 0) + length) % length;
}

export function shouldCloseMentionForScroll(menu, eventTarget) {
    return !(menu && eventTarget && (eventTarget === menu || menu.contains?.(eventTarget)));
}

export function isPromptEditingKey(key) {
    return key === "Backspace" || key === "Delete";
}

export function mentionQueryFromText(text, cursor = String(text || "").length) {
    const before = String(text || "").slice(0, Math.max(0, Number(cursor) || 0));
    const match = before.match(/@([^\s@]*)$/);
    if (!match) return null;
    return { start: before.length - match[0].length, query: match[1] };
}
