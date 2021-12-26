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
import signal
from pathlib import Path
from bpy.types import PropertyGroup
from . import bakefunctions
from . import functions
from . import bg_bake
from . import operators
from . import ui
from .bake_operation import TextureBakeConstants


def tex_per_mat_update(self, context):
    if context.scene.TextureBake_Props.tex_per_mat == True:
        context.scene.TextureBake_Props.prep_mesh = False
        context.scene.TextureBake_Props.hide_source_objects = False


def prep_mesh_update(self, context):
    if context.scene.TextureBake_Props.prep_mesh == False:
        context.scene.TextureBake_Props.hide_source_objects = False
        bpy.context.scene.TextureBake_Props.create_gltf_node = False
    else:
        context.scene.TextureBake_Props.hide_source_objects = True


def export_file_format_update(self,context):
    if context.scene.TextureBake_Props.export_file_format == "JPEG" or context.scene.TextureBake_Props.export_file_format == "TARGA":
        context.scene.TextureBake_Props.export_16bit = False


def export_textures_update(self, context):
    if bpy.context.scene.TextureBake_Props.export_textures == False:
        bpy.context.scene.TextureBake_Props.export_16bit = False
        bpy.context.scene.TextureBake_Props.run_denoise = False
        bpy.context.scene.TextureBake_Props.selected_lightmap_denoise = False
        bpy.context.scene.TextureBake_Props.export_folder_per_object = False
        bpy.context.scene.TextureBake_Props.uv_mode = "normal"


def global_mode_update(self, context):
    if not bpy.context.scene.TextureBake_Props.global_mode == "cycles_bake":
        bpy.context.scene.TextureBake_Props.tex_per_mat = False

    if not bpy.context.scene.TextureBake_Props.global_mode == "pbr_bake":
        bpy.context.scene.TextureBake_Props.selected_lightmap_denoise = False


def presets_list_update(self,context):
    index = context.scene.TextureBake_Props.presets_list_index
    item = context.scene.TextureBake_Props.presets_list[index]
    context.scene.TextureBake_Props.preset_name = item.name


def input_height_update(self,context):
    bpy.context.scene.TextureBake_Props.output_height = bpy.context.scene.TextureBake_Props.input_height


def input_width_update(self,context):
    bpy.context.scene.TextureBake_Props.output_width = bpy.context.scene.TextureBake_Props.input_width


def cp_list_index_update(self, context):
    index = bpy.context.scene.TextureBake_Props.cp_list_index
    cpt = bpy.context.scene.TextureBake_Props.cp_list[index]

    messages = []
    bpy.context.scene.TextureBake_Props.cp_file_format = cpt.file_format
    try:
        bpy.context.scene.TextureBake_Props.cptex_R = cpt.R
    except:
        messages.append(f"WARNING: {cpt.name} depends on {cpt.R} for the Red channel, but you are not baking it")
        messages.append("You can enable the required bake, or change the bake for that channel")
    try:
        bpy.context.scene.TextureBake_Props.cptex_G = cpt.G
    except:
        messages.append(f"WARNING: {cpt.name} depends on {cpt.G} for the Green channel, but you are not baking it")
        messages.append("You can enable the required bake, or change the bake for that channel")
    try:
        bpy.context.scene.TextureBake_Props.cptex_B = cpt.B
    except:
        messages.append(f"WARNING: {cpt.name} depends on {cpt.B} for the Blue channel, but you are not baking it")
        messages.append("You can enable the required bake, or change the bake for that channel")
    try:
        bpy.context.scene.TextureBake_Props.cptex_A = cpt.A
    except:
        messages.append(f"WARNING: {cpt.name} depends on {cpt.A} for the Alpha channel, but you are not baking it")
        messages.append("You can enable the required bake, or change the bake for that channel")

    bpy.context.scene.TextureBake_Props.cp_name = cpt.name

    # Show messages
    if len(messages)>0:
        functions.show_message_box(messages, title = "Warning", icon = "ERROR")


