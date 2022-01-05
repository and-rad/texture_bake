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
import sys
import subprocess
import os
import tempfile
import json

from pathlib import Path
from datetime import datetime
from math import floor

from . import functions
from . import bakefunctions
from .bake_operation import BakeOperation, MasterOperation, BakeStatus, bakes_to_list, TextureBakeConstants
from .bg_bake import background_bake_ops


class TEXTUREBAKE_OT_bake(bpy.types.Operator):
    """Start the baking process"""
    bl_idname = "texture_bake.bake"
    bl_label = "Bake Textures"

    def execute(self, context):
        def commence_bake(needed_bake_modes):
            # Prepare the BakeStatus tracker for progress bar
            num_of_objects = 0
            if bpy.context.scene.TextureBake_Props.use_object_list:
                num_of_objects = len(bpy.context.scene.TextureBake_Props.object_list)
            else:
                num_of_objects = len(bpy.context.selected_objects)

            total_maps = 0
            for need in needed_bake_modes:
                if need == TextureBakeConstants.PBR:
                    total_maps+=(bakes_to_list(justcount=True) * num_of_objects)
                if need == TextureBakeConstants.PBRS2A:
                    total_maps+=1*bakes_to_list(justcount=True)
                if need == TextureBakeConstants.CYCLESBAKE and not bpy.context.scene.TextureBake_Props.selected_to_target:
                    total_maps+=1* num_of_objects
                if need == TextureBakeConstants.CYCLESBAKE and bpy.context.scene.TextureBake_Props.selected_to_target:
                    total_maps+=1
                if need == TextureBakeConstants.SPECIALS:
                    total_maps+=(functions.import_needed_specials_materials(justcount = True) * num_of_objects)
                    if bpy.context.scene.TextureBake_Props.selected_col_mats: total_maps+=1*num_of_objects
                    if bpy.context.scene.TextureBake_Props.selected_col_vertex: total_maps+=1*num_of_objects
                if need in [TextureBakeConstants.SPECIALS_CYCLES_TARGET_ONLY, TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY]:
                    total_maps+=(functions.import_needed_specials_materials(justcount = True))
                    if bpy.context.scene.TextureBake_Props.selected_col_mats: total_maps+=1
                    if bpy.context.scene.TextureBake_Props.selected_col_vertex: total_maps+=1

            BakeStatus.total_maps = total_maps

            # Clear the MasterOperation stuff
            MasterOperation.clear()

            # Set master operation variables
            MasterOperation.merged_bake = bpy.context.scene.TextureBake_Props.merged_bake
            MasterOperation.merged_bake_name = bpy.context.scene.TextureBake_Props.merged_bake_name

            # Need to know the total operations
            MasterOperation.total_bake_operations = len(needed_bake_modes)

            # Master list of all ops
            bops = []

            for need in needed_bake_modes:
                # Create operation
                bop = BakeOperation()
                bop.bake_mode = need

                bops.append(bop)
                functions.print_msg(f"Created operation for {need}")

            # Run queued operations
            for bop in bops:
                MasterOperation.this_bake_operation_num+=1
                MasterOperation.current_bake_operation = bop
                if bop.bake_mode == TextureBakeConstants.PBR:
                    functions.print_msg("Running PBR bake")
                    bakefunctions.do_bake()
                elif bop.bake_mode == TextureBakeConstants.PBRS2A:
                    functions.print_msg("Running PBR S2A bake")
                    bakefunctions.do_bake_selected_to_target()
                elif bop.bake_mode == TextureBakeConstants.CYCLESBAKE:
                    functions.print_msg("Running Cycles bake")
                    bakefunctions.cycles_bake()
                elif bop.bake_mode in [TextureBakeConstants.SPECIALS, TextureBakeConstants.SPECIALS_CYCLES_TARGET_ONLY, TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY]:
                    functions.print_msg("Running Specials bake")
                    bakefunctions.specials_bake()

            # Call channel packing
            # Only possilbe if we baked some kind of PBR. At the moment, can't have non-S2A and S2A
            if len([bop for bop in bops if bop.bake_mode == TextureBakeConstants.PBR]) > 0:
                # Should still be active from last bake op
                objects = MasterOperation.current_bake_operation.bake_objects
                bakefunctions.channel_packing(objects)
            if len([bop for bop in bops if bop.bake_mode == TextureBakeConstants.PBRS2A]) > 0:
                # Should still be active from last bake op
                objects = [MasterOperation.current_bake_operation.sb_target_object]
                bakefunctions.channel_packing(objects)

            return True

        needed_bake_modes = []
        if bpy.context.scene.TextureBake_Props.global_mode == "pbr_bake" and not bpy.context.scene.TextureBake_Props.selected_to_target:
            needed_bake_modes.append(TextureBakeConstants.PBR)
        if bpy.context.scene.TextureBake_Props.global_mode == "pbr_bake" and bpy.context.scene.TextureBake_Props.selected_to_target:
            needed_bake_modes.append(TextureBakeConstants.PBRS2A)
        if bpy.context.scene.TextureBake_Props.global_mode == "cycles_bake":
            needed_bake_modes.append(TextureBakeConstants.CYCLESBAKE)

        if functions.any_specials() and TextureBakeConstants.PBRS2A in needed_bake_modes:
            needed_bake_modes.append(TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY)
        elif functions.any_specials() and TextureBakeConstants.CYCLESBAKE in needed_bake_modes and bpy.context.scene.TextureBake_Props.selected_to_target:
            needed_bake_modes.append(TextureBakeConstants.SPECIALS_CYCLES_TARGET_ONLY)
        elif functions.any_specials():
            needed_bake_modes.append(TextureBakeConstants.SPECIALS)

        # Clear the progress stuff
        BakeStatus.current_map = 0
        BakeStatus.total_maps = 0

        # If we have been called in background mode, just get on with it. Checks should be done.
        if "--background" in sys.argv:
            if "TextureBake_Bakes" in bpy.data.collections:
                # Remove any prior baked objects
                bpy.data.collections.remove(bpy.data.collections["TextureBake_Bakes"])

            # Bake
            ts = datetime.now()
            commence_bake(needed_bake_modes)
            tf = datetime.now()
            s = (tf-ts).seconds
            functions.print_msg(f"Time taken - {s} seconds ({floor(s/60)} minutes, {s%60} seconds)")

            self.report({"INFO"}, "Bake complete")
            return {'FINISHED'}

        # We are in foreground, do usual checks
        for mode in needed_bake_modes:
            if not functions.check_scene(bpy.context.selected_objects, mode):
                return {"CANCELLED"}

        # If the user requested background mode, fire that up now and exit
        if bpy.context.scene.TextureBake_Props.background_bake == "bg":
            bpy.ops.wm.save_mainfile()
            filepath = filepath = bpy.data.filepath
            process = subprocess.Popen(
                [bpy.app.binary_path, "--background",filepath, "--python-expr",\
                "import bpy;\
                import os;\
                from pathlib import Path;\
                savepath=Path(bpy.data.filepath).parent / (str(os.getpid()) + \".blend\");\
                bpy.ops.wm.save_as_mainfile(filepath=str(savepath), check_existing=False);\
                bpy.ops.texture_bake.bake();"],
                shell=False)

            background_bake_ops.bgops_list.append([process, bpy.context.scene.TextureBake_Props.prep_mesh,
                bpy.context.scene.TextureBake_Props.hide_source_objects, bpy.context.scene.TextureBake_Props.background_bake_name])

            self.report({"INFO"}, "Background bake process started")
            return {'FINISHED'}

        # If we are doing this here and now, get on with it
        # Create a bake operation
        ts = datetime.now()
        commence_bake(needed_bake_modes)
        tf = datetime.now()
        s = (tf-ts).seconds
        functions.print_msg(f"Time taken - {s} seconds ({floor(s/60)} minutes, {s%60} seconds)")

        self.report({"INFO"}, "Bake complete")
        return {'FINISHED'}


