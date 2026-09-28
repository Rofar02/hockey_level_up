// Every `ti-*` icon name the app references must exist in the vendored
// Tabler CSS -- a missing one renders as nothing at all, silently (found
// 2026-09-28: ti-star-filled / ti-circle-check-filled were blank in prod;
// ti-player-play-filled the same way back in August). Run after touching
// icons or updating src/assets/tabler-icons: `npm run check:icons`.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const css = readFileSync('src/assets/tabler-icons/tabler-icons.min.css', 'utf8')
const available = new Set([...css.matchAll(/\.(ti-[a-z0-9-]+):before/g)].map((match) => match[1]))

function* sourceFiles(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) {
      if (name !== 'assets') yield* sourceFiles(path)
    } else if (/\.(tsx?|jsx?)$/.test(name)) {
      yield path
    }
  }
}

// Only names inside string/template literals or class lists (preceded by a
// quote, backtick or space) -- skips prose like "`.ti-kettlebell` does NOT
// exist" in comments, which is preceded by a dot.
const reference = /(?<=['"` ])ti-[a-z0-9]+(?:-[a-z0-9]+)*/g
const missing = []
for (const file of sourceFiles('src')) {
  readFileSync(file, 'utf8')
    .split('\n')
    .forEach((line, index) => {
      if (/^\s*(\/\/|\*)/.test(line)) return
      for (const [name] of line.matchAll(reference)) {
        if (!available.has(name)) missing.push(`${file}:${index + 1}  ${name}`)
      }
    })
}

if (missing.length > 0) {
  console.error(`Icons missing from the vendored Tabler font (${available.size} available):`)
  for (const entry of missing) console.error(`  ${entry}`)
  process.exit(1)
}
console.log(`All referenced icons exist (${available.size} available).`)
