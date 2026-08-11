// Portions derived from ComfyUI_MiniMaxH3_Director
// Copyright AIMixer and contributors
// Originally licensed under Apache License 2.0
// Modified for MiniMax H3 Motion Director, 2026-08-12
// This derivative project is distributed under GPL-3.0.

/** Asset-aware prompt chips and @ picker for MiniMax H3 references. */

import { api } from "../../scripts/api.js";
import {
    refAudioLabel,
    refAudioPromptTag,
    refImageLabel,
    refImagePromptTag,
    refVideoLabel,
    refVideoPromptTag,
} from "./minimax_gen_timeline.js";
import {
    SEMANTIC_REFERENCE_RE,
    semanticReferenceToken,
} from "./minimax_reference_assets.mjs";
import { t } from "./minimax_i18n.js";
import {
    isPromptEditingKey,
    moveMentionActiveIndex,
    shouldCloseMentionForScroll,
} from "./minimax_prompt_mentions_core.mjs";
export {
    isPromptEditingKey,
    mentionQueryFromText,
    moveMentionActiveIndex,
    shouldCloseMentionForScroll,
} from "./minimax_prompt_mentions_core.mjs";

const MENTION_STYLES = `
.bd-prompt-editor{width:100%;min-height:64px;box-sizing:border-box;background:#141414;border:1px solid #333;border-radius:5px;color:#eee;padding:7px;white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.45 inherit;outline:none}
.bd-prompt-editor:focus{border-color:#4d7b5b;box-shadow:0 0 0 1px rgba(79,255,143,.12)}
.bd-prompt-chip{display:inline-flex;align-items:center;max-width:190px;margin:0 2px;padding:1px 6px;border:1px solid #45604d;border-radius:999px;background:#1a2b20;color:#8ff0aa;font-weight:700;white-space:nowrap;vertical-align:baseline;user-select:all}
.bd-prompt-chip[data-missing="1"]{border-color:#8b4b4b;background:#301b1b;color:#ff9c9c}
.bd-prompt-chip-picture:before{content:"▣";margin-right:4px}.bd-prompt-chip-video:before{content:"▶";margin-right:4px}.bd-prompt-chip-audio:before{content:"♪";margin-right:4px}
.bd-mention-menu{position:fixed;z-index:10050;min-width:230px;max-width:340px;max-height:240px;overflow:auto;background:#252525;border:1px solid #444;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.45);padding:4px 0}
.bd-mention-menu.hidden{display:none!important}.bd-mention-title{padding:6px 10px 4px;font-size:10px;color:#888;user-select:none}
.bd-mention-item{display:flex;align-items:center;gap:8px;padding:6px 10px;cursor:pointer;font-size:11px;color:#ddd}.bd-mention-item:hover,.bd-mention-item.active{background:#333;color:#fff}
.bd-mention-item img{width:36px;height:36px;object-fit:cover;border-radius:4px;flex-shrink:0;background:#111;border:1px solid #333}.bd-mention-item .bd-mention-label{font-weight:650;color:#4fff8f}.bd-mention-item .bd-mention-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#aaa}
.bd-mention-empty{padding:10px 12px;font-size:11px;color:#888;text-align:center;line-height:1.4}
`;

let stylesInjected = false;

function injectStyles() {
    if (stylesInjected) return;
    stylesInjected = true;
    const el = document.createElement("style");
    el.textContent = MENTION_STYLES;
    document.head.appendChild(el);
}

function inputViewUrl(filename, type = "input") {
    const normalized = String(filename || "").replace(/\\/g, "/");
    const subfolder = normalized.includes("/") ? normalized.slice(0, normalized.lastIndexOf("/")) : "";
    const base = subfolder ? normalized.slice(subfolder.length + 1) : normalized;
    const params = new URLSearchParams({ filename: base, type });
    if (subfolder) params.set("subfolder", subfolder);
    return api.apiURL(`/view?${params.toString()}`);
}

function refThumbUrl(ref) {
    if (ref?.imageFile) return inputViewUrl(ref.imageFile, "input");
    if (ref?.imageB64) return ref.imageB64.startsWith("data:") ? ref.imageB64 : `data:image/png;base64,${ref.imageB64}`;
    return "";
}

