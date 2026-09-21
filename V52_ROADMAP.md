# V52 Roadmap — Professional UI/UX, Settings & Presets

V52 adds a centralized Control Center, persistent user settings, production preset management, theme switching, navigation shortcuts, and settings import/export.

## Scope
- Central workspace navigation
- Dark/Light theme
- Accent color
- UI scale preference (stored; platform scaling remains OS/Qt controlled)
- Default DPI, garment and separation preferences
- Auto-validation and project snapshot preferences
- Built-in production presets
- Custom preset save/update/delete
- Settings/preset JSON package import/export
- Self-test for persistence and package round-trip

## Honest limitations
- UI scale is stored as a preference; Qt/OS DPI scaling remains the final renderer.
- Existing processing algorithms retain the limitations documented by their respective V releases.
