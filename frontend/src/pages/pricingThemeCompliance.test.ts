import { describe, expect, it } from 'vitest'

const PRICING_FILES = [
  'PricingMatrix.tsx',
  'PricingPolicyEditor.tsx',
  'PricingProductGroupEditor.tsx',
  'PricingUnitEditor.tsx',
]

const pageSources = import.meta.glob('./*.tsx', {
  eager: true,
  import: 'default',
  query: '?raw',
}) as Record<string, string>

const HARDCODED_COLOR_PATTERN = /#[0-9a-fA-F]{3,8}\b|rgba?\(|style=\{\{[^}]*color/

describe('Pricing pages theme compliance (UI Stage 5)', () => {
  it('use only design-system tokens — no hardcoded hex/rgb colors or inline color styles', () => {
    for (const filename of PRICING_FILES) {
      const source = pageSources[`./${filename}`]
      expect(source, filename).toBeTypeOf('string')
      expect(HARDCODED_COLOR_PATTERN.test(source), `${filename} contains a hardcoded color`).toBe(false)
    }
  })
})