function legacyMentionItems(refs, audios, videos) {
    const items = [];
    for (const ref of [...(refs || [])].filter((x) => x?.imageFile || x?.imageB64)
        .sort((a, b) => Number(a.index ?? a.slot ?? 0) - Number(b.index ?? b.slot ?? 0))) {
        const index = Number(ref.index ?? ref.slot ?? 0);
        items.push({ kind: "picture", label: refImageLabel(index), officialTag: refImagePromptTag(index), token: refImagePromptTag(index), thumb: refThumbUrl(ref), name: "" });
    }
    for (const ref of [...(videos || [])].filter((x) => x?.videoFile || x?.fileName)
        .sort((a, b) => Number(a.index ?? a.slot ?? 0) - Number(b.index ?? b.slot ?? 0))) {
        const index = Number(ref.index ?? ref.slot ?? 0);
        items.push({ kind: "video", label: refVideoLabel(index), officialTag: refVideoPromptTag(index), token: refVideoPromptTag(index), thumb: "", name: "" });
    }
    for (const ref of [...(audios || [])].filter((x) => x?.audioFile || x?.fileName)
        .sort((a, b) => Number(a.index ?? a.slot ?? 0) - Number(b.index ?? b.slot ?? 0))) {
        const index = Number(ref.index ?? ref.slot ?? 0);
        items.push({ kind: "audio", label: refAudioLabel(index), officialTag: refAudioPromptTag(index), token: refAudioPromptTag(index), thumb: "", name: "" });
    }
    return items;
}

export function mentionItemsFromMedia(media = {}) {
    if (Array.isArray(media.assets)) {
        return media.assets.map((asset) => ({
            kind: asset.kind,
            assetId: asset.assetId,
            label: asset.officialTag,
            officialTag: asset.officialTag,
            token: semanticReferenceToken(asset.kind, asset.assetId),
            thumb: asset.kind === "picture" ? refThumbUrl(asset.item) : "",
            name: asset.label || "",
        }));
    }
    return legacyMentionItems(media.refs, media.audios, media.videos);
}

function positionMenu(menu, editorEl) {
    const rect = editorEl.getBoundingClientRect();
    menu.style.left = `${Math.max(8, rect.left)}px`;
    menu.style.top = `${Math.min(window.innerHeight - 16, rect.bottom + 4)}px`;
    menu.style.maxWidth = `${Math.max(230, rect.width)}px`;
}

function semanticRegex() {
    return new RegExp(SEMANTIC_REFERENCE_RE.source, "gi");
}

function serializeRich(root) {
    const walk = (node) => {
        if (node.nodeType === Node.TEXT_NODE) return node.data;
        if (node.nodeType !== Node.ELEMENT_NODE) return "";
        if (node.classList?.contains("bd-prompt-chip")) return node.dataset.semanticToken || node.textContent || "";
        if (node.tagName === "BR") return "\n";
        let text = "";
        for (const child of node.childNodes) text += walk(child);
        if (node !== root && node.tagName === "DIV" && !text.endsWith("\n")) text += "\n";
        return text;
    };
    return walk(root).replace(/\n$/, "");
}

function caretMentionRange(root) {
    const selection = window.getSelection?.();
    if (!selection?.rangeCount) return null;
    const caret = selection.getRangeAt(0);
    if (!caret.collapsed || !root.contains(caret.startContainer)) return null;
    const node = caret.startContainer;
    if (node.nodeType !== Node.TEXT_NODE) return null;
    const before = node.data.slice(0, caret.startOffset);
    const match = before.match(/@([^\s@]*)$/);
    if (!match) return null;
    const range = document.createRange();
    range.setStart(node, caret.startOffset - match[0].length);
    range.setEnd(node, caret.startOffset);
    return { range, query: match[1] };
}

