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
import json
import uuid

from pathlib import Path
from datetime import datetime
from math import floor

from . import (
    bakefunctions,
    constants,
    functions,
)

from .bake_operation import (
    BakeOperation,
    MasterOperation,
    BakeStatus,
    TextureBakeConstants,
)

from .bg_bake import (
    background_bake_ops,
    BackgroundBakeParams,
    refresh_bake_progress,
)


class TEXTUREBAKE_OT_bake(bpy.types.Operator):
    """Start the baking process"""
    bl_idname = "texture_bake.bake"
    bl_label = "Bake Textures"

    def commence_bake(self, context, needed_bake_modes):
        # Prepare the BakeStatus tracker for progress bar
        num_of_objects = 0
        if context.scene.TextureBake_Props.use_object_list:
            num_of_objects = len(context.scene.TextureBake_Props.object_list)
        else:
            num_of_objects = len(context.selected_objects)

        total_maps = 0
        for need in needed_bake_modes:
            if need == TextureBakeConstants.PBR:
                total_maps += functions.get_num_maps_to_bake() * num_of_objects
            if need == TextureBakeConstants.PBRS2A:
                total_maps += functions.get_num_maps_to_bake()
            if need == TextureBakeConstants.CYCLESBAKE and not context.scene.TextureBake_Props.selected_to_target:
                total_maps += num_of_objects
            if need == TextureBakeConstants.CYCLESBAKE and context.scene.TextureBake_Props.selected_to_target:
                total_maps += 1
            if need == TextureBakeConstants.SPECIALS:
                total_maps+=(functions.import_needed_specials_materials(justcount = True) * num_of_objects)
                if context.scene.TextureBake_Props.selected_col_mats: total_maps+=1*num_of_objects
                if context.scene.TextureBake_Props.selected_col_vertex: total_maps+=1*num_of_objects
            if need in [TextureBakeConstants.SPECIALS_CYCLES_TARGET_ONLY, TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY]:
                total_maps+=(functions.import_needed_specials_materials(justcount = True))
                if context.scene.TextureBake_Props.selected_col_mats: total_maps+=1
                if context.scene.TextureBake_Props.selected_col_vertex: total_maps+=1

        BakeStatus.total_maps = total_maps

        MasterOperation.clear()
        MasterOperation.merged_bake = context.scene.TextureBake_Props.merged_bake
        MasterOperation.merged_bake_name = context.scene.TextureBake_Props.merged_bake_name
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
            MasterOperation.this_bake_operation_num += 1
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

    @classmethod
    def poll(cls,context):
        preset = context.scene.TextureBake_Props.export_preset
        if preset == 'NONE':
            return False
        prefs = context.preferences.addons[__package__].preferences
        return [p for p in prefs.export_presets if p.uid == preset]

    def execute(self, context):
        needed_bake_modes = []
        if context.scene.TextureBake_Props.global_mode == "pbr_bake" and not context.scene.TextureBake_Props.selected_to_target:
            needed_bake_modes.append(TextureBakeConstants.PBR)
        if context.scene.TextureBake_Props.global_mode == "pbr_bake" and context.scene.TextureBake_Props.selected_to_target:
            needed_bake_modes.append(TextureBakeConstants.PBRS2A)
        if context.scene.TextureBake_Props.global_mode == "cycles_bake":
            needed_bake_modes.append(TextureBakeConstants.CYCLESBAKE)

        if functions.any_specials() and TextureBakeConstants.PBRS2A in needed_bake_modes:
            needed_bake_modes.append(TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY)
        elif functions.any_specials() and TextureBakeConstants.CYCLESBAKE in needed_bake_modes and context.scene.TextureBake_Props.selected_to_target:
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
            ts = datetime.now()
            self.commence_bake(context, needed_bake_modes)
            tf = datetime.now()
            s = (tf-ts).seconds
            functions.print_msg(f"Bake complete, took {s} seconds ({floor(s/60)} minutes, {s%60} seconds)")
            return {'FINISHED'}

        # We are in foreground, do usual checks
        for mode in needed_bake_modes:
            if not functions.check_scene(context.selected_objects, mode):
                return {"CANCELLED"}

        # If the user requested background mode, fire that up now and exit
        if context.scene.TextureBake_Props.background_bake == "bg":
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

            background_bake_ops.bgops_list.append(
                BackgroundBakeParams(
                    process,
                    context.scene.TextureBake_Props.background_bake_name,
                    context.scene.TextureBake_Props.prep_mesh,
                    context.scene.TextureBake_Props.hide_source_objects
                )
            )

            bpy.app.timers.register(refresh_bake_progress)
            self.report({"INFO"}, "Background bake process started")
            return {'FINISHED'}

        # If we are doing this here and now, get on with it
        # Create a bake operation
        ts = datetime.now()
        self.commence_bake(context, needed_bake_modes)
        tf = datetime.now()
        s = (tf-ts).seconds
        functions.print_msg(f"Time taken - {s} seconds ({floor(s/60)} minutes, {s%60} seconds)")

        self.report({"INFO"}, "Bake complete")
        return {'FINISHED'}


