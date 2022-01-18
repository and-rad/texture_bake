# Changelog

## [1.0.0] - TBD

### Added
- Export presets
  - Bundle settings for baking textures
  - Presets can be modified, added, and removed
- Default export presets for
  - Unreal Engine
  - Normal maps (DirectX & OpenGL)

### Changed
- Setting the input texture size no longer overrides output texture size. The
  previous behavior was inconvenient and would cause users to constantly
  re-enter values.
- Background baking parameters are stored in a class instead of a flat array.
  This makes the code a little cleaner and easier to follow and reason about.
- Separated bake operators into baking input textures (AO, vertex color, etc.)
  and export textures (Diffuse, Normal, ORM, etc.).
- Channel packing does no longer require the "Export textures" property to be
  active. Channel packed textures are imported into Blender along with the
  other baked textures, saving to disk is now optional.
- It is no longer necessary to save the blend file before baking. Every feature
  that the add-on provides works for unsaved files as well.

### Removed
- Removed distinction between PBR bakes and Cycles bakes. The add-on uses both
  internally, depending on the required texture map and other parameters.
- Image name format preferences have been removed in favor of handling name
  formatting in export settings on a per-texture basis.
- Foreground baking was removed. All baking happens in the background now.
- Most export-related settings have been removed from the property panel if
  they're handled by export presets.

### Fixed
- Background baking progress UI refreshes properly even when the mouse does not
  move.
- Baked textures no longer lose their association with shaders after being
  baked repeatedly.
- Fixed various issues with channel packing. All kinds of textures can now be
  packed reliably.
- Background bake processes are properly killed when closing the main blend file.

## [0.9.0] - 2021-12-26

### Changed
- Made code formatting more consistent and in line with PEP8.
- UX is more in line with Blender core.
- Most operators are internal now in order to not add clutter to the search bar.

### Removed
- The add-on no longer checks for automatic updates.
- Removed Sketchfab upload API integration.
- Removed unused functions and commented-out code snippets.
- Removed monkey-head tip area. The information presented there was integrated
  into tooltips and class documentation.
- Removed automatic UV generation for texture bakes. Blender's smart UV unwrap
  method is just not usable for production work except for the simplest meshes.

### Fixed
- Fixed missing class unregister calls. Trying to deactivate and activate the
  add-on consecutively during the same Blender session no longer throws an error.
- Renamed objects already in the bake list can no longer be added twice.
- Fixed type mismatch when automatically setting bake margin.

[1.0.0]: https://github.com/and-rad/texture_bake/compare/0.9.0..HEAD
[0.9.0]: https://github.com/and-rad/texture_bake/compare/051f4a5..0.9.0