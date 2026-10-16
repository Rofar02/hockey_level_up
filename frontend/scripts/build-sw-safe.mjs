// Compiles src/sw-safe.ts (the emergency service worker, see that file) to
// dist/sw-safe.js. Runs after `vite build` (package.json "build"); the file
// has no imports, so a plain TypeScript transpile is all it needs.
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const source = readFileSync(join(root, 'src', 'sw-safe.ts'), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, removeComments: false },
})
const outDir = join(root, 'dist')
if (!existsSync(outDir)) {
  throw new Error('dist/ is missing -- run vite build first')
}
// A classic worker script: no `export {}` the transpile may add.
writeFileSync(join(outDir, 'sw-safe.js'), outputText.replace(/^export \{\};?\s*$/m, ''))
console.log('dist/sw-safe.js written')
