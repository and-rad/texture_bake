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
from .bg_bake import bgbake_ops
from .bake_operation import TextureBakeConstants

from bpy.props import StringProperty, IntProperty, CollectionProperty, PointerProperty
from bpy.types import PropertyGroup, UIList, Operator, Panel


def monkeyTip(message_lines, box):
    row = box.row()
    row.alert=True
    row.prop(bpy.context.scene.TextureBake_Props, "showtips", icon="TRIA_DOWN" if bpy.context.scene.TextureBake_Props.showtips else "TRIA_RIGHT", icon_only=True, emboss=False)
    row.label(text=f'{"Tip" if bpy.context.scene.TextureBake_Props.showtips else "Tip available"}', icon="MONKEY")
    row.alignment = 'CENTER'

    if bpy.context.scene.TextureBake_Props.showtips:
        for line in message_lines:
            row = box.row()
            row.alignment = 'CENTER'
            row.scale_y = 0.5
            row.label(text=line)


class OBJECT_PT_texture_bake_panel(bpy.types.Panel):
    bl_label = "Texture Bake"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"


    def draw(self, context):
        layout = self.layout

        #-----------Global Mode Select------------------------
        box = layout.box()
        row = box.row()
        row.scale_y = 1.5

        if context.scene.TextureBake_Props.global_mode == "pbr_bake":
            modetxt = "Bake mode (PBR)"
        if context.scene.TextureBake_Props.global_mode == "cycles_bake":
            modetxt = "Bake mode (Cycles)"

        row.prop(context.scene.TextureBake_Props, "global_mode", icon="SETTINGS", text=modetxt, expand=True)

        row = box.row()
        row.operator("object.texture_bake_hide_all", icon='PROP_OFF', text="Hide all")
        row.operator("object.texture_bake_show_all", icon='PROP_ON', text="Show all")

        #-----------------------------------------------------------------------------------------------------

        #------------Presets--------------------------------------
        box = layout.box()
        row = box.row()
        #row.prop(bpy.context.scene.TextureBake_Props, "presets_show", icon="TRIA_DOWN" if bpy.context.scene.TextureBake_Props.presets_show else "TRIA_RIGHT", icon_only=True, emboss=False)
        #row.label(text="Presets", icon="PROP_ON")
        row.prop(bpy.context.scene.TextureBake_Props, "presets_show", text="Settings presets", icon="PROP_ON" if bpy.context.scene.TextureBake_Props.presets_show else "PROP_OFF", icon_only=False, emboss=False)

        if bpy.context.scene.TextureBake_Props.presets_show:

            row = box.row()
            col = row.column()
            col.template_list("PRESETS_UL_List", "Presets List", context.scene.TextureBake_Props,
                              "presets_list", context.scene.TextureBake_Props, "presets_list_index")

            col = row.column()
            col.operator("object.texture_bake_preset_refresh", text="", icon="FILE_REFRESH")
            col.operator("object.texture_bake_preset_load", text="", icon="CHECKMARK")
            col.operator("object.texture_bake_preset_delete", text="", icon="CANCEL")


            row = box.row()
            row.prop(context.scene.TextureBake_Props, "preset_name")
            row.operator("object.texture_bake_preset_save", text="", icon="FUND")

        #--------Object selection -------------------
        box = layout.box()
        row = box.row()
        #row.prop(bpy.context.scene.TextureBake_Props, "bake_objects_show", icon="TRIA_DOWN" if bpy.context.scene.TextureBake_Props.bake_objects_show else "TRIA_RIGHT", icon_only=True, emboss=False)
        #row.label(text="Bake objects", icon="PROP_ON")
        row.prop(bpy.context.scene.TextureBake_Props, "bake_objects_show", text="Bake objects", icon="PROP_ON" if bpy.context.scene.TextureBake_Props.bake_objects_show else "PROP_OFF", icon_only=False, emboss=False)

        if bpy.context.scene.TextureBake_Props.bake_objects_show:

            row = box.row()
            row.prop(context.scene.TextureBake_Props, "advancedobjectselection")

            if context.scene.TextureBake_Props.advancedobjectselection:

                row = box.row()
                row.template_list("BAKEOBJECTS_UL_List", "Bake Objects List", context.scene.TextureBake_Props,
                              "bakeobjs_advanced_list", context.scene.TextureBake_Props, "bakeobjs_advanced_list_index")
                row = box.row()
                row.operator('bakeobjs_advanced_list.new_item', text='Add', icon="PRESET_NEW")
                row.operator('bakeobjs_advanced_list.del_item', text='Remove', icon="CANCEL")
                row.operator('bakeobjs_advanced_list.clear_all', text='Clear', icon="MATPLANE")
                row = box.row()
                row.operator('bakeobjs_advanced_list.move_item', text='Up', icon="TRIA_UP").direction="UP"
                row.operator('bakeobjs_advanced_list.move_item', text='Down', icon="TRIA_DOWN").direction="DOWN"
                row.operator('bakeobjs_advanced_list.refresh', text='Refresh', icon="FILE_REFRESH")



            if context.scene.TextureBake_Props.global_mode == "pbr_bake":
                row = box.row()
                row.prop(context.scene.TextureBake_Props, "selected_s2a")

                if(bpy.context.scene.TextureBake_Props.selected_s2a):
                    row = box.row()
                    row.alignment = "RIGHT"
                    row.prop(context.scene.TextureBake_Props, "targetobj")
                    row = box.row()
                    row.alignment = "RIGHT"
                    row.prop(context.scene.render.bake, "cage_object", text="Cage Object (Optional)")
                    row = box.row()
                    row.alignment = "RIGHT"
                    row.prop(context.scene.TextureBake_Props, "ray_distance")
                    #row = box.row()
                    row.alignment = "RIGHT"
                    row.prop(context.scene.TextureBake_Props, "cage_extrusion")



            if context.scene.TextureBake_Props.global_mode == "cycles_bake":
                row = box.row()
                row.prop(context.scene.TextureBake_Props, "cycles_s2a", text="Bake to target object (selected to active)")
                if bpy.context.scene.TextureBake_Props.cycles_s2a:
                    row = box.row()
                    row.alignment = "RIGHT"
                    row.prop(context.scene.TextureBake_Props, "targetobj_cycles")
                    row = box.row()
                    row.alignment = "RIGHT"
                    row.prop(context.scene.render.bake, "cage_object", text="Cage Object (Optional)")
                    row = box.row()
                    row.alignment = "RIGHT"
                    row.prop(context.scene.TextureBake_Props, "ray_distance")
                    row.prop(context.scene.TextureBake_Props, "cage_extrusion")

            if functions.check_for_render_inactive_modifiers():

                message_lines = [
                "One or more selected objects",
                "has a modifier enabled for",
                "render (and so baking), but disabled in",
                "viewport. May cause unexpected results"
                ]
                monkeyTip(message_lines, box)

            if functions.check_for_viewport_inactive_modifiers():

                message_lines = [
                "One or more selected objects",
                "has a modifier enabled in the",
                "viewport, but disabled for",
                "render (and so baking).",
                "May cause unexpected results"
                ]
                monkeyTip(message_lines, box)

        #--------PBR Bake Settings-------------------

        if(context.scene.TextureBake_Props.global_mode == "pbr_bake"):

            box = layout.box()
            row = box.row()
            row.prop(bpy.context.scene.TextureBake_Props, "pbr_settings_show", text="PBR Bakes", icon="PROP_ON" if bpy.context.scene.TextureBake_Props.pbr_settings_show else "PROP_OFF", icon_only=True, emboss=False)

            if bpy.context.scene.TextureBake_Props.pbr_settings_show:

                row = box.row()
                row.prop(context.scene.TextureBake_Props, "selected_col")
                row.prop(context.scene.TextureBake_Props, "selected_metal")

                row = box.row()
                row.prop(context.scene.TextureBake_Props, "selected_sss")
                row.prop(context.scene.TextureBake_Props, "selected_ssscol")

                row = box.row()
                row.prop(context.scene.TextureBake_Props, "selected_rough")
                row.prop(context.scene.TextureBake_Props, "selected_normal")
                if context.scene.TextureBake_Props.selected_rough or context.scene.TextureBake_Props.selected_normal:
                    row = box.row()
                    if context.scene.TextureBake_Props.selected_normal and context.scene.TextureBake_Props.selected_rough:
                        col = row.column()
                        col.prop(context.scene.TextureBake_Props, "rough_glossy_switch")
                        col = row.column()
                        col.prop(context.scene.TextureBake_Props, "normal_format_switch")
                    elif context.scene.TextureBake_Props.selected_rough:
                        col = row.column()
                        col.prop(context.scene.TextureBake_Props, "rough_glossy_switch")
                        col = row.column()
                        col.label(text="")
                    elif context.scene.TextureBake_Props.selected_normal:
                        col = row.column()
                        col.label(text="")
                        col = row.column()
                        col.prop(context.scene.TextureBake_Props, "normal_format_switch")

                row = box.row()
                row.prop(context.scene.TextureBake_Props, "selected_trans")
                row.prop(context.scene.TextureBake_Props, "selected_transrough")
                row = box.row()
                row.prop(context.scene.TextureBake_Props, "selected_clearcoat")
                row.prop(context.scene.TextureBake_Props, "selected_clearcoat_rough")
                row = box.row()
                row.prop(context.scene.TextureBake_Props, "selected_emission")
                row.prop(context.scene.TextureBake_Props, "selected_specular")
                row = box.row()
                row.prop(context.scene.TextureBake_Props, "selected_alpha")
                row = box.row()
                row.operator("object.texture_bake_selectall", icon='ADD')
                row.operator("object.texture_bake_selectnone", icon='REMOVE')


        #--------Cycles Bake Settings-------------------

        if(context.scene.TextureBake_Props.global_mode == "cycles_bake"):
            box = layout.box()
            row = box.row()
            #row.prop(bpy.context.scene.TextureBake_Props, "cyclesbake_settings_show", icon="TRIA_DOWN" if bpy.context.scene.TextureBake_Props.cyclesbake_settings_show else "TRIA_RIGHT", icon_only=True, emboss=False)
            #row.label(text="CyclesBake", icon="PROP_ON")
            row.prop(bpy.context.scene.TextureBake_Props, "cyclesbake_settings_show", text="CyclesBake", icon="PROP_ON" if bpy.context.scene.TextureBake_Props.cyclesbake_settings_show else "PROP_OFF", icon_only=False, emboss=False)

            if bpy.context.scene.TextureBake_Props.cyclesbake_settings_show:

                cscene = bpy.context.scene.cycles
                cbk = bpy.context.scene.render.bake
                row=box.row()
                row.prop(cscene, "bake_type")


                col = box.column()
                if cscene.bake_type == 'NORMAL':
                    col.prop(cbk, "normal_space", text="Space")

                    sub = col.column()
                    sub.prop(cbk, "normal_r", text="Swizzle R")
                    sub.prop(cbk, "normal_g", text="G")
                    sub.prop(cbk, "normal_b", text="B")

                elif cscene.bake_type == 'COMBINED':

                    col.prop(cbk, "use_pass_direct")
                    col.prop(cbk, "use_pass_indirect")

                    col = box.column()
                    col.active = cbk.use_pass_direct or cbk.use_pass_indirect
                    col.prop(cbk, "use_pass_diffuse")
                    col.prop(cbk, "use_pass_glossy")
                    col.prop(cbk, "use_pass_transmission")
                    col.prop(cbk, "use_pass_emit")

                elif cscene.bake_type in {'DIFFUSE', 'GLOSSY', 'TRANSMISSION'}:
                    col = box.column()
                    col.prop(cbk, "use_pass_direct")
                    col.prop(cbk, "use_pass_indirect")
                    col.prop(cbk, "use_pass_color")



                #Tip alert
                #message_lines = [
                #"Remember to also set bake settings",
                #"in the Blender bake panel (in Cycles)",
                #"*TextureBake settings always take precedence*"
                #]
                #monkeyTip(message_lines, box)


                row = box.row()
                col = row.column()
                col.prop(context.scene.cycles, "samples")
                #row = box.row()

                row = box.row()
                col = row.column()
                col.prop(context.scene.TextureBake_Props, "rundenoise", text="Denoise CyclesBake")
                if not bpy.context.scene.TextureBake_Props.saveExternal:
                    col.enabled = False



        #----------Specials Settings--------------------
        box = layout.box()
        row = box.row()
        #row.prop(bpy.context.scene.TextureBake_Props, "specials_show", icon="TRIA_DOWN" if bpy.context.scene.TextureBake_Props.specials_show else "TRIA_RIGHT", icon_only=True, emboss=False)
        #row.label(text="Special bakes", icon="PROP_ON")
        row.prop(bpy.context.scene.TextureBake_Props, "specials_show", text="Special bakes", icon="PROP_ON" if bpy.context.scene.TextureBake_Props.specials_show else "PROP_OFF", icon_only=False, emboss=False)

        if bpy.context.scene.TextureBake_Props.specials_show:
            #row = box.row()
            #row.prop(context.scene.TextureBake_Props, "dospecials")


            row = box.row()
            row.prop(context.scene.TextureBake_Props, "selected_col_mats")
            row.prop(context.scene.TextureBake_Props, "selected_col_vertex")
            row = box.row()
            row.prop(context.scene.TextureBake_Props, "selected_ao")
            row.prop(context.scene.TextureBake_Props, "selected_thickness")
            row = box.row()
            row.prop(context.scene.TextureBake_Props, "selected_curvature")
            row.prop(context.scene.TextureBake_Props, "selected_lightmap")

            if bpy.context.scene.TextureBake_Props.selected_lightmap and bpy.context.scene.TextureBake_Props.global_mode == "pbr_bake":

                row = box.row()
                row.alignment = "RIGHT"
                row.prop(context.scene.cycles, "samples")

                # row = box.row()
                # row.alignment = "RIGHT"
                # row.prop(context.scene.cycles, "use_square_samples")

            if bpy.context.scene.TextureBake_Props.selected_lightmap:

                row = box.row()
                row.alignment = "RIGHT"
                row.prop(context.scene.TextureBake_Props, "selected_lightmap_denoise")
                if not bpy.context.scene.TextureBake_Props.saveExternal: row.enabled = False

                row=box.row()
                row.alignment = "RIGHT"
                row.prop(context.scene.TextureBake_Props, "lightmap_apply_colman")
                if not bpy.context.scene.TextureBake_Props.saveExternal: row.enabled = False


                # row = box.row()
                # row.alignment = "RIGHT"
                # if bpy.context.scene.cycles.use_square_samples:
                    # count = bpy.context.scene.cycles.samples * bpy.context.scene.cycles.samples
                # else:
                    # count = bpy.context.scene.cycles.samples

                # count = "{:,}".format(count)
                # row.label(text=f"Total samples: {count}")

            if bpy.context.scene.TextureBake_Props.selected_lightmap and bpy.context.scene.TextureBake_Props.global_mode == "pbr_bake":

                message_lines = [
                "PBR bake doesn't normally need a sample",
                "count, but a lightmap does"
                ]
                monkeyTip(message_lines, box)

            if bpy.context.scene.TextureBake_Props.selected_lightmap and bpy.context.scene.TextureBake_Props.global_mode == "cycles_bake":
                message_lines = [
                "Lightmap will have sample count",
                "settings that you have set for CyclesBake"
                ]
                monkeyTip(message_lines, box)


            row = box.row()
            #row.alignment = "RIGHT"
            row.operator("object.texture_bake_import_special_mats", icon='ADD')


        if context.scene.TextureBake_Props.selected_s2a or context.scene.TextureBake_Props.cycles_s2a:
            message_lines = [
            "Note: You are baking to taget object,",
            "so these special maps will be based on",
            "that target object only"
            ]
            monkeyTip(message_lines, box)


        #--------Texture Settings-------------------

        box = layout.box()
        row=box.row()
        #row.prop(bpy.context.scene.TextureBake_Props, "textures_show", icon="TRIA_DOWN" if bpy.context.scene.TextureBake_Props.textures_show else "TRIA_RIGHT", icon_only=True, emboss=False)
        #row.label(text="Texture settings", icon="PROP_ON")
        row.prop(bpy.context.scene.TextureBake_Props, "textures_show", text="Texture settings", icon="PROP_ON" if bpy.context.scene.TextureBake_Props.textures_show else "PROP_OFF", icon_only=False, emboss=False)

        if bpy.context.scene.TextureBake_Props.textures_show:

            row = box.row()
            row.label(text="Bake at:")
            row.scale_y = 0.5

            row = box.row()
            row.prop(context.scene.TextureBake_Props, "imgwidth")
            row.prop(context.scene.TextureBake_Props, "imgheight")

            row = box.row()
            row.operator("object.texture_bake_decrease_texture_res", icon = "TRIA_DOWN")
            row.operator("object.texture_bake_increase_texture_res", icon = "TRIA_UP")

            row=box.row()

            row = box.row()
            row.label(text="Output at:")
            row.scale_y = 0.5

            row = box.row()
            row.prop(context.scene.TextureBake_Props, "outputwidth")
            row.prop(context.scene.TextureBake_Props, "outputheight")

            row = box.row()
            row.operator("object.texture_bake_decrease_output_res", icon = "TRIA_DOWN")
            row.operator("object.texture_bake_increase_output_res", icon = "TRIA_UP")


            row = box.row()
            row.alignment = "RIGHT"
            row.prop(context.scene.render.bake, "margin", text="Bake Margin")

            row = box.row()
            row.prop(context.scene.TextureBake_Props, "everything32bitfloat")
            #if bpy.context.scene.TextureBake_Props.saveExternal:
                #row.enabled = False

            row = box.row()
            row.prop(context.scene.TextureBake_Props, "useAlpha")

            #For now, this is CyclesBake only
            if context.scene.TextureBake_Props.global_mode == "cycles_bake":
                row = box.row()
                row.prop(context.scene.TextureBake_Props, "tex_per_mat")

            row = box.row()
            row.prop(context.scene.TextureBake_Props, "mergedBake")
            # if context.scene.TextureBake_Props.useAlpha or context.scene.TextureBake_Props.selected_s2a or context.scene.TextureBake_Props.cycles_s2a or context.scene.TextureBake_Props.tex_per_mat:
                # row.enabled = False
            # if (context.scene.TextureBake_Props.advancedobjectselection and len(context.scene.TextureBake_Props.bakeobjs_advanced_list)<2) or ((not context.scene.TextureBake_Props.advancedobjectselection) and len(context.selected_objects)<2):
                # row.enabled = False

            if context.scene.TextureBake_Props.mergedBake:
                row = box.row()
                row.prop(context.scene.TextureBake_Props, "mergedBakeName")

        #--------Export Settings-------------------

        box = layout.box()
        row = box.row()
        #row.prop(bpy.context.scene.TextureBake_Props, "export_show", icon="TRIA_DOWN" if bpy.context.scene.TextureBake_Props.export_show else "TRIA_RIGHT", icon_only=True, emboss=False)
        #row.label(text="Export settings", icon="PROP_ON")
        row.prop(bpy.context.scene.TextureBake_Props, "export_show", text="Export settings", icon="PROP_ON" if bpy.context.scene.TextureBake_Props.export_show else "PROP_OFF", icon_only=False, emboss=False)

        if bpy.context.scene.TextureBake_Props.export_show:

            if functions.isBlendSaved():

                row = box.row()
                col = row.column()
                col.prop(context.scene.TextureBake_Props, "saveExternal")
                if(not functions.isBlendSaved()):
                    col.enabled = False
                col = row.column()
                col.prop(context.scene.TextureBake_Props, "saveObj")
                if(not functions.isBlendSaved()):
                    col.enabled = False


                if context.scene.TextureBake_Props.saveExternal or context.scene.TextureBake_Props.saveObj:
                    row = box.row()
                    #row.alignment = "RIGHT"
                    row.prop(context.scene.TextureBake_Props, "saveFolder", text="Folder name")


                    row = box.row()
                    row.prop(context.scene.TextureBake_Props, "exportFolderPerObject")
                    if bpy.context.scene.TextureBake_Props.saveExternal == False:
                        row.enabled = False

                    if context.scene.TextureBake_Props.saveObj:
                        row=box.row()
                        row.prop(context.scene.TextureBake_Props, "applymodsonmeshexport")
                        #row.alignment = "RIGHT"

                        row=box.row()
                        row.prop(context.scene.TextureBake_Props, "applytransformation")


                    row = box.row()
                    #row.alignment = "RIGHT"
                    row.prop(context.scene.TextureBake_Props, "folderdatetime")



                    if context.scene.TextureBake_Props.saveObj and not bpy.context.scene.TextureBake_Props.exportFolderPerObject:
                        row = box.row()
                        row.alignment = "RIGHT"
                        row.prop(context.scene.TextureBake_Props, "fbxName")


                    row = box.row()
                    #row.alignment = "RIGHT"
                    row.prop(context.scene.TextureBake_Props, "exportfileformat", text="Format")


                    row = box.row()
                    #row.alignment = "RIGHT"
                    if context.scene.TextureBake_Props.exportfileformat == "OPEN_EXR":
                        row.label(text="EXR exported as (max) 32bit")
                    else:
                        row.prop(context.scene.TextureBake_Props, "everything16bit")
                        if not context.scene.TextureBake_Props.saveExternal or context.scene.TextureBake_Props.exportfileformat == "JPEG"\
                        or context.scene.TextureBake_Props.exportfileformat == "TARGA":
                            row.enabled = False


                    if(context.scene.TextureBake_Props.global_mode == "pbr_bake"):
                        row = box.row()
                        row.prop(context.scene.TextureBake_Props, "selected_applycolmantocol")
                        if not bpy.context.scene.TextureBake_Props.selected_col:
                            row.enabled = False

                    if(context.scene.TextureBake_Props.global_mode == "cycles_bake"):
                        row = box.row()
                        row.prop(context.scene.TextureBake_Props, "exportcyclescolspace")
                        if bpy.context.scene.cycles.bake_type == "NORMAL":
                            row.enabled = False




                if not context.scene.TextureBake_Props.folderdatetime and context.scene.TextureBake_Props.saveExternal:
                    #Tip alert
                    message_lines = [
                        "Not appending date and time to folder name",
                        "means all previous bakes will be",
                        "overwritten. Be careful!"
                        ]
                    monkeyTip(message_lines, box)


                if context.scene.TextureBake_Props.everything32bitfloat and context.scene.TextureBake_Props.saveExternal and context.scene.TextureBake_Props.exportfileformat != "OPEN_EXR":
                    #Tip alert
                    message_lines = [
                        "You are creating all images as 32bit float.",
                        "You may want to export to EXR",
                        "to preserve your 32bit image(s)"
                        ]
                    monkeyTip(message_lines, box)


                if context.scene.TextureBake_Props.exportfileformat == "OPEN_EXR" and context.scene.TextureBake_Props.saveExternal:
                    #Tip alert
                    message_lines = [
                        "Note: EXR files cannot be exported",
                        "with colour management settings.",
                        "EXR doesn't support them. Even",
                        "Blender defaults will be ignored"
                        ]
                    monkeyTip(message_lines, box)

            else:
                row=box.row()
                row.label(text="Unavailable - Blend file not saved")


        #--------UV Settings-------------------
        box = layout.box()
        row = box.row()
        #row.prop(bpy.context.scene.TextureBake_Props, "uv_show", icon="TRIA_DOWN" if bpy.context.scene.TextureBake_Props.uv_show else "TRIA_RIGHT", icon_only=True, emboss=False)
        #row.label(text="UV settings", icon="PROP_ON")
        row.prop(bpy.context.scene.TextureBake_Props, "uv_show", text="UV settings", icon="PROP_ON" if bpy.context.scene.TextureBake_Props.uv_show else "PROP_OFF", icon_only=False, emboss=False)

        if bpy.context.scene.TextureBake_Props.uv_show:

            #UV mode
            row = box.row()
            row.prop(context.scene.TextureBake_Props, "uv_mode", expand=True)
            if context.scene.TextureBake_Props.saveExternal:
                row.enabled = True
            else:
                row.enabled = False


            if bpy.context.scene.TextureBake_Props.uv_mode == "udims":

                #Tip alert
                message_lines = [
                    "You must manually create UV map over",
                    "UDIM tiles prior to bake"
                    ]
                monkeyTip(message_lines, box)

                row = box.row()
                row.prop(context.scene.TextureBake_Props, "udim_tiles")



            if bpy.context.scene.TextureBake_Props.uv_mode == "udims":
                pass

            elif not context.scene.TextureBake_Props.tex_per_mat:
                row = box.row()
                row.prop(context.scene.TextureBake_Props, "newUVoption")

                if context.scene.TextureBake_Props.newUVoption:
                    objects = []
                    if context.scene.TextureBake_Props.advancedobjectselection:
                        objects = functions.advanced_object_selection_to_list()
                    else:
                        objects = context.selected_objects


                    if len(objects) >1 and not (context.scene.TextureBake_Props.selected_s2a or context.scene.TextureBake_Props.cycles_s2a):
                        row = box.row()
                        row.alignment = "RIGHT"
                        row.prop(context.scene.TextureBake_Props, "newUVmethod")
                        if context.scene.TextureBake_Props.newUVmethod == "SmartUVProject_Atlas" or context.scene.TextureBake_Props.newUVmethod == "SmartUVProject_Individual":
                            row = box.row()
                            row.alignment = "RIGHT"
                            row.prop(context.scene.TextureBake_Props, "unwrapmargin")
                        else:
                            row = box.row()
                            row.alignment = "RIGHT"
                            row.prop(context.scene.TextureBake_Props, "averageUVsize")
                            row.prop(context.scene.TextureBake_Props, "uvpackmargin")
                    else:
                        #One object selected
                        row = box.row()
                        row.alignment = "RIGHT"
                        row.label(text="Smart UV Project")
                        row.prop(context.scene.TextureBake_Props, "unwrapmargin")
            else:
                row = box.row()
                row.prop(context.scene.TextureBake_Props, "expand_mat_uvs")


            row = box.row()
            row.prop(context.scene.TextureBake_Props, "prefer_existing_sbmap")
            if context.scene.TextureBake_Props.newUVoption == True or context.scene.TextureBake_Props.expand_mat_uvs:
                row.enabled = False


            row = box.row()
            row.prop(context.scene.TextureBake_Props, "restoreOrigUVmap")

            if bpy.context.scene.TextureBake_Props.newUVoption and bpy.context.scene.TextureBake_Props.restoreOrigUVmap and not bpy.context.scene.TextureBake_Props.prepmesh:
                #Tip alert
                message_lines = [
                "Generating new UVs, but restoring originals",
                "after bake. Baked textures won't align with the",
                "original UVs. Manually change active UV map ",
                "after bake"
                ]


            if bpy.context.scene.TextureBake_Props.newUVoption and bpy.context.scene.TextureBake_Props.newUVmethod == "SmartUVProject_Individual" and bpy.context.scene.TextureBake_Props.mergedBake and bpy.context.scene.TextureBake_Props.uv_mode != "udims":
                #Tip alert
                message_lines = [
                "Current settings will unwrap objects",
                "individually but bake to one texture set",
                "Bakes will be on top of each other!"
                ]
                monkeyTip(message_lines, box)


            if not bpy.context.scene.TextureBake_Props.newUVoption  and bpy.context.scene.TextureBake_Props.mergedBake:
                #Tip alert
                message_lines = [
                "ALERT: You are baking multiple objects to one texture",
                "set with existing UVs. You will need to manually",
                "make sure those UVs don't overlap!"
                ]
                monkeyTip(message_lines, box)


            if bpy.context.scene.TextureBake_Props.newUVoption and not bpy.context.scene.TextureBake_Props.saveObj and not bpy.context.scene.TextureBake_Props.prepmesh and bpy.context.scene.TextureBake_Props.bgbake == "bg":
                #Tip alert
                message_lines = [
                "You are baking in background with new UVs, but",
                "not exporting FBX or using 'Copy Objects and Apply Bakes'",
                "You will recieve the baked textures on import, but you will",
                "have no access to an object with the new UV map!"
                ]
                monkeyTip(message_lines, box)



        #--------Other Settings-------------------


        box = layout.box()
        row = box.row()
        #row.prop(bpy.context.scene.TextureBake_Props, "other_show", icon="TRIA_DOWN" if bpy.context.scene.TextureBake_Props.other_show else "TRIA_RIGHT", icon_only=True, emboss=False)
        #row.label(text="Other settings", icon="PROP_ON")
        row.prop(bpy.context.scene.TextureBake_Props, "other_show", text="Other settings", icon="PROP_ON" if bpy.context.scene.TextureBake_Props.other_show else "PROP_OFF", icon_only=False, emboss=False)

        if bpy.context.scene.TextureBake_Props.other_show:

            row=box.row()
            row.alignment = 'LEFT'
            row.prop(context.scene.TextureBake_Props, "batchName")


            row = box.row()
            if bpy.context.scene.TextureBake_Props.bgbake == "fg":
                text = "Copy objects and apply bakes"
            else:
                text = "Copy objects and apply bakes (after import)"

            row.prop(context.scene.TextureBake_Props, "prepmesh", text=text)
            if context.scene.TextureBake_Props.tex_per_mat:
                row.enabled = False


            if (context.scene.TextureBake_Props.prepmesh == True):
                if bpy.context.scene.TextureBake_Props.bgbake == "fg":
                    text = "Hide source objects after bake"
                else:
                    text = "Hide source objects after bake (after import)"
                row = box.row()
                row.prop(context.scene.TextureBake_Props, "hidesourceobjects", text=text)

                row = box.row()
                row.prop(context.scene.TextureBake_Props, "createglTFnode")
                if bpy.context.scene.TextureBake_Props.createglTFnode:
                    row.prop(context.scene.TextureBake_Props, "glTFselection", text="")

            row = box.row()
            row.prop(context.scene.TextureBake_Props, "preserve_materials")



            if bpy.context.preferences.addons["cycles"].preferences.has_active_device():
                row=box.row()
                row.prop(context.scene.cycles, "device")
                row = box.row()
                row.alignment = "RIGHT"
                row.prop(context.scene.TextureBake_Props, "memLimit")
                if bpy.context.scene.cycles.device == "CPU":
                    row.enabled = False
            else:
                row=box.row()
                row.label(text="No valid GPU device in Blender Preferences. Using CPU.")

            if bpy.context.preferences.addons["cycles"].preferences.compute_device_type == "OPTIX" and bpy.context.preferences.addons["cycles"].preferences.has_active_device():
                #Tip alert
                message_lines = [
                "Other users have reported problems baking",
                "with GPU and OptiX. This is a Blender issue",
                "If you encounter problems bake with CPU"
                ]
                monkeyTip(message_lines, box)


            if bpy.context.scene.TextureBake_Props.global_mode == "pbr_bake" and\
                not bpy.context.scene.TextureBake_Props.selected_col and\
                not bpy.context.scene.TextureBake_Props.selected_metal and\
                not bpy.context.scene.TextureBake_Props.selected_sss and\
                not bpy.context.scene.TextureBake_Props.selected_ssscol and\
                not bpy.context.scene.TextureBake_Props.selected_rough and\
                not bpy.context.scene.TextureBake_Props.selected_normal and\
                not bpy.context.scene.TextureBake_Props.selected_trans and\
                not bpy.context.scene.TextureBake_Props.selected_transrough and\
                not bpy.context.scene.TextureBake_Props.selected_clearcoat and\
                not bpy.context.scene.TextureBake_Props.selected_clearcoat_rough and\
                not bpy.context.scene.TextureBake_Props.selected_emission and\
                not bpy.context.scene.TextureBake_Props.selected_specular and\
                not bpy.context.scene.TextureBake_Props.selected_alpha and\
                bpy.context.scene.TextureBake_Props.prepmesh and\
                (bpy.context.scene.TextureBake_Props.selected_col_mats or \
                    bpy.context.scene.TextureBake_Props.selected_col_vertex or \
                    bpy.context.scene.TextureBake_Props.selected_ao or \
                    bpy.context.scene.TextureBake_Props.selected_thickness or \
                    bpy.context.scene.TextureBake_Props.selected_curvature):

                        message_lines = [
                        "You are baking only special maps (no primary)",
                        "while using 'Copy objects and apply bakes'",
                        "Special maps will be in the new object(s)",
                        "material(s), but disconnected"
                        ]
                        monkeyTip(message_lines, box)




        #-------------Channel packing --------------------------
        if(context.scene.TextureBake_Props.global_mode == "pbr_bake"):

            box = layout.box()
            row = box.row()
            #row.prop(bpy.context.scene.TextureBake_Props, "channelpacking_show", icon="TRIA_DOWN" if bpy.context.scene.TextureBake_Props.channelpacking_show else "TRIA_RIGHT", icon_only=True, emboss=False)
            #row.label(text="Channel packing", icon="PROP_ON")
            row.prop(bpy.context.scene.TextureBake_Props, "channelpacking_show", text="Channel packing", icon="PROP_ON" if bpy.context.scene.TextureBake_Props.channelpacking_show else "PROP_OFF", icon_only=False, emboss=False)

            if bpy.context.scene.TextureBake_Props.channelpacking_show:

                if not functions.isBlendSaved():

                    row=box.row()
                    row.label(text="Unavailable - Blend file not saved")

                elif not bpy.context.scene.TextureBake_Props.saveExternal:

                    row=box.row()
                    row.label(text="Unavailable - You must be exporting your bakes")

                else:

                    row=box.row()
                    col = row.column()

                    col.template_list("CPTEX_UL_List", "CP Textures List", context.scene.TextureBake_Props,
                                          "cp_list", context.scene.TextureBake_Props, "cp_list_index")
                    col = row.column()
                    col.operator("object.texture_bake_cptex_delete", text="", icon="CANCEL")
                    col.operator("object.texture_bake_cptex_setdefaults", text="", icon="MONKEY")

                    row=box.row()
                    row.prop(context.scene.TextureBake_Props, "cp_name")
                    row=box.row()
                    row.prop(context.scene.TextureBake_Props, "channelpackfileformat", text="Format")
                    row=box.row()
                    row.scale_y=0.7
                    row.prop(context.scene.TextureBake_Props, "cptex_R", text="R")
                    row=box.row()
                    row.scale_y=0.7
                    row.prop(context.scene.TextureBake_Props, "cptex_G", text="G")
                    row=box.row()
                    row.scale_y=0.7
                    row.prop(context.scene.TextureBake_Props, "cptex_B", text="B")
                    row=box.row()
                    row.scale_y=0.7
                    row.prop(context.scene.TextureBake_Props, "cptex_A", text="A")


                    cp_list = bpy.context.scene.TextureBake_Props.cp_list
                    current_name = bpy.context.scene.TextureBake_Props.cp_name
                    if current_name in cp_list: #Editing a cpt that is already there
                        index = cp_list.find(current_name)
                        cpt = cp_list[index]

                        if cpt.R != bpy.context.scene.TextureBake_Props.cptex_R or\
                            cpt.G != bpy.context.scene.TextureBake_Props.cptex_G or\
                            cpt.B != bpy.context.scene.TextureBake_Props.cptex_B or\
                            cpt.A != bpy.context.scene.TextureBake_Props.cptex_A or\
                            cpt.file_format != bpy.context.scene.TextureBake_Props.channelpackfileformat:

                                row = box.row()
                                row.alert=True
                                text = f"Update {current_name} (!!not saved!!)"
                                row.operator("object.texture_bake_cptex_add", text=text, icon="ADD")
                        else: #No changes, no button
                            text = f"Editing {current_name}"
                            row = box.row()
                            row.label(text=text)
                            row.alignment = 'CENTER'

                    else: #New item
                        row = box.row()
                        text = "Add new (!!not saved!!)"
                        row.alert = True
                        row.operator("object.texture_bake_cptex_add", text=text, icon="ADD")



                    if bpy.context.scene.TextureBake_Props.cptex_R == "" or\
                        bpy.context.scene.TextureBake_Props.cptex_G == "" or\
                        bpy.context.scene.TextureBake_Props.cptex_B == "" or\
                        bpy.context.scene.TextureBake_Props.cptex_A == "":
                            row.enabled = False

                if context.scene.TextureBake_Props.channelpackfileformat != "OPEN_EXR":
                    lines = [\
                        "Other formats MIGHT work, but the",\
                        "only way to get consistent, reliable",\
                        "channel packing in Blender is to use",\
                        "OpenEXR. Use OpenEXR if you can"]
                    monkeyTip(lines, box)


        #-------------Buttons-------------------------


        row = layout.row()
        row.scale_y = 1.5
        row.prop(context.scene.TextureBake_Props, "bgbake", expand=True)

        if bpy.context.scene.TextureBake_Props.bgbake == "bg":
            row=layout.row()
            row.prop(context.scene.TextureBake_Props, "bgbake_name", text="Name: ")

        row = layout.row()
        row.scale_y = 2
        row.operator("object.texture_bake_mapbake", icon='RENDER_RESULT')




        box = layout.box()
        row=box.row()
        row.label(text="Background bakes")

        row = box.row()
        row.prop(context.scene.TextureBake_Props, "bg_status_show", text="", icon="TRIA_DOWN" if bpy.context.scene.TextureBake_Props.bg_status_show else "TRIA_RIGHT", icon_only=False, emboss=False)
        row.label(text="Show status of background bakes")

        if context.scene.TextureBake_Props.bg_status_show:

            if len(bgbake_ops.bgops_list) == 0 and len(bgbake_ops.bgops_list_finished) == 0:
                row = box.row()
                row.label(text="No running or finished background bakes", icon="MONKEY")
                row.scale_y = 0.7
            else:
                for p in bgbake_ops.bgops_list:
                    t = Path(tempfile.gettempdir())
                    t = t / f"TextureBake_Bgbake_{str(p[0].pid)}"

                    try:
                        with open(str(t), "r") as progfile:
                            progress = progfile.readline()
                    except:
                        #No file yet, as no bake operation has completed yet. Holding message
                        progress = 0

                    row = box.row()
                    name = p[3]
                    if name == "": name = "Untitled"
                    row.label(text=f"{name} - baking in progress {progress}%", icon="GHOST_DISABLED")
                    row.scale_y = 0.7


            if len(bgbake_ops.bgops_list_finished) == 0:
                pass
            else:
                for p in bgbake_ops.bgops_list_finished:
                    row = box.row()
                    row.scale_y = 0.7
                    col = row.column()
                    name = p[3]
                    if name == "": name = "Untitled"
                    col.label(text=f"{name} - finished!", icon="GHOST_ENABLED")
                    col = row.column()
                    col.operator("object.texture_bake_bgbake_import_individual", text="", icon="IMPORT").pnum = int(p[0].pid)
                    col = row.column()
                    col.operator("object.texture_bake_bgbake_delete_individual", text="", icon="CANCEL").pnum = int(p[0].pid)




        #-----Import buttons-----------------

        row = box.row()
        row.scale_y = 1.5

        # - BG status button
        # col = row.column()
        # if len(bgbake_ops.bgops_list) == 0:
            # enable = False
            # icon = "GHOST_DISABLED"
        # else:
            # enable = True
            # icon = "GHOST_ENABLED"

        # col.operator("object.texture_bake_bgbake_status", text="Status", icon=icon)
        # col.enabled = enable

        # - BG import button

        col = row.column()
        if len(bgbake_ops.bgops_list_finished) != 0:
            enable = True
            icon = "IMPORT"
        else:
            enable = False
            icon = "IMPORT"

        col.operator("object.texture_bake_bgbake_import", text="Import all", icon=icon)
        col.enabled = enable


        #BG erase button

        col = row.column()
        if len(bgbake_ops.bgops_list_finished) != 0:
            enable = True
            icon = "TRASH"
        else:
            enable = False
            icon = "TRASH"

        col.operator("object.texture_bake_bgbake_clear", text="Discard all", icon=icon)
        col.enabled = enable


        # row = box.row()
        # row.alignment = 'CENTER'
        # row.label(text=f"BG bakes running - {len(bgbake_ops.bgops_list)} | Available for import - {len(bgbake_ops.bgops_list_finished)}")

        #Tip alert
        # if context.scene.TextureBake_Props.bg_status_show and len(bgbake_ops.bgops_list) > 0:
            # message_lines = [
            # "NOTE: The list of BG bakes will only really",
            # "refresh when your mouse cursor is over",
            # "the TextureBake panel (Blender limitation)"
            # ]
            # monkeyTip(message_lines, box)


        if(context.scene.TextureBake_Props.global_mode == "pbr_bake"):
            row = layout.row()
            row.scale_y = 1.5
            row.operator("object.texture_bake_sketchfabupload", text="Sketchfab Upload", icon="EXPORT")

        box = layout.box()
        row = box.row()
        #row.operator("object.texture_bake_popnodegroups")




