import test from "node:test";
import assert from "node:assert/strict";

import {
    compileSemanticPrompt,
    effectiveReferenceAssets,
    ensureReferenceAssetSchema,
    semanticReferenceToken,
} from "../web/js/minimax_reference_assets.mjs";


function fixture() {
    return {
        global: {
            prompt: "COMMON",
            refs: [
                { index: 0, assetId: "A", imageFile: "a.png" },
                { index: 1, assetId: "B", imageFile: "b.png" },
                { index: 2, assetId: "C", imageFile: "c.png" },
            ],
            refVideos: [
                { index: 0, assetId: "V", videoFile: "v.mp4", pairedAudioFile: "v.wav" },
            ],
            refAudios: [{ index: 0, assetId: "AU", audioFile: "a.wav" }],
        },
        segments: [{
            id: "s1",
            commonAssetIds: ["A", "C", "V", "AU"],
            useCommonPrompt: true,
            refs: [{ index: 0, assetId: "D", imageFile: "d.png" }],
            refVideos: [{ index: 0, assetId: "VL", videoFile: "vl.mp4" }],
            refAudios: [{ index: 0, assetId: "AL", audioFile: "al.wav" }],
        }],
    };
}


test("new segment defaults to every existing Common asset independently of Common Prompt", () => {
    const timeline = fixture();
    timeline.segments.push({ id: "s2", refs: [], refVideos: [], refAudios: [] });
    ensureReferenceAssetSchema(timeline, () => "generated");
    assert.deepEqual(timeline.segments[1].commonAssetIds, ["A", "B", "C", "V", "AU"]);
    assert.equal(timeline.segments[1].useCommonPrompt, true);
    timeline.segments[1].commonAssetIds = [];
    assert.equal(timeline.segments[1].useCommonPrompt, true);
    timeline.segments[1].useCommonPrompt = false;
    assert.deepEqual(timeline.segments[0].commonAssetIds, ["A", "C", "V", "AU"]);
});


test("effective references are dense Common-first then Local with paired soundtrack audio order", () => {
    const timeline = fixture();
    ensureReferenceAssetSchema(timeline);
    const assets = effectiveReferenceAssets(timeline.global, timeline.segments[0]);

    assert.deepEqual(
        assets.filter((x) => x.kind === "picture").map((x) => [x.assetId, x.officialTag]),
        [["A", "<Picture 1>"], ["C", "<Picture 2>"], ["D", "<Picture 3>"]],
    );
    assert.deepEqual(
        assets.filter((x) => x.kind === "video").map((x) => [x.assetId, x.officialTag]),
        [["V", "<Video 1>"], ["VL", "<Video 2>"]],
    );
    assert.deepEqual(
        assets.filter((x) => x.kind === "audio").map((x) => [x.assetId, x.officialTag, x.paired]),
        [["V", "<Audio 1>", true], ["AU", "<Audio 2>", false], ["AL", "<Audio 3>", false]],
    );
});


test("semantic asset identity survives Common subset renumbering", () => {
    const timeline = fixture();
    const token = semanticReferenceToken("picture", "C");
    let assets = effectiveReferenceAssets(timeline.global, {
        ...timeline.segments[0], commonAssetIds: ["A", "B", "C"], refs: [], refVideos: [], refAudios: [],
    });
    assert.equal(compileSemanticPrompt(token, assets), "<Picture 3>");
    assets = effectiveReferenceAssets(timeline.global, {
        ...timeline.segments[0], commonAssetIds: ["A", "C"], refs: [], refVideos: [], refAudios: [],
    });
    assert.equal(compileSemanticPrompt(token, assets), "<Picture 2>");
});


test("disabled Common assets are excluded from picker data and prompt preflight fails", () => {
    const timeline = fixture();
    const assets = effectiveReferenceAssets(timeline.global, {
        ...timeline.segments[0], commonAssetIds: ["A"], refs: [], refVideos: [], refAudios: [],
    });
    assert.deepEqual(assets.map((x) => x.assetId), ["A"]);
    assert.throws(
        () => compileSemanticPrompt(semanticReferenceToken("picture", "B"), assets, {
            knownAssets: [{ kind: "picture", assetId: "B", label: "B" }],
            segmentLabel: "Segment 2",
        }),
        /Segment 2.*B.*disabled/,
    );
});


test("asset IDs persist through JSON workflow save and reopen", () => {
    const timeline = fixture();
    const reopened = JSON.parse(JSON.stringify(timeline));
    ensureReferenceAssetSchema(reopened);
    assert.equal(reopened.global.refs[2].assetId, "C");
    assert.equal(reopened.segments[0].refs[0].assetId, "D");
    assert.deepEqual(reopened.segments[0].commonAssetIds, ["A", "C", "V", "AU"]);
});