def get_selected_bakes_dropdown(self, context):
    items = [("none", "None","")]

    if bpy.context.scene.TextureBake_Props.selected_col:
        items.append(("diffuse", "Diffuse",""))
    if bpy.context.scene.TextureBake_Props.selected_metal:
        items.append(("metalness", "Metal",""))

    if bpy.context.scene.TextureBake_Props.selected_sss:
        items.append(("sss", "SSS",""))
    if bpy.context.scene.TextureBake_Props.selected_ssscol:
        items.append(("ssscol", "SSS Color",""))

    if bpy.context.scene.TextureBake_Props.selected_rough:
        if bpy.context.scene.TextureBake_Props.rough_glossy_switch == "glossy":
            items.append(("glossy", "Glossy",""))
        else:
            items.append(("roughness", "Rouchness",""))

    if bpy.context.scene.TextureBake_Props.selected_normal:
        items.append(("normal", "Normal",""))
    if bpy.context.scene.TextureBake_Props.selected_trans:
        items.append(("transparency", "Transmission",""))
    if bpy.context.scene.TextureBake_Props.selected_transrough:
        items.append(("transparencyroughness", "Transmission Rough",""))
    if bpy.context.scene.TextureBake_Props.selected_clearcoat:
        items.append(("clearcoat", "Clearcoat",""))
    if bpy.context.scene.TextureBake_Props.selected_clearcoat_rough:
        items.append(("clearcoatroughness", "ClearcoatRough",""))
    if bpy.context.scene.TextureBake_Props.selected_emission:
        items.append(("emission", "Emission",""))
    if bpy.context.scene.TextureBake_Props.selected_specular:
        items.append(("specular", "Specular",""))
    if bpy.context.scene.TextureBake_Props.selected_alpha:
        items.append(("alpha", "Alpha",""))

    if bpy.context.scene.TextureBake_Props.selected_col_mats:
        items.append((TextureBakeConstants.COLOURID, TextureBakeConstants.COLOURID,""))
    if bpy.context.scene.TextureBake_Props.selected_col_vertex:
        items.append((TextureBakeConstants.VERTEXCOL, TextureBakeConstants.VERTEXCOL,""))
    if bpy.context.scene.TextureBake_Props.selected_ao:
        items.append((TextureBakeConstants.AO, TextureBakeConstants.AO,""))
    if bpy.context.scene.TextureBake_Props.selected_thickness:
        items.append((TextureBakeConstants.THICKNESS, TextureBakeConstants.THICKNESS,""))
    if bpy.context.scene.TextureBake_Props.selected_curvature:
        items.append((TextureBakeConstants.CURVATURE, TextureBakeConstants.CURVATURE,""))
    if bpy.context.scene.TextureBake_Props.selected_lightmap:
        items.append((TextureBakeConstants.LIGHTMAP, TextureBakeConstants.LIGHTMAP,""))

    return items