class TEXTUREBAKE_OT_pbr_select_all(bpy.types.Operator):
    """Select all PBR bake types"""
    bl_idname = "texture_bake.pbr_select_all"
    bl_label = "Select All"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        bpy.context.scene.TextureBake_Props.selected_col = True
        bpy.context.scene.TextureBake_Props.selected_metal = True
        bpy.context.scene.TextureBake_Props.selected_rough = True
        bpy.context.scene.TextureBake_Props.selected_normal = True
        bpy.context.scene.TextureBake_Props.selected_trans = True
        bpy.context.scene.TextureBake_Props.selected_transrough = True
        bpy.context.scene.TextureBake_Props.selected_emission = True
        bpy.context.scene.TextureBake_Props.selected_clearcoat = True
        bpy.context.scene.TextureBake_Props.selected_clearcoat_rough = True
        bpy.context.scene.TextureBake_Props.selected_specular = True
        bpy.context.scene.TextureBake_Props.selected_alpha = True
        bpy.context.scene.TextureBake_Props.selected_sss = True
        bpy.context.scene.TextureBake_Props.selected_ssscol = True
        return {'FINISHED'}


class TEXTUREBAKE_OT_pbr_select_none(bpy.types.Operator):
    """Select none PBR bake types"""
    bl_idname = "texture_bake.pbr_select_none"
    bl_label = "Select None"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        bpy.context.scene.TextureBake_Props.selected_col = False
        bpy.context.scene.TextureBake_Props.selected_metal = False
        bpy.context.scene.TextureBake_Props.selected_rough = False
        bpy.context.scene.TextureBake_Props.selected_normal = False
        bpy.context.scene.TextureBake_Props.selected_trans = False
        bpy.context.scene.TextureBake_Props.selected_transrough = False
        bpy.context.scene.TextureBake_Props.selected_emission = False
        bpy.context.scene.TextureBake_Props.selected_clearcoat = False
        bpy.context.scene.TextureBake_Props.selected_clearcoat_rough = False
        bpy.context.scene.TextureBake_Props.selected_specular = False
        bpy.context.scene.TextureBake_Props.selected_alpha = False
        bpy.context.scene.TextureBake_Props.selected_sss = False
        bpy.context.scene.TextureBake_Props.selected_ssscol = False
        return {'FINISHED'}


class TEXTUREBAKE_OT_reset_name_format(bpy.types.Operator):
    """Reset the image name format string to default"""
    bl_idname = "texture_bake.reset_name_format"
    bl_label = "Restore Defaults"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        bpy.context.preferences.addons[__package__].preferences.property_unset("img_name_format")
        bpy.ops.wm.save_userpref()
        return {'FINISHED'}


class TEXTUREBAKE_OT_reset_aliases(bpy.types.Operator):
    """Reset the baked image name aliases"""
    bl_idname = "texture_bake.reset_aliases"
    bl_label = "Restore Defaults"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        bpy.context.preferences.addons[__package__].preferences.reset_aliases()
        return {'FINISHED'}


class TEXTUREBAKE_OT_bake_import(bpy.types.Operator):
    """Import baked objects previously baked in the background"""
    bl_idname = "texture_bake.bake_import"
    bl_label = "Import baked objects previously baked in the background"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        if bpy.context.mode != "OBJECT":
            self.report({"ERROR"}, "You must be in object mode")
            return {'CANCELLED'}

        for p in background_bake_ops.bgops_list_finished:
            savepath = Path(bpy.data.filepath).parent
            pid_str = str(p[0].pid)
            path = savepath / (pid_str + ".blend")
            path = str(path) + "\\Collection\\"

            # Record the objects and collections before append (as append doesn't give us a reference to the new stuff)
            functions.spot_new_items(initialise=True, item_type="objects")
            functions.spot_new_items(initialise=True, item_type="collections")
            functions.spot_new_items(initialise=True, item_type="images")

            # Append
            bpy.ops.wm.append(filename="TextureBake_Bakes", directory=path, use_recursive=False, active_collection=False)

            # If we didn't actually want the objects, delete them
            if not p[1]:
                # Delete objects we just imported (leaving only textures)
                for obj_name in functions.spot_new_items(initialise=False, item_type = "objects"):
                    bpy.data.objects.remove(bpy.data.objects[obj_name])
                for col_name in functions.spot_new_items(initialise=False, item_type = "collections"):
                    bpy.data.collections.remove(bpy.data.collections[col_name])

            # If we have to hide the source objects, do it
            if p[2]:
                # Get the newly introduced objects:
                objects_before_names = functions.spot_new_items(initialise=False, item_type="objects")

                for obj_name in objects_before_names:
                    # Try this in case there are issues with long object names.. better than a crash
                    try:
                        bpy.data.objects[obj_name.replace("_Baked", "")].hide_set(True)
                    except:
                        pass

            # Delete the temp blend file
            try:
                os.remove(str(savepath / pid_str) + ".blend")
                os.remove(str(savepath / pid_str) + ".blend1")
            except:
                pass

        # Clear list for next time
        background_bake_ops.bgops_list_finished = []

        # Confirm back to user
        self.report({"INFO"}, "Import complete")

        messagelist = []
        messagelist.append(f"{len(functions.spot_new_items(initialise=False, item_type='objects'))} objects imported")
        messagelist.append(f"{len(functions.spot_new_items(initialise=False, item_type='images'))} textures imported")
        functions.show_message_box(messagelist, "Import complete", icon = 'INFO')

        # If we imported an image, and we already had an image with the same name, get rid of the original in favour of the imported
        new_images_names = functions.spot_new_items(initialise=False, item_type="images")

        # Find any .001s
        for imgname in new_images_names:
            try:
                int(imgname[-3:])

                # Delete the existing version
                bpy.data.images.remove(bpy.data.images[imgname[0:-4]])

                # Rename our version
                bpy.data.images[imgname].name = imgname[0:-4]

            except ValueError:
                pass

        return {'FINISHED'}


