import { promises as fs } from "node:fs";
import path from "node:path";

export interface DiscoverOptions {
  /** Project root to search from. */
  cwd: string;
  /** Directories (relative to cwd) to search. Defaults to common e2e dirs. */
  roots?: string[];
  /** Filename matcher for spec files. */
  pattern?: RegExp;
  /** Path matcher for directories/files to skip. */
  ignore?: RegExp;
}

const DEFAULT_PATTERN = /\.(spec|test|e2e)\.[cm]?[jt]sx?$/;
const DEFAULT_IGNORE =
  /(^|\/)(node_modules|dist|build|coverage|\.git|test-results|playwright-report)(\/|$)/;
const DEFAULT_ROOTS = ["e2e", "tests", "test"];

/**
 * Find e2e spec files under the given roots. If none of the default roots
 * exist, falls back to scanning the whole project (still respecting `ignore`).
 * Returns paths relative to `cwd`, sorted.
 */
export async function discoverSpecs(opts: DiscoverOptions): Promise<string[]> {
  const pattern = opts.pattern ?? DEFAULT_PATTERN;
  const ignore = opts.ignore ?? DEFAULT_IGNORE;

  const candidateRoots = (opts.roots ?? DEFAULT_ROOTS).map((r) => path.resolve(opts.cwd, r));
  const searchDirs: string[] = [];
  for (const root of candidateRoots) {
    try {
      if ((await fs.stat(root)).isDirectory()) searchDirs.push(root);
    } catch {
      /* root does not exist — skip */
    }
  }
  if (searchDirs.length === 0) searchDirs.push(path.resolve(opts.cwd));

  const found = new Set<string>();
  for (const dir of searchDirs) await walk(dir, pattern, ignore, found);

  return [...found].map((p) => path.relative(opts.cwd, p)).sort();
}

async function walk(dir: string, pattern: RegExp, ignore: RegExp, out: Set<string>): Promise<void> {
  let entries: import("node:fs").Dirent[];
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (ignore.test(full.replace(/\\/g, "/"))) continue;
    if (entry.isDirectory()) await walk(full, pattern, ignore, out);
    else if (entry.isFile() && pattern.test(entry.name)) out.add(full);
  }
}
