import test from "node:test";
import assert from "node:assert/strict";

import { setLocale, t } from "../web/js/minimax_i18n.js";

const EXPECTED = {
    zh: {
        "widget.grpMotion": "跨段续接",
        "widget.continuityMultiOnly": "仅多段生成时使用",
        "widget.motionContextEnabled": "Motion Context",
        "widget.contextLength": "上下文帧数",
        "widget.audioContextEnabled": "延续生成音频",
        "widget.visualContinuity": "视觉续接方式",
        "widget.strategy.sourceBridge": "原片桥接",
        "widget.strategy.motionContext": "Motion Context",
        "widget.strategy.off": "关闭",
        "widget.bridgeLength": "桥接长度",
        "widget.bridgeLengthFixed": "5 帧（固定）",
        "widget.tooltip.motionContextEnabled": "使用上一段生成结果延续下一段。适合 T2V、I2V、R2V、FL2V。",
        "widget.tooltip.contextLength": "使用上一段尾部多少帧作为 Motion Context。",
        "widget.tooltip.audioContextEnabled": "延续上一段的模型生成音频。需要 Motion Context；V2V/RV2V 使用原声或静音时不可用。",
        "widget.tooltip.sourceBridgeEnabled": "V2V/RV2V 专用。使用固定5帧 H3 Bridge 改善分段接缝。",
        "widget.tooltip.visualContinuity": "选择 V2V/RV2V 多段视频的视觉续接方式。",
    },
    en: {
        "widget.grpMotion": "Cross-Segment Continuity",
        "widget.continuityMultiOnly": "Available for multi-segment generation only",
        "widget.motionContextEnabled": "Motion Context",
        "widget.contextLength": "Context Frames",
        "widget.audioContextEnabled": "Continue Generated Audio",
        "widget.visualContinuity": "Visual Continuity",
        "widget.strategy.sourceBridge": "Source Bridge",
        "widget.strategy.motionContext": "Motion Context",
        "widget.strategy.off": "Off",
        "widget.bridgeLength": "Bridge Length",
        "widget.bridgeLengthFixed": "5 frames (fixed)",
        "widget.tooltip.motionContextEnabled": "Continue the next segment from the previous generated result. Recommended for T2V, I2V, R2V and FL2V.",
        "widget.tooltip.contextLength": "Number of previous generated frames used as Motion Context.",
        "widget.tooltip.audioContextEnabled": "Continue model-generated audio from the previous segment. Requires Motion Context; unavailable for V2V/RV2V when using source audio or mute.",
        "widget.tooltip.sourceBridgeEnabled": "V2V/RV2V only. Use a fixed five-frame H3 Bridge to improve segment seams.",
        "widget.tooltip.visualContinuity": "Choose the visual continuity method for multi-segment V2V/RV2V video.",
    },
};

test("continuity UI labels are complete in Chinese and English", () => {
    for (const [locale, labels] of Object.entries(EXPECTED)) {
        setLocale(locale);
        for (const [key, expected] of Object.entries(labels)) {
            assert.equal(t(key), expected, `${locale}:${key}`);
        }
    }
});

test("continuity UI labels contain no tree-layout characters", () => {
    const forbidden = /[└├│↳┌┐┘┴┬]/u;
    for (const [locale, labels] of Object.entries(EXPECTED)) {
        setLocale(locale);
        for (const key of Object.keys(labels)) {
            assert.doesNotMatch(t(key), forbidden, `${locale}:${key}`);
        }
    }
});
