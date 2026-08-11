/** Stable R2V asset identity and per-segment official tag compilation. */

export const SEMANTIC_REFERENCE_RE = /\{\{mmx-ref:(picture|video|audio):([A-Za-z0-9_.:-]+)\}\}/gi;

function defaultIdFactory(kind = "asset") {
    if (globalThis.crypto?.randomUUID) return `${kind}-${globalThis.crypto.randomUUID()}`;
    return `${kind}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function semanticReferenceToken(kind, assetId) {
    const normalized = String(kind || "").trim().toLowerCase();
    const identity = String(assetId || "").trim();
    if (!["picture", "video", "audio"].includes(normalized)) {
        throw new Error("Reference kind must be picture, video, or audio");
    }
    if (!identity || !/^[A-Za-z0-9_.:-]+$/.test(identity)) {
        throw new Error("Reference asset ID is empty or unsafe");
    }
    return `{{mmx-ref:${normalized}:${identity}}}`;
}

function arraysFor(container) {
    if (!container || typeof container !== "object") return [];
    container.refs = Array.isArray(container.refs) ? container.refs : [];
    container.refVideos = Array.isArray(container.refVideos)
        ? container.refVideos : (Array.isArray(container.ref_videos) ? container.ref_videos : []);
    container.refAudios = Array.isArray(container.refAudios)
        ? container.refAudios : (Array.isArray(container.ref_audios) ? container.ref_audios : []);
    return [
        ["picture", container.refs],
        ["video", container.refVideos],
        ["audio", container.refAudios],
    ];
}

function hasMedia(kind, item) {
    if (!item) return false;
    if (kind === "picture") return !!(item.imageFile || item.imageB64);
    if (kind === "video") return !!(
        item.videoFile || item.fileName || item.previewImageFile || item.previewImageUrl || item.linked
    );
    return !!(item.audioFile || item.fileName);
}

function ensureIds(container, scope, idFactory, used) {
    for (const [kind, items] of arraysFor(container)) {
        for (const item of items) {
            if (!item || typeof item !== "object") continue;
            let assetId = String(item.assetId || item.asset_id || "").trim();
            if (!assetId || used.has(assetId)) {
                do {
                    assetId = String(idFactory(`${scope}-${kind}`));
                } while (!assetId || used.has(assetId));
            }
            item.assetId = assetId;
            delete item.asset_id;
            used.add(assetId);
        }
    }
}

export function commonAssetIds(globalBlock) {
    const ids = [];
    for (const [kind, items] of arraysFor(globalBlock)) {
        for (const item of items) {
            if (hasMedia(kind, item) && item.assetId) ids.push(String(item.assetId));
        }
    }
    return ids;
}

export function ensureReferenceAssetSchema(timeline, idFactory = defaultIdFactory) {
    const data = timeline || {};
    data.global = data.global || {};
    data.segments = Array.isArray(data.segments) ? data.segments : [];
    const used = new Set();
    ensureIds(data.global, "common", idFactory, used);
    const allCommon = commonAssetIds(data.global);
    for (let index = 0; index < data.segments.length; index += 1) {
        const segment = data.segments[index] || (data.segments[index] = {});
        ensureIds(segment, `segment-${segment.id || index}`, idFactory, used);
        if (!Array.isArray(segment.commonAssetIds)) {
            segment.commonAssetIds = [...allCommon];
        } else {
            segment.commonAssetIds = segment.commonAssetIds.map(String);
        }
        if (segment.useCommonPrompt == null) segment.useCommonPrompt = true;
        else segment.useCommonPrompt = !!segment.useCommonPrompt;
    }
    return data;
}

function assetDescriptor(kind, item, source) {
    const assetId = String(item.assetId || "");
    const path = kind === "picture"
        ? (item.imageFile || "")
        : kind === "video"
            ? (item.videoFile || item.fileName || item.previewImageFile || "")
            : (item.audioFile || item.fileName || "");
    return {
        kind,
        assetId,
        source,
        item,
        label: String(item.name || item.label || path.split(/[\\/]/).pop() || assetId),
        officialTag: "",
        paired: false,
    };
}

export function allKnownReferenceAssets(globalBlock, segment = null) {
    const out = [];
    for (const [kind, items] of arraysFor(globalBlock)) {
        for (const item of items) if (hasMedia(kind, item)) out.push(assetDescriptor(kind, item, "common"));
    }
    if (segment) {
        for (const [kind, items] of arraysFor(segment)) {
            for (const item of items) if (hasMedia(kind, item)) out.push(assetDescriptor(kind, item, "local"));
        }
    }
    return out;
}

export function effectiveReferenceAssets(globalBlock, segment) {
    const selected = new Set((segment?.commonAssetIds || []).map(String));
    const common = allKnownReferenceAssets(globalBlock).filter((x) => selected.has(x.assetId));
    const local = allKnownReferenceAssets({}, segment);
    const pictures = [...common, ...local].filter((x) => x.kind === "picture");
    const videos = [...common, ...local].filter((x) => x.kind === "video");
    const standaloneAudios = [...common, ...local].filter((x) => x.kind === "audio");

    pictures.forEach((item, index) => { item.officialTag = `<Picture ${index + 1}>`; });
    videos.forEach((item, index) => { item.officialTag = `<Video ${index + 1}>`; });

    const pairedAudios = videos
        .filter((asset) => !!(asset.item.pairedAudioFile || asset.item.paired_audio_file))
        .map((asset) => ({
            ...asset,
            kind: "audio",
            paired: true,
            label: `${asset.label} soundtrack`,
            officialTag: "",
        }));
    const audios = [...pairedAudios, ...standaloneAudios];
    audios.forEach((item, index) => { item.officialTag = `<Audio ${index + 1}>`; });
    return [...pictures, ...videos, ...audios];
}

export function compileSemanticPrompt(prompt, effectiveAssets, options = {}) {
    const mapping = new Map(
        (effectiveAssets || []).map((asset) => [
            `${asset.kind}:${asset.assetId}`,
            asset.officialTag,
        ]),
    );
    const known = new Map(
        (options.knownAssets || []).map((asset) => [
            `${asset.kind}:${asset.assetId}`,
            asset,
        ]),
    );
    const segmentLabel = options.segmentLabel || "Segment";
    return String(prompt || "").replace(SEMANTIC_REFERENCE_RE, (_whole, rawKind, assetId) => {
        const kind = String(rawKind).toLowerCase();
        const key = `${kind}:${assetId}`;
        if (mapping.has(key)) return mapping.get(key);
        const asset = known.get(key);
        const pretty = kind[0].toUpperCase() + kind.slice(1);
        if (asset) {
            throw new Error(
                `${segmentLabel} prompt references ${pretty} "${asset.label || assetId}", `
                + "but that asset is disabled for this segment.",
            );
        }
        throw new Error(`${segmentLabel} prompt references unknown ${pretty} asset "${assetId}".`);
    });
}
