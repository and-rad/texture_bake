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

import bpy
from pathlib import Path
import tempfile
from . import functions
from . import bakefunctions
from .bg_bake import background_bake_ops
from .bake_operation import TextureBakeConstants

from bpy.props import StringProperty, IntProperty, CollectionProperty, PointerProperty
from bpy.types import PropertyGroup, UIList, Operator, Panel


class TextureBakeCategoryPanel:
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"


class TEXTUREBAKE_PT_main(bpy.types.Panel):
    bl_label = "Texture Bake"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "global_mode", text = "Bake Mode", expand = True)

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "background_bake", expand = True)

        if bpy.context.scene.TextureBake_Props.background_bake == "bg":
            layout.row().prop(context.scene.TextureBake_Props, "background_bake_name", text="Name")

        row = layout.row()
        row.scale_y = 1.5
        row.operator("texture_bake.bake", icon='RENDER_RESULT')

        box = layout.box()
        row = box.row()
        row.label(text="Background bakes")

        if len(background_bake_ops.bgops_list) == 0 and len(background_bake_ops.bgops_list_finished) == 0:
            row = box.row()
            row.label(text="No running or finished background bakes", icon="MONKEY")
        else:
            for p in background_bake_ops.bgops_list:
                t = Path(tempfile.gettempdir())
                t = t / f"TextureBake_background_bake_{str(p[0].pid)}"

                try:
                    with open(str(t), "r") as progfile:
                        progress = progfile.readline()
                except:
                    # No file yet, as no bake operation has completed yet. Holding message
                    progress = 0

                row = box.row()
                name = p[3]
                if name == "":
                    name = "Untitled"
                row.label(text=f"{name} - baking in progress {progress}%", icon="GHOST_DISABLED")

        if len(background_bake_ops.bgops_list_finished) != 0:
            for p in background_bake_ops.bgops_list_finished:
                row = box.row()
                col = row.column()
                name = p[3]
                if name == "":
                    name = "Untitled"
                col.label(text=f"{name} - finished!", icon="GHOST_ENABLED")
                col = row.column()
                col.operator("texture_bake.bake_import_individual", text="", icon="IMPORT").pnum = int(p[0].pid)
                col = row.column()
                col.operator("texture_bake.bake_delete_individual", text="", icon="CANCEL").pnum = int(p[0].pid)

        row = box.row()
        row.operator("texture_bake.bake_import", text="Import all", icon="IMPORT")
        row.operator("texture_bake.bake_delete", text="Discard all", icon="TRASH")
        row.enabled = len(background_bake_ops.bgops_list_finished) != 0


class TEXTUREBAKE_PT_presets(TextureBakeCategoryPanel, bpy.types.Panel):
    bl_label = "Presets"
    bl_parent_id = "TEXTUREBAKE_PT_main"

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        col = row.column()
        col.template_list("TEXTUREBAKE_UL_presets", "", context.scene.TextureBake_Props,
                          "presets_list", context.scene.TextureBake_Props, "presets_list_index")

        col = row.column()
        col.operator("texture_bake.refresh_presets", text="", icon="FILE_REFRESH")
        col.operator("texture_bake.load_preset", text="", icon="CHECKMARK")
        col.operator("texture_bake.delete_preset", text="", icon="CANCEL")

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "preset_name")
        row.operator("texture_bake.save_preset", text="", icon="ADD")