class TEXTUREBAKE_OT_reset_aliases(bpy.types.Operator):
    """Reset the baked image name aliases"""
    bl_idname = "texture_bake.reset_aliases"
    bl_label = "Restore Defaults"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        context.preferences.addons[__package__].preferences.reset_aliases()
        return {'FINISHED'}


class TEXTUREBAKE_OT_bake_import(bpy.types.Operator):
    """Import baked objects previously baked in the background"""
    bl_idname = "texture_bake.bake_import"
    bl_label = "Import baked objects previously baked in the background"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        if context.mode != "OBJECT":
            self.report({"ERROR"}, "You must be in object mode")
            return {'CANCELLED'}

        for p in background_bake_ops.bgops_list_finished:
            savepath = Path(bpy.data.filepath).parent
            pid_str = str(p.process.pid)
            path = savepath / (pid_str + ".blend")
            path = str(path) + "\\Collection\\"

            # Record the objects and collections before append (as append doesn't give us a reference to the new stuff)
            functions.spot_new_items(initialise=True, item_type="objects")
            functions.spot_new_items(initialise=True, item_type="collections")
            functions.spot_new_items(initialise=True, item_type="images")

            # Append
            bpy.ops.wm.append(filename="TextureBake_Bakes", directory=path, use_recursive=False, active_collection=False)

            # If we didn't actually want the objects, delete them
            if not p.copy_objects:
                # Delete objects we just imported (leaving only textures)
                for obj_name in functions.spot_new_items(initialise=False, item_type = "objects"):
                    bpy.data.objects.remove(bpy.data.objects[obj_name])
                for col_name in functions.spot_new_items(initialise=False, item_type = "collections"):
                    bpy.data.collections.remove(bpy.data.collections[col_name])

            # If we have to hide the source objects, do it
            if p.hide_source:
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
        if context.mode != "OBJECT":
            self.report({"ERROR"}, "You must be in object mode")
            return {'CANCELLED'}

        # Need to get the actual SINGLE entry from the list
        p = ([p for p in background_bake_ops.bgops_list_finished if p.process.pid == self.pnum])[0]

        savepath = Path(bpy.data.filepath).parent
        pid_str = str(p.process.pid)
        path = savepath / (pid_str + ".blend")
        path = str(path) + "\\Collection\\"

        # Record the objects and collections before append (as append doesn't give us a reference to the new stuff)
        functions.spot_new_items(initialise=True, item_type="objects")
        functions.spot_new_items(initialise=True, item_type="collections")
        functions.spot_new_items(initialise=True, item_type="images")

        # Append
        bpy.ops.wm.append(filename="TextureBake_Bakes", directory=path, use_recursive=False, active_collection=False)

        # If we didn't actually want the objects, delete them
        if not p.copy_objects:
            for obj_name in functions.spot_new_items(initialise=False, item_type = "objects"):
                bpy.data.objects.remove(bpy.data.objects[obj_name])
            for col_name in functions.spot_new_items(initialise=False, item_type = "collections"):
                bpy.data.collections.remove(bpy.data.collections[col_name])

        # If we have to hide the source objects, do it
        if p.hide_source:
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
        background_bake_ops.bgops_list_finished = [p for p in background_bake_ops.bgops_list_finished if p.process.pid != self.pnum]

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
            pid_str = str(p.process.pid)
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

        background_bake_ops.bgops_list_finished = [p for p in background_bake_ops.bgops_list_finished if p.process.pid != self.pnum]
        return {'FINISHED'}


