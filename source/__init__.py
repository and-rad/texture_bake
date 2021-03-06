#########################################################################
#
# Copyright (C) 2021-2022 Andreas Raddau
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#########################################################################

bl_info = {
    "name": "Texture Bake",
    "author": "Andreas Raddau <and.rad@posteo.de>",
    "version": (0, 9, 0),
    "blender": (3, 0, 0),
    "location": "Properties Panel -> Render Settings Tab",
    "description": "Streamlined PBR texture baking",
    "warning": "",
    "doc_url": "https://github.com/and-rad/texture_bake/wiki",
    "tracker_url": "https://github.com/and-rad/texture_bake/issues",
    "category": "Object",
}

import bpy
import os
import re
import signal
import sys
import tempfile

from pathlib import Path
from bpy.types import PropertyGroup

from bpy.props import (
    FloatProperty,
    StringProperty,
    BoolProperty,
    EnumProperty,
    PointerProperty,
    IntProperty,
    CollectionProperty,
)

from . import (
    bg_bake,
    constants,
    functions,
    operators,
    ui,
)


def export_folder_name_update(self, context):
    if self.export_folder_name.startswith("//"):
        self.export_folder_name = os.path.normpath(bpy.path.abspath(self.export_folder_name))


def export_textures_update(self, context):
    if context.scene.TextureBake_Props.export_textures == False:
        context.scene.TextureBake_Props.bake_udims = False


def presets_list_update(self,context):
    index = context.scene.TextureBake_Props.presets_list_index
    item = context.scene.TextureBake_Props.presets_list[index]
    context.scene.TextureBake_Props.preset_name = item.name


def get_export_presets_enum(self, context):
    items = [('NONE', "None", "")]
    prefs = context.preferences.addons[__package__].preferences
    for idx, pr in enumerate(prefs.export_presets):
        items.append((pr.uid, pr.name, ""))
    return items


def export_preset_name_update(self, context):
    prefs = bpy.context.preferences.addons[__package__].preferences
    presets = prefs.export_presets
    if [p for p in presets if p != self and p.name == self.name]:
        if re.match("^.*\.\d\d\d$", self.name):
            self.name = self.name[:-3] + f"{(int(self.name[-3:]) + 1):03d}"
        else:
            self.name += ".001"
        bpy.ops.wm.save_userpref()


def export_texture_name_update(self, context):
    prefs = bpy.context.preferences.addons[__package__].preferences
    textures = prefs.export_presets[prefs.export_presets_index].textures
    if [t for t in textures if t != self and t.name == self.name]:
        if re.match("^.*\.\d\d\d$", self.name):
            self.name = self.name[:-3] + f"{(int(self.name[-3:]) + 1):03d}"
        else:
            self.name += ".001"
    bpy.ops.wm.save_userpref()


def export_texture_update(self, context):
    bpy.ops.wm.save_userpref()


def texture_channel_info_update(self, context):
    if self.info in [constants.PBR_DIFFUSE, constants.PBR_EMISSION]:
        self.space = 'sRGB'
    else:
        self.space = 'Non-Color'
    bpy.ops.wm.save_userpref()


class TextureBakeObjectProperty(bpy.types.PropertyGroup):
    """Group of properties representing an object selected for baking."""

    obj: PointerProperty(
        name="Bake Object",
        description="An object in the scene to be baked",
        type=bpy.types.Object
    )


