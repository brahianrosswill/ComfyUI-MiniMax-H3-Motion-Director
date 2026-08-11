/** DOM-independent prompt mention behavior used by Node regression tests. */

export function moveMentionActiveIndex(current, delta, length) {
    if (!length) return 0;
    return (Number(current || 0) + Number(delta || 0) + length) % length;
}

export function shouldCloseMentionForScroll(menu, eventTarget) {
    return !(menu && eventTarget && (eventTarget === menu || menu.contains?.(eventTarget)));
}

export function isPromptEditingKey(key) {
    return [
        "Backspace", "Delete", " ", "Spacebar", "ArrowLeft", "ArrowRight",
        "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown",
    ].includes(key);
}

const FORM_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT", "BUTTON", "OPTION"]);

/** True for native controls and rich editors, including nested/inherited contenteditable nodes. */
export function isEditableTarget(target) {
    let current = target && typeof target === "object" ? target : null;
    if (current?.nodeType === 3) current = current.parentElement;
    if (!current) return false;
    if (FORM_TAGS.has(String(current.tagName || "").toUpperCase())) return true;
    if (current.isContentEditable) return true;
    if (current.classList?.contains?.("bd-prompt-editor")) return true;
    if (current.closest?.("input, textarea, select, button, [contenteditable], .bd-prompt-editor")) return true;
    while (current) {
        if (FORM_TAGS.has(String(current.tagName || "").toUpperCase())) return true;
        if (current.isContentEditable || current.classList?.contains?.("bd-prompt-editor")) return true;
        const attr = current.getAttribute?.("contenteditable");
        if (attr != null && String(attr).toLowerCase() !== "false") return true;
        current = current.parentElement;
    }
    return false;
}

/** Timeline shortcuts are valid only while the canvas owns the keyboard context. */
export function shouldHandleTimelineShortcut(event, { activeElement, timelineElement } = {}) {
    if (!event || event.defaultPrevented || event.isComposing) return false;
    if (isEditableTarget(event.target) || isEditableTarget(activeElement)) return false;
    if (!timelineElement) return false;
    return event.target === timelineElement || activeElement === timelineElement;
}

export function createTimelineShortcutHandler(options = {}) {
    return (event) => {
        const timelineElement = typeof options.timelineElement === "function"
            ? options.timelineElement() : options.timelineElement;
        const activeElement = options.getActiveElement?.();
        if (!shouldHandleTimelineShortcut(event, { activeElement, timelineElement })) return false;
        if (event.key === "Delete" || event.key === "Backspace") {
            if (options.hasSelectedSplit?.()) {
                event.preventDefault?.();
                return true;
            }
            if (!options.canDelete?.()) return false;
            options.onDelete?.();
            event.preventDefault?.();
            return true;
        }
        if (event.code === "Space") {
            options.onTogglePlay?.();
            event.preventDefault?.();
            return true;
        }
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            const direction = event.key === "ArrowLeft" ? -1 : 1;
            options.onStepFrame?.(direction * (event.shiftKey ? 10 : 1));
            event.preventDefault?.();
            return true;
        }
        return false;
    };
}

export function createListenerRegistry() {
    const listeners = [];
    return {
        add(target, type, handler, options) {
            target?.addEventListener?.(type, handler, options);
            listeners.push([target, type, handler, options]);
        },
        destroy() {
            for (const [target, type, handler, options] of listeners.splice(0)) {
                target?.removeEventListener?.(type, handler, options);
            }
        },
        get size() { return listeners.length; },
    };
}

export function promptValueNeedsRender(hiddenValue, richValue, nextValue) {
    const next = String(nextValue || "");
    return String(hiddenValue || "") !== next || String(richValue || "") !== next;
}

export function referenceChipPresentation(item = {}, formatters = {}) {
    const state = item.status || (item.assetId ? "active" : "missing");
    const identity = String(item.assetId || "");
    const name = String(item.name || item.label || identity);
    if (state === "active") {
        return {
            state,
            text: String(item.effectiveTag || item.officialTag || item.label || identity),
            title: name || String(item.effectiveTag || item.officialTag || ""),
        };
    }
    if (state === "disabled") {
        return {
            state,
            text: formatters.formatDisabled?.(name) || name,
            title: formatters.formatDisabledTitle?.(String(item.authoringTag || ""), name) || name,
        };
    }
    return {
        state: "missing",
        text: formatters.formatMissing?.(name) || name,
        title: formatters.formatMissingTitle?.(name) || name,
    };
}

export function mentionQueryFromText(text, cursor = String(text || "").length) {
    const before = String(text || "").slice(0, Math.max(0, Number(cursor) || 0));
    const match = before.match(/@([^\s@]*)$/);
    if (!match) return null;
    return { start: before.length - match[0].length, query: match[1] };
}
