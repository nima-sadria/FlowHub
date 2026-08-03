# FlowHub Frontend Design System

FlowHub's shared visual language is implemented in `frontend/src/globals.css`.
Pages and components must use its `--fh-*` tokens and reusable `fh-*` classes
instead of introducing page-specific copies of common controls.

## Form Controls

Use `.fh-field` with `.fh-label` and one of `.fh-input`, `.fh-select`, or
`.fh-textarea` for standard forms. Compact operational controls may use their
specialized component classes, but they remain subject to the same mobile
typography contract.

| Context | Token | Computed size |
| --- | --- | --- |
| Pointer-accurate desktop | `--fh-control-font-size` | `14px` |
| Narrow or touch-first device | `--fh-control-font-size-mobile` | `16px` |

The mobile token applies globally to editable text inputs, date/time/number
inputs, textareas, selects, and dynamically mounted editors. It is independent
of language direction and color theme, so English LTR, Persian RTL, light, and
dark modes have identical focus behavior.

Checkboxes, radios, ranges, colors, files, image inputs, hidden inputs, and
button inputs retain native sizing because they do not accept typed text and do
not trigger Safari's text-entry focus zoom.

### Mobile Accessibility Rules

- Never render an editable form control below `16px` on a narrow or
  touch-first device. iOS Safari zooms controls below this threshold.
- Do not use `maximum-scale=1` or `user-scalable=no`. Manual pinch zoom must
  remain available.
- Use logical properties such as `padding-inline-start` and
  `padding-inline-end` so icons and select indicators work in LTR and RTL.
- Theme variants may change surfaces, borders, and text colors, but must not
  change control typography or focus behavior.

Regression coverage lives in `frontend/e2e/login-screen.spec.ts` and validates
the supported language/theme matrix and the compact control variants used
across the application.