class TEXTUREBAKE_OT_import_materials(bpy.types.Operator):
    """Import the selected specials materials if you want to edit them. Once edited, they will be used for all bakes of that type in this file"""
    bl_idname = "texture_bake.import_materials"
    bl_label = "Import specials materials"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls,context):
        return context.scene.TextureBake_Props.selected_ao or\
            context.scene.TextureBake_Props.selected_curvature or\
            context.scene.TextureBake_Props.selected_thickness or\
            context.scene.TextureBake_Props.selected_lightmap

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
        return context.scene.TextureBake_Props.preset_name != ""

    def execute(self, context):
        d = {}
        d["export_preset"] = context.scene.TextureBake_Props.export_preset
        d["global_mode"] = context.scene.TextureBake_Props.global_mode
        d["ray_distance"] = context.scene.TextureBake_Props.ray_distance
        d["cage_extrusion"] = context.scene.TextureBake_Props.cage_extrusion
        d["selected_to_target"] = context.scene.TextureBake_Props.selected_to_target
        d["merged_bake"] = context.scene.TextureBake_Props.merged_bake
        d["merged_bake_name"] = context.scene.TextureBake_Props.merged_bake_name
        d["input_height"] = context.scene.TextureBake_Props.input_height
        d["input_width"] = context.scene.TextureBake_Props.input_width
        d["output_height"] = context.scene.TextureBake_Props.output_height
        d["output_width"] = context.scene.TextureBake_Props.output_width
        d["bake_32bit_float"] = context.scene.TextureBake_Props.bake_32bit_float
        d["use_alpha"] = context.scene.TextureBake_Props.use_alpha
        d["rough_glossy_switch"] = context.scene.TextureBake_Props.rough_glossy_switch
        d["normal_format_switch"] = context.scene.TextureBake_Props.normal_format_switch
        d["tex_per_mat"] = context.scene.TextureBake_Props.tex_per_mat
        d["selected_col_mats"] = context.scene.TextureBake_Props.selected_col_mats
        d["selected_col_vertex"] = context.scene.TextureBake_Props.selected_col_vertex
        d["selected_ao"] = context.scene.TextureBake_Props.selected_ao
        d["selected_thickness"] = context.scene.TextureBake_Props.selected_thickness
        d["selected_curvature"] = context.scene.TextureBake_Props.selected_curvature
        d["selected_lightmap"] = context.scene.TextureBake_Props.selected_lightmap
        d["lightmap_apply_colman"] = context.scene.TextureBake_Props.lightmap_apply_colman
        d["selected_lightmap_denoise"] = context.scene.TextureBake_Props.selected_lightmap_denoise
        d["prefer_existing_uvmap"] = context.scene.TextureBake_Props.prefer_existing_uvmap
        d["restore_active_uvmap"] = context.scene.TextureBake_Props.restore_active_uvmap
        d["uv_mode"] = context.scene.TextureBake_Props.uv_mode
        d["udim_tiles"] = context.scene.TextureBake_Props.udim_tiles
        d["cp_file_format"] = context.scene.TextureBake_Props.cp_file_format
        d["export_textures"] = context.scene.TextureBake_Props.export_textures
        d["export_folder_per_object"] = context.scene.TextureBake_Props.export_folder_per_object
        d["export_mesh"] = context.scene.TextureBake_Props.export_mesh
        d["fbx_name"] = context.scene.TextureBake_Props.fbx_name
        d["prep_mesh"] = context.scene.TextureBake_Props.prep_mesh
        d["hide_source_objects"] = context.scene.TextureBake_Props.hide_source_objects
        d["preserve_materials"] = context.scene.TextureBake_Props.preserve_materials
        d["export_16bit"] = context.scene.TextureBake_Props.export_16bit
        d["export_file_format"] = context.scene.TextureBake_Props.export_file_format
        d["export_folder_name"] = context.scene.TextureBake_Props.export_folder_name
        d["export_color_space"] = context.scene.TextureBake_Props.export_color_space
        d["export_datetime"] = context.scene.TextureBake_Props.export_datetime
        d["run_denoise"] = context.scene.TextureBake_Props.run_denoise
        d["export_apply_modifiers"] = context.scene.TextureBake_Props.export_apply_modifiers
        d["use_object_list"] = context.scene.TextureBake_Props.use_object_list
        d["object_list_index"] = context.scene.TextureBake_Props.object_list_index
        d["background_bake"] = context.scene.TextureBake_Props.background_bake
        d["memory_limit"] = context.scene.TextureBake_Props.memory_limit
        d["batch_name"] = context.scene.TextureBake_Props.batch_name
        d["first_texture_show"] = context.scene.TextureBake_Props.first_texture_show
        d["background_bake_name"] = context.scene.TextureBake_Props.background_bake_name

        d["bake_type"] = context.scene.cycles.bake_type
        d["use_pass_direct"] = context.scene.render.bake.use_pass_direct
        d["use_pass_indirect"] = context.scene.render.bake.use_pass_indirect
        d["use_pass_diffuse"] = context.scene.render.bake.use_pass_diffuse
        d["use_pass_glossy"] = context.scene.render.bake.use_pass_glossy
        d["use_pass_transmission"] = context.scene.render.bake.use_pass_transmission
        d["use_pass_emit"] = context.scene.render.bake.use_pass_emit
        d["cycles.samples"] = context.scene.cycles.samples
        d["bake.normal_space"] = context.scene.render.bake.normal_space
        d["render.bake.normal_r"] = context.scene.render.bake.normal_r
        d["render.bake.normal_g"] = context.scene.render.bake.normal_g
        d["render.bake.normal_b"] = context.scene.render.bake.normal_b
        d["use_pass_color"] = context.scene.render.bake.use_pass_color
        d["bake.margin"] = context.scene.render.bake.margin

        # Grab the objects in the advanced list (if any)
        d["object_list"] = [i.obj.name for i in context.scene.TextureBake_Props.object_list]
        # Grab the target objects if there is one
        if context.scene.TextureBake_Props.target_object != None:
            d["target_object"] = context.scene.TextureBake_Props.target_object.name
        else:
            d["target_object"] = None
        # Cage object if there is one
        if context.scene.render.bake.cage_object != None:
            d["cage_object"] = context.scene.render.bake.cage_object.name
        else:
            d["cage_object"] = None

        # Channel packed images
        cp_images_dict = {}
        for cpi in context.scene.TextureBake_Props.cp_list:
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
        savename = functions.clean_file_name(context.scene.TextureBake_Props.preset_name)

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
            context.scene.TextureBake_Props.presets_list[context.scene.TextureBake_Props.presets_list_index].name
            return True
        except:
            return False

    def execute(self, context):
        # Load it
        loadname = functions.clean_file_name(\
            context.scene.TextureBake_Props.presets_list[\
            context.scene.TextureBake_Props.presets_list_index].name)

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

        context.scene.TextureBake_Props.export_preset = d["export_preset"]
        context.scene.TextureBake_Props.global_mode = d["global_mode"]
        context.scene.TextureBake_Props.ray_distance = d["ray_distance"]
        context.scene.TextureBake_Props.cage_extrusion = d["cage_extrusion"]
        context.scene.TextureBake_Props.selected_to_target = d["selected_to_target"]
        context.scene.TextureBake_Props.merged_bake = d["merged_bake"]
        context.scene.TextureBake_Props.merged_bake_name = d["merged_bake_name"]
        context.scene.TextureBake_Props.input_height = d["input_height"]
        context.scene.TextureBake_Props.input_width = d["input_width"]
        context.scene.TextureBake_Props.output_height = d["output_height"]
        context.scene.TextureBake_Props.output_width = d["output_width"]
        context.scene.TextureBake_Props.bake_32bit_float = d["bake_32bit_float"]
        context.scene.TextureBake_Props.use_alpha = d["use_alpha"]
        context.scene.TextureBake_Props.rough_glossy_switch = d["rough_glossy_switch"]
        context.scene.TextureBake_Props.normal_format_switch = d["normal_format_switch"]
        context.scene.TextureBake_Props.tex_per_mat = d["tex_per_mat"]
        context.scene.TextureBake_Props.selected_col_mats = d["selected_col_mats"]
        context.scene.TextureBake_Props.selected_col_vertex = d["selected_col_vertex"]
        context.scene.TextureBake_Props.selected_ao = d["selected_ao"]
        context.scene.TextureBake_Props.selected_thickness = d["selected_thickness"]
        context.scene.TextureBake_Props.selected_curvature = d["selected_curvature"]
        context.scene.TextureBake_Props.selected_lightmap = d["selected_lightmap"]
        context.scene.TextureBake_Props.lightmap_apply_colman = d["lightmap_apply_colman"]
        context.scene.TextureBake_Props.selected_lightmap_denoise = d["selected_lightmap_denoise"]
        context.scene.TextureBake_Props.restore_active_uvmap = d["restore_active_uvmap"]
        context.scene.TextureBake_Props.uv_mode = d["uv_mode"]
        context.scene.TextureBake_Props.udim_tiles = d["udim_tiles"]
        context.scene.TextureBake_Props.cp_file_format = d["cp_file_format"]
        context.scene.TextureBake_Props.export_textures = d["export_textures"]
        context.scene.TextureBake_Props.export_folder_per_object = d["export_folder_per_object"]
        context.scene.TextureBake_Props.export_mesh = d["export_mesh"]
        context.scene.TextureBake_Props.fbx_name = d["fbx_name"]
        context.scene.TextureBake_Props.prep_mesh = d["prep_mesh"]
        context.scene.TextureBake_Props.hide_source_objects = d["hide_source_objects"]
        context.scene.TextureBake_Props.preserve_materials = d["preserve_materials"]
        context.scene.TextureBake_Props.export_16bit = d["export_16bit"]
        context.scene.TextureBake_Props.export_file_format = d["export_file_format"]
        context.scene.TextureBake_Props.export_folder_name = d["export_folder_name"]
        context.scene.TextureBake_Props.export_color_space = d["export_color_space"]
        context.scene.TextureBake_Props.export_datetime = d["export_datetime"]
        context.scene.TextureBake_Props.run_denoise = d["run_denoise"]
        context.scene.TextureBake_Props.export_apply_modifiers = d["export_apply_modifiers"]
        context.scene.TextureBake_Props.use_object_list = d["use_object_list"]
        context.scene.TextureBake_Props.object_list_index = d["object_list_index"]
        context.scene.TextureBake_Props.background_bake = d["background_bake"]
        context.scene.TextureBake_Props.memory_limit = d["memory_limit"]
        context.scene.TextureBake_Props.batch_name = d["batch_name"]
        context.scene.TextureBake_Props.first_texture_show = d["first_texture_show"]
        context.scene.TextureBake_Props.background_bake_name = d["background_bake_name"]
        context.scene.TextureBake_Props.prefer_existing_uvmap = d["prefer_existing_uvmap"]

        context.scene.cycles.bake_type = d["bake_type"]
        context.scene.render.bake.use_pass_direct = d["use_pass_direct"]
        context.scene.render.bake.use_pass_indirect = d["use_pass_indirect"]
        context.scene.render.bake.use_pass_diffuse = d["use_pass_diffuse"]
        context.scene.render.bake.use_pass_glossy = d["use_pass_glossy"]
        context.scene.render.bake.use_pass_transmission = d["use_pass_transmission"]
        context.scene.render.bake.use_pass_emit = d["use_pass_emit"]
        context.scene.cycles.samples = d["cycles.samples"]
        context.scene.render.bake.normal_space = d["bake.normal_space"]
        context.scene.render.bake.normal_r = d["render.bake.normal_r"]
        context.scene.render.bake.normal_g = d["render.bake.normal_g"]
        context.scene.render.bake.normal_b = d["render.bake.normal_b"]
        context.scene.render.bake.use_pass_color = d["use_pass_color"]
        context.scene.render.bake.margin = d["bake.margin"]

        # Channel packing images
        if "channel_packed_images" in d:
            channel_packed_images = d["channel_packed_images"]

            if len(channel_packed_images) > 0:
                context.scene.TextureBake_Props.cp_list.clear()

            for imgname in channel_packed_images:
                thiscpi_dict = channel_packed_images[imgname]

                # Create the list item
                li = context.scene.TextureBake_Props.cp_list.add()
                li.name = imgname

                # Set the list item properies
                li.R = thiscpi_dict["R"]
                li.G = thiscpi_dict["G"]
                li.B = thiscpi_dict["B"]
                li.A = thiscpi_dict["A"]
                li.file_format = thiscpi_dict["file_format"]

        # And now the objects, if they are here
        context.scene.TextureBake_Props.object_list.clear()
        for name in d["object_list"]:
            if name in bpy.data.objects:
                item = context.scene.TextureBake_Props.object_list.add()
                item.obj = bpy.data.objects[name]

        if d["target_object"] != None and d["target_object"] in bpy.data.objects:
            context.scene.TextureBake_Props.target_object = bpy.data.objects[d["target_object"]]
        # Cage object
        if d["cage_object"] != None and d["cage_object"] in bpy.data.objects:
            context.scene.render.bake.cage_object = bpy.data.objects[d["cage_object"]]

        self.report({"INFO"}, f"Preset {loadname} loaded")
        return {'FINISHED'}