class TextureBakeProperties(bpy.types.PropertyGroup):
    """Contains per-file bake properties."""

    export_preset: EnumProperty(
        name = "Export Preset",
        description = "The export preset to use when baking textures",
        items = get_export_presets_enum,
    )

    ray_distance: FloatProperty(
        name = "Ray Distance",
        description = "Distance to cast rays from target object to selected object(s)",
        default = 0.0,
    )

    cage_extrusion: FloatProperty(
        name = "Cage Extrusion",
        description = "Inflate the target object by specified value for baking",
        default = 0.0,
    )

    selected_to_target: BoolProperty(
        name = "Bake selected objects to target object",
        description = "Bake maps from one or more source objects (usually high poly) to a single target object (usually low poly). Source and target objects must be in the same location (overlapping). See Blender documentation on selected to active baking for more details",
    )

    target_object: PointerProperty(
        name = "Target Object",
        description = "Specify the target object for the baking. Note, this need not be part of your selection in the viewport (though it can be)",
        type = bpy.types.Object,
    )

    merged_bake: BoolProperty(
        name = "Merge Baked Textures",
        default = False,
        description = "Bake multiple objects to one set of textures. You must have more than one object selected for baking. You will need to manually make sure their UVs don't overlap",
    )

    merged_bake_name: StringProperty(
        name = "Merge Name",
        description = "When baking one object at a time, the object's name is used in the texture name. Baking multiple objects to one texture set, however requires you to proivde a name for the textures",
        default = "merged_bake",
    )

    input_height: IntProperty(
        name = "Bake height",
        default = 1024,
        description = "Set the height of the baked image that will be produced",
    )

    input_width: IntProperty(
        name = "Bake width",
        description = "Set the width of the baked image that will be produced",
        default = 1024,
    )

    output_height: IntProperty(
        name = "Output Height",
        description = "Set the height of the baked image that will be ouput",
        default = 1024,
    )

    output_width: IntProperty(
        name = "Output Width",
        description = "Set the width of the baked image that will be output",
        default = 1024,
    )

    bake_32bit_float: BoolProperty(
        name = "32-bit Color Depth",
        description = "All images will be saved with full 32-bit floating-point color precision internally. This increases image quality at the cost of significantly higher memory usage and rendering time",
        default = False,
    )

    rough_glossy_switch: EnumProperty(
        name = "",
        description = "Switch between roughness and glossiness (inverts of each other). NOTE: Roughness is the default for Blender so, if you change this, texture probably won't look right when used in Blender",
        default = "rough",
        items = [
            ("rough", "Rough", ""),
            ("glossy", "Glossy", ""),
        ],
    )

    tex_per_mat: BoolProperty(
        name = "One Texture Per Material",
        description = "Bake each material into its own texture (for export to virtual worlds like Second Life",
    )

    selected_col_mats: BoolProperty(
        name = "Material ID",
        description = "ColorID Map based on random color per material",
    )

    selected_col_vertex: BoolProperty(
        name = "Vertex Color",
        description = "Bake the active vertex colors to a texture",
    )

    selected_ao: BoolProperty(
        name = "Ambient Occlusion",
        description = "Ambient Occlusion",
    )

    selected_thickness: BoolProperty(
        name = "Thickness",
        description = "Thickness map",
    )

    selected_curvature: BoolProperty(
        name = "Curvature",
        description = "Curvature map",
    )

    prefer_existing_uvmap: BoolProperty(
        name = "Prefer existing UV maps",
        description = "If one exists for the object being baked, use any existing UV maps called 'TextureBake' for baking (rather than the active UV map)",
    )

    bake_udims: BoolProperty(
        name = "Bake UDIMs",
        description = "Bake to UDIMs. You must be exporting your bakes to use UDIMs. UDIM UVs have to be created manually",
    )

    udim_tiles: IntProperty(
        name = "UDIM Tiles",
        description = "Set the number of tiles that your UV map has used",
        default = 2,
    )

    export_textures: BoolProperty(
        name = "Save to Disk",
        description = "Export your bakes to the folder specified below, under the same folder where your .blend file is saved. Not available if .blend file not saved",
        default = False,
        update = export_textures_update,
    )

    export_folder_per_object: BoolProperty(
        name = "Subfolder per object",
        description = "Create a subfolder for the textures of each baked object",
        default = False,
    )

    export_folder_name: StringProperty(
        name = "Folder Name",
        description = "Exported textures are saved in this location. NOTE: To maintain compatibility, only MS Windows acceptable characters will be used",
        subtype = 'DIR_PATH',
        update = export_folder_name_update,
    )

    export_datetime: BoolProperty(
        name = "Append date and time",
        description = "Append date and time to folder name. If you turn this off, previous bakes with the same name will be overwritten",
        default = True,
    )

    use_object_list: BoolProperty(
        name = "Use advanced object selection",
        description = "When turned on, you will bake the objects added to the bake list. When turned off, you will bake objects selected in the viewport",
        default = True,
    )

    object_list: CollectionProperty(
        type = TextureBakeObjectProperty,
    )

    object_list_index: IntProperty(
        name = "Index for bake objects list",
        default = 0,
    )

    memory_limit: EnumProperty(
        name = "GPU Memory Limit",
        description = "Limit memory usage by limiting render tile size. More memory means faster bake times, but it is possible to exceed the capabilities of your computer which will lead to a crash or slow bake times",
        default = "4096",
        items = [
            ("512", "Ultra Low", "Ultra Low memory usage (max 512 tile size)"),
            ("1024", "Low", "Low memory usage (max 1024 tile size)"),
            ("2048", "Medium", "Medium memory usage (max 2048 tile size)"),
            ("4096", "Normal", "Normal memory usage, for a reasonably modern computer (max 4096 tile size)"),
            ("Off", "No Limit", "Don't limit memory usage (tile size matches render image size)"),
        ],
    )

    batch_name: StringProperty(
        name = "Batch Name",
        description = "Name to apply to these bakes (is incorporated into the bakes file name, provided you have included this in the image format string - see addon preferences). NOTE: To maintain compatibility, only MS Windows acceptable characters will be used",
        default = "Bake1",
        maxlen = 20,
    )

    presets_list: CollectionProperty(
        name = "Presets",
        description = "List of presets",
        type = ui.TextureBakePresetItem,
    )

    presets_list_index: IntProperty(
        name = "Index for bake presets list",
        default = 0,
        update = presets_list_update,
    )

    preset_name: StringProperty(
        name = "Name",
        description = "Name to save this preset under",
        default = "Preset Name",
        maxlen = 20,
    )