class TEXTUREBAKE_PT_objects(TextureBakeCategoryPanel, bpy.types.Panel):
    bl_label = "Objects"
    bl_parent_id = "TEXTUREBAKE_PT_main"

    def draw(self, context):
        layout = self.layout
        layout.use_property_decorate = False

        layout.row().prop(context.scene.TextureBake_Props, "use_object_list")
        if context.scene.TextureBake_Props.use_object_list:
            row = layout.row()
            col = row.column()
            col.template_list("TEXTUREBAKE_UL_object_list", "", context.scene.TextureBake_Props,
                            "object_list", context.scene.TextureBake_Props, "object_list_index")
            col = row.column()
            col.operator('texture_bake.add_object', text="", icon="ADD")
            col.operator('texture_bake.remove_object', text="", icon="REMOVE")
            col.operator('texture_bake.clear_objects', text="", icon="TRASH")
            col.separator()
            col.operator('texture_bake.move_object', text="", icon="TRIA_UP").direction="UP"
            col.operator('texture_bake.move_object', text="", icon="TRIA_DOWN").direction="DOWN"

        layout.row().prop(context.scene.TextureBake_Props, "selected_to_target")
        if bpy.context.scene.TextureBake_Props.selected_to_target:
            layout.use_property_split = True
            layout.row().prop(context.scene.TextureBake_Props, "target_object")
            layout.row().prop(context.scene.render.bake, "cage_object", text="Cage Object (Optional)")
            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "ray_distance")
            row.prop(context.scene.TextureBake_Props, "cage_extrusion")


class TEXTUREBAKE_PT_input(TextureBakeCategoryPanel, bpy.types.Panel):
    bl_label = "Input Textures"
    bl_parent_id = "TEXTUREBAKE_PT_main"

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "selected_col_mats")
        row.prop(context.scene.TextureBake_Props, "selected_col_vertex")

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "selected_ao")
        row.prop(context.scene.TextureBake_Props, "selected_thickness")

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "selected_curvature")
        row.prop(context.scene.TextureBake_Props, "selected_lightmap")

        if bpy.context.scene.TextureBake_Props.selected_lightmap and bpy.context.scene.TextureBake_Props.global_mode == "pbr_bake":
            layout.row().prop(context.scene.cycles, "samples")

        if bpy.context.scene.TextureBake_Props.selected_lightmap:
            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "selected_lightmap_denoise")
            if not bpy.context.scene.TextureBake_Props.export_textures:
                row.enabled = False

            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "lightmap_apply_colman")
            if not bpy.context.scene.TextureBake_Props.export_textures:
                row.enabled = False

        layout.row().operator("texture_bake.import_materials", icon='ADD')


class TEXTUREBAKE_PT_output(TextureBakeCategoryPanel, bpy.types.Panel):
    bl_label = "Output Textures"
    bl_parent_id = "TEXTUREBAKE_PT_main"

    def draw(self, context):
        layout = self.layout
        layout.use_property_decorate = False

        # PBR
        if(context.scene.TextureBake_Props.global_mode == "pbr_bake"):
            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "selected_col")
            row.prop(context.scene.TextureBake_Props, "selected_metal")

            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "selected_sss")
            row.prop(context.scene.TextureBake_Props, "selected_ssscol")

            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "selected_rough")
            row.prop(context.scene.TextureBake_Props, "selected_normal")

            if context.scene.TextureBake_Props.selected_rough or context.scene.TextureBake_Props.selected_normal:
                row = layout.row()
                if context.scene.TextureBake_Props.selected_normal and context.scene.TextureBake_Props.selected_rough:
                    row.column().prop(context.scene.TextureBake_Props, "rough_glossy_switch")
                    row.column().prop(context.scene.TextureBake_Props, "normal_format_switch")
                elif context.scene.TextureBake_Props.selected_rough:
                    row.column().prop(context.scene.TextureBake_Props, "rough_glossy_switch")
                    row.column().label(text="")
                elif context.scene.TextureBake_Props.selected_normal:
                    row.column().label(text="")
                    row.column().prop(context.scene.TextureBake_Props, "normal_format_switch")

            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "selected_trans")
            row.prop(context.scene.TextureBake_Props, "selected_transrough")

            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "selected_clearcoat")
            row.prop(context.scene.TextureBake_Props, "selected_clearcoat_rough")

            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "selected_emission")
            row.prop(context.scene.TextureBake_Props, "selected_specular")

            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "selected_alpha")

            row = layout.row()
            row.operator("texture_bake.pbr_select_all", icon='ADD')
            row.operator("texture_bake.pbr_select_none", icon='REMOVE')

        # Cycles
        if(context.scene.TextureBake_Props.global_mode == "cycles_bake"):
            layout.use_property_split = True

            cscene = bpy.context.scene.cycles
            layout.row().prop(cscene, "bake_type")

            cbk = bpy.context.scene.render.bake
            if cscene.bake_type == 'NORMAL':
                layout.row().prop(cbk, "normal_space", text="Space")
                layout.row().prop(cbk, "normal_r", text="Swizzle R")
                layout.row().prop(cbk, "normal_g", text="G")
                layout.row().prop(cbk, "normal_b", text="B")
            elif cscene.bake_type == 'COMBINED':
                layout.row().prop(cbk, "use_pass_direct")
                layout.row().prop(cbk, "use_pass_indirect")
                if cbk.use_pass_direct or cbk.use_pass_indirect:
                    layout.row().prop(cbk, "use_pass_diffuse")
                    layout.row().prop(cbk, "use_pass_glossy")
                    layout.row().prop(cbk, "use_pass_transmission")
                    layout.row().prop(cbk, "use_pass_emit")
            elif cscene.bake_type in {'DIFFUSE', 'GLOSSY', 'TRANSMISSION'}:
                layout.row().prop(cbk, "use_pass_direct")
                layout.row().prop(cbk, "use_pass_indirect")
                layout.row().prop(cbk, "use_pass_color")

            layout.row().prop(context.scene.cycles, "samples")

            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "run_denoise", text="Denoise CyclesBake")
            if not bpy.context.scene.TextureBake_Props.export_textures:
                row.enabled = False