class TEXTUREBAKE_OT_bake_import_individual(bpy.types.Operator):
    """Import baked objects previously baked in the background"""
    bl_idname = "texture_bake.bake_import_individual"
    bl_label = "Import baked objects previously baked in the background"
    bl_options = {'INTERNAL'}

    pnum: bpy.props.IntProperty()

    def execute(self, context):
        if bpy.context.mode != "OBJECT":
            self.report({"ERROR"}, "You must be in object mode")
            return {'CANCELLED'}

        # Need to get the actual SINGLE entry from the list
        p = [p for p in background_bake_ops.bgops_list_finished if p[0].pid == self.pnum]
        assert(len(p) == 1)
        p = p[0]

        savepath = Path(bpy.data.filepath).parent
        pid_str = str(p[0].pid)
        path = savepath / (pid_str + ".blend")
        path = str(path) + "\\Collection\\"

        # Record the objects and collections before append (as append doesn't give us a reference to the new stuff)
        functions.spot_new_items(initialise=True, item_type="objects")
        functions.spot_new_items(initialise=True, item_type="collections")
        functions.spot_new_items(initialise=True, item_type="images")

        # Append
        bpy.ops.wm.append(filename="TextureBake_Bakes", directory=path, use_recursive=False, active_collection=False)

        # If we didn't actually want the objects, delete them
        if not p[1]:
            for obj_name in functions.spot_new_items(initialise=False, item_type = "objects"):
                bpy.data.objects.remove(bpy.data.objects[obj_name])
            for col_name in functions.spot_new_items(initialise=False, item_type = "collections"):
                bpy.data.collections.remove(bpy.data.collections[col_name])

        # If we have to hide the source objects, do it
        if p[2]:
            # Get the newly introduced objects:
            objects_before_names = functions.spot_new_items(initialise=False, item_type="objects")

            for obj_name in objects_before_names:
                # Try this in case there are issues with long object names.. better than a crash
                try:
                    bpy.data.objects[obj_name.replace("_Baked", "")].hide_set(True)
                except:
                    pass

        # Delete the temp blend file
        try:
            os.remove(str(savepath / pid_str) + ".blend")
            os.remove(str(savepath / pid_str) + ".blend1")
        except:
            pass

        # Remove this P from the list
        background_bake_ops.bgops_list_finished = [p for p in background_bake_ops.bgops_list_finished if p[0].pid != self.pnum]

        # Confirm back to user
        self.report({"INFO"}, "Import complete")

        messagelist = []
        messagelist.append(f"{len(functions.spot_new_items(initialise=False, item_type='objects'))} objects imported")
        messagelist.append(f"{len(functions.spot_new_items(initialise=False, item_type='images'))} textures imported")

        functions.show_message_box(messagelist, "Import complete", icon = 'INFO')

        # If we imported an image, and we already had an image with the same name, get rid of the original in favour of the imported
        new_images_names = functions.spot_new_items(initialise=False, item_type="images")

        # Find any .001s
        for imgname in new_images_names:
            try:
                int(imgname[-3:])

                # Delete the existing version
                bpy.data.images.remove(bpy.data.images[imgname[0:-4]])

                # Rename our version
                bpy.data.images[imgname].name = imgname[0:-4]

            except ValueError:
                pass

        return {'FINISHED'}


class TEXTUREBAKE_OT_bake_delete(bpy.types.Operator):
    """Delete the background bakes because you don't want to import them into Blender. NOTE: If you chose to save bakes or FBX externally, these are safe and NOT deleted. This is just if you don't want to import into this Blender session"""
    bl_idname = "texture_bake.bake_delete"
    bl_label = "Delete the background bakes"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        savepath = Path(bpy.data.filepath).parent

        for p in background_bake_ops.bgops_list_finished:
            pid_str = str(p[0].pid)
            try:
                os.remove(str(savepath / pid_str) + ".blend")
                os.remove(str(savepath / pid_str) + ".blend1")
            except:
                pass

        background_bake_ops.bgops_list_finished = []
        return {'FINISHED'}


class TEXTUREBAKE_OT_bake_delete_individual(bpy.types.Operator):
    """Delete this individual background bake because you don't want to import the results into Blender. NOTE: If you chose to save bakes or FBX externally, these are safe and NOT deleted. This is just if you don't want to import into this Blender session"""
    bl_idname = "texture_bake.bake_delete_individual"
    bl_label = "Delete the individual background bake"
    bl_options = {'INTERNAL'}

    pnum: bpy.props.IntProperty()

    def execute(self, context):
        pid_str = str(self.pnum)
        savepath = Path(bpy.data.filepath).parent
        try:
            os.remove(str(savepath / pid_str) + ".blend")
            os.remove(str(savepath / pid_str) + ".blend1")
        except:
            pass

        background_bake_ops.bgops_list_finished = [p for p in background_bake_ops.bgops_list_finished if p[0].pid != self.pnum]
        return {'FINISHED'}


