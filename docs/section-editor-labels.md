# Section Editor Labels

The section popup uses serviceItemOrdinalDisplayLabel, matching the controller:
one automatic numbered element displays without its ordinal; multiple peers
retain their current display order. Custom numeric names are not stripped.

The editable field tracks its displayed baseline in data-ordinal-display-value.
An unchanged field does not overwrite the stored label or trigger label-change
side effects when other fields are committed. Actual edits use the existing UI
field update path. Persistence adapters and database contracts are unchanged.

Regression tests: smoke_section_label_display.py and smoke_section_editor_actions.py
(Chrome and WebKit, synthetic data with Supabase requests blocked).