class TextureBakeTextureChannel(PropertyGroup):
    """Group of properties representing a texture channel."""

    info: EnumProperty(
        name="Info",
        description="The type of information to be stored in this channel",
        default = 'NONE',
        items = [
            ('NONE', "None", "Do not store anything in this channel"),
            (constants.PBR_AO, "Ambient Occlusion", ""),
            (constants.PBR_DIFFUSE, "Diffuse", ""),
            (constants.PBR_EMISSION, "Emission", ""),
            (constants.PBR_METAL, "Metalness", ""),
            (constants.PBR_NORMAL_OGL, "Normal (OpenGL)", ""),
            (constants.PBR_NORMAL_DX, "Normal (DirectX)", ""),
            (constants.PBR_OPACITY, "Opacity", ""),
            (constants.PBR_ROUGHNESS, "Roughness", ""),
        ],
        update = texture_channel_info_update,
    )

    space: EnumProperty(
        name = "Color Space",
        description = "The color space for this channel",
        default = 'Non-Color',
        items = [
            ('sRGB', "sRGB", ""),
            ('Linear', "Linear", ""),
            ('Non-Color', "Non-Color", ""),
        ],
        update = export_texture_update,
    )


class TextureBakePackedTexture(PropertyGroup):
    """Group of properties representing a packed RGBA texture."""

    name: StringProperty(
        name = "Name",
        description = "The name of this texture. See below for available placeholders",
        default = "%OBJ%_%BATCH%_Texture",
        update = export_texture_name_update,
    )

    file_format: EnumProperty(
        name = "File Format",
        description = "The file format to save this texture at",
        default = 'PNG',
        items = [
            ('JPEG', "JPEG", "Supports 8-bit color depth"),
            ('OPEN_EXR', "OpenEXR", "Always uses 32-bit color depth"),
            ('PNG', "PNG", "Supports 8-bit and 16-bit color depth"),
            ('TARGA', "Targa", "Supports 8-bit color depth"),
        ],
        update = export_texture_update,
    )

    depth: EnumProperty(
        name = "Bit Depth",
        description = "The amount of bits to use to encode each color channel. Not every file format supports every bit depth",
        default = '8',
        items = [
            ('8', "8-bit", ""),
            ('16', "16-bit", ""),
        ],
        update = export_texture_update,
    )

    red: PointerProperty(
        name = "R",
        description = "The texture's red channel",
        type = TextureBakeTextureChannel,
    )

    green: PointerProperty(
        name = "G",
        description = "The texture's green channel",
        type = TextureBakeTextureChannel,
    )

    blue: PointerProperty(
        name = "B",
        description = "The texture's blue channel",
        type = TextureBakeTextureChannel,
    )

    alpha: PointerProperty(
        name = "A",
        description = "The texture's alpha channel",
        type = TextureBakeTextureChannel,
    )


class TextureBakeExportPreset(bpy.types.PropertyGroup):
    """Group of properties representing an export preset."""

    uid: StringProperty(
        name = "UID",
        description = "A unique identifier used internally to allow renaming and reordering presets",
    )

    name: StringProperty(
        name = "Name",
        description = "The preset's name. Has to be unique",
        default = "New Preset",
        update = export_preset_name_update,
    )

    textures: CollectionProperty(
        name = "Textures",
        description = "The texture maps to bake out for this preset",
        type = TextureBakePackedTexture,
    )

    textures_index: IntProperty(
        description = "The active texture index",
        default = 0,
    )


class TextureBakePreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    # Export presets
    export_presets: CollectionProperty(
        type = TextureBakeExportPreset,
    )

    export_presets_index: IntProperty(
        description = "The active export preset index",
        default = 0,
    )

    # Aliases
    diffuse_alias: StringProperty(name="Diffuse", default="diffuse")
    metal_alias: StringProperty(name="Metal", default="metalness")
    roughness_alias: StringProperty(name="Roughness", default="roughness")
    glossy_alias: StringProperty(name="Glossy", default="glossy")
    normal_alias: StringProperty(name="Normal", default="normal")
    transmission_alias: StringProperty(name="Transmission", default="transmission")
    transmissionrough_alias: StringProperty(name="Transmission Roughness", default="transmissionroughness")
    clearcoat_alias: StringProperty(name="Clearcost", default="clearcoat")
    clearcoatrough_alias: StringProperty(name="Clearcoat Roughness", default="clearcoatroughness")
    emission_alias: StringProperty(name="Emission", default="emission")
    specular_alias: StringProperty(name="Specular", default="specular")
    alpha_alias: StringProperty(name="Alpha", default="alpha")
    sss_alias: StringProperty(name="SSS", default="sss")
    ssscol_alias: StringProperty(name="SSS Color", default="ssscol")

    ao_alias: StringProperty(name="Ambient Occlusion", default="ao")
    curvature_alias: StringProperty(name="Curvature", default="curvature")
    thickness_alias: StringProperty(name="Thickness", default="thickness")
    vertexcol_alias: StringProperty(name="Vertex Color", default="vertexcol")
    matid_alias: StringProperty(name="Material ID", default="matid")

    @classmethod
    def reset_aliases(self):
        prefs = bpy.context.preferences.addons[__package__].preferences
        prefs.property_unset("diffuse_alias")
        prefs.property_unset("metal_alias")
        prefs.property_unset("roughness_alias")
        prefs.property_unset("normal_alias")
        prefs.property_unset("transmission_alias")
        prefs.property_unset("transmissionrough_alias")
        prefs.property_unset("clearcoat_alias")
        prefs.property_unset("clearcoatrough_alias")
        prefs.property_unset("emission_alias")
        prefs.property_unset("specular_alias")
        prefs.property_unset("alpha_alias")
        prefs.property_unset("sss_alias")
        prefs.property_unset("ssscol_alias")
        prefs.property_unset("ao_alias")
        prefs.property_unset("curvature_alias")
        prefs.property_unset("thickness_alias")
        prefs.property_unset("vertexcol_alias")
        prefs.property_unset("matid_alias")
        bpy.ops.wm.save_userpref()

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.row().label(text="Export Presets")
        row = box.row()
        row.template_list("TEXTUREBAKE_UL_export_presets", "", self, "export_presets", self, "export_presets_index")
        col = row.column()
        col.operator("texture_bake.add_export_preset", text="", icon='ADD')
        col.operator("texture_bake.delete_export_preset", text="", icon='REMOVE')
        col.separator()
        col.operator("texture_bake.reset_export_presets", text="", icon='FILE_REFRESH')

        if 0 <= self.export_presets_index and self.export_presets_index < len(self.export_presets):
            preset = self.export_presets[self.export_presets_index]
            row = box.row()
            row.template_list("TEXTUREBAKE_UL_export_preset_textures", "", preset, "textures", preset, "textures_index")
            col = row.column()
            col.operator("texture_bake.add_export_texture", text="", icon='ADD')
            col.operator("texture_bake.delete_export_texture", text="", icon='REMOVE')
            col.separator()
            col.operator("texture_bake.format_info", text="", icon='INFO')

            if 0 <= preset.textures_index and preset.textures_index < len(preset.textures):
                texture = preset.textures[preset.textures_index]
                col = box.column()

                row = col.split(factor=0.1)
                row.label(text="Format:")
                if texture.file_format == 'PNG':
                    row = row.split(factor=0.7)
                    row.prop(texture, "file_format", text="")
                    row.prop(texture, "depth", text="")
                else:
                    row.prop(texture, "file_format", text="")

                col.separator()
                row = col.split(factor=0.1)
                row.label(text="Red:")
                row = row.split(factor=0.7)
                row.prop(texture.red, "info", text="")
                row.prop(texture.red, "space", text="")

                row = col.split(factor=0.1)
                row.label(text="Green:")
                row = row.split(factor=0.7)
                row.prop(texture.green, "info", text="")
                row.prop(texture.green, "space", text="")

                row = col.split(factor=0.1)
                row.label(text="Blue:")
                row = row.split(factor=0.7)
                row.prop(texture.blue, "info", text="")
                row.prop(texture.blue, "space", text="")

                row = col.split(factor=0.1)
                row.enabled = texture.file_format != 'JPEG'
                row.label(text="Alpha:")
                row = row.split(factor=0.7)
                row.prop(texture.alpha, "info", text="")
                row.prop(texture.alpha, "space", text="")

        # Aliases
        box = layout.box()
        box.row().label(text="Texture Aliases")
        box.row().prop(self, "diffuse_alias")
        box.row().prop(self, "metal_alias")
        box.row().prop(self, "sss_alias")
        box.row().prop(self, "ssscol_alias")
        box.row().prop(self, "roughness_alias")
        box.row().prop(self, "glossy_alias")
        box.row().prop(self, "transmission_alias")
        box.row().prop(self, "transmissionrough_alias")
        box.row().prop(self, "clearcoat_alias")
        box.row().prop(self, "clearcoatrough_alias")
        box.row().prop(self, "emission_alias")
        box.row().prop(self, "specular_alias")
        box.row().prop(self, "alpha_alias")
        box.row().prop(self, "normal_alias")
        box.row().prop(self, "ao_alias")
        box.row().prop(self, "curvature_alias")
        box.row().prop(self, "thickness_alias")
        box.row().prop(self, "vertexcol_alias")
        box.row().prop(self, "matid_alias")
        box.row().operator("texture_bake.reset_aliases")