class TEXTUREBAKE_OT_import_materials(bpy.types.Operator):
    """Import the selected specials materials if you want to edit them. Once edited, they will be used for all bakes of that type in this file"""
    bl_idname = "texture_bake.import_materials"
    bl_label = "Import specials materials"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls,context):
        return bpy.context.scene.TextureBake_Props.selected_ao or\
            bpy.context.scene.TextureBake_Props.selected_curvature or\
            bpy.context.scene.TextureBake_Props.selected_thickness or\
            bpy.context.scene.TextureBake_Props.selected_lightmap

    def execute(self, context):
        functions.import_needed_specials_materials()
        self.report({"INFO"}, "Materials imported into scene. Create a dummy object and edit them. They will be used for Specials bakes of this type going forwards")
        return {'FINISHED'}


class TEXTUREBAKE_OT_save_preset(bpy.types.Operator):
    """Save current TextureBake settings to preset"""
    bl_idname = "texture_bake.save_preset"
    bl_label = "Save"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls,context):
        return bpy.context.scene.TextureBake_Props.preset_name != ""

    def execute(self, context):
        d = {}
        d["global_mode"] = bpy.context.scene.TextureBake_Props.global_mode
        d["ray_distance"] = bpy.context.scene.TextureBake_Props.ray_distance
        d["cage_extrusion"] = bpy.context.scene.TextureBake_Props.cage_extrusion
        d["selected_to_target"] = bpy.context.scene.TextureBake_Props.selected_to_target
        d["merged_bake"] = bpy.context.scene.TextureBake_Props.merged_bake
        d["merged_bake_name"] = bpy.context.scene.TextureBake_Props.merged_bake_name
        d["input_height"] = bpy.context.scene.TextureBake_Props.input_height
        d["input_width"] = bpy.context.scene.TextureBake_Props.input_width
        d["output_height"] = bpy.context.scene.TextureBake_Props.output_height
        d["output_width"] = bpy.context.scene.TextureBake_Props.output_width
        d["bake_32bit_float"] = bpy.context.scene.TextureBake_Props.bake_32bit_float
        d["use_alpha"] = bpy.context.scene.TextureBake_Props.use_alpha
        d["rough_glossy_switch"] = bpy.context.scene.TextureBake_Props.rough_glossy_switch
        d["normal_format_switch"] = bpy.context.scene.TextureBake_Props.normal_format_switch
        d["tex_per_mat"] = bpy.context.scene.TextureBake_Props.tex_per_mat
        d["selected_col"] = bpy.context.scene.TextureBake_Props.selected_col
        d["selected_metal"] = bpy.context.scene.TextureBake_Props.selected_metal
        d["selected_rough"] = bpy.context.scene.TextureBake_Props.selected_rough
        d["selected_normal"] = bpy.context.scene.TextureBake_Props.selected_normal
        d["selected_trans"] = bpy.context.scene.TextureBake_Props.selected_trans
        d["selected_transrough"] = bpy.context.scene.TextureBake_Props.selected_transrough
        d["selected_emission"] = bpy.context.scene.TextureBake_Props.selected_emission
        d["selected_sss"] = bpy.context.scene.TextureBake_Props.selected_sss
        d["selected_ssscol"] = bpy.context.scene.TextureBake_Props.selected_ssscol
        d["selected_clearcoat"] = bpy.context.scene.TextureBake_Props.selected_clearcoat
        d["selected_clearcoat_rough"] = bpy.context.scene.TextureBake_Props.selected_clearcoat_rough
        d["selected_specular"] = bpy.context.scene.TextureBake_Props.selected_specular
        d["selected_alpha"] = bpy.context.scene.TextureBake_Props.selected_alpha
        d["selected_col_mats"] = bpy.context.scene.TextureBake_Props.selected_col_mats
        d["selected_col_vertex"] = bpy.context.scene.TextureBake_Props.selected_col_vertex
        d["selected_ao"] = bpy.context.scene.TextureBake_Props.selected_ao
        d["selected_thickness"] = bpy.context.scene.TextureBake_Props.selected_thickness
        d["selected_curvature"] = bpy.context.scene.TextureBake_Props.selected_curvature
        d["selected_lightmap"] = bpy.context.scene.TextureBake_Props.selected_lightmap
        d["lightmap_apply_colman"] = bpy.context.scene.TextureBake_Props.lightmap_apply_colman
        d["selected_lightmap_denoise"] = bpy.context.scene.TextureBake_Props.selected_lightmap_denoise
        d["prefer_existing_uvmap"] = bpy.context.scene.TextureBake_Props.prefer_existing_uvmap
        d["restore_active_uvmap"] = bpy.context.scene.TextureBake_Props.restore_active_uvmap
        d["uv_mode"] = bpy.context.scene.TextureBake_Props.uv_mode
        d["udim_tiles"] = bpy.context.scene.TextureBake_Props.udim_tiles
        d["cp_file_format"] = bpy.context.scene.TextureBake_Props.cp_file_format
        d["export_textures"] = bpy.context.scene.TextureBake_Props.export_textures
        d["export_folder_per_object"] = bpy.context.scene.TextureBake_Props.export_folder_per_object
        d["export_mesh"] = bpy.context.scene.TextureBake_Props.export_mesh
        d["fbx_name"] = bpy.context.scene.TextureBake_Props.fbx_name
        d["prep_mesh"] = bpy.context.scene.TextureBake_Props.prep_mesh
        d["hide_source_objects"] = bpy.context.scene.TextureBake_Props.hide_source_objects
        d["preserve_materials"] = bpy.context.scene.TextureBake_Props.preserve_materials
        d["export_16bit"] = bpy.context.scene.TextureBake_Props.export_16bit
        d["export_file_format"] = bpy.context.scene.TextureBake_Props.export_file_format
        d["export_folder_name"] = bpy.context.scene.TextureBake_Props.export_folder_name
        d["export_color_space"] = bpy.context.scene.TextureBake_Props.export_color_space
        d["export_datetime"] = bpy.context.scene.TextureBake_Props.export_datetime
        d["run_denoise"] = bpy.context.scene.TextureBake_Props.run_denoise
        d["export_apply_modifiers"] = bpy.context.scene.TextureBake_Props.export_apply_modifiers
        d["use_object_list"] = bpy.context.scene.TextureBake_Props.use_object_list
        d["object_list_index"] = bpy.context.scene.TextureBake_Props.object_list_index
        d["background_bake"] = bpy.context.scene.TextureBake_Props.background_bake
        d["memory_limit"] = bpy.context.scene.TextureBake_Props.memory_limit
        d["batch_name"] = bpy.context.scene.TextureBake_Props.batch_name
        d["first_texture_show"] = bpy.context.scene.TextureBake_Props.first_texture_show
        d["background_bake_name"] = bpy.context.scene.TextureBake_Props.background_bake_name

        d["bake_type"] = bpy.context.scene.cycles.bake_type
        d["use_pass_direct"] = bpy.context.scene.render.bake.use_pass_direct
        d["use_pass_indirect"] = bpy.context.scene.render.bake.use_pass_indirect
        d["use_pass_diffuse"] = bpy.context.scene.render.bake.use_pass_diffuse
        d["use_pass_glossy"] = bpy.context.scene.render.bake.use_pass_glossy
        d["use_pass_transmission"] = bpy.context.scene.render.bake.use_pass_transmission
        d["use_pass_emit"] = bpy.context.scene.render.bake.use_pass_emit
        d["cycles.samples"] = bpy.context.scene.cycles.samples
        d["bake.normal_space"] = bpy.context.scene.render.bake.normal_space
        d["render.bake.normal_r"] = bpy.context.scene.render.bake.normal_r
        d["render.bake.normal_g"] = bpy.context.scene.render.bake.normal_g
        d["render.bake.normal_b"] = bpy.context.scene.render.bake.normal_b
        d["use_pass_color"] = bpy.context.scene.render.bake.use_pass_color
        d["bake.margin"] = bpy.context.scene.render.bake.margin

        # Grab the objects in the advanced list (if any)
        d["object_list"] = [i.obj.name for i in bpy.context.scene.TextureBake_Props.object_list]
        # Grab the target objects if there is one
        if bpy.context.scene.TextureBake_Props.target_object != None:
            d["target_object"] = bpy.context.scene.TextureBake_Props.target_object.name
        else:
            d["target_object"] = None
        # Cage object if there is one
        if bpy.context.scene.render.bake.cage_object != None:
            d["cage_object"] = bpy.context.scene.render.bake.cage_object.name
        else:
            d["cage_object"] = None

        # Channel packed images
        cp_images_dict = {}
        for cpi in bpy.context.scene.TextureBake_Props.cp_list:
            thiscpi_dict = {}
            thiscpi_dict["R"] = cpi.R
            thiscpi_dict["G"] = cpi.G
            thiscpi_dict["B"] = cpi.B
            thiscpi_dict["A"] = cpi.A

            thiscpi_dict["file_format"] = cpi.file_format

            cp_images_dict[cpi.name] = thiscpi_dict
        if len(cp_images_dict)>0:
            d["channel_packed_images"] = cp_images_dict

        # Find where we want to save
        p = Path(bpy.utils.script_path_user())
        p = p.parents[1]
        savename = functions.clean_file_name(bpy.context.scene.TextureBake_Props.preset_name)

        # Check for data directory
        if not os.path.isdir(str(p / "data")):
            # Create it
            os.mkdir(str(p / "data"))

        p = p / "data"

        # Check for TextureBake directory
        if not os.path.isdir(str(p / "TextureBake")):
            # Create it
            os.mkdir(str(p / "TextureBake"))

        p = p / "TextureBake"

        functions.print_msg(f"Saving preset to {str(p)}")

        jsonString = json.dumps(d)
        jsonFile = open(str(p / savename), "w")
        jsonFile.write(jsonString)
        jsonFile.close()

        # Refreh the list
        bpy.ops.texture_bake.refresh_presets()

        self.report({"INFO"}, "Preset saved")
        return {'FINISHED'}


