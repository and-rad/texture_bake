# Changelog

## [0.9.0] - TBD

### Added

### Changed
- Made code formatting more consistent and in line with PEP8.
- UX is more in line with Blender core

### Removed
- The add-on no longer checks for automatic updates.
- Removed Sketchfab upload API integration.
- Removed monkey-head tip area. The information presented there was integrated
  into tooltips and class documentation.
- Removed automatic UV generation for texture bakes. Blender's smart UV unwrap
  method is just not usable for production work except for the simplest meshes.

### Fixed
- Trying to deactivate and activate the add-on consecutively during the same
  Blender session no longer throws an error.
- Fixed type mismatch when automatically setting bake margin.