class TEXTUREBAKE_OT_refresh_presets(bpy.types.Operator):
    """Refresh list of TextureBake presets"""
    bl_idname = "texture_bake.refresh_presets"
    bl_label = "Refresh"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        context.scene.TextureBake_Props.presets_list.clear()

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
            i = context.scene.TextureBake_Props.presets_list.add()
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
            context.scene.TextureBake_Props.presets_list[context.scene.TextureBake_Props.presets_list_index].name
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
        x = context.scene.TextureBake_Props.input_width
        context.scene.TextureBake_Props.input_width = x + 1024
        y = context.scene.TextureBake_Props.input_height
        context.scene.TextureBake_Props.input_height = y + 1024

        while context.scene.TextureBake_Props.input_height % 1024 != 0:
            context.scene.TextureBake_Props.input_height -= 1

        while context.scene.TextureBake_Props.input_width % 1024 != 0:
            context.scene.TextureBake_Props.input_width -= 1

        result = min(context.scene.TextureBake_Props.input_width, context.scene.TextureBake_Props.input_height)
        context.scene.TextureBake_Props.input_width = result
        context.scene.TextureBake_Props.input_height = result

        functions.auto_set_bake_margin()
        return {'FINISHED'}


class TEXTUREBAKE_OT_decrease_bake_res(bpy.types.Operator):
    """Decrease texture resolution by 1k"""
    bl_idname = "texture_bake.decrease_bake_res"
    bl_label = "-1k"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        x = context.scene.TextureBake_Props.input_width
        context.scene.TextureBake_Props.input_width = x - 1024
        y = context.scene.TextureBake_Props.input_height
        context.scene.TextureBake_Props.input_height = y - 1024

        if context.scene.TextureBake_Props.input_height < 1:
            context.scene.TextureBake_Props.input_height = 1024

        if context.scene.TextureBake_Props.input_width < 1:
            context.scene.TextureBake_Props.input_width = 1024

        while context.scene.TextureBake_Props.input_height % 1024 != 0:
            context.scene.TextureBake_Props.input_height += 1

        while context.scene.TextureBake_Props.input_width % 1024 != 0:
            context.scene.TextureBake_Props.input_width += 1

        result = max(context.scene.TextureBake_Props.input_width, context.scene.TextureBake_Props.input_height)
        context.scene.TextureBake_Props.input_width = result
        context.scene.TextureBake_Props.input_height = result

        functions.auto_set_bake_margin()
        return {'FINISHED'}