class TEXTUREBAKE_OT_load_preset(bpy.types.Operator):
    """Load selected TextureBake preset"""
    bl_idname = "texture_bake.load_preset"
    bl_label = "Load"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls,context):
        try:
            bpy.context.scene.TextureBake_Props.presets_list[bpy.context.scene.TextureBake_Props.presets_list_index].name
            return True
        except:
            return False

    def execute(self, context):
        # Load it
        loadname = functions.clean_file_name(\
            bpy.context.scene.TextureBake_Props.presets_list[\
            bpy.context.scene.TextureBake_Props.presets_list_index].name)

        p = Path(bpy.utils.script_path_user())
        p = p.parents[1]
        p = p /  "data" / "TextureBake" / loadname

        functions.print_msg(f"Loading preset from {str(p)}")

        try:
            fileObject = open(str(p), "r")
        except:
            bpy.ops.texture_bake.refresh_presets()
            self.report({"ERROR"}, f"Preset {loadname} no longer exists")
            return {'CANCELLED'}

        jsonContent = fileObject.read()
        d = json.loads(jsonContent)

        bpy.context.scene.TextureBake_Props.global_mode = d["global_mode"]
        bpy.context.scene.TextureBake_Props.ray_distance = d["ray_distance"]
        bpy.context.scene.TextureBake_Props.cage_extrusion = d["cage_extrusion"]
        bpy.context.scene.TextureBake_Props.selected_to_target = d["selected_to_target"]
        bpy.context.scene.TextureBake_Props.merged_bake = d["merged_bake"]
        bpy.context.scene.TextureBake_Props.merged_bake_name = d["merged_bake_name"]
        bpy.context.scene.TextureBake_Props.input_height = d["input_height"]
        bpy.context.scene.TextureBake_Props.input_width = d["input_width"]
        bpy.context.scene.TextureBake_Props.output_height = d["output_height"]
        bpy.context.scene.TextureBake_Props.output_width = d["output_width"]
        bpy.context.scene.TextureBake_Props.bake_32bit_float = d["bake_32bit_float"]
        bpy.context.scene.TextureBake_Props.use_alpha = d["use_alpha"]
        bpy.context.scene.TextureBake_Props.rough_glossy_switch = d["rough_glossy_switch"]
        bpy.context.scene.TextureBake_Props.normal_format_switch = d["normal_format_switch"]
        bpy.context.scene.TextureBake_Props.tex_per_mat = d["tex_per_mat"]
        bpy.context.scene.TextureBake_Props.selected_col = d["selected_col"]
        bpy.context.scene.TextureBake_Props.selected_metal = d["selected_metal"]
        bpy.context.scene.TextureBake_Props.selected_rough = d["selected_rough"]
        bpy.context.scene.TextureBake_Props.selected_normal = d["selected_normal"]
        bpy.context.scene.TextureBake_Props.selected_trans = d["selected_trans"]
        bpy.context.scene.TextureBake_Props.selected_transrough = d["selected_transrough"]
        bpy.context.scene.TextureBake_Props.selected_emission = d["selected_emission"]
        bpy.context.scene.TextureBake_Props.selected_sss = d["selected_sss"]
        bpy.context.scene.TextureBake_Props.selected_ssscol = d["selected_ssscol"]
        bpy.context.scene.TextureBake_Props.selected_clearcoat = d["selected_clearcoat"]
        bpy.context.scene.TextureBake_Props.selected_clearcoat_rough = d["selected_clearcoat_rough"]
        bpy.context.scene.TextureBake_Props.selected_specular = d["selected_specular"]
        bpy.context.scene.TextureBake_Props.selected_alpha = d["selected_alpha"]
        bpy.context.scene.TextureBake_Props.selected_col_mats = d["selected_col_mats"]
        bpy.context.scene.TextureBake_Props.selected_col_vertex = d["selected_col_vertex"]
        bpy.context.scene.TextureBake_Props.selected_ao = d["selected_ao"]
        bpy.context.scene.TextureBake_Props.selected_thickness = d["selected_thickness"]
        bpy.context.scene.TextureBake_Props.selected_curvature = d["selected_curvature"]
        bpy.context.scene.TextureBake_Props.selected_lightmap = d["selected_lightmap"]
        bpy.context.scene.TextureBake_Props.lightmap_apply_colman = d["lightmap_apply_colman"]
        bpy.context.scene.TextureBake_Props.selected_lightmap_denoise = d["selected_lightmap_denoise"]
        bpy.context.scene.TextureBake_Props.restore_active_uvmap = d["restore_active_uvmap"]
        bpy.context.scene.TextureBake_Props.uv_mode = d["uv_mode"]
        bpy.context.scene.TextureBake_Props.udim_tiles = d["udim_tiles"]
        bpy.context.scene.TextureBake_Props.cp_file_format = d["cp_file_format"]
        bpy.context.scene.TextureBake_Props.export_textures = d["export_textures"]
        bpy.context.scene.TextureBake_Props.export_folder_per_object = d["export_folder_per_object"]
        bpy.context.scene.TextureBake_Props.export_mesh = d["export_mesh"]
        bpy.context.scene.TextureBake_Props.fbx_name = d["fbx_name"]
        bpy.context.scene.TextureBake_Props.prep_mesh = d["prep_mesh"]
        bpy.context.scene.TextureBake_Props.hide_source_objects = d["hide_source_objects"]
        bpy.context.scene.TextureBake_Props.preserve_materials = d["preserve_materials"]
        bpy.context.scene.TextureBake_Props.export_16bit = d["export_16bit"]
        bpy.context.scene.TextureBake_Props.export_file_format = d["export_file_format"]
        bpy.context.scene.TextureBake_Props.export_folder_name = d["export_folder_name"]
        bpy.context.scene.TextureBake_Props.export_color_space = d["export_color_space"]
        bpy.context.scene.TextureBake_Props.export_datetime = d["export_datetime"]
        bpy.context.scene.TextureBake_Props.run_denoise = d["run_denoise"]
        bpy.context.scene.TextureBake_Props.export_apply_modifiers = d["export_apply_modifiers"]
        bpy.context.scene.TextureBake_Props.use_object_list = d["use_object_list"]
        bpy.context.scene.TextureBake_Props.object_list_index = d["object_list_index"]
        bpy.context.scene.TextureBake_Props.background_bake = d["background_bake"]
        bpy.context.scene.TextureBake_Props.memory_limit = d["memory_limit"]
        bpy.context.scene.TextureBake_Props.batch_name = d["batch_name"]
        bpy.context.scene.TextureBake_Props.first_texture_show = d["first_texture_show"]
        bpy.context.scene.TextureBake_Props.background_bake_name = d["background_bake_name"]
        bpy.context.scene.TextureBake_Props.prefer_existing_uvmap = d["prefer_existing_uvmap"]

        bpy.context.scene.cycles.bake_type = d["bake_type"]
        bpy.context.scene.render.bake.use_pass_direct = d["use_pass_direct"]
        bpy.context.scene.render.bake.use_pass_indirect = d["use_pass_indirect"]
        bpy.context.scene.render.bake.use_pass_diffuse = d["use_pass_diffuse"]
        bpy.context.scene.render.bake.use_pass_glossy = d["use_pass_glossy"]
        bpy.context.scene.render.bake.use_pass_transmission = d["use_pass_transmission"]
        bpy.context.scene.render.bake.use_pass_emit = d["use_pass_emit"]
        bpy.context.scene.cycles.samples = d["cycles.samples"]
        bpy.context.scene.render.bake.normal_space = d["bake.normal_space"]
        bpy.context.scene.render.bake.normal_r = d["render.bake.normal_r"]
        bpy.context.scene.render.bake.normal_g = d["render.bake.normal_g"]
        bpy.context.scene.render.bake.normal_b = d["render.bake.normal_b"]
        bpy.context.scene.render.bake.use_pass_color = d["use_pass_color"]
        bpy.context.scene.render.bake.margin = d["bake.margin"]

        # Channel packing images
        if "channel_packed_images" in d:
            channel_packed_images = d["channel_packed_images"]

            if len(channel_packed_images) > 0:
                bpy.context.scene.TextureBake_Props.cp_list.clear()

            for imgname in channel_packed_images:
                thiscpi_dict = channel_packed_images[imgname]

                # Create the list item
                li = bpy.context.scene.TextureBake_Props.cp_list.add()
                li.name = imgname

                # Set the list item properies
                li.R = thiscpi_dict["R"]
                li.G = thiscpi_dict["G"]
                li.B = thiscpi_dict["B"]
                li.A = thiscpi_dict["A"]
                li.file_format = thiscpi_dict["file_format"]

        # And now the objects, if they are here
        bpy.context.scene.TextureBake_Props.object_list.clear()
        for name in d["object_list"]:
            if name in bpy.data.objects:
                item = bpy.context.scene.TextureBake_Props.object_list.add()
                item.obj = bpy.data.objects[name]

        if d["target_object"] != None and d["target_object"] in bpy.data.objects:
            bpy.context.scene.TextureBake_Props.target_object = bpy.data.objects[d["target_object"]]
        # Cage object
        if d["cage_object"] != None and d["cage_object"] in bpy.data.objects:
            bpy.context.scene.render.bake.cage_object = bpy.data.objects[d["cage_object"]]

        self.report({"INFO"}, f"Preset {loadname} loaded")
        return {'FINISHED'}