class TEXTUREBAKE_PT_bake_settings(TextureBakeCategoryPanel, bpy.types.Panel):
    bl_label = "Bake Settings"
    bl_parent_id = "TEXTUREBAKE_PT_main"

    def draw(self, context):
        layout = self.layout

        layout.row().label(text="Bake at:")

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "input_width")
        row.prop(context.scene.TextureBake_Props, "input_height")

        row = layout.row()
        row.operator("texture_bake.decrease_bake_res", icon = "TRIA_DOWN")
        row.operator("texture_bake.increase_bake_res", icon = "TRIA_UP")

        layout.separator()
        layout.row().label(text="Output at:")

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "output_width")
        row.prop(context.scene.TextureBake_Props, "output_height")

        row = layout.row()
        row.operator("texture_bake.decrease_output_res", icon = "TRIA_DOWN")
        row.operator("texture_bake.increase_output_res", icon = "TRIA_UP")

        layout.row().prop(context.scene.render.bake, "margin", text="Bake Margin")

        layout.separator()
        layout.row().prop(context.scene.TextureBake_Props, "bake_32bit_float")
        layout.row().prop(context.scene.TextureBake_Props, "use_alpha")

        # For now, this is CyclesBake only
        if context.scene.TextureBake_Props.global_mode == "cycles_bake":
            layout.row().prop(context.scene.TextureBake_Props, "tex_per_mat")

        layout.row().prop(context.scene.TextureBake_Props, "merged_bake")

        if context.scene.TextureBake_Props.merged_bake:
            layout.row().prop(context.scene.TextureBake_Props, "merged_bake_name")