class TEXTUREBAKE_OT_increase_output_res(bpy.types.Operator):
    """Increase output resolution by 1k"""
    bl_idname = "texture_bake.increase_output_res"
    bl_label = "+1k"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        x = context.scene.TextureBake_Props.output_width
        context.scene.TextureBake_Props.output_width = x + 1024
        y = context.scene.TextureBake_Props.output_height
        context.scene.TextureBake_Props.output_height = y + 1024

        while context.scene.TextureBake_Props.output_height % 1024 != 0:
            context.scene.TextureBake_Props.output_height -= 1

        while context.scene.TextureBake_Props.output_width % 1024 != 0:
            context.scene.TextureBake_Props.output_width -= 1

        result = min(context.scene.TextureBake_Props.output_width, context.scene.TextureBake_Props.output_height)
        context.scene.TextureBake_Props.output_width = result
        context.scene.TextureBake_Props.output_height = result

        functions.auto_set_bake_margin()
        return {'FINISHED'}


class TEXTUREBAKE_OT_decrease_output_res(bpy.types.Operator):
    """Decrease output resolution by 1k"""
    bl_idname = "texture_bake.decrease_output_res"
    bl_label = "-1k"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        x = context.scene.TextureBake_Props.output_width
        context.scene.TextureBake_Props.output_width = x - 1024
        y = context.scene.TextureBake_Props.output_height
        context.scene.TextureBake_Props.output_height = y - 1024

        if context.scene.TextureBake_Props.output_height < 1:
            context.scene.TextureBake_Props.output_height = 1024

        if context.scene.TextureBake_Props.output_width < 1:
            context.scene.TextureBake_Props.output_width = 1024

        while context.scene.TextureBake_Props.output_height % 1024 != 0:
            context.scene.TextureBake_Props.output_height += 1

        while context.scene.TextureBake_Props.output_width % 1024 != 0:
            context.scene.TextureBake_Props.output_width += 1

        result = max(context.scene.TextureBake_Props.output_width, context.scene.TextureBake_Props.output_height)
        context.scene.TextureBake_Props.output_width = result
        context.scene.TextureBake_Props.output_height = result

        functions.auto_set_bake_margin()
        return {'FINISHED'}