class TextureBakePreferences(bpy.types.AddonPreferences):
    # this must match the add-on name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = __package__

    apikey: bpy.props.StringProperty(name="Sketchfab API Key: ")
    img_name_format: bpy.props.StringProperty(name="Image format string",
        default="%OBJ%_%BATCH%_%BAKEMODE%_%BAKETYPE%")

    justupdated = False

    #Aliases
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
    ssscol_alias: bpy.props.StringProperty(name="SSS Colour", default="ssscol")

    ao_alias: bpy.props.StringProperty(name=TextureBakeConstants.AO, default="ao")
    curvature_alias: bpy.props.StringProperty(name=TextureBakeConstants.CURVATURE, default="curvature")
    thickness_alias: bpy.props.StringProperty(name=TextureBakeConstants.THICKNESS, default="thickness")
    vertexcol_alias: bpy.props.StringProperty(name=TextureBakeConstants.VERTEXCOL, default="vertexcol")
    colid_alias: bpy.props.StringProperty(name=TextureBakeConstants.COLOURID, default="colid")
    lightmap_alias: bpy.props.StringProperty(name=TextureBakeConstants.LIGHTMAP, default="lightmap")

    @classmethod
    def reset_img_string(self):
        prefs = bpy.context.preferences.addons[__package__].preferences
        #prefs.img_name_format = "BOO"
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
        row = layout.row()
        row.label(text="Enter your Sketchfab API key below. Don't forget to click \"Save Preferences\" after.")
        row = layout.row()
        row.prop(self, "apikey")
        row = layout.row()
        row.scale_y = 2
        row.operator("object.texture_bake_releasenotes", icon="MOD_WAVE")

        box = layout.box()
        row = box.row()
        row.label(text="Format string for image names")
        row = box.row()
        row.label(text="Valid variables are %OBJ% (object name or 'MergedBake'), %BATCH% (batch name),")
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
        row.operator("object.texture_bake_default_imgname_string")

        #PBR Aliases
        box = layout.box()


        row = box.row()
        row.label(text="Aliases for PBR bake types")

        row = box.row()
        row.label(text="WARNING: Sketchfab looks for certain values. Changing these may break SF Upload")

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

        #Specials Aliases
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

        #Reset button
        box = layout.box()
        row = box.row()
        row.operator("object.texture_bake_default_aliases")