class TEXTUREBAKE_PT_export_settings(TextureBakeCategoryPanel, bpy.types.Panel):
    bl_label = "Export Settings"
    bl_parent_id = "TEXTUREBAKE_PT_main"

    def draw(self, context):
        layout = self.layout
        layout.use_property_decorate = False

        if functions.is_blend_saved():
            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "export_textures")
            row.prop(context.scene.TextureBake_Props, "export_mesh")

            layout.use_property_split = True
            if context.scene.TextureBake_Props.export_textures or context.scene.TextureBake_Props.export_mesh:
                layout.separator()
                layout.row().prop(context.scene.TextureBake_Props, "export_folder_name", text="Folder name")

                row = layout.row()
                row.prop(context.scene.TextureBake_Props, "export_folder_per_object")
                row.enabled = bpy.context.scene.TextureBake_Props.export_textures

                if context.scene.TextureBake_Props.export_mesh:
                    layout.row().prop(context.scene.TextureBake_Props, "export_apply_modifiers")
                    layout.row().prop(context.scene.TextureBake_Props, "export_apply_transforms")

                layout.row().prop(context.scene.TextureBake_Props, "export_datetime")

                if context.scene.TextureBake_Props.export_mesh and not bpy.context.scene.TextureBake_Props.export_folder_per_object:
                    layout.row().prop(context.scene.TextureBake_Props, "fbx_name")

                layout.row().prop(context.scene.TextureBake_Props, "export_file_format", text="Format")

                row = layout.row()
                row.prop(context.scene.TextureBake_Props, "export_16bit")
                if (not context.scene.TextureBake_Props.export_textures
                    or context.scene.TextureBake_Props.export_file_format == "JPEG"
                    or context.scene.TextureBake_Props.export_file_format == "TARGA"):
                    row.enabled = False

                row = layout.row()
                row.prop(context.scene.TextureBake_Props, "export_color_space")
                if context.scene.TextureBake_Props.global_mode == "pbr_bake":
                    row.enabled = bpy.context.scene.TextureBake_Props.selected_col

                if context.scene.TextureBake_Props.global_mode == "cycles_bake":
                    row.enabled = bpy.context.scene.cycles.bake_type != "NORMAL"
        else:
            layout.row().label(text="Unavailable - Blend file not saved")


class TEXTUREBAKE_PT_uv(TextureBakeCategoryPanel, bpy.types.Panel):
    bl_label = "UV Settings"
    bl_parent_id = "TEXTUREBAKE_PT_main"

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "uv_mode", expand=True)
        row.enabled = context.scene.TextureBake_Props.export_textures

        if bpy.context.scene.TextureBake_Props.uv_mode == "udims":
            layout.row().prop(context.scene.TextureBake_Props, "udim_tiles")

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "prefer_existing_uvmap")

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "restore_active_uvmap")


class TEXTUREBAKE_PT_other(TextureBakeCategoryPanel, bpy.types.Panel):
    bl_label = "Other Settings"
    bl_parent_id = "TEXTUREBAKE_PT_main"

    def draw(self, context):
        layout = self.layout

        row=layout.row()
        row.prop(context.scene.TextureBake_Props, "batch_name")

        row = layout.row()
        if bpy.context.scene.TextureBake_Props.background_bake == "fg":
            text = "Copy objects and apply bakes"
        else:
            text = "Copy objects and apply bakes (after import)"

        row.prop(context.scene.TextureBake_Props, "prep_mesh", text=text)
        row.enabled = not context.scene.TextureBake_Props.tex_per_mat

        if (context.scene.TextureBake_Props.prep_mesh):
            if bpy.context.scene.TextureBake_Props.background_bake == "fg":
                text = "Hide source objects after bake"
            else:
                text = "Hide source objects after bake (after import)"
            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "hide_source_objects", text=text)

            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "create_gltf_node")
            if bpy.context.scene.TextureBake_Props.create_gltf_node:
                row.prop(context.scene.TextureBake_Props, "gltf_selection", text="")

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "preserve_materials")

        if bpy.context.preferences.addons["cycles"].preferences.has_active_device():
            row = layout.row()
            row.prop(context.scene.cycles, "device")
            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "memory_limit")
            row.enabled = bpy.context.scene.cycles.device != "CPU"
        else:
            row=layout.row()
            row.label(text="No valid GPU device in Blender Preferences. Using CPU.")


