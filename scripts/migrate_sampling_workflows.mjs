import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const root = resolve(scriptDir, "..");
const helperPath = resolve(root, "web/js/minimax_sampling_ui.js");
const helperSource = await readFile(helperPath, "utf8");
const { migrateLegacySamplingControlWorkflow } = await import(
    `data:text/javascript;base64,${Buffer.from(helperSource).toString("base64")}`
);

const paths = process.argv.slice(2);
if (!paths.length) {
    throw new Error("Pass one or more ComfyUI workflow JSON paths.");
}

for (const inputPath of paths) {
    const path = resolve(inputPath);
    const workflow = JSON.parse(await readFile(path, "utf8"));
    const changed = migrateLegacySamplingControlWorkflow(workflow);
    if (changed) {
        await writeFile(path, `${JSON.stringify(workflow, null, 2)}\n`, "utf8");
    }
    console.log(`${pathToFileURL(path).pathname}: migrated ${changed} Director node(s)`);
}
