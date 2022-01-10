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

from .bake_operation import TextureBakeConstants


def tex_per_mat_update(self, context):
    if context.scene.TextureBake_Props.tex_per_mat == True:
        context.scene.TextureBake_Props.prep_mesh = False
        context.scene.TextureBake_Props.hide_source_objects = False


def prep_mesh_update(self, context):
    if context.scene.TextureBake_Props.prep_mesh == False:
        context.scene.TextureBake_Props.hide_source_objects = False
    else:
        context.scene.TextureBake_Props.hide_source_objects = True


def export_file_format_update(self,context):
    if context.scene.TextureBake_Props.export_file_format == "JPEG" or context.scene.TextureBake_Props.export_file_format == "TARGA":
        context.scene.TextureBake_Props.export_16bit = False


def export_textures_update(self, context):
    if context.scene.TextureBake_Props.export_textures == False:
        context.scene.TextureBake_Props.export_16bit = False
        context.scene.TextureBake_Props.run_denoise = False
        context.scene.TextureBake_Props.export_folder_per_object = False
        context.scene.TextureBake_Props.uv_mode = "normal"


def presets_list_update(self,context):
    index = context.scene.TextureBake_Props.presets_list_index
    item = context.scene.TextureBake_Props.presets_list[index]
    context.scene.TextureBake_Props.preset_name = item.name


def cp_list_index_update(self, context):
    index = context.scene.TextureBake_Props.cp_list_index
    cpt = context.scene.TextureBake_Props.cp_list[index]

    messages = []
    context.scene.TextureBake_Props.cp_file_format = cpt.file_format
    try:
        context.scene.TextureBake_Props.cptex_R = cpt.R
    except:
        messages.append(f"WARNING: {cpt.name} depends on {cpt.R} for the Red channel, but you are not baking it")
        messages.append("You can enable the required bake, or change the bake for that channel")
    try:
        context.scene.TextureBake_Props.cptex_G = cpt.G
    except:
        messages.append(f"WARNING: {cpt.name} depends on {cpt.G} for the Green channel, but you are not baking it")
        messages.append("You can enable the required bake, or change the bake for that channel")
    try:
        context.scene.TextureBake_Props.cptex_B = cpt.B
    except:
        messages.append(f"WARNING: {cpt.name} depends on {cpt.B} for the Blue channel, but you are not baking it")
        messages.append("You can enable the required bake, or change the bake for that channel")
    try:
        context.scene.TextureBake_Props.cptex_A = cpt.A
    except:
        messages.append(f"WARNING: {cpt.name} depends on {cpt.A} for the Alpha channel, but you are not baking it")
        messages.append("You can enable the required bake, or change the bake for that channel")

    context.scene.TextureBake_Props.cp_name = cpt.name

    # Show messages
    if len(messages)>0:
        functions.show_message_box(messages, title = "Warning", icon = "ERROR")


