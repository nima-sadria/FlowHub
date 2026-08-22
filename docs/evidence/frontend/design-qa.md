# Channel API docs — design QA

## Comparison target

- **Source visual truth:** FlowHub’s browser-rendered login screen, captured in the in-app browser from `http://127.0.0.1:5173/login` at approximately `1280 × 720` CSS pixels. The existing `globals.css`, `PageShell`, card, button, typography, and theme tokens were the authoritative component specification for the authenticated docs view.
- **Implementation:** Browser-rendered `ChannelDocs` view for Technolife from the temporary local QA route `http://127.0.0.1:5173/__docs-preview/technolife`, captured at approximately `1280 × 720` and `390 × 844` CSS pixels. The temporary route was removed after verification; the production route remains protected at `/docs/channels/:channelId`.
- **Normalization:** Both desktop captures used the same in-app browser and default density. The mobile capture used an explicit `390 × 844` viewport. The source screen is an application-shell reference rather than the same content state, so this review assesses adherence to FlowHub’s shared visual primitives rather than a pixel-for-pixel content comparison.

## Findings

- [Resolved P2] The initial implementation rendered the Markdown title and description a second time inside the document card.
  - **Location:** `ChannelDocs.tsx`, section extraction.
  - **Evidence:** The first implementation screenshot showed a duplicate document title in both the page header and the card.
  - **Fix:** The renderer now excludes the Markdown H1 and introductory preamble before generating the section list.
  - **Post-fix evidence:** The final desktop and mobile captures begin with the first API section (`۱ — احراز هویت`), and the table of contents contains only document sections.

- No remaining P0, P1, or P2 visual differences were found against the FlowHub component baseline.

## Required fidelity surfaces

- **Fonts and typography:** Persian content inherits FlowHub’s Yekan Bakh/Vazirmatn stack; code uses the project monospace token. Heading, body, table, and code hierarchy remain readable at desktop and mobile widths.
- **Spacing and layout rhythm:** The shared 12-column page shell, cards, borders, radii, and spacing tokens are used. Desktop keeps a sticky table of contents; mobile converts it into a horizontal, scrollable section list.
- **Colors and tokens:** Cards, muted text, code surfaces, notes, focus state, and statuses use existing FlowHub semantic tokens.
- **Image quality and assets:** The page introduces no raster imagery or custom-drawn assets. It reuses the existing FlowHub icon component, which is backed by the project icon library.
- **Copy and content:** All three Persian API documents are rendered from their Markdown sources. Long code examples are preserved in scrollable, copyable blocks.

## Interaction checks

- Searching for `قیمت‌گذاری` displayed the matching Technolife section.
- Clearing the search restored the full document.
- Code-copy controls are exposed for each fenced example.
- Browser console: no errors in the verified view.

## Follow-up polish

- No blocking follow-up items. A future authenticated-session review can verify the docs route within the full sidebar and topbar shell.

final result: passed
