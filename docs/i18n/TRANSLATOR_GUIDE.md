# FlowHub translator guide

The canonical English template is:

```text
locales/flowhub.pot
```

## Create the Persian catalog with Poedit

1. Open `locales/flowhub.pot` in Poedit.
2. Choose **Create new translation from POT/PO file** and select Persian (`fa`).
3. Preserve every placeholder exactly, including `{{count}}`, `{{channel}}`, `{{product}}`, and `{{date}}`.
4. Review translator comments for FlowHub-specific terms such as Apply, Review, Draft, Listing, Source, Channel, Mapping, Current, Target, Stock, and Reconciliation.
5. Save the catalog as `locales/fa/flowhub.po` using UTF-8.
6. From `frontend/`, run:

   ```text
   npm run i18n:compile
   npm run i18n:validate
   npm test -- --run
   npm run build
   npm run test:e2e
   ```

7. When all messages are translated and validation/RTL review passes, Persian becomes selectable in Settings. No manual copying of individual strings is required.

Do not place Persian translations in `flowhub.pot`. Do not machine-translate the production catalog. An incomplete PO is safe to compile for review, but its manifest keeps Persian unavailable to normal users and missing values fall back to English.

## Update an existing translation

Regenerate the English template with `npm run i18n:extract`, then use Poedit’s **Update from POT file** action against `locales/flowhub.pot`. Resolve changed and obsolete entries, save `locales/fa/flowhub.po`, and compile again.

## Plurals and interpolation

Translate both singular and plural forms. Keep placeholder names unchanged and position them naturally for the target language. Never split a sentence into concatenated translated fragments.

FlowHub currently uses standard locale-aware digits and Gregorian `Intl` dates. Persian digits or Jalali dates require an explicit future locale policy; translators must not encode those behaviors into message text.

## Terms that remain untranslated as data

Do not translate product names, user-entered descriptions, spreadsheet content, SKU values, external marketplace IDs, Channel technical IDs, API routes, raw log/audit payloads, or connector protocol values. Friendly Channel display names and interface labels are translated separately from their technical identities.

## Translation review

Review English LTR and Persian RTL at minimum on Login, Dashboard, Workspace, FlowHub Sheet, Import Wizard, Products, Sources, Data Quality, Settings, and confirmation dialogs. Confirm Sidebar placement, directional icons, mixed-script names, horizontal Grid scrolling, accessibility labels, and non-clipped controls before marking a locale complete.
