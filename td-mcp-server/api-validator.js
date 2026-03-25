/**
 * api-validator.js — Loads td_python_api.json and provides
 * class lookup, inheritance resolution, and basic script validation.
 */

import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

let apiDB = null;

/**
 * Load the API database from disk (lazy-loaded on first call).
 */
function getDB() {
  if (apiDB) return apiDB;
  const dbPath =
    process.env.TD_API_DB || resolve(__dirname, "..", "td_python_api.json");
  const raw = readFileSync(dbPath, "utf-8");
  apiDB = JSON.parse(raw);
  return apiDB;
}

/**
 * Get info for a specific class, with inheritance resolved.
 * Returns { members, methods } including all inherited ones.
 */
export function resolveClassAPI(className) {
  const db = getDB();
  const cls = db.classes?.[className];
  if (!cls) return null;

  const members = { ...cls.members };
  const methods = { ...cls.methods };

  // Walk the inheritance chain
  for (const parent of cls.inherits || []) {
    const parentCls = db.classes?.[parent];
    if (parentCls) {
      Object.assign(members, parentCls.members || {});
      Object.assign(methods, parentCls.methods || {});
      // Recursively resolve parent's parents
      const resolved = resolveClassAPI(parent);
      if (resolved) {
        Object.assign(members, resolved.members);
        Object.assign(methods, resolved.methods);
      }
    }
  }

  return {
    url: cls.url,
    description: cls.description,
    inherits: cls.inherits,
    members,
    methods,
  };
}

/**
 * Get class info without inheritance resolution.
 */
export function getClassInfo(className) {
  const db = getDB();
  return db.classes?.[className] || null;
}

/**
 * List all class names in the database.
 */
export function listClasses() {
  const db = getDB();
  return Object.keys(db.classes || {});
}

/**
 * Get the td module globals (me, op, run, etc.).
 */
export function getTDModule() {
  const db = getDB();
  return db.td_module || null;
}

/**
 * Get a specific utility module (TDFunctions, TDJSON, etc.).
 */
export function getUtilityModule(name) {
  const db = getDB();
  return db.utility_modules?.[name] || null;
}

/**
 * Get the list of standard Python imports (no import needed).
 */
export function getStandardImports() {
  const db = getDB();
  return db.standard_imports || [];
}

/**
 * Get the full database metadata.
 */
export function getMetadata() {
  const db = getDB();
  return db.metadata || {};
}

/**
 * Basic script validation: check for common issues.
 * Returns { valid: boolean, warnings: string[] }
 */
export function validateScript(code) {
  const warnings = [];
  const db = getDB();
  const stdImports = db.standard_imports || [];

  // Check for unnecessary imports of auto-imported modules
  for (const mod of stdImports) {
    const importPattern = new RegExp(
      `^\\s*import\\s+${mod}\\b|^\\s*from\\s+${mod}\\s+import`,
      "m"
    );
    if (importPattern.test(code)) {
      warnings.push(
        `Unnecessary import: '${mod}' is auto-imported in TouchDesigner.`
      );
    }
  }

  // Check for import td (also auto-imported)
  if (/^\s*import\s+td\b/m.test(code)) {
    warnings.push("Unnecessary import: 'td' module is auto-imported.");
  }

  return {
    valid: warnings.length === 0,
    warnings,
  };
}