class TEXTUREBAKE_PT_packing(TextureBakeCategoryPanel, bpy.types.Panel):
    bl_label = "Channel Packing"
    bl_parent_id = "TEXTUREBAKE_PT_main"

    def draw(self, context):
        layout = self.layout

        if context.scene.TextureBake_Props.global_mode != "pbr_bake":
            layout.row().label(text="Unavailable - Channel packing requires PBR bake mode")
        elif not functions.is_blend_saved():
            layout.row().label(text="Unavailable - Blend file not saved")
        elif not bpy.context.scene.TextureBake_Props.export_textures:
            layout.row().label(text="Unavailable - You must be exporting your bakes")
        else:
            row = layout.row()
            col = row.column()
            col.template_list("TEXTUREBAKE_UL_packed_textures", "", context.scene.TextureBake_Props,
                                "cp_list", context.scene.TextureBake_Props, "cp_list_index")
            col = row.column()
            col.operator("texture_bake.delete_packed_texture", text="", icon="CANCEL")
            col.operator("texture_bake.reset_packed_textures", text="", icon="MONKEY")

            layout.row().prop(context.scene.TextureBake_Props, "cp_name")
            layout.row().prop(context.scene.TextureBake_Props, "cp_file_format", text="Format")
            layout.row().prop(context.scene.TextureBake_Props, "cptex_R", text="R")
            layout.row().prop(context.scene.TextureBake_Props, "cptex_G", text="G")
            layout.row().prop(context.scene.TextureBake_Props, "cptex_B", text="B")
            layout.row().prop(context.scene.TextureBake_Props, "cptex_A", text="A")

            cp_list = bpy.context.scene.TextureBake_Props.cp_list
            current_name = bpy.context.scene.TextureBake_Props.cp_name
            if current_name in cp_list: # Editing a cpt that is already there
                index = cp_list.find(current_name)
                cpt = cp_list[index]

                if (cpt.R != bpy.context.scene.TextureBake_Props.cptex_R
                    or cpt.G != bpy.context.scene.TextureBake_Props.cptex_G
                    or cpt.B != bpy.context.scene.TextureBake_Props.cptex_B
                    or cpt.A != bpy.context.scene.TextureBake_Props.cptex_A
                    or cpt.file_format != bpy.context.scene.TextureBake_Props.cp_file_format):
                    row = layout.row()
                    row.alert=True
                    text = f"Update {current_name} (!!not saved!!)"
                    row.operator("texture_bake.add_packed_texture", text=text, icon="ADD")
                else: # No changes, no button
                    text = f"Editing {current_name}"
                    row = layout.row()
                    row.label(text=text)
                    row.alignment = 'CENTER'
            else: # New item
                row = layout.row()
                text = "Add new (!!not saved!!)"
                row.alert = True
                row.operator("texture_bake.add_packed_texture", text=text, icon="ADD")


