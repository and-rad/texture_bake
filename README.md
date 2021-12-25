# Texture Bake

**Texture Bake** is a [Blender](https://www.blender.org) add-on that facilitates
3D texturing workflows by providing a comprehensive suite of texture baking functionality.
It started out as a fork of [SimpleBake](https://blendermarket.com/products/simplebake---simple-pbr-and-other-baking-in-blender-2).

## Building & Testing

The project directory does not have to live inside the Blender add-on directory.
Before you can buid the project, you have to create an `env.mk` file in the root
of the project. It needs to contain the following:

```
ADDON_DIR := /path/to/addon_contrib
```

`ADDON_DIR` is the path to the `addon_contrib` folder of the Blender version you want
to develop for. Prefer this over the `addon` folder for plugins in development.

Once this file is in place, you can build the add-on by executing the build command:

```
$ make build
```

Whenever you rebuild the add-on, Blender needs to reload the changed files. There are
several ways to do this:
- Restart Blender
- Main Menu > System > Reload Scripts
- press the Search hotkey (default F3), search for and execute the `Reload Scripts` operator