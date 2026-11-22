// Non-destructive guard: run from the official external project before building.
import { realpathSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const official = realpathSync(resolve(dirname(fileURLToPath(import.meta.url)), '..'));
const actual = realpathSync(process.cwd());
if (actual.toLowerCase() !== official.toLowerCase()) {
  console.error(`Projeto incorreto: ${actual}. Use ${official}`);
  process.exitCode = 1;
} else {
  console.log(`Projeto externo confirmado: ${official}`);
}