function previousChipAtCaret(root) {
    const selection = window.getSelection?.();
    if (!selection?.rangeCount) return null;
    const range = selection.getRangeAt(0);
    if (!range.collapsed || !root.contains(range.startContainer)) return null;
    const node = range.startContainer;
    if (node.nodeType === Node.TEXT_NODE && range.startOffset === 0) {
        return node.previousSibling?.classList?.contains("bd-prompt-chip") ? node.previousSibling : null;
    }
    if (node === root && range.startOffset > 0) {
        const prev = root.childNodes[range.startOffset - 1];
        return prev?.classList?.contains("bd-prompt-chip") ? prev : null;
    }
    return null;
}

/** Replace a textarea with a contenteditable semantic-chip editor. */
export function wirePromptImageMentions(editor, textarea, getMedia) {
    if (!textarea || textarea.dataset.mentionWired) return;
    textarea.dataset.mentionWired = "1";
    injectStyles();

    const rich = document.createElement("div");
    rich.className = "bd-prompt-editor";
    rich.contentEditable = "true";
    rich.setAttribute("role", "textbox");
    rich.setAttribute("aria-multiline", "true");
    rich.dataset.promptEditor = "1";
    textarea.insertAdjacentElement("afterend", rich);
    textarea.style.display = "none";

    let menu = null;
    let mentionRange = null;
    let activeIndex = 0;
    let filtered = [];

    const mediaItems = () => mentionItemsFromMedia(typeof getMedia === "function" ? (getMedia() || {}) : {});
    const mapping = () => new Map(mediaItems().map((item) => [item.token, item]));

    const makeChip = (token, item = null) => {
        const chip = document.createElement("span");
        const parsed = token.match(/^\{\{mmx-ref:(picture|video|audio):([^}]+)\}\}$/i);
        const kind = item?.kind || parsed?.[1]?.toLowerCase() || "picture";
        chip.className = `bd-prompt-chip bd-prompt-chip-${kind}`;
        chip.contentEditable = "false";
        chip.dataset.semanticToken = token;
        chip.dataset.missing = item ? "0" : "1";
        chip.textContent = item?.officialTag || item?.label || `<${kind} disabled>`;
        chip.title = item?.name || (item ? item.officialTag : t("mention.disabledAsset"));
        return chip;
    };

    const renderRich = () => {
        const items = mapping();
        const fragment = document.createDocumentFragment();
        const text = String(textarea.value || "");
        const re = semanticRegex();
        let cursor = 0;
        let match;
        while ((match = re.exec(text))) {
            if (match.index > cursor) fragment.appendChild(document.createTextNode(text.slice(cursor, match.index)));
            fragment.appendChild(makeChip(match[0], items.get(match[0])));
            cursor = match.index + match[0].length;
        }
        if (cursor < text.length) fragment.appendChild(document.createTextNode(text.slice(cursor)));
        rich.replaceChildren(fragment);
    };

    // Bind pasted/typed official tags to the asset that currently owns the tag.
    const hydrateOfficialTags = () => {
        let value = String(textarea.value || "");
        for (const item of mediaItems()) {
            if (!item.assetId || !item.officialTag) continue;
            value = value.split(item.officialTag).join(item.token);
        }
        textarea.value = value;
    };
    hydrateOfficialTags();
    renderRich();

    const syncTextarea = () => {
        textarea.value = serializeRich(rich);
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
    };

    const ensureMenu = () => {
        if (menu) return menu;
        menu = document.createElement("div");
        menu.className = "bd-mention-menu hidden";
        menu.setAttribute("role", "listbox");
        menu.addEventListener("mousedown", (event) => event.preventDefault());
        document.body.appendChild(menu);
        return menu;
    };

    const closeMenu = () => {
        mentionRange = null;
        filtered = [];
        activeIndex = 0;
        menu?.classList.add("hidden");
    };

    const updateActiveRow = () => {
        const rows = [...(menu?.querySelectorAll(".bd-mention-item") || [])];
        rows.forEach((row, index) => row.classList.toggle("active", index === activeIndex));
        rows[activeIndex]?.scrollIntoView?.({ block: "nearest" });
    };

    const insertMention = (item) => {
        if (!mentionRange) return;
        mentionRange.deleteContents();
        const chip = makeChip(item.token, item);
        const space = document.createTextNode(" ");
        mentionRange.insertNode(space);
        mentionRange.insertNode(chip);
        const selection = window.getSelection();
        const caret = document.createRange();
        caret.setStartAfter(space);
        caret.collapse(true);
        selection.removeAllRanges();
        selection.addRange(caret);
        closeMenu();
        syncTextarea();
        rich.focus();
    };

    const renderMenu = (query) => {
        const m = ensureMenu();
        const all = mediaItems();
        const q = String(query || "").toLowerCase();
        filtered = all.filter((item) => !q || `${item.label} ${item.name}`.toLowerCase().includes(q));
        activeIndex = Math.min(activeIndex, Math.max(0, filtered.length - 1));
        m.replaceChildren();
        const title = document.createElement("div");
        title.className = "bd-mention-title";
        title.textContent = t("mention.title");
        m.appendChild(title);
        if (!filtered.length) {
            const empty = document.createElement("div");
            empty.className = "bd-mention-empty";
            empty.textContent = all.length ? t("mention.emptyFilter") : t("mention.emptyNoUpload");
            m.appendChild(empty);
        }
        filtered.forEach((item, index) => {
            const row = document.createElement("div");
            row.className = `bd-mention-item${index === activeIndex ? " active" : ""}`;
            if (item.thumb) {
                const img = document.createElement("img");
                img.src = item.thumb;
                img.alt = item.label;
                row.appendChild(img);
            }
            const tag = document.createElement("span");
            tag.className = "bd-mention-label";
            tag.textContent = item.label;
            row.appendChild(tag);
            if (item.name) {
                const name = document.createElement("span");
                name.className = "bd-mention-name";
                name.textContent = item.name;
                row.appendChild(name);
            }
            row.onmousedown = (event) => {
                event.preventDefault();
                insertMention(item);
            };
            m.appendChild(row);
        });
        positionMenu(m, rich);
        m.classList.remove("hidden");
    };

    const openIfMention = () => {
        const found = caretMentionRange(rich);
        if (!found) {
            closeMenu();
            return;
        }
        mentionRange = found.range;
        activeIndex = 0;
        renderMenu(found.query);
    };

    rich.addEventListener("input", () => {
        syncTextarea();
        openIfMention();
    });
    rich.addEventListener("click", openIfMention);
    rich.addEventListener("keydown", (event) => {
        if (isPromptEditingKey(event.key)) {
            // Never bubble to Director's segment/group delete shortcuts.
            event.stopPropagation();
            if (event.key === "Backspace") {
                const chip = previousChipAtCaret(rich);
                if (chip) {
                    event.preventDefault();
                    chip.remove();
                    syncTextarea();
                    return;
                }
            }
        }
        if (!menu || menu.classList.contains("hidden") || !filtered.length) return;
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            activeIndex = moveMentionActiveIndex(activeIndex, event.key === "ArrowDown" ? 1 : -1, filtered.length);
            updateActiveRow();
        } else if (event.key === "Enter" || event.key === "Tab") {
            event.preventDefault();
            insertMention(filtered[activeIndex]);
        } else if (event.key === "Escape") {
            event.preventDefault();
            closeMenu();
        }
    });

    document.addEventListener("mousedown", (event) => {
        if (!menu || menu.classList.contains("hidden")) return;
        if (event.target === rich || rich.contains(event.target) || menu.contains(event.target)) return;
        closeMenu();
    });
    window.addEventListener("scroll", (event) => {
        if (shouldCloseMentionForScroll(menu, event.target)) closeMenu();
    }, true);
    window.addEventListener("resize", closeMenu);
}

/** Legacy/global editors keep direct official-tag behavior outside R2V Common cards. */
export function mountPromptImageMentions(editor) {
    if (!editor) return;
    wirePromptImageMentions(editor, editor.globalPrompt, () => ({
        refs: editor.timeline?.global?.refs || [],
        audios: editor.timeline?.global?.refAudios || [],
        videos: editor.timeline?.global?.refVideos || [],
    }));
    wirePromptImageMentions(editor, editor.segPrompt, () => {
        const seg = editor.timeline?.segments?.[editor.selectedIndex];
        return { refs: seg?.refs || [], audios: seg?.refAudios || [], videos: seg?.refVideos || [] };
    });
}