class TEXTUREBAKE_OT_add_packed_texture(bpy.types.Operator):
    """Add a TextureBake CP Texture item"""
    bl_idname = "texture_bake.add_packed_texture"
    bl_label = "Add"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls,context):
        return context.scene.TextureBake_Props.cp_name != ""

    def execute(self, context):
        cp_list = context.scene.TextureBake_Props.cp_list
        name = functions.clean_file_name(context.scene.TextureBake_Props.cp_name)

        if name in cp_list:
            # Delete it
            index = context.scene.TextureBake_Props.cp_list.find(name)
            context.scene.TextureBake_Props.cp_list.remove(index)

        li = cp_list.add()
        li.name = name

        li.R = context.scene.TextureBake_Props.cptex_R
        li.G = context.scene.TextureBake_Props.cptex_G
        li.B = context.scene.TextureBake_Props.cptex_B
        li.A = context.scene.TextureBake_Props.cptex_A
        li.file_format = context.scene.TextureBake_Props.cp_file_format

        context.scene.TextureBake_Props.cp_list_index = context.scene.TextureBake_Props.cp_list.find(name)

        self.report({"INFO"}, "CP texture saved")
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
        preset.uid = str(uuid.uuid4())
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

        # Unreal Engine
        item = presets.add()
        item.uid = "6a8abd21-609f-4219-9268-b5c6656a501b"
        item.name = "Unreal Engine"
        tex = item.textures.add()
        tex.name = "T_%OBJ%_%BATCH%_D"
        tex.file_format = 'TGA'
        tex.red.info = constants.PBR_DIFFUSE
        tex.green.info = constants.PBR_DIFFUSE
        tex.blue.info = constants.PBR_DIFFUSE
        tex.alpha.info = constants.PBR_OPACITY
        tex.alpha.space = 'NON_COLOR'
        tex = item.textures.add()
        tex.name = "T_%OBJ%_%BATCH%_N"
        tex.file_format = 'TGA'
        tex.red.info = constants.PBR_NORMAL_DX
        tex.red.space = 'NON_COLOR'
        tex.green.info = constants.PBR_NORMAL_DX
        tex.green.space = 'NON_COLOR'
        tex.blue.info = constants.PBR_NORMAL_DX
        tex.blue.space = 'NON_COLOR'
        tex = item.textures.add()
        tex.name = "T_%OBJ%_%BATCH%_ORM"
        tex.file_format = 'TGA'
        tex.red.info = constants.TEX_AO
        tex.red.space = 'NON_COLOR'
        tex.green.info = constants.PBR_ROUGHNESS
        tex.green.space = 'NON_COLOR'
        tex.blue.info = constants.PBR_METAL
        tex.blue.space = 'NON_COLOR'

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


class TEXTUREBAKE_OT_format_info(bpy.types.Operator):
    """Displays information about available format strings for naming textures"""
    bl_idname = "texture_bake.format_info"
    bl_label = "Formatting Options"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width = 500)

    def draw(self, context):
        layout = self.layout
        layout.row().label(text="These placeholders are available to generate image file names:")
        col = layout.column()
        row = col.split(factor=0.25)
        row.label(text="%OBJ%")
        row.label(text="Object name or 'merged_bake' for multiple objects")
        row = col.split(factor=0.25)
        row.label(text="%BATCH%")
        row.label(text="Batch name as defined in the Properties panel")
        row = col.split(factor=0.25)
        row.label(text="%BAKEMODE%")
        row.label(text="PBR or Cycles")
        row = col.split(factor=0.25)
        row.label(text="%BAKETYPE%")
        row.label(text="Diffuse, emission, AO, etc.")
