# Citation Quick Insert

- The citation input exposes an `추가 즉시 송출` checkbox, enabled by default.
- The controller session retains the setting across board renders. Changing the checkbox never changes the current output.
- Enter captures the setting before asynchronous verse lookup. When enabled, successful lookup jumps to the first added verse and opens the output if needed. When disabled, it adds and saves without explicit selection, output opening, or scrolling.
- A browser window is reserved synchronously within the Enter gesture when output is closed. It navigates to the presenter only after lookup succeeds, and closes on lookup failure.
- Duplicate Enter requests for the same element are ignored while resolving. IME composition does not submit. Switching services while resolving prevents automatic navigation on completion.
- Tests: `smoke_citation_output_navigation.py` and `smoke_citation_toggle_layout.py`.
