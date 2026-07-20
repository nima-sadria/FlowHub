import { describe, expect, it } from 'vitest'

const primaryPages = [
  'Dashboard.tsx',
  'Products.tsx',
  'CommerceHub.tsx',
  'Workspace.tsx',
  'Activity.tsx',
  'DataQuality.tsx',
  'Diagnostics.tsx',
  'RateLimits.tsx',
  'Settings.tsx',
]

const pageSources = import.meta.glob('./*.tsx', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as Record<string, string>

describe('primary page layout rule', () => {
  it('keeps every primary page on the shared PageShell container', () => {
    for (const filename of primaryPages) {
      const source = pageSources[`./${filename}`]
      expect(source, filename).toBeTypeOf('string')
      expect(source, filename).toContain("PageShell")
      expect(source, filename).not.toMatch(/className=["'`][^"'`]*fh-page\s+max-w-/)
    }
  })
})