class OBJECT_OT_texture_bake_releasenotes(bpy.types.Operator):
    """View the TextureBake release notes (opens browser)"""
    bl_idname = "object.texture_bake_releasenotes"
    bl_label = "View the TextureBake release notes (opens browser)"

    def execute(self, context):
        import webbrowser
        webbrowser.open('http://www.toohey.co.uk/TextureBake/releasenotes3.html', new=2)
        return {'FINISHED'}



#---------------------Advanced object selection list -----------------------------------
class ListItem(PropertyGroup):
    """Group of properties representing an item in the list."""

    obj_point:   PointerProperty(
            name="Bake Object",
            description="An object in the scene to be baked",
            #update=obj_point_update,
            type=bpy.types.Object)

    name: StringProperty(
           name="Name",
           description="A name for this item",
           default= "Untitled")

class BAKEOBJECTS_UL_List(UIList):
    """UIList."""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):

        # We could write some code to decide which icon to use here...
        custom_icon = 'OBJECT_DATAMODE'

        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=item.obj_point.name, icon = custom_icon)

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)


class LIST_OT_NewItem(Operator):
    """Add selected object(s) to the bake list"""

    bl_idname = "bakeobjs_advanced_list.new_item"
    bl_label = "Add a new object to bake list"

    @classmethod
    def poll(cls, context):
        return len(bpy.context.selected_objects)

    def execute(self, context):
        #Lets get rid of the non-mesh objects
        functions.deselect_all_not_mesh()


        objs = bpy.context.selected_objects.copy()

        #Check all mesh. Throw error if not
        for obj in objs:

            if obj.type != "MESH":
                self.report({"ERROR"}, f"ERROR: Selected object '{obj.name}' is not mesh")
                return {"CANCELLED"}


        #Add if not already in the list
        for obj in objs:
            r = [i.name for i in context.scene.TextureBake_Props.bakeobjs_advanced_list if i.name == obj.name]

            if len(r) == 0:
                n = context.scene.TextureBake_Props.bakeobjs_advanced_list.add()
                n.obj_point = obj
                n.name = obj.name

        #Throw in a refresh
        functions.update_advanced_object_list()

        return{'FINISHED'}