class TEXTUREBAKE_OT_refresh_presets(bpy.types.Operator):
    """Refresh list of TextureBake presets"""
    bl_idname = "texture_bake.refresh_presets"
    bl_label = "Refresh"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        bpy.context.scene.TextureBake_Props.presets_list.clear()

        p = Path(bpy.utils.script_path_user())
        p = p.parents[1]
        p = p /  "data" / "TextureBake"

        try:
            presets = os.listdir(str(p))
        except:
            self.report({"INFO"}, "No presets found")
            return {'CANCELLED'}

        if len(presets) == 0:
            self.report({"INFO"}, "No presets found")
            return {'CANCELLED'}

        for preset in presets:
            # List should be clear
            i = bpy.context.scene.TextureBake_Props.presets_list.add()
            i.name = preset

        return {'FINISHED'}


class TEXTUREBAKE_OT_delete_preset(bpy.types.Operator):
    """Delete selected TextureBake preset"""
    bl_idname = "texture_bake.delete_preset"
    bl_label = "Delete"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls,context):
        try:
            bpy.context.scene.TextureBake_Props.presets_list[bpy.context.scene.TextureBake_Props.presets_list_index].name
            return True
        except:
            return False

    def execute(self, context):
        p = Path(bpy.utils.script_path_user())
        p = p.parents[1]
        p = p /  "data" / "TextureBake"

        index = context.scene.TextureBake_Props.presets_list_index
        item = context.scene.TextureBake_Props.presets_list[index]
        p = p / item.name

        os.remove(str(p))

        bpy.ops.texture_bake.refresh_presets()
        return {'FINISHED'}


