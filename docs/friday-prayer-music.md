# Friday Prayer Music and Button States

## Scope

- Friday free-prayer items (slot `prayer.meeting.free` or exact label `자율기도`) offer a dedicated player at the element, separate from sidebar background music.
- Other service types do not receive this player. Existing explicit slide audio is unchanged.
- Selection and rendering never start playback. The operator starts music explicitly.
- Play/pause, stop, repeat and volume have independent session state and a persistent, lazily created Audio instance. Navigation does not stop playback. No worship records or schema are changed.
- While output is open, the topbar offers a return to the live service from other views, protecting unsaved edits and preserving output/index without reloading service data.
- Presenter/editor button hover, pressed, busy and disabled states use existing theme tokens. Disabled pointer handling remains unchanged.
- The section editor uses the existing ordinal display helper without rewriting untouched labels.

## Audio

- Original supplied M4A, unchanged, approximately 46 minutes 42 seconds.
- SHA-256: `8c888a525cde94b7fbd91046f0ee774a7ba8fda06a199646112b201eb57f72da`
- Path: `assets/presenter/friday-free-prayer.m4a`
- No transcoding, trimming, automatic playback or database upload.

## Verification

- `tests/smoke_friday_music.py`: Chrome/WebKit player isolation, explicit playback, repeat, stop, compact layout and guarded live-service return. Audio playback is stubbed; original AAC metadata was verified in the initial release.
- `tests/smoke_section_label_display.py`: singleton/peer/custom labels and unchanged-source preservation.
- Physical church audio routing is not covered by these local tests.

## Release Status

Prepared and verified in an isolated worktree. The DB task confirmed that this UI-only release can proceed; its inactive atomic-storage changes in the root worktree are excluded.
