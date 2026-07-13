import { describe, expect, it } from 'vitest'
const forbidden = new RegExp([
  [0x00e2, 0x20ac], [0x00e2, 0x2014], [0x00e2, 0x2013],
  [0x00c2], [0x00d8], [0x00d9], [0x0622, 0x00b7], [0x0622, 0x20ac],
].map(sequence => String.fromCodePoint(...sequence)).join('|'), 'u')

const sources = import.meta.glob('./**/*.{ts,tsx,css,html}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

describe('frontend source encoding', () => {
  it('contains no known mojibake sequences', () => {
    const matches = Object.entries(sources).flatMap(([file, content]) => forbidden.test(content) ? [file] : [])
    expect(matches).toEqual([])
  })
})
