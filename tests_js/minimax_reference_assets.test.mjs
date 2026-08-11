import test from "node:test";
import assert from "node:assert/strict";

import {
    allKnownReferenceAssets,
    compileSemanticPrompt,
    effectiveReferenceAssets,
    ensureR2vReferenceAssetSchema,
    ensureReferenceAssetSchema,
    referenceAssetStates,
    moveReferenceAssetSlot,
    replaceReferenceAssetAtSlot,
    setCommonAssetEnabled,
    semanticReferenceToken,
} from "../web/js/minimax_reference_assets.mjs";


function fixture() {
    return {
        global: {
            prompt: "COMMON",
        },
        r2vCommon: {
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
            useCommonAssets: true,
            excludedCommonAssetIds: ["B"],
            refs: [{ index: 0, assetId: "D", imageFile: "d.png" }],
            refVideos: [{ index: 0, assetId: "VL", videoFile: "vl.mp4" }],
            refAudios: [{ index: 0, assetId: "AL", audioFile: "al.wav" }],
        }],
    };
}


test("new segment defaults to every existing Common asset independently of Common Prompt", () => {
    const timeline = fixture();
    timeline.segments.push({ id: "s2", refs: [], refVideos: [], refAudios: [] });
    ensureR2vReferenceAssetSchema(timeline, () => "generated");
    assert.equal(timeline.segments[1].useCommonAssets, true);
    assert.deepEqual(timeline.segments[1].excludedCommonAssetIds, []);
    timeline.r2vCommon.refs.push({ index: 3, assetId: "D2", imageFile: "d2.png" });
    assert.deepEqual(
        effectiveReferenceAssets(timeline.r2vCommon, timeline.segments[1])
            .filter((x) => x.kind === "picture").map((x) => x.assetId),
        ["A", "B", "C", "D2"],
    );
    timeline.segments[1].useCommonAssets = false;
    assert.deepEqual(effectiveReferenceAssets(timeline.r2vCommon, timeline.segments[1]), []);
});

test("enabling one Common asset after select-none does not enable the whole pool", () => {
    const segment = { useCommonAssets: false, excludedCommonAssetIds: [] };
    setCommonAssetEnabled(segment, ["A", "B", "C"], "B", true);
    assert.equal(segment.useCommonAssets, true);
    assert.deepEqual(segment.excludedCommonAssetIds.sort(), ["A", "C"]);
});


test("effective references are dense Common-first then Local with paired soundtrack audio order", () => {
    const timeline = fixture();
    ensureReferenceAssetSchema(timeline);
    const assets = effectiveReferenceAssets(timeline.r2vCommon, timeline.segments[0]);

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
    let assets = effectiveReferenceAssets(timeline.r2vCommon, {
        ...timeline.segments[0], excludedCommonAssetIds: [], refs: [], refVideos: [], refAudios: [],
    });
    assert.equal(compileSemanticPrompt(token, assets), "<Picture 3>");
    assets = effectiveReferenceAssets(timeline.r2vCommon, {
        ...timeline.segments[0], excludedCommonAssetIds: ["B"], refs: [], refVideos: [], refAudios: [],
    });
    assert.equal(compileSemanticPrompt(token, assets), "<Picture 2>");
});