class TextureBakePreferences(bpy.types.AddonPreferences):
    # this must match the add-on name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = __package__

    img_name_format: bpy.props.StringProperty(name="Image format string",
        default="%OBJ%_%BATCH%_%BAKEMODE%_%BAKETYPE%")

    # Aliases
    diffuse_alias: bpy.props.StringProperty(name="Diffuse", default="diffuse")
    metal_alias: bpy.props.StringProperty(name="Metal", default="metalness")
    roughness_alias: bpy.props.StringProperty(name="Roughness", default="roughness")
    glossy_alias: bpy.props.StringProperty(name="Glossy", default="glossy")
    normal_alias: bpy.props.StringProperty(name="Normal", default="normal")
    transmission_alias: bpy.props.StringProperty(name="Transmission", default="transparency")
    transmissionrough_alias: bpy.props.StringProperty(name="Transmission Roughness", default="transparencyroughness")
    clearcoat_alias: bpy.props.StringProperty(name="Clearcost", default="clearcoat")
    clearcoatrough_alias: bpy.props.StringProperty(name="Clearcoat Roughness", default="clearcoatroughness")
    emission_alias: bpy.props.StringProperty(name="Emission", default="emission")
    specular_alias: bpy.props.StringProperty(name="Specular", default="specular")
    alpha_alias: bpy.props.StringProperty(name="Alpha", default="alpha")
    sss_alias: bpy.props.StringProperty(name="SSS", default="sss")
    ssscol_alias: bpy.props.StringProperty(name="SSS Color", default="ssscol")

    ao_alias: bpy.props.StringProperty(name=TextureBakeConstants.AO, default="ao")
    curvature_alias: bpy.props.StringProperty(name=TextureBakeConstants.CURVATURE, default="curvature")
    thickness_alias: bpy.props.StringProperty(name=TextureBakeConstants.THICKNESS, default="thickness")
    vertexcol_alias: bpy.props.StringProperty(name=TextureBakeConstants.VERTEXCOL, default="vertexcol")
    colid_alias: bpy.props.StringProperty(name=TextureBakeConstants.COLOURID, default="colid")
    lightmap_alias: bpy.props.StringProperty(name=TextureBakeConstants.LIGHTMAP, default="lightmap")

    @classmethod
    def reset_img_string(self):
        prefs = bpy.context.preferences.addons[__package__].preferences
        prefs.property_unset("img_name_format")
        bpy.ops.wm.save_userpref()

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
        prefs.property_unset("lightmap_alias")
        bpy.ops.wm.save_userpref()

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        row = box.row()
        row.label(text="Format string for image names")
        row = box.row()
        row.label(text="Valid variables are %OBJ% (object name or 'merged_bake'), %BATCH% (batch name),")
        row.scale_y = 0.5
        row = box.row()
        row.label(text="%BAKEMODE% (pbr or cycles bake) and %BAKETYPE% (diffuse, emission etc.)")
        row.scale_y = 0.5
        row = box.row()
        row.label(text="An example based on your current settings is shown below")
        row.scale_y = 0.5

        row = box.row()
        test_obj = "Cube"
        test_baketype = "diffuse"
        row.label(text=f"Current: {functions.gen_image_name(test_obj, test_baketype, demo=True)}")

        row = box.row()
        row.prop(self, "img_name_format")
        row = box.row()
        row.operator("texture_bake.reset_name_format")

        # PBR Aliases
        box = layout.box()

        row = box.row()
        row.label(text="Aliases for PBR bake types")

        row = box.row()
        col = row.column()
        col.prop(self, "diffuse_alias")
        col = row.column()
        col.prop(self, "metal_alias")

        row = box.row()
        col = row.column()
        col.prop(self, "sss_alias")
        col = row.column()
        col.prop(self, "ssscol_alias")

        row = box.row()
        col = row.column()
        col.prop(self, "roughness_alias")
        col = row.column()
        col.prop(self, "glossy_alias")

        row = box.row()
        col = row.column()
        col.prop(self, "transmission_alias")
        col = row.column()
        col.prop(self, "transmissionrough_alias")

        row = box.row()
        col = row.column()
        col.prop(self, "clearcoat_alias")
        col = row.column()
        col.prop(self, "clearcoatrough_alias")

        row = box.row()
        col = row.column()
        col.prop(self, "emission_alias")
        col = row.column()
        col.prop(self, "specular_alias")

        row = box.row()
        col = row.column()
        col.prop(self, "alpha_alias")
        col = row.column()
        col.prop(self, "normal_alias")
        col.label(text="")

        # Specials Aliases
        box = layout.box()

        row = box.row()
        row.label(text="Aliases for special bake types")

        row = box.row()
        col = row.column()
        col.prop(self, "ao_alias")
        col = row.column()
        col.prop(self, "curvature_alias")

        row = box.row()
        col = row.column()
        col.prop(self, "thickness_alias")
        col = row.column()
        col.prop(self, "vertexcol_alias")

        row = box.row()
        col = row.column()
        col.prop(self, "colid_alias")
        col = row.column()
        col.prop(self, "lightmap_alias")

        # Reset button
        box = layout.box()
        row = box.row()
        row.operator("texture_bake.reset_aliases")


