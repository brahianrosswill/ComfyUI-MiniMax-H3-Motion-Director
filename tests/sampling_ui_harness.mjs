import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function loadSourceModule(relativePath) {
    const url = new URL(relativePath, import.meta.url);
    const source = await readFile(url, "utf8");
    return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
}

const samplingUi = await loadSourceModule("../web/js/minimax_sampling_ui.js");

function mockWidget(name, value) {
    const computeSize = (width) => [width, 20];
    return {
        name,
        value,
        computeSize,
        options: {},
        element: { style: { display: "grid" } },
        _originalComputeSize: computeSize,
    };
}

const widgets = samplingUi.INTERNAL_SAMPLING_WIDGETS.map((name, index) =>
    mockWidget(name, index + 10),
);
const node = {
    inputs: [
        { name: "sampler", link: null },
        { name: "sigmas", link: null },
    ],
    widgets,
};

assert.equal(samplingUi.applySamplingWidgetVisibility(node), "internal");
assert.ok(widgets.every((widget) => !widget.hidden));

node.inputs[0].link = 0;
node.inputs[1].link = 12;
assert.equal(samplingUi.applySamplingWidgetVisibility(node), "external");
for (const [index, widget] of widgets.entries()) {
    assert.equal(widget.hidden, true);
    assert.deepEqual(widget.computeSize(900), [0, 0]);
    assert.equal(widget.element.style.display, "none");
    assert.equal(widget.value, index + 10, "hiding must not overwrite saved values");
}

node.inputs[0].link = null;
node.inputs[1].link = null;
assert.equal(samplingUi.applySamplingWidgetVisibility(node), "internal");
for (const widget of widgets) {
    assert.equal(widget.computeSize, widget._originalComputeSize);
    assert.equal(widget.element.style.display, "grid");
    assert.equal(widget.options.hidden, undefined);
}

node.inputs[0].link = 3;
assert.equal(samplingUi.applySamplingWidgetVisibility(node), "incomplete");
assert.ok(widgets.every((widget) => !widget.hidden));

const workflow = {
    nodes: [{
        id: 5,
        type: "MiniMaxH3MotionDirector",
        inputs: [
            { name: "model", type: "MODEL", link: 1 },
            { name: "bd_grp_advanced", widget: { name: "bd_grp_advanced" }, link: null },
            { name: "sampling_control", widget: { name: "sampling_control" }, link: null },
            { name: "steps", widget: { name: "steps" }, link: null },
            { name: "sampler", type: "SAMPLER", link: 8 },
        ],
        widgets_values: ["Advanced", "external", 25],
    }],
    links: [[8, 7, 0, 5, 4, "SAMPLER"]],
};
assert.equal(samplingUi.migrateLegacySamplingControlWorkflow(workflow), 1);
assert.deepEqual(workflow.nodes[0].inputs.map((input) => input.name), [
    "model", "bd_grp_advanced", "steps", "sampler",
]);
assert.deepEqual(workflow.nodes[0].widgets_values, ["Advanced", 25]);
assert.equal(workflow.links[0][4], 3);
assert.equal(samplingUi.migrateLegacySamplingControlWorkflow(workflow), 0);

const timelineSource = await readFile(new URL("../web/js/minimax_timeline.js", import.meta.url), "utf8");
assert.ok(!timelineSource.includes("appendChild(liveSample)"), "bottom live preview must not be mounted");
assert.ok(!timelineSource.includes("insertAdjacentElement(\"afterend\", panel)"));
assert.ok(timelineSource.includes("setImageBatchPreview("), "per-card previews must remain");
assert.ok(timelineSource.includes("setRunProgress?.(detail)"), "progress event must remain");
assert.ok(timelineSource.includes("minimax_motion_director_preview"), "shared preview event must remain");