test("disabled Common assets are excluded from picker data and prompt preflight fails", () => {
    const timeline = fixture();
    const assets = effectiveReferenceAssets(timeline.r2vCommon, {
        ...timeline.segments[0], excludedCommonAssetIds: ["B", "C", "V", "AU"], refs: [], refVideos: [], refAudios: [],
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
    assert.equal(reopened.r2vCommon.refs[2].assetId, "C");
    assert.equal(reopened.segments[0].refs[0].assetId, "D");
    assert.deepEqual(reopened.segments[0].excludedCommonAssetIds, ["B"]);
});

test("legacy allow-list migrates once to exclusions and Common never copies into Local", () => {
    const timeline = {
        global: { refs: [{ index: 0, assetId: "G", imageFile: "global.png" }] },
        r2vCommon: { refs: [{ index: 0, assetId: "A", imageFile: "a.png" }, { index: 1, assetId: "B", imageFile: "b.png" }] },
        segments: [{ commonAssetIds: ["A"], refs: [] }],
    };
    ensureR2vReferenceAssetSchema(timeline);
    assert.deepEqual(timeline.segments[0].excludedCommonAssetIds, ["B"]);
    assert.equal("commonAssetIds" in timeline.segments[0], false);
    assert.deepEqual(timeline.segments[0].refs, []);
    assert.equal(timeline.global.refs[0].assetId, "G");
});

test("snake-case legacy R2V state migrates into the independent Common container", () => {
    const timeline = {
        global: {
            refs: [{ index: 0, asset_id: "A", imageFile: "a.png" }],
            ref_videos: [{ index: 0, asset_id: "V", videoFile: "v.mp4" }],
            ref_audios: [{ index: 0, asset_id: "AU", audioFile: "a.wav" }],
        },
        segments: [{
            common_asset_ids: ["A", "AU"],
            use_common_prompt: false,
            refs: [],
        }],
    };
    ensureR2vReferenceAssetSchema(timeline);
    assert.deepEqual(timeline.r2vCommon.refs.map((x) => x.assetId), ["A"]);
    assert.deepEqual(timeline.r2vCommon.refVideos.map((x) => x.assetId), ["V"]);
    assert.deepEqual(timeline.r2vCommon.refAudios.map((x) => x.assetId), ["AU"]);
    assert.deepEqual(timeline.segments[0].excludedCommonAssetIds, ["V"]);
    assert.deepEqual(timeline.global.refs, []);
    assert.deepEqual(timeline.global.refVideos, []);
    assert.deepEqual(timeline.global.refAudios, []);
    assert.equal("ref_videos" in timeline.global, false);
    assert.equal("ref_audios" in timeline.global, false);
});

test("snake-case new Common container normalizes without touching global assets", () => {
    const timeline = {
        global: { refs: [{ index: 0, assetId: "G", imageFile: "g.png" }] },
        r2v_common: { refs: [{ index: 0, assetId: "C", imageFile: "c.png" }] },
        segments: [{ use_common_assets: false, excluded_common_asset_ids: ["C"] }],
    };
    ensureR2vReferenceAssetSchema(timeline);
    assert.equal(timeline.r2vCommon.refs[0].assetId, "C");
    assert.equal(timeline.global.refs[0].assetId, "G");
    assert.equal(timeline.segments[0].useCommonAssets, false);
    assert.deepEqual(timeline.segments[0].excludedCommonAssetIds, ["C"]);
    assert.equal("r2v_common" in timeline, false);
});

test("active, disabled and missing semantic assets remain distinct", () => {
    const timeline = fixture();
    ensureR2vReferenceAssetSchema(timeline);
    const states = referenceAssetStates(timeline.r2vCommon, timeline.segments[0]);
    assert.equal(states.find((x) => x.assetId === "A").status, "active");
    assert.equal(states.find((x) => x.assetId === "B").status, "disabled");
    assert.throws(() => compileSemanticPrompt(semanticReferenceToken("picture", "B"), states, {
        knownAssets: states,
        segmentLabel: "Segment 1",
    }), /disabled/i);
    const known = allKnownReferenceAssets(timeline.r2vCommon, timeline.segments[0]);
    assert.throws(() => compileSemanticPrompt(semanticReferenceToken("picture", "MISSING"), states, {
        knownAssets: known,
        segmentLabel: "Segment 1",
    }), /unknown.*MISSING/i);
});

test("replace and move preserve stable asset IDs; delete leaves semantic prompt identity missing", () => {
    const container = {
        refs: [
            { index: 0, assetId: "stable-A", imageFile: "old.png" },
            { index: 1, assetId: "stable-B", imageFile: "b.png" },
        ],
    };
    replaceReferenceAssetAtSlot(container, "refs", 0, { imageFile: "new.png" });
    assert.equal(container.refs.find((x) => x.index === 0).assetId, "stable-A");
    assert.equal(moveReferenceAssetSlot(container, "refs", 0, 1), true);
    assert.equal(container.refs.find((x) => x.index === 1).assetId, "stable-A");
    assert.equal(container.refs.find((x) => x.index === 0).assetId, "stable-B");
    const prompt = semanticReferenceToken("picture", "stable-A");
    container.refs = container.refs.filter((x) => x.assetId !== "stable-A");
    assert.equal(prompt, "{{mmx-ref:picture:stable-A}}");
    assert.throws(() => compileSemanticPrompt(prompt, [], { knownAssets: [] }), /unknown.*stable-A/i);
});