def get_selected_bakes_dropdown(self, context):
    return [("none", "None","")]


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
        name = "Multiple objects to one texture set",
        default = False,
        description = "Bake multiple objects to one set of textures. You must have more than one object selected for baking. You will need to manually make sure their UVs don't overlap",
    )

    merged_bake_name: StringProperty(
        name = "Texture name for multiple bake",
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
        name = "All internal 32bit float",
        description = "Normal maps are always created as 32bit float images, but this option causes all images to be created as 32bit float. Image quality is theoretically increased, but often not noticably. Images must be exported as EXR to preserve 32bit quality",
        default = False,
    )

    use_alpha: BoolProperty(
        name = "Use Alpha",
        description = "Baked images have a transparent background (else Black)",
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

    normal_format_switch: EnumProperty(
        name = "",
        description = "Switch between OpenGL and DirectX formats for normal map. NOTE: Opengl is the default for Blender so, if you change this, texture probably won't look right when used in Blender",
        default = "opengl",
        items = [
            ("opengl", "OpenGL", ""),
            ("directx", "DirectX", ""),
        ],
    )

    tex_per_mat: BoolProperty(
        name = "Texture per material",
        description = "Bake each material into its own texture (for export to virtual worlds like Second Life",
        update = tex_per_mat_update,
    )

    selected_col_mats: BoolProperty(
        name = TextureBakeConstants.COLORID,
        description = "ColorID Map based on random color per material",
    )

    selected_col_vertex: BoolProperty(
        name = TextureBakeConstants.VERTEXCOL,
        description = "Bake the active vertex colors to a texture",
    )

    selected_ao: BoolProperty(
        name = "Ambient Occlusion",
        description = "Ambient Occlusion",
    )

    selected_thickness: BoolProperty(
        name = TextureBakeConstants.THICKNESS,
        description = "Thickness map",
    )

    selected_curvature: BoolProperty(
        name = TextureBakeConstants.CURVATURE,
        description = "Curvature map",
    )

    prefer_existing_uvmap: BoolProperty(
        name = "Prefer existing UV maps called TextureBake",
        description = "If one exists for the object being baked, use any existing UV maps called 'TextureBake' for baking (rather than the active UV map)",
    )

    restore_active_uvmap: BoolProperty(
        name = "Restore originally active UV map at end",
        description = "If you are preferring an existing UV map called TextureBake, the UV map used for baking may not be the one you had displayed in the viewport before baking. This option restores what you had active before baking",
        default = True,
    )

    uv_mode: EnumProperty(
        name = "UV Mode",
        description = "Bake to UDIMs or normal UVs. You must be exporting your bakes to use UDIMs. You must manually create your UDIM UVs (this cannot be automated)",
        default = "normal",
        items = [
            ("normal", "Normal", "Normal UV maps"),
            ("udims", "UDIMs", "UDIM UV maps"),
        ],
    )

    udim_tiles: IntProperty(
        name = "UDIM Tiles",
        description = "Set the number of tiles that your UV map has used",
        default = 2,
    )

    export_textures: BoolProperty(
        name = "Export bakes",
        description = "Export your bakes to the folder specified below, under the same folder where your .blend file is saved. Not available if .blend file not saved",
        default = False,
        update = export_textures_update,
    )

    export_folder_per_object: BoolProperty(
        name = "Sub-folder per object",
        description = "Create a sub-folder for the textures and FBX of each baked object. Only available if you are exporting bakes",
        default = False,
    )

    export_mesh: BoolProperty(
        name = "Export mesh",
        description = "Export your mesh as a .fbx file with a single texture and the UV map used for baking (i.e. ready for import somewhere else. File is saved in the folder specified below, under the folder where your blend file is saved. Not available if .blend file not saved",
        default = False,
    )

    fbx_name: StringProperty(
        name = "FBX name",
        description = "File name of the fbx. NOTE: To maintain compatibility, only MS Windows acceptable characters will be used",
        default = "Export",
        maxlen = 20,
    )

    prep_mesh: BoolProperty(
        name = "Copy objects and apply bakes",
        description = "Create a copy of your selected objects in Blender (or target object if baking to a target) and apply the baked textures to it. If you are baking in the background, this happens after you import",
        default = False,
        update = prep_mesh_update,
    )

    hide_source_objects: BoolProperty(
        name = "Hide source objects after bake",
        description = "Hide the source object that you baked from in the viewport after baking. If you are baking in the background, this happens after you import",
        default = False,
    )

    preserve_materials: BoolProperty(
        name = "Preserve object original materials (BETA)",
        description = "Preserve original material assignments for baked objects (NOTE: all materials will be identical, and point to the baked texture set, but face assignments for each material will be preserved)",
    )

    export_16bit: BoolProperty(
        name = "All exports 16bit",
        description = "Normal maps are always exported as 16bit, but this option causes all images to be exported 16bit. This should probably stay enabled unless file sizes are an issue",
        default = True,
    )

    export_file_format: EnumProperty(
        name = "Export File Format",
        description = "Select the file format for exported bakes",
        default = "PNG",
        items = [
            ("PNG", "PNG", ""),
            ("JPEG", "JPG", ""),
            ("TIFF", "TIFF", ""),
            ("TARGA", "TGA", ""),
            ("OPEN_EXR", "Open EXR", "Color management settings are not supported by the EXR format"),
        ],
        update = export_file_format_update,
    )

    export_folder_name: StringProperty(
        name = "Save folder name",
        description = "Name of the folder to create and save the bakes/mesh into. Created in the folder where you blend file is saved. NOTE: To maintain compatibility, only MS Windows acceptable characters will be used",
        default = "TextureBake_Bakes",
        maxlen = 20,
    )

    export_color_space: BoolProperty(
        name = "Export color space settings",
        description = "Apply color space settings (exposure, gamma etc.) from current scene when saving the diffuse image externally. Only available if you are exporting baked images. Will be ignored if exporting to EXR files as these don't support color management",
        default = False,
    )

    export_datetime: BoolProperty(
        name = "Append date and time to folder",
        description = "Append date and time to folder name. If you turn this off, previous bakes with the same name will be overwritten",
        default = True,
    )

    run_denoise: BoolProperty(
        name = "Denoise",
        description = "Run baked images through the compositor. Your blend file must be saved, and you must be exporting your bakes",
        default = False,
    )

    export_apply_modifiers: BoolProperty(
        name = "Apply object modifiers",
        description = "Apply modifiers to object on export of the mesh to FBX",
        default = True,
    )

    export_apply_transforms: BoolProperty(
        name = "Apply transformation",
        description = "Use the 'Apply Transformation' option when exporting to FBX",
        default = False,
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

    background_bake: EnumProperty(
        name="Background Bake",
        default="fg",
        items=[
            ("fg", "Foreground", "Perform baking in the foreground. Blender will lock up until baking is complete"),
            ("bg", "Background", "Perform baking in the background, leaving you free to continue to work in Blender while the baking is being carried out"),
        ],
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
        name = "Batch name",
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

    cptex_R: EnumProperty(
        description = "Bake type to use for the Red channel of the channel packed image",
        items = get_selected_bakes_dropdown,
    )

    cptex_G: EnumProperty(
        description = "Bake type to use for the Greeb channel of the channel packed image",
        items = get_selected_bakes_dropdown,
    )

    cptex_B: EnumProperty(
        description = "Bake type to use for the Blue channel of the channel packed image",
        items = get_selected_bakes_dropdown,
    )

    cptex_A: EnumProperty(
        description = "Bake type to use for the Alpha channel of the channel packed image",
        items = get_selected_bakes_dropdown,
    )

    cp_name: StringProperty(
        name = "Name",
        description = "List of Channel Packed Textures", # TODO: this might not belong here
        default = "PackedTex",
        maxlen = 30,
    )

    cp_list: CollectionProperty(
        name = "CP Textures",
        description = "CP Textures",
        type = ui.TextureBakePackedTextureItem,
    )

    cp_list_index: IntProperty(
        name = "Index for CP Textures list",
        default = 0,
        update = cp_list_index_update,
    )

    cp_file_format: EnumProperty(
        name = "Export File Format for Channel Packing",
        default = "OPEN_EXR",
        items = [
            ("PNG", "PNG", ""),
            ("TARGA", "TGA", ""),
            ("OPEN_EXR", "Open EXR", "Offers the most constent and reliable channel packing at the cost of memory"),
        ],
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
        update = export_texture_update,
    )

    space: EnumProperty(
        name = "Color Space",
        description = "The color space for this channel",
        default = 'SRGB',
        items = [
            ('SRGB', "sRGB", ""),
            ('LINEAR', "Linear", ""),
            ('NON_COLOR', "Non-Color", ""),
            ('RAW', "Raw", ""),
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
            ('JPG', "JPEG", "Supports 8-bit color depth"),
            ('EXR', "OpenEXR", "Always uses 32-bit color depth"),
            ('PNG', "PNG", "Supports 8-bit and 16-bit color depth"),
            ('TGA', "Targa", "Supports 8-bit color depth"),
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
    curvature_alias: StringProperty(name=TextureBakeConstants.CURVATURE, default="curvature")
    thickness_alias: StringProperty(name=TextureBakeConstants.THICKNESS, default="thickness")
    vertexcol_alias: StringProperty(name=TextureBakeConstants.VERTEXCOL, default="vertexcol")
    colid_alias: StringProperty(name=TextureBakeConstants.COLORID, default="colid")

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
        prefs.property_unset("colid_alias")
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
                row = box.row()
                row.prop(texture, "file_format", text="")
                row.prop(texture, "depth", text="")
                col = box.column()
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
                row.enabled = texture.file_format != 'JPG'
                row.label(text="Alpha:")
                row = row.split(factor=0.7)
                row.prop(texture.alpha, "info", text="")
                row.prop(texture.alpha, "space", text="")

        # Aliases
        box = layout.box()
        box.row().label(text="Aliases")
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
        box.row().prop(self, "colid_alias")
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
    operators.TEXTUREBAKE_OT_add_packed_texture,
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
    ui.TEXTUREBAKE_PT_uv,
    ui.TEXTUREBAKE_PT_other,
    ui.TEXTUREBAKE_PT_packing,
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
    from .bg_bake import background_bake_ops

    # Stop any ongoing background bakes
    bpy.ops.texture_bake.bake_delete()
    running = background_bake_ops.bgops_list
    savepath = Path(bpy.data.filepath).parent
    for p in running:
        pid_str = str(p[0].pid)
        try:
            os.kill(pid_str, signal.SIGKILL)
        except:
            pass

        try:
            os.remove(str(savepath / pid_str) + '.blend')
            os.remove(str(savepath / pid_str) + '.blend1')
        except:
            pass

    # User preferences
    del bpy.types.Scene.TextureBake_Props
    for cls in classes:
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
