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

        box = layout.box()
        row = box.row()
        row.label(text="Active Processes")

        if background_bake_ops.bgops_list or background_bake_ops.bgops_list_finished:
            for p in background_bake_ops.bgops_list:
                box.row().label(text=f"{p.name} - in progress {p.progress}%", icon='CHECKBOX_DEHLT')
        else:
            box.row().label(text="No running or finished bakes", icon='SORTTIME')

        if len(background_bake_ops.bgops_list_finished) != 0:
            for p in background_bake_ops.bgops_list_finished:
                row = box.row()
                col = row.column()
                col.label(text=f"{p.name} - done", icon='CHECKBOX_HLT')
                col = row.column()
                col.operator("texture_bake.bake_import_individual", text="", icon='IMPORT').pnum = int(p.process.pid)
                col = row.column()
                col.operator("texture_bake.bake_delete_individual", text="", icon='TRASH').pnum = int(p.process.pid)

        row = box.row()
        row.operator("texture_bake.bake_import", text="Import all", icon='IMPORT')
        row.operator("texture_bake.bake_delete", text="Discard all", icon='TRASH')
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
        col.operator("texture_bake.refresh_presets", text="", icon='FILE_REFRESH')
        col.operator("texture_bake.load_preset", text="", icon='CHECKMARK')
        col.operator("texture_bake.delete_preset", text="", icon='CANCEL')

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "preset_name")
        row.operator("texture_bake.save_preset", text="", icon='ADD')


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
            col.operator('texture_bake.add_object', text="", icon='ADD')
            col.operator('texture_bake.remove_object', text="", icon='REMOVE')
            col.operator('texture_bake.clear_objects', text="", icon='TRASH')
            col.separator()
            col.operator('texture_bake.move_object', text="", icon='TRIA_UP').direction="UP"
            col.operator('texture_bake.move_object', text="", icon='TRIA_DOWN').direction="DOWN"

        layout.row().prop(context.scene.TextureBake_Props, "selected_to_target")
        if context.scene.TextureBake_Props.selected_to_target:
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
        row = layout.row()
        row.scale_y = 1.5
        row.operator("texture_bake.bake_input_textures", icon='RENDER_RESULT')


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
            layout.row().prop(context.scene.TextureBake_Props, "export_preset", text="Preset")
            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "export_textures")
            row.prop(context.scene.TextureBake_Props, "export_mesh")

            layout.use_property_split = True
            if context.scene.TextureBake_Props.export_textures or context.scene.TextureBake_Props.export_mesh:
                layout.separator()
                layout.row().prop(context.scene.TextureBake_Props, "export_folder_name")

                row = layout.row()
                row.prop(context.scene.TextureBake_Props, "export_folder_per_object")
                row.enabled = context.scene.TextureBake_Props.export_textures

                if context.scene.TextureBake_Props.export_mesh:
                    layout.row().prop(context.scene.TextureBake_Props, "export_apply_modifiers")
                    layout.row().prop(context.scene.TextureBake_Props, "export_apply_transforms")

                layout.row().prop(context.scene.TextureBake_Props, "export_datetime")

                if context.scene.TextureBake_Props.export_mesh and not context.scene.TextureBake_Props.export_folder_per_object:
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

            row = layout.row()
            row.scale_y = 1.5
            row.operator("texture_bake.bake", icon='RENDER_RESULT')
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

        if context.scene.TextureBake_Props.uv_mode == "udims":
            layout.row().prop(context.scene.TextureBake_Props, "udim_tiles")

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "prefer_existing_uvmap")


class TEXTUREBAKE_PT_other(TextureBakeCategoryPanel, bpy.types.Panel):
    bl_label = "Other Settings"
    bl_parent_id = "TEXTUREBAKE_PT_main"

    def draw(self, context):
        layout = self.layout

        row=layout.row()
        row.prop(context.scene.TextureBake_Props, "batch_name")

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "prep_mesh", text="Copy objects and apply bakes (after import)")
        row.enabled = not context.scene.TextureBake_Props.tex_per_mat

        if (context.scene.TextureBake_Props.prep_mesh):
            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "hide_source_objects", text="Hide source objects after bake (after import)")

        row = layout.row()
        row.prop(context.scene.TextureBake_Props, "preserve_materials")

        if context.preferences.addons["cycles"].preferences.has_active_device():
            row = layout.row()
            row.prop(context.scene.cycles, "device")
            row = layout.row()
            row.prop(context.scene.TextureBake_Props, "memory_limit")
            row.enabled = context.scene.cycles.device != "CPU"
        else:
            row=layout.row()
            row.label(text="No valid GPU device in Blender Preferences. Using CPU.")


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
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.selected_objects

    def execute(self, context):
        object_list = context.scene.TextureBake_Props.object_list
        for obj in context.selected_objects:
            if obj.type != "MESH":
                continue
            if [i for i in object_list if i.obj.name == obj.name]:
                continue
            new_item = object_list.add()
            new_item.obj = obj
        return {'FINISHED'}


class TEXTUREBAKE_OT_remove_object(Operator):
    """Remove the selected object from the bake list."""
    bl_idname = "texture_bake.remove_object"
    bl_label = "Remove an object from the bake list"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.scene.TextureBake_Props.object_list

    def execute(self, context):
        object_list = context.scene.TextureBake_Props.object_list
        index = context.scene.TextureBake_Props.object_list_index
        object_list.remove(index)
        context.scene.TextureBake_Props.object_list_index = min(max(0, index - 1), len(object_list) - 1)
        return {'FINISHED'}


class TEXTUREBAKE_OT_clear_objects(Operator):
    """Clear the object list"""
    bl_idname = "texture_bake.clear_objects"
    bl_label = "Removes all objects from the bake list"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.scene.TextureBake_Props.object_list

    def execute(self, context):
        context.scene.TextureBake_Props.object_list.clear()
        return {'FINISHED'}


class TEXTUREBAKE_OT_move_object(Operator):
    """Move an object in the list."""
    bl_idname = "texture_bake.move_object"
    bl_label = "Move an object in the bake list"
    bl_options = {'INTERNAL'}

    direction: bpy.props.EnumProperty(items=(('UP', 'Up', ""), ('DOWN', 'Down', "")))

    @classmethod
    def poll(cls, context):
        return len(context.scene.TextureBake_Props.object_list) > 1

    def execute(self, context):
        object_list = context.scene.TextureBake_Props.object_list
        old_index = context.scene.TextureBake_Props.object_list_index
        new_index = old_index + (-1 if self.direction == 'UP' else 1)
        max_index = len(context.scene.TextureBake_Props.object_list) - 1
        object_list.move(old_index, new_index)
        context.scene.TextureBake_Props.object_list_index = max(0, min(new_index, max_index))
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


class TEXTUREBAKE_UL_export_presets(UIList):
    """List of existing export presets."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        custom_icon = 'RENDERLAYERS'
        layout.prop(item, "name", text="", emboss=False, icon=custom_icon)

class TEXTUREBAKE_UL_export_preset_textures(UIList):
    """List of existing export presets."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        custom_icon = 'IMAGE_DATA'
        layout.prop(item, "name", text="", emboss=False, icon=custom_icon)