class LIST_OT_DeleteItem(Operator):
    """Remove the selected object from the bake list."""

    bl_idname = "bakeobjs_advanced_list.del_item"
    bl_label = "Deletes an item"

    @classmethod
    def poll(cls, context):
        return context.scene.TextureBake_Props.bakeobjs_advanced_list

    def execute(self, context):
        my_list = context.scene.TextureBake_Props.bakeobjs_advanced_list
        index = context.scene.TextureBake_Props.bakeobjs_advanced_list_index

        my_list.remove(index)
        context.scene.TextureBake_Props.bakeobjs_advanced_list_index = min(max(0, index - 1), len(my_list) - 1)

        #Throw in a refresh
        functions.update_advanced_object_list()

        return{'FINISHED'}


class LIST_OT_ClearAll(Operator):
    """Clear the object list"""

    bl_idname = "bakeobjs_advanced_list.clear_all"
    bl_label = "Deletes an item"

    @classmethod
    def poll(cls, context):
        return True
        #return context.scene.TextureBake_Props.bakeobjs_advanced_list

    def execute(self, context):
        my_list = context.scene.TextureBake_Props.bakeobjs_advanced_list
        my_list.clear()

        #Throw in a refresh
        functions.update_advanced_object_list()


        return{'FINISHED'}