class TEXTUREBAKE_UL_object_list(UIList):
    """List type to display objects selected for baking"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # We could write some code to decide which icon to use here...
        custom_icon = 'OBJECT_DATAMODE'

        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=item.obj.name, icon = custom_icon)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)


class TEXTUREBAKE_OT_add_object(Operator):
    """Add selected object(s) to the bake list"""
    bl_idname = "texture_bake.add_object"
    bl_label = "Add a new object to bake list"

    @classmethod
    def poll(cls, context):
        return bpy.context.selected_objects

    def execute(self, context):
        object_list = context.scene.TextureBake_Props.object_list
        for obj in bpy.context.selected_objects:
            if obj.type != "MESH":
                continue
            if [i for i in object_list if i.obj.name == obj.name]:
                continue
            new_item = object_list.add()
            new_item.obj = obj
        return{'FINISHED'}


class TEXTUREBAKE_OT_remove_object(Operator):
    """Remove the selected object from the bake list."""
    bl_idname = "texture_bake.remove_object"
    bl_label = "Remove an object from the bake list"

    @classmethod
    def poll(cls, context):
        return context.scene.TextureBake_Props.object_list

    def execute(self, context):
        object_list = context.scene.TextureBake_Props.object_list
        index = context.scene.TextureBake_Props.object_list_index
        object_list.remove(index)
        context.scene.TextureBake_Props.object_list_index = min(max(0, index - 1), len(object_list) - 1)
        return{'FINISHED'}


class TEXTUREBAKE_OT_clear_objects(Operator):
    """Clear the object list"""
    bl_idname = "texture_bake.clear_objects"
    bl_label = "Removes all objects from the bake list"

    @classmethod
    def poll(cls, context):
        return context.scene.TextureBake_Props.object_list

    def execute(self, context):
        context.scene.TextureBake_Props.object_list.clear()
        return{'FINISHED'}


class TEXTUREBAKE_OT_move_object(Operator):
    """Move an object in the list."""
    bl_idname = "texture_bake.move_object"
    bl_label = "Move an object in the bake list"

    direction: bpy.props.EnumProperty(items=(('UP', 'Up', ""), ('DOWN', 'Down', "")))

    @classmethod
    def poll(cls, context):
        return len(context.scene.TextureBake_Props.object_list) > 1

    def execute(self, context):
        object_list = context.scene.TextureBake_Props.object_list
        old_index = context.scene.TextureBake_Props.object_list_index
        new_index = old_index + (-1 if self.direction == 'UP' else 1)
        max_index = len(bpy.context.scene.TextureBake_Props.object_list) - 1
        object_list.move(old_index, new_index)
        bpy.context.scene.TextureBake_Props.object_list_index = max(0, min(new_index, max_index))
        return{'FINISHED'}


class TEXTUREBAKE_UL_presets(UIList):
    """List of Texure Bake presets."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # We could write some code to decide which icon to use here...
        custom_icon = 'PACKAGE'

        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=item.name, icon = custom_icon)

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)


class TextureBakePresetItem(PropertyGroup):
    """Group of properties representing a TextureBake preset."""

    name: bpy.props.StringProperty(
        name="Name",
        description="A name for this item",
        default= "Untitled"
    )


class TEXTUREBAKE_UL_packed_textures(UIList):
    """List of channel-packed texture sets."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # We could write some code to decide which icon to use here...
        custom_icon = 'NODE_COMPOSITING'

        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=item.name, icon = custom_icon)

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)


class TextureBakePackedTextureItem(PropertyGroup):
    """Group of properties representing a TextureBake CP Texture."""

    name: bpy.props.StringProperty(
        name="Name",
        description="A name for this item",
        default= "Untitled"
    )
    R: bpy.props.StringProperty(
        name="R",
        description="Bake type for R channel"
    )
    G: bpy.props.StringProperty(
        name="G",
        description="Bake type for G channel"
    )
    B: bpy.props.StringProperty(
        name="B",
        description="Bake type for B channel"
    )
    A: bpy.props.StringProperty(
        name="A",
        description="Bake type for A channel"
    )
    file_format: bpy.props.StringProperty(
        name="File Format",
        description="File format for CP texture"
    )
