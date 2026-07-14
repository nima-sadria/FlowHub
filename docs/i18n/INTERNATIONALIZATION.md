# FlowHub internationalization

FlowHub uses `i18next` and `react-i18next` for its React translation layer. English (`en`) is the application default and fallback language. The gettext template at `locales/flowhub.pot` is the canonical translator input; generated JSON files under `frontend/src/i18n/locales` are runtime artifacts.

## Architecture

- Application code uses stable, feature-oriented keys such as `workspace:sourceCentricWorkspace.applyResults`.
- Runtime resources are split into 17 namespaces: `common`, `navigation`, `authentication`, `dashboard`, `products`, `orders`, `sources`, `commerce`, `workspace`, `flowhubSheet`, `dataQuality`, `activity`, `diagnostics`, `settings`, `validation`, `errors`, and `notifications`.
- `frontend/src/i18n/index.ts` owns initialization, English fallback, persistence, catalog completeness, and `document.documentElement.lang`/`dir`.
- `frontend/src/i18n/format.ts` owns locale-sensitive number, percent, date, time, relative-time, and price presentation. It does not change price units or currency-domain values.
- `frontend/src/i18n/errors.ts` maps stable API error codes to translated messages. Backend prose remains a diagnostic fallback for legacy responses.
- `frontend/src/i18n/display.ts` localizes common status and field labels without changing technical identifiers.
- Persian is declared as the future RTL locale but is disabled until its PO catalog is complete. `VITE_ENABLE_PSEUDO_RTL=true` is allowed only for automated non-production visual tests.

Language resolution is:

1. persisted user preference (`flowhub.locale`);
2. application default;
3. English fallback.

The Settings language selector applies a complete catalog immediately and updates the document language, direction, and locale formatters without logout.

## Key policy

Keys are stable semantic identifiers grouped by namespace and feature. Do not use English sentences, numbered keys, or presentation position as keys. Use interpolation and plural entries instead of concatenating translated fragments.

```ts
translate('workspace:workspace.productReadyForReview', { count })
translate('workspace:sourceCentricWorkspace.selectListing', { channel, listing })
```

Product names, user-entered text, spreadsheet values, SKU values, external IDs, Channel technical IDs, API paths, audit payloads, and log payloads remain unchanged.

## Commands

Run from `frontend/`:

```text
npm run i18n:extract
npm run i18n:validate
npm run i18n:compile
```

- `i18n:extract` deterministically rebuilds `locales/flowhub.pot` and the complete English `locales/en/flowhub.po`, including source references, plural forms, placeholders, contexts, and FlowHub terminology comments.
- `i18n:validate` parses the POT, checks source keys and placeholders, and fails on unapproved hardcoded JSX, labels, placeholders, tooltips, accessibility text, notification text, dialogs, and rendered constants.
- `i18n:compile` converts every `locales/<locale>/flowhub.po` into namespaced runtime JSON and a completion manifest. An incomplete locale remains unavailable in Settings while individual missing messages still safely fall back to English.

The hardcoded-string exception is deliberately narrow. A technical or immutable diagnostic literal may use `i18n-ignore` only with an inline reason. Tests, fixtures, API constants, technical IDs, and developer diagnostics are excluded from source extraction. User-facing copy must never use this exception.

## Direction and layout

RTL is applied with `lang="fa"` and `dir="rtl"` on the document root. Layout code uses logical properties and Tailwind logical utilities (`start`, `end`, `ms`, `me`, `border-e`, and `text-start`) where direction matters. Directional icons opt into RTL mirroring; non-directional icons do not. Product values, SKU values, external IDs, and currency/number cells preserve their original content.

## API errors

New backend errors should retain a stable machine code and may retain English diagnostic prose:

```json
{
  "code": "STALE_REVIEW",
  "message": "Review is stale."
}
```

The frontend translates the code first. Adding or changing a translated error message must not change the API code or business behavior.

## Dependencies and licenses

- `i18next` — MIT
- `react-i18next` — MIT
- `gettext-parser` — MIT (development tooling)
- `glob` — ISC (development tooling)

Existing Handsontable licensing requirements are unchanged by this implementation.