class TextureBakePropGroup(bpy.types.PropertyGroup):
    """Contains per-file bake properties."""

    from bpy.props import (
        FloatProperty,
        StringProperty,
        BoolProperty,
        EnumProperty,
        PointerProperty,
        IntProperty,
        CollectionProperty,
    )

    global_mode: EnumProperty(
        name = "Bake Mode",
        description = "Global Baking Mode",
        default = "pbr_bake",
        items = [
            ("pbr_bake", "PBR Bake", "Bake PBR maps from materials created around the Principled BSDF and Emission shaders"),
            ("cycles_bake", "Cycles Bake", "Bake the 'traditional' cycles bake modes"),
        ],
        update = global_mode_update,
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
        update = input_height_update,
    )

    input_width: IntProperty(
        name = "Bake width",
        description = "Set the width of the baked image that will be produced",
        default = 1024,
        update = input_width_update,
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

    selected_col: BoolProperty(
        name = "Diffuse",
        description = "Bake a PBR Color map",
        default = True,
    )

    selected_metal: BoolProperty(
        name = "Metal",
        description = "Bake a PBR Metalness map",
    )

    selected_rough: BoolProperty(
        name = "Roughness/Glossy",
        description = "Bake a PBR Roughness or Glossy map",
    )

    selected_normal: BoolProperty(
        name = "Normal",
        description = "Bake a Normal map",
    )

    selected_trans: BoolProperty(
        name = "Transmission",
        description = "Bake a PBR Transmission map",
    )

    selected_transrough: BoolProperty(
        name = "Transmission Rough",
        description = "Bake a PBR Transmission Roughness map",
    )

    selected_emission: BoolProperty(
        name = "Emission",
        description = "Bake an Emission map",
    )

    selected_sss: BoolProperty(
        name = "SSS",
        description = "Bake a Subsurface Scattering map",
    )

    selected_ssscol: BoolProperty(
        name = "SSS Col",
        description = "Bake a Subsurface color map",
    )

    selected_clearcoat: BoolProperty(
        name = "Clearcoat",
        description = "Bake a PBR Clearcoat Map",
    )

    selected_clearcoat_rough: BoolProperty(
        name = "Clearcoat Roughness",
        description = "Bake a PBR Clearcoat Roughness map",
    )

    selected_specular: BoolProperty(
        name = "Specular",
        description = "Bake a Specular/Reflection map",
    )

    selected_alpha: BoolProperty(
        name = "Alpha",
        description = "Bake a PBR Alpha map",
    )

    selected_col_mats: BoolProperty(
        name = TextureBakeConstants.COLOURID,
        description = "ColorID Map based on random color per material",
    )

    selected_col_vertex: BoolProperty(
        name = TextureBakeConstants.VERTEXCOL,
        description = "Bake the active vertex colors to a texture",
    )

    selected_ao: BoolProperty(
        name = TextureBakeConstants.AO,
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

    selected_lightmap: BoolProperty(
        name = TextureBakeConstants.LIGHTMAP,
        description = "Lightmap. PBR baking doesn't normally need a sample count, but a lightmap does",
    )

    lightmap_apply_colman: BoolProperty(
        name = "Export with color management settings",
        description = "Apply the color management settings you have set in the render properties panel to the lightmap. Only available when you are exporting your bakes. Will be ignored if exporting to EXR files as these don't support color management",
        default = False,
    )

    selected_lightmap_denoise: BoolProperty(
        name = "Denoise Lightmap",
        description = "Run lightmap through the compositor denoise node, only available when you are exporting you bakes",
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
        type = ui.TextureBakeObjectListItem,
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

    background_bake_name: StringProperty(
        name = "Background bake task name",
        description = "Name to help you identify the background bake task. This can be anything, and is only to help keep track of multiple background bake tasks. The name will show in the list below",
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

    create_gltf_node: BoolProperty(
        name = "Create glTF settings",
        description = "Create the glTF settings node group",
        default = False,
    )

    gltf_selection: EnumProperty(
        name = "glTF selection",
        description = "Which map should be plugged into the glTF settings node",
        default = TextureBakeConstants.AO,
        items = [
            (TextureBakeConstants.AO, TextureBakeConstants.AO, "Use ambient occlusion"),
            (TextureBakeConstants.LIGHTMAP, TextureBakeConstants.LIGHTMAP, "Use lightmap"),
        ],
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

    first_texture_show: BoolProperty(
        name = "",
        default = True,
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
        name = "Name: ",
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


# List of all classes that will be registered
classes = [
    operators.TEXTUREBAKE_OT_bake,
    operators.TEXTUREBAKE_OT_pbr_select_all,
    operators.TEXTUREBAKE_OT_pbr_select_none,
    operators.TEXTUREBAKE_OT_reset_name_format,
    operators.TEXTUREBAKE_OT_reset_aliases,
    operators.TEXTUREBAKE_OT_bake_status,
    operators.TEXTUREBAKE_OT_bake_import,
    operators.TEXTUREBAKE_OT_bake_delete_individual,
    operators.TEXTUREBAKE_OT_bake_import_individual,
    operators.TEXTUREBAKE_OT_bake_delete,
    operators.TEXTUREBAKE_OT_import_materials,
    operators.TEXTUREBAKE_OT_save_preset,
    operators.TEXTUREBAKE_OT_load_preset,
    operators.TEXTUREBAKE_OT_refresh_presets,
    operators.TEXTUREBAKE_OT_delete_preset,
    operators.TEXTUREBAKE_OT_increase_bake_res,
    operators.TEXTUREBAKE_OT_decrease_bake_res,
    operators.TEXTUREBAKE_OT_increase_output_res,
    operators.TEXTUREBAKE_OT_decrease_output_res,
    operators.TEXTUREBAKE_OT_add_packed_texture,
    operators.TEXTUREBAKE_OT_delete_packed_texture,
    operators.TEXTUREBAKE_OT_reset_packed_textures,
    ui.TEXTUREBAKE_PT_main,
    ui.TEXTUREBAKE_PT_presets,
    ui.TEXTUREBAKE_PT_objects,
    ui.TEXTUREBAKE_PT_input,
    ui.TEXTUREBAKE_PT_output,
    ui.TEXTUREBAKE_PT_bake_settings,
    ui.TEXTUREBAKE_PT_export_settings,
    ui.TEXTUREBAKE_PT_uv,
    ui.TEXTUREBAKE_PT_other,
    ui.TEXTUREBAKE_PT_packing,
    ui.TextureBakePreferences,
    ui.TextureBakeObjectListItem,
    ui.TEXTUREBAKE_UL_object_list,
    ui.TEXTUREBAKE_OT_add_object,
    ui.TEXTUREBAKE_OT_remove_object,
    ui.TEXTUREBAKE_OT_move_object,
    ui.TEXTUREBAKE_OT_clear_objects,
    ui.TEXTUREBAKE_OT_refresh_objects,
    ui.TextureBakePresetItem,
    ui.TextureBakePackedTextureItem,
    ui.TEXTUREBAKE_UL_presets,
    ui.TEXTUREBAKE_UL_packed_textures,
    TextureBakePropGroup,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.TextureBake_Props = bpy.props.PointerProperty(type=TextureBakePropGroup)


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
