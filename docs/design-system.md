# MINDEX Design System

This document is the stable UI design grammar for the app shell. It complements
`docs/ui-contracts.md`: this file owns reusable design tokens and migration
rules, while `docs/ui-contracts.md` owns screen-level behavior contracts.

## Runtime Owner

`mindex.design-tokens.js` owns the small set of app UI tokens that need to be
shared by multiple screens without turning `app.js` into a styling glossary.
It loads after `mindex.constants.js` and before `mindex.presenter.js`/`app.js`.

The DEX-family numeric baseline lives at workspace-level
`docs/dex-design-tokens.json`. Mindex may add domain tokens, but shared role,
icon, button, and tab values must remain compatible with that baseline and
`tools/check_dex_shell.py`.

Keep presenter output typography and layout rules in `mindex.presenter.js` and
`styles.presenter-output.css`. The design-token file is for the controller app
shell, navigation, buttons, labels, and shared UI copy.

## Token Rules

- Use the shared `5px` rhythm for shell spacing and `10px` steps for larger UI spacing.
- Use the shared typography ladder before adding a new one-off size:
  `12/700` labels, `12/500` metadata, `14/600` rows and controls,
  `16/700` compact titles, `20/700` page titles.
- Use shared icon sizes before adding local values: 14px helper, 16px normal,
  20px large (navigation rail).
- Use the shared 1.5 stroke for Lucide controls. Scope icon defaults to `.lucide`,
  never all SVGs; document previews and illustrations own their dimensions.
- Size both Lucide placeholders and rendered SVGs when styling an icon control.
- Use shared button sizes: 40px topbar, 35px icon, 30px dense, 28px compact.
- Do not add accent color to neutral shell controls. Accent is for selected
  state, primary creation actions, or explicit attention.

## Button Grammar

- Sidebar and ambient utility actions should be icon-only with an accessible
  `aria-label`.
- Use text labels only when the command is primary, destructive, or ambiguous
  without text.
- Primary creation buttons may use accent fill; repeated inline add controls
  should stay visually quiet.
- Danger buttons must remain visually distinct from primary actions.

## Service Navigation Copy

- Home tab default: show `이번 주 예배` and `다가오는 예배`.
- Worship tab default: show `전체 예배`.
- Service week panel title: `이번 주 예배`. Keep it available as a sidebar panel,
  but do not use it as the Worship tab's default screen.
- Service list title: `전체 예배`.
- Template surfaces should not appear as ordinary default navigation unless
  the user is explicitly managing templates.

## Migration Rule

Do not split `styles.css` or mechanically move large UI blocks without smoke or
visual coverage. The safe sequence is:

1. Document the rule.
2. Add or reuse a token in `mindex.design-tokens.js`.
3. Replace narrow repeated literals.
4. Add smoke coverage if behavior can regress.
5. Only then extract larger CSS or JS modules.