class TEXTUREBAKE_OT_increase_bake_res(bpy.types.Operator):
    """Increase texture resolution by 1k"""
    bl_idname = "texture_bake.increase_bake_res"
    bl_label = "+1k"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        x = bpy.context.scene.TextureBake_Props.input_width
        bpy.context.scene.TextureBake_Props.input_width = x + 1024
        y = bpy.context.scene.TextureBake_Props.input_height
        bpy.context.scene.TextureBake_Props.input_height = y + 1024

        while bpy.context.scene.TextureBake_Props.input_height % 1024 != 0:
            bpy.context.scene.TextureBake_Props.input_height -= 1

        while bpy.context.scene.TextureBake_Props.input_width % 1024 != 0:
            bpy.context.scene.TextureBake_Props.input_width -= 1

        result = min(bpy.context.scene.TextureBake_Props.input_width, bpy.context.scene.TextureBake_Props.input_height)
        bpy.context.scene.TextureBake_Props.input_width = result
        bpy.context.scene.TextureBake_Props.input_height = result

        functions.auto_set_bake_margin()
        return {'FINISHED'}


class TEXTUREBAKE_OT_decrease_bake_res(bpy.types.Operator):
    """Decrease texture resolution by 1k"""
    bl_idname = "texture_bake.decrease_bake_res"
    bl_label = "-1k"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        x = bpy.context.scene.TextureBake_Props.input_width
        bpy.context.scene.TextureBake_Props.input_width = x - 1024
        y = bpy.context.scene.TextureBake_Props.input_height
        bpy.context.scene.TextureBake_Props.input_height = y - 1024

        if bpy.context.scene.TextureBake_Props.input_height < 1:
            bpy.context.scene.TextureBake_Props.input_height = 1024

        if bpy.context.scene.TextureBake_Props.input_width < 1:
            bpy.context.scene.TextureBake_Props.input_width = 1024

        while bpy.context.scene.TextureBake_Props.input_height % 1024 != 0:
            bpy.context.scene.TextureBake_Props.input_height += 1

        while bpy.context.scene.TextureBake_Props.input_width % 1024 != 0:
            bpy.context.scene.TextureBake_Props.input_width += 1

        result = max(bpy.context.scene.TextureBake_Props.input_width, bpy.context.scene.TextureBake_Props.input_height)
        bpy.context.scene.TextureBake_Props.input_width = result
        bpy.context.scene.TextureBake_Props.input_height = result

        functions.auto_set_bake_margin()
        return {'FINISHED'}


class TEXTUREBAKE_OT_increase_output_res(bpy.types.Operator):
    """Increase output resolution by 1k"""
    bl_idname = "texture_bake.increase_output_res"
    bl_label = "+1k"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        x = bpy.context.scene.TextureBake_Props.output_width
        bpy.context.scene.TextureBake_Props.output_width = x + 1024
        y = bpy.context.scene.TextureBake_Props.output_height
        bpy.context.scene.TextureBake_Props.output_height = y + 1024

        while bpy.context.scene.TextureBake_Props.output_height % 1024 != 0:
            bpy.context.scene.TextureBake_Props.output_height -= 1

        while bpy.context.scene.TextureBake_Props.output_width % 1024 != 0:
            bpy.context.scene.TextureBake_Props.output_width -= 1

        result = min(bpy.context.scene.TextureBake_Props.output_width, bpy.context.scene.TextureBake_Props.output_height)
        bpy.context.scene.TextureBake_Props.output_width = result
        bpy.context.scene.TextureBake_Props.output_height = result

        functions.auto_set_bake_margin()
        return {'FINISHED'}


class TEXTUREBAKE_OT_decrease_output_res(bpy.types.Operator):
    """Decrease output resolution by 1k"""
    bl_idname = "texture_bake.decrease_output_res"
    bl_label = "-1k"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        x = bpy.context.scene.TextureBake_Props.output_width
        bpy.context.scene.TextureBake_Props.output_width = x - 1024
        y = bpy.context.scene.TextureBake_Props.output_height
        bpy.context.scene.TextureBake_Props.output_height = y - 1024

        if bpy.context.scene.TextureBake_Props.output_height < 1:
            bpy.context.scene.TextureBake_Props.output_height = 1024

        if bpy.context.scene.TextureBake_Props.output_width < 1:
            bpy.context.scene.TextureBake_Props.output_width = 1024

        while bpy.context.scene.TextureBake_Props.output_height % 1024 != 0:
            bpy.context.scene.TextureBake_Props.output_height += 1

        while bpy.context.scene.TextureBake_Props.output_width % 1024 != 0:
            bpy.context.scene.TextureBake_Props.output_width += 1

        result = max(bpy.context.scene.TextureBake_Props.output_width, bpy.context.scene.TextureBake_Props.output_height)
        bpy.context.scene.TextureBake_Props.output_width = result
        bpy.context.scene.TextureBake_Props.output_height = result

        functions.auto_set_bake_margin()
        return {'FINISHED'}


