/**
 * td-bridge.js — HTTP client bridging to TouchDesigner's WebServer DAT.
 *
 * All communication with TD goes through this module.
 * The WebServer DAT listens on TD_HOST:TD_PORT (default localhost:9980).
 */

const TD_HOST = process.env.TD_HOST || "localhost";
const TD_PORT = process.env.TD_PORT || "9980";
const BASE_URL = `http://${TD_HOST}:${TD_PORT}`;

/**
 * POST a script to TD for execution.
 * @param {string} script - Python script to execute
 * @param {string} [undoLabel] - Optional undo block label
 * @returns {{ output: string, errors: string[] }}
 */
export async function executeScript(script, undoLabel = "MCP Script") {
  const payload = JSON.stringify({ script, undo_label: undoLabel });
  const resp = await fetch(`${BASE_URL}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
  });
  if (!resp.ok) {
    throw new Error(`TD returned ${resp.status}: ${await resp.text()}`);
  }
  return resp.json();
}

/**
 * GET the current Error DAT table from TD.
 * @returns {{ errors: Array<{type: string, absFrame: string, text: string}> }}
 */
export async function getErrors() {
  const resp = await fetch(`${BASE_URL}/errors`);
  if (!resp.ok) {
    throw new Error(`TD returned ${resp.status}: ${await resp.text()}`);
  }
  return resp.json();
}

/**
 * GET operator info from TD.
 * @param {string} path - Operator path (e.g. "/project1/base1")
 * @returns {{ name, type, pars, inputs, outputs, children }}
 */
export async function getOperatorInfo(path) {
  const resp = await fetch(
    `${BASE_URL}/operator?path=${encodeURIComponent(path)}`
  );
  if (!resp.ok) {
    throw new Error(`TD returned ${resp.status}: ${await resp.text()}`);
  }
  return resp.json();
}

/**
 * GET image stats from row/column average CHOPs.
 * @param {string} rowsChop - Path to the rows CHOP (e.g. "/project1/analyze_rows")
 * @param {string} colsChop - Path to the cols CHOP (e.g. "/project1/analyze_cols")
 * @returns {{ rows, cols, overall }} — per-sample arrays + aggregate stats per channel
 */
export async function getImageStats(rowsChop, colsChop) {
  const url = `${BASE_URL}/image_stats?rows_chop=${encodeURIComponent(rowsChop)}&cols_chop=${encodeURIComponent(colsChop)}`;
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`TD returned ${resp.status}: ${await resp.text()}`);
  }
  return resp.json();
}

/**
 * GET a screenshot of a TOP operator.
 * @param {string} opPath - Operator path (e.g. "/project1/out1")
 * @param {string} [saveDir] - Directory to save the PNG on the TD machine
 * @returns {{ path, saved_to, image_b64, mime_type }}
 */
export async function takeScreenshot(opPath, saveDir) {
  let url = `${BASE_URL}/screenshot?path=${encodeURIComponent(opPath)}`;
  if (saveDir) url += `&save_dir=${encodeURIComponent(saveDir)}`;
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`TD returned ${resp.status}: ${await resp.text()}`);
  }
  return resp.json();
}

/**
 * Health-check: is TD's WebServer DAT reachable?
 * @returns {boolean}
 */
export async function isConnected() {
  try {
    const resp = await fetch(`${BASE_URL}/health`, { signal: AbortSignal.timeout(2000) });
    return resp.ok;
  } catch {
    return false;
  }
}
