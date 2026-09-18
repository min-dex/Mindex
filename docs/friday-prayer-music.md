# Friday Prayer Music and Button States

## Scope

- Friday free-prayer items (slot `prayer.meeting.free` or exact label `자율기도`) offer the bundled music in the existing controller player.
- A slide's explicit audio takes precedence. Other service types do not receive the default.
- Selection and rendering never start playback. The operator starts music explicitly.
- Repeat is a session-only control; volume uses the existing player. No worship records or schema are changed.
- Presenter/editor button hover, pressed, busy and disabled states use existing theme tokens. Disabled pointer handling remains unchanged.
- The section editor uses the existing ordinal display helper without rewriting untouched labels.

## Audio

- Original supplied M4A, unchanged, approximately 46 minutes 42 seconds.
- SHA-256: `8c888a525cde94b7fbd91046f0ee774a7ba8fda06a199646112b201eb57f72da`
- Path: `assets/presenter/friday-free-prayer.m4a`
- No transcoding, trimming, automatic playback or database upload.

## Verification

- `tests/smoke_friday_music.py`: Chrome/WebKit context isolation, explicit playback, repeat, volume, compact layout, AAC metadata.
- `tests/smoke_section_label_display.py`: singleton/peer/custom labels and unchanged-source preservation.
- Physical church audio routing is not covered by these local tests.

## Release Status

Prepared in isolated worktree; deployment held pending resolution of the concurrent DB task's app.js/HTML deployment hold.