# List of all classes that will be registered
classes = [
    operators.TEXTUREBAKE_OT_bake,
    operators.TEXTUREBAKE_OT_bake_input_textures,
    operators.TEXTUREBAKE_OT_reset_aliases,
    operators.TEXTUREBAKE_OT_bake_import,
    operators.TEXTUREBAKE_OT_bake_delete_individual,
    operators.TEXTUREBAKE_OT_bake_import_individual,
    operators.TEXTUREBAKE_OT_bake_delete,
    operators.TEXTUREBAKE_OT_save_preset,
    operators.TEXTUREBAKE_OT_load_preset,
    operators.TEXTUREBAKE_OT_refresh_presets,
    operators.TEXTUREBAKE_OT_delete_preset,
    operators.TEXTUREBAKE_OT_increase_bake_res,
    operators.TEXTUREBAKE_OT_decrease_bake_res,
    operators.TEXTUREBAKE_OT_increase_output_res,
    operators.TEXTUREBAKE_OT_decrease_output_res,
    operators.TEXTUREBAKE_OT_add_export_preset,
    operators.TEXTUREBAKE_OT_delete_export_preset,
    operators.TEXTUREBAKE_OT_reset_export_presets,
    operators.TEXTUREBAKE_OT_add_export_texture,
    operators.TEXTUREBAKE_OT_delete_export_texture,
    operators.TEXTUREBAKE_OT_format_info,
    ui.TEXTUREBAKE_PT_main,
    ui.TEXTUREBAKE_PT_presets,
    ui.TEXTUREBAKE_PT_objects,
    ui.TEXTUREBAKE_PT_input,
    ui.TEXTUREBAKE_PT_bake_settings,
    ui.TEXTUREBAKE_PT_export_settings,
    ui.TEXTUREBAKE_UL_object_list,
    ui.TEXTUREBAKE_OT_add_object,
    ui.TEXTUREBAKE_OT_remove_object,
    ui.TEXTUREBAKE_OT_move_object,
    ui.TEXTUREBAKE_OT_clear_objects,
    ui.TextureBakePresetItem,
    ui.TextureBakePackedTextureItem,
    ui.TEXTUREBAKE_UL_presets,
    ui.TEXTUREBAKE_UL_packed_textures,
    ui.TEXTUREBAKE_UL_export_presets,
    ui.TEXTUREBAKE_UL_export_preset_textures,
    TextureBakeObjectProperty,
    TextureBakeTextureChannel,
    TextureBakePackedTexture,
    TextureBakeExportPreset,
    TextureBakeProperties,
    TextureBakePreferences,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.TextureBake_Props = PointerProperty(type=TextureBakeProperties)

    prefs = bpy.context.preferences.addons[__package__].preferences
    prefs.export_presets_index = 0
    if not prefs.export_presets:
        bpy.ops.texture_bake.reset_export_presets


def unregister():
    # Stop any ongoing background bakes
    savepath = Path(tempfile.gettempdir())
    if not "--background" in sys.argv:
        try:
            os.remove(str(savepath / str(os.getpid())) + '.blend')
            os.remove(str(savepath / str(os.getpid())) + '.blend1')
        except:
            pass

    bpy.ops.texture_bake.bake_delete()
    for p in bg_bake.background_bake_ops.bgops_list:
        pid = p.process.pid
        try:
            os.kill(pid, signal.SIGKILL)
        except:
            pass
        try:
            os.remove(str(savepath / str(pid)) + '.blend')
            os.remove(str(savepath / str(pid)) + '.blend1')
        except:
            pass

    # User preferences
    del bpy.types.Scene.TextureBake_Props
    for cls in classes:
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