class TEXTUREBAKE_OT_add_packed_texture(bpy.types.Operator):
    """Add a TextureBake CP Texture item"""
    bl_idname = "texture_bake.add_packed_texture"
    bl_label = "Add"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls,context):
        return bpy.context.scene.TextureBake_Props.cp_name != ""

    def execute(self, context):
        cp_list = bpy.context.scene.TextureBake_Props.cp_list
        name = functions.clean_file_name(bpy.context.scene.TextureBake_Props.cp_name)

        if name in cp_list:
            # Delete it
            index = bpy.context.scene.TextureBake_Props.cp_list.find(name)
            bpy.context.scene.TextureBake_Props.cp_list.remove(index)

        li = cp_list.add()
        li.name = name

        li.R = bpy.context.scene.TextureBake_Props.cptex_R
        li.G = bpy.context.scene.TextureBake_Props.cptex_G
        li.B = bpy.context.scene.TextureBake_Props.cptex_B
        li.A = bpy.context.scene.TextureBake_Props.cptex_A
        li.file_format = bpy.context.scene.TextureBake_Props.cp_file_format

        bpy.context.scene.TextureBake_Props.cp_list_index = bpy.context.scene.TextureBake_Props.cp_list.find(name)

        self.report({"INFO"}, "CP texture saved")
        return {'FINISHED'}


class TEXTUREBAKE_OT_delete_packed_texture(bpy.types.Operator):
    """Delete the selected channel pack texture"""
    bl_idname = "texture_bake.delete_packed_texture"
    bl_label = "Delete"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls,context):
        try:
            bpy.context.scene.TextureBake_Props.cp_list[bpy.context.scene.TextureBake_Props.cp_list_index].name
            return True
        except:
            return False

    def execute(self, context):
        bpy.context.scene.TextureBake_Props.cp_list.remove(bpy.context.scene.TextureBake_Props.cp_list_index)
        self.report({"INFO"}, "CP texture deleted")
        return {'FINISHED'}


class TEXTUREBAKE_OT_reset_packed_textures(bpy.types.Operator):
    """Add some example channel pack textures"""
    bl_idname = "texture_bake.reset_packed_textures"
    bl_label = "Add examples"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls,context):
        return True

    def execute(self, context):
        cp_list = bpy.context.scene.TextureBake_Props.cp_list

        # Unity Lit shader. R=metalness, G=AO, B=N/A, A=Glossy.
        li = cp_list.add()
        li.name = "Unity Lit Shader"
        li.file_format = "OPEN_EXR"
        li.R = "metalness"
        li.G = TextureBakeConstants.AO
        li.B = "none"
        li.A = "glossy"

        # Unity Legacy Standard Diffuse. RGB=diffuse, A=alpha.
        li = cp_list.add()
        li.name = "Unity Legacy Shader"
        li.file_format = "OPEN_EXR"
        li.R = "diffuse"
        li.G = "diffuse"
        li.B = "diffuse"
        li.A = "alpha"

        # ORM format. R=AO, G=Roughness, B=Metalness, A=N/A.
        li = cp_list.add()
        li.name = "ORM"
        li.file_format = "OPEN_EXR"
        li.R = TextureBakeConstants.AO
        li.G = "roughness"
        li.B = "metalness"
        li.A = "none"

        # diffuse plus specular in the alpha channel.
        li = cp_list.add()
        li.name = "Diffuse and Spec in alpha"
        li.file_format = "OPEN_EXR"
        li.R = "diffuse"
        li.G = "diffuse"
        li.B = "diffuse"
        li.A = "specular"

        self.report({"INFO"}, "Default textures added")
        return {'FINISHED'}


class TEXTUREBAKE_OT_add_export_preset(bpy.types.Operator):
    """Adds a new global export preset"""
    bl_idname = "texture_bake.add_export_preset"
    bl_label = "Add Export Presets"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        presets = prefs.export_presets
        preset = presets.add()
        preset.name = "New Preset"
        bpy.ops.wm.save_userpref()
        return {'FINISHED'}


class TEXTUREBAKE_OT_delete_export_preset(bpy.types.Operator):
    """Deletes the selected export preset"""
    bl_idname = "texture_bake.delete_export_preset"
    bl_label = "Delete Export Presets"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls,context):
        prefs = context.preferences.addons[__package__].preferences
        return prefs.export_presets

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        presets = prefs.export_presets
        index = prefs.export_presets_index
        presets.remove(index)
        prefs.export_presets_index = min(index, len(presets))
        bpy.ops.wm.save_userpref()
        return {'FINISHED'}


class TEXTUREBAKE_OT_reset_export_presets(bpy.types.Operator):
    """Resets export presets to their default values. This deletes all custom presets"""
    bl_idname = "texture_bake.reset_export_presets"
    bl_label = "Reset Export Presets"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        presets = prefs.export_presets
        presets.clear()
        item = presets.add()
        item.name = "Default Preset"
        bpy.ops.wm.save_userpref()
        return {'FINISHED'}


class TEXTUREBAKE_OT_add_export_texture(bpy.types.Operator):
    """Adds a new texture to the selected export preset"""
    bl_idname = "texture_bake.add_export_texture"
    bl_label = "Add Texture"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        preset = prefs.export_presets[prefs.export_presets_index]
        tex = preset.textures.add()
        tex.name = "%OBJ%_%BATCH%_Texture"
        bpy.ops.wm.save_userpref()
        return {'FINISHED'}


class TEXTUREBAKE_OT_delete_export_texture(bpy.types.Operator):
    """Deletes the selected texture from the export preset"""
    bl_idname = "texture_bake.delete_export_texture"
    bl_label = "Delete Texture"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls,context):
        prefs = context.preferences.addons[__package__].preferences
        if prefs.export_presets:
            preset = prefs.export_presets[prefs.export_presets_index]
            return preset.textures
        return False

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        presets = prefs.export_presets
        if presets:
            preset = presets[prefs.export_presets_index]
            index = preset.textures_index
            preset.textures.remove(index)
            preset.textures_index = min(index, len(preset.textures))
            bpy.ops.wm.save_userpref()
        return {'FINISHED'}
