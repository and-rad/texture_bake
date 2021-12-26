# Changelog

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