// @vitest-environment node
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

function productionFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name)
    if (name === 'test' || name.endsWith('.test.ts') || name.endsWith('.test.tsx')) return []
    return statSync(path).isDirectory() ? productionFiles(path) : [path]
  })
}

describe('production trust boundary', () => {
  it('does not reference prohibited challenge sources', () => {
    const sourceRoot = dirname(fileURLToPath(import.meta.url))
    const forbidden = [
      ['ground', 'truth'].join('_'),
      ['answer', 'key'].join('_'),
      ['planted', 'ground', 'truth'].join('_'),
      ['raw', 'corpus'].join(' '),
    ]
    const source = productionFiles(sourceRoot).map((path) => readFileSync(path, 'utf8')).join('\n').toLowerCase()
    forbidden.forEach((term) => expect(source).not.toContain(term))
  })
})