class LIST_OT_MoveItem(Operator):
    """Move an object in the list."""

    bl_idname = "bakeobjs_advanced_list.move_item"
    bl_label = "Move an item in the list"

    direction: bpy.props.EnumProperty(items=(('UP', 'Up', ""),
                                              ('DOWN', 'Down', ""),))

    @classmethod
    def poll(cls, context):
        return context.scene.TextureBake_Props.bakeobjs_advanced_list

    def move_index(self):
        """ Move index of an item render queue while clamping it. """

        index = bpy.context.scene.TextureBake_Props.bakeobjs_advanced_list_index
        list_length = len(bpy.context.scene.TextureBake_Props.bakeobjs_advanced_list) - 1  # (index starts at 0)
        new_index = index + (-1 if self.direction == 'UP' else 1)

        bpy.context.scene.TextureBake_Props.bakeobjs_advanced_list_index = max(0, min(new_index, list_length))

    def execute(self, context):
        my_list = context.scene.TextureBake_Props.bakeobjs_advanced_list
        index = context.scene.TextureBake_Props.bakeobjs_advanced_list_index

        neighbor = index + (-1 if self.direction == 'UP' else 1)
        my_list.move(neighbor, index)
        self.move_index()

        #Throw in a refresh
        functions.update_advanced_object_list()

        return{'FINISHED'}


