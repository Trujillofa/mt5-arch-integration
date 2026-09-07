import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "apps", "seven-desk", "src");

export async function resolve(specifier, context, nextResolve) {
  if (!specifier.startsWith("@/")) {
    return nextResolve(specifier, context);
  }
  const rel = specifier.slice(2);
  const candidates = [
    join(SRC, rel),
    join(SRC, `${rel}.ts`),
    join(SRC, `${rel}.tsx`),
    join(SRC, rel, "index.ts"),
  ];
  for (const file of candidates) {
    if (existsSync(file)) {
      return { url: pathToFileURL(file).href, shortCircuit: true };
    }
  }
  return nextResolve(specifier, context);
}
