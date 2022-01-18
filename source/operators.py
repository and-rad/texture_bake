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
import tempfile
import os
import json
import uuid

from pathlib import Path
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

    def bake_textures(self, context, bake_mode):
        BakeStatus.current_map = 0
        BakeStatus.total_maps = 0

        if bake_mode == constants.BAKE_MODE_PBR:
            num_objects = len(context.selected_objects)
            if context.scene.TextureBake_Props.use_object_list:
                num_objects = len(context.scene.TextureBake_Props.object_list)
            BakeStatus.total_maps = functions.get_num_maps_to_bake() * num_objects
        elif bake_mode == constants.BAKE_MODE_S2A:
            BakeStatus.total_maps = functions.get_num_maps_to_bake()

        MasterOperation.clear()
        MasterOperation.merged_bake = context.scene.TextureBake_Props.merged_bake
        MasterOperation.merged_bake_name = context.scene.TextureBake_Props.merged_bake_name
        MasterOperation.bake_op = BakeOperation()
        MasterOperation.bake_op.bake_mode = bake_mode

        bakefunctions.common_bake_prep()

        if bake_mode == constants.BAKE_MODE_PBR:
            bakefunctions.do_bake()
        elif bake_mode == constants.BAKE_MODE_S2A:
            bakefunctions.do_bake_selected_to_target()

        # Call channel packing
        objects = MasterOperation.bake_op.bake_objects
        if bake_mode == constants.BAKE_MODE_S2A:
            objects = [MasterOperation.bake_op.sb_target_object]
        bakefunctions.channel_packing(objects)

        bakefunctions.common_bake_finishing()

        return {'FINISHED'}

    @classmethod
    def poll(cls,context):
        if bpy.context.mode != "OBJECT":
            return False
        preset = context.scene.TextureBake_Props.export_preset
        if preset == 'NONE':
            return False
        prefs = context.preferences.addons[__package__].preferences
        return [p for p in prefs.export_presets if p.uid == preset]

    def execute(self, context):
        bake_mode = constants.BAKE_MODE_PBR
        if context.scene.TextureBake_Props.selected_to_target:
            bake_mode = constants.BAKE_MODE_S2A

        # If we have been called in background mode, just get on with it. Checks should be done.
        if "--background" in sys.argv:
            return self.bake_textures(context, bake_mode)

        # We are in foreground, do usual checks
        if not functions.check_scene(context.selected_objects, bake_mode):
            return {"CANCELLED"}

        path = str(Path(tempfile.gettempdir()) / f"{os.getpid()}.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path, copy=True, check_existing=False)
        process = subprocess.Popen(
            [bpy.app.binary_path, "--background", path, "--python-expr",\
            "import bpy; import os; from pathlib import Path;\
            savepath=Path(bpy.data.filepath).parent / (str(os.getpid()) + \".blend\");\
            bpy.ops.wm.save_as_mainfile(filepath=str(savepath), check_existing=False);\
            bpy.ops.texture_bake.bake();"],
            shell=False)

        background_bake_ops.bgops_list.append(BackgroundBakeParams(process, "Export textures"))
        bpy.app.timers.register(refresh_bake_progress)
        self.report({"INFO"}, "Background bake process started")

        return {'FINISHED'}


class TEXTUREBAKE_OT_bake_input_textures(bpy.types.Operator):
    """Start the baking process for input textures"""
    bl_idname = "texture_bake.bake_input_textures"
    bl_label = "Bake Textures"

    def bake_input_maps(self, context, bake_mode):
        # Prepare the BakeStatus tracker for progress bar
        BakeStatus.current_map = 0
        BakeStatus.total_maps = 0

        if bake_mode == constants.BAKE_MODE_INPUTS:
            num_objects = len(context.selected_objects)
            if context.scene.TextureBake_Props.use_object_list:
                num_objects = len(context.scene.TextureBake_Props.object_list)
            BakeStatus.total_maps = functions.get_num_input_maps_to_bake() * num_objects
        elif bake_mode == constants.BAKE_MODE_INPUTS_S2A:
            BakeStatus.total_maps = functions.get_num_input_maps_to_bake()

        MasterOperation.clear()
        MasterOperation.merged_bake = context.scene.TextureBake_Props.merged_bake
        MasterOperation.merged_bake_name = context.scene.TextureBake_Props.merged_bake_name
        MasterOperation.bake_op = BakeOperation()
        MasterOperation.bake_op.bake_mode = bake_mode

        bakefunctions.common_bake_prep()
        bakefunctions.specials_bake()
        bakefunctions.common_bake_finishing()

        return {'FINISHED'}

    @classmethod
    def poll(cls,context):
        if not functions.any_specials():
            return False
        if bpy.context.mode != "OBJECT":
            return False
        return True

    def execute(self, context):
        bake_mode = constants.BAKE_MODE_INPUTS
        if context.scene.TextureBake_Props.selected_to_target:
            bake_mode = constants.BAKE_MODE_INPUTS_S2A

        # If we have been called in background mode, just get on with it. Checks should be done.
        if "--background" in sys.argv:
            return self.bake_input_maps(context, bake_mode)

        # We are in foreground, do usual checks
        if not functions.check_scene(context.selected_objects, bake_mode):
            return {"CANCELLED"}

        path = str(Path(tempfile.gettempdir()) / f"{os.getpid()}.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path, copy=True, check_existing=False)
        process = subprocess.Popen(
            [bpy.app.binary_path, "--background", path, "--python-expr",\
            "import bpy; import os; from pathlib import Path;\
            savepath=Path(bpy.data.filepath).parent / (str(os.getpid()) + \".blend\");\
            bpy.ops.wm.save_as_mainfile(filepath=str(savepath), check_existing=False);\
            bpy.ops.texture_bake.bake_input_textures();"],
            shell=False)

        background_bake_ops.bgops_list.append(BackgroundBakeParams(process, "Bake input maps"))
        bpy.app.timers.register(refresh_bake_progress)
        self.report({"INFO"}, "Background bake process started")

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

    @classmethod
    def poll(cls,context):
        return context.mode == "OBJECT"

    def execute(self, context):
        num_textures = 0
        while background_bake_ops.bgops_list_finished:
            pid = background_bake_ops.bgops_list_finished[0].process.pid
            bpy.ops.texture_bake.bake_import_individual(pnum = pid)
            num_textures += len(functions.read_baked_textures(pid))
        self.report({"INFO"}, f"Import complete, {num_textures} textures imported")
        return {'FINISHED'}


class TEXTUREBAKE_OT_bake_import_individual(bpy.types.Operator):
    """Import baked objects previously baked in the background"""
    bl_idname = "texture_bake.bake_import_individual"
    bl_label = "Import baked objects previously baked in the background"
    bl_options = {'INTERNAL'}

    pnum: bpy.props.IntProperty()

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        # Import textures and delete blend file
        p = ([p for p in background_bake_ops.bgops_list_finished if p.process.pid == self.pnum])[0]
        background_bake_ops.bgops_list_finished.remove(p)
        path = Path(tempfile.gettempdir()) / (str(p.process.pid) + ".blend")
        textures = functions.read_baked_textures(p.process.pid)

        with bpy.data.libraries.load(str(path), link=False) as (data_from, data_to):
            data_to.images = [name for name in data_from.images if name in textures]

        try:
            path.unlink()
            path.with_suffix(".blend1").unlink()
        except:
            pass

        # Replace previous versions of the imported textures
        for img_id in textures:
            dup_id = img_id + ".001"
            if dup_id in bpy.data.images:
                old_img = bpy.data.images[img_id]
                new_img = bpy.data.images[dup_id]
                functions.replace_image(old_img, new_img)

        self.report({"INFO"}, f"Import complete, {len(textures)} textures imported")
        return {'FINISHED'}


class TEXTUREBAKE_OT_bake_delete(bpy.types.Operator):
    """Delete all background bakes without importing the results into Blender. Exported textures are not deleted and remain on disk"""
    bl_idname = "texture_bake.bake_delete"
    bl_label = "Delete the background bakes"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        while background_bake_ops.bgops_list_finished:
            pid = background_bake_ops.bgops_list_finished[0].process.pid
            bpy.ops.texture_bake.bake_delete_individual(pnum = pid)
        return {'FINISHED'}


class TEXTUREBAKE_OT_bake_delete_individual(bpy.types.Operator):
    """Delete this individual background bake without importing the results into Blender. Exported textures are not deleted and remain on disk"""
    bl_idname = "texture_bake.bake_delete_individual"
    bl_label = "Delete the individual background bake"
    bl_options = {'INTERNAL'}

    pnum: bpy.props.IntProperty()

    def execute(self, context):
        try:
            path = Path(tempfile.gettempdir()) / (str(self.pnum) + ".blend")
            path.unlink()
            path.with_suffix(".blend1").unlink()
        except:
            pass

        background_bake_ops.bgops_list_finished = [p for p in background_bake_ops.bgops_list_finished if p.process.pid != self.pnum]
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
        d["rough_glossy_switch"] = context.scene.TextureBake_Props.rough_glossy_switch
        d["tex_per_mat"] = context.scene.TextureBake_Props.tex_per_mat
        d["selected_col_mats"] = context.scene.TextureBake_Props.selected_col_mats
        d["selected_col_vertex"] = context.scene.TextureBake_Props.selected_col_vertex
        d["selected_ao"] = context.scene.TextureBake_Props.selected_ao
        d["selected_thickness"] = context.scene.TextureBake_Props.selected_thickness
        d["selected_curvature"] = context.scene.TextureBake_Props.selected_curvature
        d["prefer_existing_uvmap"] = context.scene.TextureBake_Props.prefer_existing_uvmap
        d["bake_udims"] = context.scene.TextureBake_Props.bake_udims
        d["udim_tiles"] = context.scene.TextureBake_Props.udim_tiles
        d["export_textures"] = context.scene.TextureBake_Props.export_textures
        d["export_folder_per_object"] = context.scene.TextureBake_Props.export_folder_per_object
        d["export_folder_name"] = context.scene.TextureBake_Props.export_folder_name
        d["export_datetime"] = context.scene.TextureBake_Props.export_datetime
        d["use_object_list"] = context.scene.TextureBake_Props.use_object_list
        d["object_list_index"] = context.scene.TextureBake_Props.object_list_index
        d["memory_limit"] = context.scene.TextureBake_Props.memory_limit
        d["batch_name"] = context.scene.TextureBake_Props.batch_name

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
        context.scene.TextureBake_Props.rough_glossy_switch = d["rough_glossy_switch"]
        context.scene.TextureBake_Props.tex_per_mat = d["tex_per_mat"]
        context.scene.TextureBake_Props.selected_col_mats = d["selected_col_mats"]
        context.scene.TextureBake_Props.selected_col_vertex = d["selected_col_vertex"]
        context.scene.TextureBake_Props.selected_ao = d["selected_ao"]
        context.scene.TextureBake_Props.selected_thickness = d["selected_thickness"]
        context.scene.TextureBake_Props.selected_curvature = d["selected_curvature"]
        context.scene.TextureBake_Props.bake_udims = d["bake_udims"]
        context.scene.TextureBake_Props.udim_tiles = d["udim_tiles"]
        context.scene.TextureBake_Props.export_textures = d["export_textures"]
        context.scene.TextureBake_Props.export_folder_per_object = d["export_folder_per_object"]
        context.scene.TextureBake_Props.export_folder_name = d["export_folder_name"]
        context.scene.TextureBake_Props.export_datetime = d["export_datetime"]
        context.scene.TextureBake_Props.use_object_list = d["use_object_list"]
        context.scene.TextureBake_Props.object_list_index = d["object_list_index"]
        context.scene.TextureBake_Props.memory_limit = d["memory_limit"]
        context.scene.TextureBake_Props.batch_name = d["batch_name"]
        context.scene.TextureBake_Props.prefer_existing_uvmap = d["prefer_existing_uvmap"]

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
        tex.file_format = 'TARGA'
        tex.depth = '8'
        tex.red.info = constants.PBR_DIFFUSE
        tex.red.space = 'sRGB'
        tex.green.info = constants.PBR_DIFFUSE
        tex.green.space = 'sRGB'
        tex.blue.info = constants.PBR_DIFFUSE
        tex.blue.space = 'sRGB'
        tex.alpha.info = constants.PBR_OPACITY
        tex.alpha.space = 'Non-Color'

        tex = item.textures.add()
        tex.name = "T_%OBJ%_%BATCH%_E"
        tex.file_format = 'TARGA'
        tex.depth = '8'
        tex.red.info = constants.PBR_EMISSION
        tex.red.space = 'sRGB'
        tex.green.info = constants.PBR_EMISSION
        tex.green.space = 'sRGB'
        tex.blue.info = constants.PBR_EMISSION
        tex.blue.space = 'sRGB'

        tex = item.textures.add()
        tex.name = "T_%OBJ%_%BATCH%_N"
        tex.file_format = 'TARGA'
        tex.depth = '8'
        tex.red.info = constants.PBR_NORMAL_DX
        tex.red.space = 'Non-Color'
        tex.green.info = constants.PBR_NORMAL_DX
        tex.green.space = 'Non-Color'
        tex.blue.info = constants.PBR_NORMAL_DX
        tex.blue.space = 'Non-Color'

        tex = item.textures.add()
        tex.name = "T_%OBJ%_%BATCH%_ORM"
        tex.file_format = 'TARGA'
        tex.depth = '8'
        tex.red.info = constants.PBR_AO
        tex.red.space = 'Non-Color'
        tex.green.info = constants.PBR_ROUGHNESS
        tex.green.space = 'Non-Color'
        tex.blue.info = constants.PBR_METAL
        tex.blue.space = 'Non-Color'

        # Normal map DirectX
        item = presets.add()
        item.uid = "52819e17-c9e2-454c-8be8-e75c2b04e1cd"
        item.name = "Normal Map (DirectX)"

        tex = item.textures.add()
        tex.name = "%OBJ%_%BATCH%_Normal_DX"
        tex.file_format = 'PNG'
        tex.depth = '16'
        tex.red.info = constants.PBR_NORMAL_DX
        tex.red.space = 'Non-Color'
        tex.green.info = constants.PBR_NORMAL_DX
        tex.green.space = 'Non-Color'
        tex.blue.info = constants.PBR_NORMAL_DX
        tex.blue.space = 'Non-Color'

        # Normal map OpenGL
        item = presets.add()
        item.uid = "6711b4ef-064f-42fb-be00-fd8662cf4382"
        item.name = "Normal Map (OpenGL)"

        tex = item.textures.add()
        tex.name = "%OBJ%_%BATCH%_Normal_OGL"
        tex.file_format = 'PNG'
        tex.depth = '16'
        tex.red.info = constants.PBR_NORMAL_OGL
        tex.red.space = 'Non-Color'
        tex.green.info = constants.PBR_NORMAL_OGL
        tex.green.space = 'Non-Color'
        tex.blue.info = constants.PBR_NORMAL_OGL
        tex.blue.space = 'Non-Color'

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