class LIST_OT_Refresh(Operator):
    """Refresh the list to remove objects"""

    bl_idname = "bakeobjs_advanced_list.refresh"
    bl_label = "Refresh the list"


    @classmethod
    def poll(cls, context):
        #return context.scene.TextureBake_Props.bakeobjs_advanced_list
        return True


    def execute(self, context):
        functions.update_advanced_object_list()

        return{'FINISHED'}

#----------------------Presets


class PRESETS_UL_List(UIList):
    """UIList."""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):

        # We could write some code to decide which icon to use here...
        custom_icon = 'PACKAGE'

        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=item.name, icon = custom_icon)

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)

class PresetItem(PropertyGroup):
    """Group of properties representing a TextureBake preset."""

    name: bpy.props.StringProperty(
           name="Name",
           description="A name for this item",
           default= "Untitled")

#-----------------------Channel packing
class CPTEX_UL_List(UIList):
    """UIList."""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):

        # We could write some code to decide which icon to use here...
        custom_icon = 'NODE_COMPOSITING'

        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=item.name, icon = custom_icon)

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)



class CPTexItem(PropertyGroup):
    """Group of properties representing a TextureBake CP Texture."""

    name: bpy.props.StringProperty(
           name="Name",
           description="A name for this item",
           default= "Untitled")
    R: bpy.props.StringProperty(
           name="R",
           description="Bake type for R channel")
    G: bpy.props.StringProperty(
           name="G",
           description="Bake type for G channel")
    B: bpy.props.StringProperty(
           name="B",
           description="Bake type for B channel")
    A: bpy.props.StringProperty(
           name="A",
           description="Bake type for A channel")
    file_format: bpy.props.StringProperty(
           name="File Format",
           description="File format for CP texture")
