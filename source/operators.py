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
from .bake_operation import BakeOperation, MasterOperation, BakeStatus, bakestolist, SimpleBakeConstants
from . import functions
from . import bakefunctions
from .bg_bake import bgbake_ops
from pathlib import Path
import tempfile
import json

from .ui import SimpleBakePreferences
from datetime import datetime
from math import floor


class OBJECT_OT_simple_bake_mapbake(bpy.types.Operator):
    """Start the baking process"""
    bl_idname = "object.simple_bake_mapbake"
    bl_label = "Bake"


    def execute(self, context):

        def commence_bake(needed_bake_modes):

            #Prepare the BakeStatus tracker for progress bar
            num_of_objects = 0
            if bpy.context.scene.SimpleBake_Props.advancedobjectselection:
                num_of_objects = len(bpy.context.scene.SimpleBake_Props.bakeobjs_advanced_list)
            else:
                num_of_objects = len(bpy.context.selected_objects)


            total_maps = 0
            for need in needed_bake_modes:
                if need == SimpleBakeConstants.PBR:
                    total_maps+=(bakestolist(justcount=True) * num_of_objects)
                if need == SimpleBakeConstants.PBRS2A:
                    total_maps+=1*bakestolist(justcount=True)
                if need == SimpleBakeConstants.CYCLESBAKE and not bpy.context.scene.SimpleBake_Props.cycles_s2a:
                    total_maps+=1* num_of_objects
                if need == SimpleBakeConstants.CYCLESBAKE and bpy.context.scene.SimpleBake_Props.cycles_s2a:
                    total_maps+=1
                if need == SimpleBakeConstants.SPECIALS:
                    total_maps+=(functions.import_needed_specials_materials(justcount = True) * num_of_objects)
                    if bpy.context.scene.SimpleBake_Props.selected_col_mats: total_maps+=1*num_of_objects
                    if bpy.context.scene.SimpleBake_Props.selected_col_vertex: total_maps+=1*num_of_objects
                if need in [SimpleBakeConstants.SPECIALS_CYCLES_TARGET_ONLY, SimpleBakeConstants.SPECIALS_PBR_TARGET_ONLY]:
                    total_maps+=(functions.import_needed_specials_materials(justcount = True))
                    if bpy.context.scene.SimpleBake_Props.selected_col_mats: total_maps+=1
                    if bpy.context.scene.SimpleBake_Props.selected_col_vertex: total_maps+=1


            BakeStatus.total_maps = total_maps


            #Clear the MasterOperation stuff
            MasterOperation.clear()

            #Set master operation variables
            MasterOperation.merged_bake = bpy.context.scene.SimpleBake_Props.mergedBake
            MasterOperation.merged_bake_name = bpy.context.scene.SimpleBake_Props.mergedBakeName

            #Make sure there are no deleted items in the list
            functions.update_advanced_object_list()

            #Need to know the total operations
            MasterOperation.total_bake_operations = len(needed_bake_modes)

            #Master list of all ops
            bops = []

            for need in needed_bake_modes:
                #Create operation
                bop = BakeOperation()
                bop.bake_mode = need

                bops.append(bop)
                functions.printmsg(f"Created operation for {need}")

            #Run queued operations
            for bop in bops:
                MasterOperation.this_bake_operation_num+=1
                MasterOperation.current_bake_operation = bop
                if bop.bake_mode == SimpleBakeConstants.PBR:
                    functions.printmsg("Running PBR bake")
                    bakefunctions.doBake()
                elif bop.bake_mode == SimpleBakeConstants.PBRS2A:
                    functions.printmsg("Running PBR S2A bake")
                    bakefunctions.doBakeS2A()
                elif bop.bake_mode == SimpleBakeConstants.CYCLESBAKE:
                    functions.printmsg("Running Cycles bake")
                    bakefunctions.cyclesBake()
                elif bop.bake_mode in [SimpleBakeConstants.SPECIALS, SimpleBakeConstants.SPECIALS_CYCLES_TARGET_ONLY, SimpleBakeConstants.SPECIALS_PBR_TARGET_ONLY]:
                    functions.printmsg("Running Specials bake")
                    bakefunctions.specialsBake()

            #Call channel packing
            #Only possilbe if we baked some kind of PBR. At the moment, can't have non-S2A and S2A
            if len([bop for bop in bops if bop.bake_mode == SimpleBakeConstants.PBR]) > 0:
                #Should still be active from last bake op
                objects = MasterOperation.current_bake_operation.bake_objects
                bakefunctions.channel_packing(objects)
            if len([bop for bop in bops if bop.bake_mode == SimpleBakeConstants.PBRS2A]) > 0:
                #Should still be active from last bake op
                objects = [MasterOperation.current_bake_operation.sb_target_object]
                bakefunctions.channel_packing(objects)

            return True



        #Entry Point ----------------------------------------------------


        needed_bake_modes = []
        if bpy.context.scene.SimpleBake_Props.global_mode == "pbr_bake" and not bpy.context.scene.SimpleBake_Props.selected_s2a:
            needed_bake_modes.append(SimpleBakeConstants.PBR)
        if bpy.context.scene.SimpleBake_Props.global_mode == "pbr_bake" and bpy.context.scene.SimpleBake_Props.selected_s2a:
            needed_bake_modes.append(SimpleBakeConstants.PBRS2A)
        if bpy.context.scene.SimpleBake_Props.global_mode == "cycles_bake":
            needed_bake_modes.append(SimpleBakeConstants.CYCLESBAKE)

        if functions.any_specials() and SimpleBakeConstants.PBRS2A in needed_bake_modes:
            needed_bake_modes.append(SimpleBakeConstants.SPECIALS_PBR_TARGET_ONLY)
        elif functions.any_specials() and SimpleBakeConstants.CYCLESBAKE in needed_bake_modes and bpy.context.scene.SimpleBake_Props.cycles_s2a:
            needed_bake_modes.append(SimpleBakeConstants.SPECIALS_CYCLES_TARGET_ONLY)
        elif functions.any_specials():
            needed_bake_modes.append(SimpleBakeConstants.SPECIALS)


        #Clear the progress stuff
        BakeStatus.current_map = 0
        BakeStatus.total_maps = 0


        #If we have been called in background mode, just get on with it. Checks should be done.
        if "--background" in sys.argv:
            if "SimpleBake_Bakes" in bpy.data.collections:
                #Remove any prior baked objects
                bpy.data.collections.remove(bpy.data.collections["SimpleBake_Bakes"])

            #Bake
            ts = datetime.now()
            commence_bake(needed_bake_modes)
            tf = datetime.now()
            s = (tf-ts).seconds
            functions.printmsg(f"Time taken - {s} seconds ({floor(s/60)} minutes, {s%60} seconds)")

            self.report({"INFO"}, "Bake complete")
            return {'FINISHED'}


        #We are in foreground, do usual checks
        result = True
        for need in needed_bake_modes:
            if not functions.startingChecks(bpy.context.selected_objects, need):
                result = False

        if not result:
            return {"CANCELLED"}


        #If the user requested background mode, fire that up now and exit
        if bpy.context.scene.SimpleBake_Props.bgbake == "bg":
            bpy.ops.wm.save_mainfile()
            filepath = filepath = bpy.data.filepath
            process = subprocess.Popen(
                [bpy.app.binary_path, "--background",filepath, "--python-expr",\
                "import bpy;\
                import os;\
                from pathlib import Path;\
                savepath=Path(bpy.data.filepath).parent / (str(os.getpid()) + \".blend\");\
                bpy.ops.wm.save_as_mainfile(filepath=str(savepath), check_existing=False);\
                bpy.ops.object.simple_bake_mapbake();"],
                shell=False)

            bgbake_ops.bgops_list.append([process, bpy.context.scene.SimpleBake_Props.prepmesh,
                bpy.context.scene.SimpleBake_Props.hidesourceobjects, bpy.context.scene.SimpleBake_Props.bgbake_name])

            self.report({"INFO"}, "Background bake process started")
            return {'FINISHED'}

        #If we are doing this here and now, get on with it

        #Create a bake operation
        ts = datetime.now()
        commence_bake(needed_bake_modes)
        tf = datetime.now()
        s = (tf-ts).seconds
        functions.printmsg(f"Time taken - {s} seconds ({floor(s/60)} minutes, {s%60} seconds)")

        self.report({"INFO"}, "Bake complete")
        return {'FINISHED'}

class OBJECT_OT_simple_bake_sketchfabupload(bpy.types.Operator):
    """You can only upload (an) object(s) created with the "Copy objects and apply bakes" option. If this button is grayed out, you haven't got the correct objects selected.
Not available if .blend file not saved or if no Sketchfab API key set in user preferences.
Get your API key from the account section of Sketchfab.com"""
    bl_idname = "object.simple_bake_sketchfabupload"
    bl_label = "Upload to Sketchfab"

    @classmethod
    def poll(cls, context):
        for obj in bpy.context.selected_objects:
            try:
                obj["SB_createdfrom"]
            except:
                return False

        try:
            bpy.context.active_object["SB_createdfrom"]
        except:
            return False

        return True

    def execute(self, context):

        #Sketchfab upload

        #Check for API key
        preferences = bpy.context.preferences
        addon_prefs = preferences.addons[__package__].preferences
        apikey = addon_prefs.apikey
        if apikey == "":
            self.report({"ERROR"}, "ERROR: Sketchfab API key needed. Set your API key in Blender user preferences under addons, SimpleBake. Get your API key from Sketchfab.com")
            return {'CANCELLED'}

        result = bakefunctions.sketchfabupload(self)

        if result:
            self.report({"INFO"}, "Upload operation complete. Your web browser should have opened. Check console for any errors.")
            return {'FINISHED'}
        else:
            return {'CANCELLED'}


class OBJECT_OT_simple_bake_selectall(bpy.types.Operator):
    """Select all PBR bake types"""
    bl_idname = "object.simple_bake_selectall"
    bl_label = "Select All"

    def execute(self, context):
        bpy.context.scene.SimpleBake_Props.selected_col = True
        bpy.context.scene.SimpleBake_Props.selected_metal = True
        bpy.context.scene.SimpleBake_Props.selected_rough = True
        bpy.context.scene.SimpleBake_Props.selected_normal = True
        bpy.context.scene.SimpleBake_Props.selected_trans = True
        bpy.context.scene.SimpleBake_Props.selected_transrough = True
        bpy.context.scene.SimpleBake_Props.selected_emission = True
        bpy.context.scene.SimpleBake_Props.selected_clearcoat = True
        bpy.context.scene.SimpleBake_Props.selected_clearcoat_rough = True
        bpy.context.scene.SimpleBake_Props.selected_specular = True
        bpy.context.scene.SimpleBake_Props.selected_alpha = True
        bpy.context.scene.SimpleBake_Props.selected_sss = True
        bpy.context.scene.SimpleBake_Props.selected_ssscol = True
        return {'FINISHED'}

class OBJECT_OT_simple_bake_selectnone(bpy.types.Operator):
    """Select none PBR bake types"""
    bl_idname = "object.simple_bake_selectnone"
    bl_label = "Select None"

    def execute(self, context):
        bpy.context.scene.SimpleBake_Props.selected_col = False
        bpy.context.scene.SimpleBake_Props.selected_metal = False
        bpy.context.scene.SimpleBake_Props.selected_rough = False
        bpy.context.scene.SimpleBake_Props.selected_normal = False
        bpy.context.scene.SimpleBake_Props.selected_trans = False
        bpy.context.scene.SimpleBake_Props.selected_transrough = False
        bpy.context.scene.SimpleBake_Props.selected_emission = False
        bpy.context.scene.SimpleBake_Props.selected_clearcoat = False
        bpy.context.scene.SimpleBake_Props.selected_clearcoat_rough = False
        bpy.context.scene.SimpleBake_Props.selected_specular = False
        bpy.context.scene.SimpleBake_Props.selected_alpha = False
        bpy.context.scene.SimpleBake_Props.selected_sss = False
        bpy.context.scene.SimpleBake_Props.selected_ssscol = False
        return {'FINISHED'}

class OBJECT_OT_simple_bake_installupdate(bpy.types.Operator):
    """Download and install the most recent version of SimpleBake"""
    bl_idname = "object.simple_bake_installupdate"
    bl_label = "Download and Install Update"

    def execute(self, context):
        global justupdated
        result = functions.install_addon_update()

        if result[0] == True:
            self.report({"INFO"}, "Update complete. Restart Blender")
            SimpleBakePreferences.justupdated = True
        else:
            self.report({"ERROR"}, f"Could not download update. Error: {result[1]}")
            justupdated = False
        return {'FINISHED'}

class OBJECT_OT_simple_bake_default_imgname_string(bpy.types.Operator):
    """Reset the image name string to default (Sketchfab compatible)"""
    bl_idname = "object.simple_bake_default_imgname_string"
    bl_label = "Restore image string to default"

    def execute(self, context):
        from .ui import SimpleBakePreferences
        SimpleBakePreferences.reset_img_string()

        return {'FINISHED'}

class OBJECT_OT_simple_bake_default_aliases(bpy.types.Operator):
    """Reset the image name string to default (Sketchfab compatible)"""
    bl_idname = "object.simple_bake_default_aliases"
    bl_label = "Restore all bake type aliases to default"

    def execute(self, context):
        from .ui import SimpleBakePreferences
        SimpleBakePreferences.reset_aliases()

        return {'FINISHED'}

class OBJECT_OT_simple_bake_bgbake_status(bpy.types.Operator):
    """Check on the status of bakes running in the background"""
    bl_idname = "object.simple_bake_bgbake_status"
    bl_label = "Check on the status of bakes running in the background"

    def execute(self, context):
        msg_items = []


        #Display remaining
        if len(bgbake_ops.bgops_list) == 0:
            msg_items.append("No background bakes are currently running")

        else:
            msg_items.append(f"--------------------------")
            for p in bgbake_ops.bgops_list:

                t = Path(tempfile.gettempdir())
                t = t / f"SimpleBake_Bgbake_{str(p[0].pid)}"
                try:
                    with open(str(t), "r") as progfile:
                        progress = progfile.readline()
                except:
                    #No file yet, as no bake operation has completed yet. Holding message
                    progress = 0

                msg_items.append(f"RUNNING: Process ID: {str(p[0].pid)} - Progress {progress}%")
                msg_items.append(f"--------------------------")

        functions.ShowMessageBox(msg_items, "Background Bake Status(es)")

        return {'FINISHED'}

class OBJECT_OT_simple_bake_bgbake_import(bpy.types.Operator):
    """Import baked objects previously baked in the background"""
    bl_idname = "object.simple_bake_bgbake_import"
    bl_label = "Import baked objects previously baked in the background"

    def execute(self, context):

        if bpy.context.mode != "OBJECT":
            self.report({"ERROR"}, "You must be in object mode")
            return {'CANCELLED'}



        for p in bgbake_ops.bgops_list_finished:

            savepath = Path(bpy.data.filepath).parent
            pid_str = str(p[0].pid)
            path = savepath / (pid_str + ".blend")
            path = str(path) + "\\Collection\\"

            #Record the objects and collections before append (as append doesn't give us a reference to the new stuff)
            functions.spot_new_items(initialise=True, item_type="objects")
            functions.spot_new_items(initialise=True, item_type="collections")
            functions.spot_new_items(initialise=True, item_type="images")


            #Append
            bpy.ops.wm.append(filename="SimpleBake_Bakes", directory=path, use_recursive=False, active_collection=False)

            # #No idea why we have to do this, but apparently we do
            # for img in bpy.data.images:
                # try:
                    # if img["SB"] != "":
                        # img.filepath = img.filepath.replace("../../", "")
                # except:
                    # pass

            #If we didn't actually want the objects, delete them
            if not p[1]:
                #Delete objects we just imported (leaving only textures)

                # for obj in bpy.data.objects:
                    # if not obj.name in objects_before_names:
                        # bpy.data.objects.remove(obj)
                # for col in bpy.data.collections:
                    # if not col.name in cols_before_names:
                        # bpy.data.collections.remove(col)

                for obj_name in functions.spot_new_items(initialise=False, item_type = "objects"):
                    bpy.data.objects.remove(bpy.data.objects[obj_name])
                for col_name in functions.spot_new_items(initialise=False, item_type = "collections"):
                    bpy.data.collections.remove(bpy.data.collections[col_name])


            #If we have to hide the source objects, do it
            if p[2]:
                #Get the newly introduced objects:
                objects_before_names = functions.spot_new_items(initialise=False, item_type="objects")

                for obj_name in objects_before_names:
                    #Try this in case there are issues with long object names.. better than a crash
                    try:
                        bpy.data.objects[obj_name.replace("_Baked", "")].hide_set(True)
                    except:
                        pass


            #Delete the temp blend file
            try:
                os.remove(str(savepath / pid_str) + ".blend")
                os.remove(str(savepath / pid_str) + ".blend1")
            except:
                pass

        #Clear list for next time
        bgbake_ops.bgops_list_finished = []


        #Confirm back to user
        self.report({"INFO"}, "Import complete")

        messagelist = []
        #messagelist.append(f"{len(bpy.data.objects)-len(objects_before_names)} objects imported")
        #messagelist.append(f"{len(bpy.data.images)-len(images_before_names)} textures imported")

        messagelist.append(f"{len(functions.spot_new_items(initialise=False, item_type='objects'))} objects imported")
        messagelist.append(f"{len(functions.spot_new_items(initialise=False, item_type='images'))} textures imported")

        functions.ShowMessageBox(messagelist, "Import complete", icon = 'INFO')


        #If we imported an image, and we already had an image with the same name, get rid of the original in favour of the imported
        new_images_names = functions.spot_new_items(initialise=False, item_type="images")


        # images_before_names #We have a list of the names before
        # #Get a list of the names after
        # images_after_names = []
        # for img in bpy.data.images:
            # images_after_names.append(img.name)

        # #Compaure lists
        # new_images_names = functions.diff(images_after_names, images_before_names)

        #Find any .001s
        for imgname in new_images_names:
            try:
                int(imgname[-3:])

                #Delete the existing version
                bpy.data.images.remove(bpy.data.images[imgname[0:-4]])

                #Rename our version
                bpy.data.images[imgname].name = imgname[0:-4]

            except ValueError:
                pass


        return {'FINISHED'}


class OBJECT_OT_simple_bake_bgbake_import_individual(bpy.types.Operator):
    """Import baked objects previously baked in the background"""
    bl_idname = "object.simple_bake_bgbake_import_individual"
    bl_label = "Import baked objects previously baked in the background"

    pnum: bpy.props.IntProperty()

    def execute(self, context):

        if bpy.context.mode != "OBJECT":
            self.report({"ERROR"}, "You must be in object mode")
            return {'CANCELLED'}

        #Need to get the actual SINGLE entry from the list
        p = [p for p in bgbake_ops.bgops_list_finished if p[0].pid == self.pnum]
        assert(len(p) == 1)
        p = p[0]


        savepath = Path(bpy.data.filepath).parent
        pid_str = str(p[0].pid)
        path = savepath / (pid_str + ".blend")
        path = str(path) + "\\Collection\\"

        #Record the objects and collections before append (as append doesn't give us a reference to the new stuff)
        functions.spot_new_items(initialise=True, item_type="objects")
        functions.spot_new_items(initialise=True, item_type="collections")
        functions.spot_new_items(initialise=True, item_type="images")

        #Append
        bpy.ops.wm.append(filename="SimpleBake_Bakes", directory=path, use_recursive=False, active_collection=False)


        #If we didn't actually want the objects, delete them
        if not p[1]:

            for obj_name in functions.spot_new_items(initialise=False, item_type = "objects"):
                bpy.data.objects.remove(bpy.data.objects[obj_name])
            for col_name in functions.spot_new_items(initialise=False, item_type = "collections"):
                bpy.data.collections.remove(bpy.data.collections[col_name])


        #If we have to hide the source objects, do it
        if p[2]:
            #Get the newly introduced objects:
            objects_before_names = functions.spot_new_items(initialise=False, item_type="objects")

            for obj_name in objects_before_names:
                #Try this in case there are issues with long object names.. better than a crash
                try:
                    bpy.data.objects[obj_name.replace("_Baked", "")].hide_set(True)
                except:
                    pass


        #Delete the temp blend file
        try:
            os.remove(str(savepath / pid_str) + ".blend")
            os.remove(str(savepath / pid_str) + ".blend1")
        except:
            pass


        #Remove this P from the list
        bgbake_ops.bgops_list_finished = [p for p in bgbake_ops.bgops_list_finished if p[0].pid != self.pnum]

        #Confirm back to user
        self.report({"INFO"}, "Import complete")

        messagelist = []
        messagelist.append(f"{len(functions.spot_new_items(initialise=False, item_type='objects'))} objects imported")
        messagelist.append(f"{len(functions.spot_new_items(initialise=False, item_type='images'))} textures imported")

        functions.ShowMessageBox(messagelist, "Import complete", icon = 'INFO')

        #If we imported an image, and we already had an image with the same name, get rid of the original in favour of the imported
        new_images_names = functions.spot_new_items(initialise=False, item_type="images")

        #Find any .001s
        for imgname in new_images_names:
            try:
                int(imgname[-3:])

                #Delete the existing version
                bpy.data.images.remove(bpy.data.images[imgname[0:-4]])

                #Rename our version
                bpy.data.images[imgname].name = imgname[0:-4]

            except ValueError:
                pass

        return {'FINISHED'}

class OBJECT_OT_simple_bake_bgbake_clear(bpy.types.Operator):
    """Delete the background bakes because you don't want to import them into Blender. NOTE: If you chose to save bakes or FBX externally, these are safe and NOT deleted. This is just if you don't want to import into this Blender session"""
    bl_idname = "object.simple_bake_bgbake_clear"
    bl_label = "Delete the background bakes"

    def execute(self, context):
        savepath = Path(bpy.data.filepath).parent

        for p in bgbake_ops.bgops_list_finished:
            pid_str = str(p[0].pid)
            try:
                os.remove(str(savepath / pid_str) + ".blend")
                os.remove(str(savepath / pid_str) + ".blend1")
            except:
                pass

        bgbake_ops.bgops_list_finished = []

        return {'FINISHED'}

class OBJECT_OT_simple_bake_bgbake_delete_individual(bpy.types.Operator):
    """Delete this individual background bake because you don't want to import the results into Blender. NOTE: If you chose to save bakes or FBX externally, these are safe and NOT deleted. This is just if you don't want to import into this Blender session"""
    bl_idname = "object.simple_bake_bgbake_delete_individual"
    bl_label = "Delete the individual background bake"

    pnum: bpy.props.IntProperty()

    def execute(self, context):
        pid_str = str(self.pnum)
        savepath = Path(bpy.data.filepath).parent
        try:
            os.remove(str(savepath / pid_str) + ".blend")
            os.remove(str(savepath / pid_str) + ".blend1")
        except:
            pass

        bgbake_ops.bgops_list_finished = [p for p in bgbake_ops.bgops_list_finished if p[0].pid != self.pnum]

        return {'FINISHED'}


class OBJECT_OT_simple_bake_protect_clear(bpy.types.Operator):
    """If you are online, you likely need to complete the 'I am not a robot' check on the web server. Click here to do that. All will be explained..."""
    bl_idname = "object.simple_bake_protect_clear"
    bl_label = "Launch web browser"

    def execute(self, context):
        import webbrowser
        webbrowser.open('http://www.toohey.co.uk/SimpleBake/protect_clear.html', new=2)

        return {'FINISHED'}



class OBJECT_OT_simple_bake_import_special_mats(bpy.types.Operator):
    """Import the selected specials materials if you want to edit them. Once edited, they will be used for all bakes of that type in this file"""
    bl_idname = "object.simple_bake_import_special_mats"
    bl_label = "Import specials materials"

    @classmethod
    def poll(cls,context):
        return bpy.context.scene.SimpleBake_Props.selected_ao or\
            bpy.context.scene.SimpleBake_Props.selected_curvature or\
            bpy.context.scene.SimpleBake_Props.selected_thickness or\
            bpy.context.scene.SimpleBake_Props.selected_lightmap

    def execute(self, context):
        functions.import_needed_specials_materials()
        self.report({"INFO"}, "Materials imported into scene. Create a dummy object and edit them. They will be used for Specials bakes of this type going forwards")

        return {'FINISHED'}


class OBJECT_OT_simple_bake_preset_save(bpy.types.Operator):
    """Save current SimpleBake settings to preset"""
    bl_idname = "object.simple_bake_preset_save"
    bl_label = "Save"

    @classmethod
    def poll(cls,context):
        return bpy.context.scene.SimpleBake_Props.preset_name != ""

    def execute(self, context):

        d = {}

        #SimpleBake internal
        d["global_mode"] = bpy.context.scene.SimpleBake_Props.global_mode
        d["ray_distance"] = bpy.context.scene.SimpleBake_Props.ray_distance
        d["cage_extrusion"] = bpy.context.scene.SimpleBake_Props.cage_extrusion
        d["selected_s2a"] = bpy.context.scene.SimpleBake_Props.selected_s2a
        d["mergedBake"] = bpy.context.scene.SimpleBake_Props.mergedBake
        d["mergedBakeName"] = bpy.context.scene.SimpleBake_Props.mergedBakeName
        d["cycles_s2a"] = bpy.context.scene.SimpleBake_Props.cycles_s2a
        d["imgheight"] = bpy.context.scene.SimpleBake_Props.imgheight
        d["imgwidth"] = bpy.context.scene.SimpleBake_Props.imgwidth
        d["outputheight"] = bpy.context.scene.SimpleBake_Props.outputheight
        d["outputwidth"] = bpy.context.scene.SimpleBake_Props.outputwidth
        d["everything32bitfloat"] = bpy.context.scene.SimpleBake_Props.everything32bitfloat
        d["useAlpha"] = bpy.context.scene.SimpleBake_Props.useAlpha
        d["rough_glossy_switch"] = bpy.context.scene.SimpleBake_Props.rough_glossy_switch
        d["normal_format_switch"] = bpy.context.scene.SimpleBake_Props.normal_format_switch
        d["tex_per_mat"] = bpy.context.scene.SimpleBake_Props.tex_per_mat
        d["selected_col"] = bpy.context.scene.SimpleBake_Props.selected_col
        d["selected_metal"] = bpy.context.scene.SimpleBake_Props.selected_metal
        d["selected_rough"] = bpy.context.scene.SimpleBake_Props.selected_rough
        d["selected_normal"] = bpy.context.scene.SimpleBake_Props.selected_normal
        d["selected_trans"] = bpy.context.scene.SimpleBake_Props.selected_trans
        d["selected_transrough"] = bpy.context.scene.SimpleBake_Props.selected_transrough
        d["selected_emission"] = bpy.context.scene.SimpleBake_Props.selected_emission
        d["selected_sss"] = bpy.context.scene.SimpleBake_Props.selected_sss
        d["selected_ssscol"] = bpy.context.scene.SimpleBake_Props.selected_ssscol
        d["selected_clearcoat"] = bpy.context.scene.SimpleBake_Props.selected_clearcoat
        d["selected_clearcoat_rough"] = bpy.context.scene.SimpleBake_Props.selected_clearcoat_rough
        d["selected_specular"] = bpy.context.scene.SimpleBake_Props.selected_specular
        d["selected_alpha"] = bpy.context.scene.SimpleBake_Props.selected_alpha
        d["selected_col_mats"] = bpy.context.scene.SimpleBake_Props.selected_col_mats
        d["selected_col_vertex"] = bpy.context.scene.SimpleBake_Props.selected_col_vertex
        d["selected_ao"] = bpy.context.scene.SimpleBake_Props.selected_ao
        d["selected_thickness"] = bpy.context.scene.SimpleBake_Props.selected_thickness
        d["selected_curvature"] = bpy.context.scene.SimpleBake_Props.selected_curvature
        d["selected_lightmap"] = bpy.context.scene.SimpleBake_Props.selected_lightmap
        d["lightmap_apply_colman"] = bpy.context.scene.SimpleBake_Props.lightmap_apply_colman
        d["selected_lightmap_denoise"] = bpy.context.scene.SimpleBake_Props.selected_lightmap_denoise
        d["newUVoption"] = bpy.context.scene.SimpleBake_Props.newUVoption
        d["prefer_existing_sbmap"] = bpy.context.scene.SimpleBake_Props.prefer_existing_sbmap
        d["newUVmethod"] = bpy.context.scene.SimpleBake_Props.newUVmethod
        d["restoreOrigUVmap"] = bpy.context.scene.SimpleBake_Props.restoreOrigUVmap
        d["uvpackmargin"] = bpy.context.scene.SimpleBake_Props.uvpackmargin
        d["averageUVsize"] = bpy.context.scene.SimpleBake_Props.averageUVsize
        d["expand_mat_uvs"] = bpy.context.scene.SimpleBake_Props.expand_mat_uvs
        d["uv_mode"] = bpy.context.scene.SimpleBake_Props.uv_mode
        d["udim_tiles"] = bpy.context.scene.SimpleBake_Props.udim_tiles
        d["unwrapmargin"] = bpy.context.scene.SimpleBake_Props.unwrapmargin
        d["channelpackfileformat"] = bpy.context.scene.SimpleBake_Props.channelpackfileformat
        d["saveExternal"] = bpy.context.scene.SimpleBake_Props.saveExternal
        d["exportFolderPerObject"] = bpy.context.scene.SimpleBake_Props.exportFolderPerObject
        d["saveObj"] = bpy.context.scene.SimpleBake_Props.saveObj
        d["fbxName"] = bpy.context.scene.SimpleBake_Props.fbxName
        d["prepmesh"] = bpy.context.scene.SimpleBake_Props.prepmesh
        d["hidesourceobjects"] = bpy.context.scene.SimpleBake_Props.hidesourceobjects
        d["preserve_materials"] = bpy.context.scene.SimpleBake_Props.preserve_materials
        d["everything16bit"] = bpy.context.scene.SimpleBake_Props.everything16bit
        d["exportfileformat"] = bpy.context.scene.SimpleBake_Props.exportfileformat
        d["saveFolder"] = bpy.context.scene.SimpleBake_Props.saveFolder
        d["selected_applycolmantocol"] = bpy.context.scene.SimpleBake_Props.selected_applycolmantocol
        d["exportcyclescolspace"] = bpy.context.scene.SimpleBake_Props.exportcyclescolspace
        d["folderdatetime"] = bpy.context.scene.SimpleBake_Props.folderdatetime
        d["rundenoise"] = bpy.context.scene.SimpleBake_Props.rundenoise
        d["applymodsonmeshexport"] = bpy.context.scene.SimpleBake_Props.applymodsonmeshexport
        d["advancedobjectselection"] = bpy.context.scene.SimpleBake_Props.advancedobjectselection
        d["bakeobjs_advanced_list_index"] = bpy.context.scene.SimpleBake_Props.bakeobjs_advanced_list_index
        d["bgbake"] = bpy.context.scene.SimpleBake_Props.bgbake
        d["memLimit"] = bpy.context.scene.SimpleBake_Props.memLimit
        d["batchName"] = bpy.context.scene.SimpleBake_Props.batchName
        d["showtips"] = bpy.context.scene.SimpleBake_Props.showtips
        d["first_texture_show"] = bpy.context.scene.SimpleBake_Props.first_texture_show
        d["bgbake_name"] = bpy.context.scene.SimpleBake_Props.bgbake_name

        #Non SimpleBake settings
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

        #Show/Hide
        d["showtips"] = bpy.context.scene.SimpleBake_Props.showtips
        d["presets_show"] = bpy.context.scene.SimpleBake_Props.presets_show
        d["bake_objects_show"] = bpy.context.scene.SimpleBake_Props.bake_objects_show
        d["pbr_settings_show"] = bpy.context.scene.SimpleBake_Props.pbr_settings_show
        d["cyclesbake_settings_show"] = bpy.context.scene.SimpleBake_Props.cyclesbake_settings_show
        d["specials_show"] = bpy.context.scene.SimpleBake_Props.specials_show
        d["textures_show"] = bpy.context.scene.SimpleBake_Props.textures_show
        d["export_show"] = bpy.context.scene.SimpleBake_Props.export_show
        d["uv_show"] = bpy.context.scene.SimpleBake_Props.uv_show
        d["other_show"] = bpy.context.scene.SimpleBake_Props.other_show
        d["channelpacking_show"] = bpy.context.scene.SimpleBake_Props.channelpacking_show

        #Grab the objects in the advanced list (if any)
        d["object_list"] = [o.name for o in bpy.context.scene.SimpleBake_Props.bakeobjs_advanced_list]
        #Grab the target objects if there is one
        if bpy.context.scene.SimpleBake_Props.targetobj != None:
            d["pbr_target_obj"] =  bpy.context.scene.SimpleBake_Props.targetobj.name
        else:
            d["pbr_target_obj"] = None
        if bpy.context.scene.SimpleBake_Props.targetobj_cycles != None:
            d["cycles_target_obj"] = bpy.context.scene.SimpleBake_Props.targetobj_cycles.name
        else:
            d["cycles_target_obj"] = None
        #Cage object if there is one
        if bpy.context.scene.render.bake.cage_object != None:
            d["cage_object"] = bpy.context.scene.render.bake.cage_object.name
        else:
            d["cage_object"] = None

        #Channel packed images
        cp_images_dict = {}
        for cpi in bpy.context.scene.SimpleBake_Props.cp_list:
            thiscpi_dict = {}
            thiscpi_dict["R"] = cpi.R
            thiscpi_dict["G"] = cpi.G
            thiscpi_dict["B"] = cpi.B
            thiscpi_dict["A"] = cpi.A

            thiscpi_dict["file_format"] = cpi.file_format

            cp_images_dict[cpi.name] = thiscpi_dict
        if len(cp_images_dict)>0:
            d["channel_packed_images"] = cp_images_dict

        #Find where we want to save
        p = Path(bpy.utils.script_path_user())
        p = p.parents[1]
        savename = functions.cleanFileName(bpy.context.scene.SimpleBake_Props.preset_name)

        #Check for data directory
        if not os.path.isdir(str(p / "data")):
            #Create it
            os.mkdir(str(p / "data"))

        p = p / "data"

        #Check for SimpleBake directory
        if not os.path.isdir(str(p / "SimpleBake")):
            #Create it
            os.mkdir(str(p / "SimpleBake"))

        p = p / "SimpleBake"

        functions.printmsg(f"Saving preset to {str(p)}")

        jsonString = json.dumps(d)
        jsonFile = open(str(p / savename), "w")
        jsonFile.write(jsonString)
        jsonFile.close()

        #Refreh the list
        bpy.ops.object.simple_bake_preset_refresh()


        self.report({"INFO"}, "Preset saved")
        return {'FINISHED'}

class OBJECT_OT_simple_bake_preset_load(bpy.types.Operator):
    """Load selected SimpleBake preset"""
    bl_idname = "object.simple_bake_preset_load"
    bl_label = "Load"

    @classmethod
    def poll(cls,context):
        try:
            bpy.context.scene.SimpleBake_Props.presets_list[bpy.context.scene.SimpleBake_Props.presets_list_index].name
            return True
        except:
            return False

    def execute(self, context):

        #Load it
        loadname = functions.cleanFileName(\
            bpy.context.scene.SimpleBake_Props.presets_list[\
            bpy.context.scene.SimpleBake_Props.presets_list_index].name)

        p = Path(bpy.utils.script_path_user())
        p = p.parents[1]
        p = p /  "data" / "SimpleBake" / loadname

        functions.printmsg(f"Loading preset from {str(p)}")

        try:
            fileObject = open(str(p), "r")
        except:
            bpy.ops.object.simple_bake_preset_refresh()
            self.report({"ERROR"}, f"Preset {loadname} no longer exists")
            return {'CANCELLED'}



        jsonContent = fileObject.read()
        d = json.loads(jsonContent)

        #SimpleBake internal
        bpy.context.scene.SimpleBake_Props.global_mode = d["global_mode"]
        bpy.context.scene.SimpleBake_Props.ray_distance = d["ray_distance"]
        bpy.context.scene.SimpleBake_Props.cage_extrusion = d["cage_extrusion"]
        bpy.context.scene.SimpleBake_Props.selected_s2a = d["selected_s2a"]
        bpy.context.scene.SimpleBake_Props.mergedBake = d["mergedBake"]
        bpy.context.scene.SimpleBake_Props.mergedBakeName = d["mergedBakeName"]
        bpy.context.scene.SimpleBake_Props.cycles_s2a = d["cycles_s2a"]
        bpy.context.scene.SimpleBake_Props.imgheight = d["imgheight"]
        bpy.context.scene.SimpleBake_Props.imgwidth = d["imgwidth"]
        bpy.context.scene.SimpleBake_Props.outputheight = d["outputheight"]
        bpy.context.scene.SimpleBake_Props.outputwidth = d["outputwidth"]
        bpy.context.scene.SimpleBake_Props.everything32bitfloat = d["everything32bitfloat"]
        bpy.context.scene.SimpleBake_Props.useAlpha = d["useAlpha"]
        bpy.context.scene.SimpleBake_Props.rough_glossy_switch = d["rough_glossy_switch"]
        bpy.context.scene.SimpleBake_Props.normal_format_switch = d["normal_format_switch"]
        bpy.context.scene.SimpleBake_Props.tex_per_mat = d["tex_per_mat"]
        bpy.context.scene.SimpleBake_Props.selected_col = d["selected_col"]
        bpy.context.scene.SimpleBake_Props.selected_metal = d["selected_metal"]
        bpy.context.scene.SimpleBake_Props.selected_rough = d["selected_rough"]
        bpy.context.scene.SimpleBake_Props.selected_normal = d["selected_normal"]
        bpy.context.scene.SimpleBake_Props.selected_trans = d["selected_trans"]
        bpy.context.scene.SimpleBake_Props.selected_transrough = d["selected_transrough"]
        bpy.context.scene.SimpleBake_Props.selected_emission = d["selected_emission"]
        bpy.context.scene.SimpleBake_Props.selected_sss = d["selected_sss"]
        bpy.context.scene.SimpleBake_Props.selected_ssscol = d["selected_ssscol"]
        bpy.context.scene.SimpleBake_Props.selected_clearcoat = d["selected_clearcoat"]
        bpy.context.scene.SimpleBake_Props.selected_clearcoat_rough = d["selected_clearcoat_rough"]
        bpy.context.scene.SimpleBake_Props.selected_specular = d["selected_specular"]
        bpy.context.scene.SimpleBake_Props.selected_alpha = d["selected_alpha"]
        bpy.context.scene.SimpleBake_Props.selected_col_mats = d["selected_col_mats"]
        bpy.context.scene.SimpleBake_Props.selected_col_vertex = d["selected_col_vertex"]
        bpy.context.scene.SimpleBake_Props.selected_ao = d["selected_ao"]
        bpy.context.scene.SimpleBake_Props.selected_thickness = d["selected_thickness"]
        bpy.context.scene.SimpleBake_Props.selected_curvature = d["selected_curvature"]
        bpy.context.scene.SimpleBake_Props.selected_lightmap = d["selected_lightmap"]
        bpy.context.scene.SimpleBake_Props.lightmap_apply_colman = d["lightmap_apply_colman"]
        bpy.context.scene.SimpleBake_Props.selected_lightmap_denoise = d["selected_lightmap_denoise"]
        bpy.context.scene.SimpleBake_Props.newUVoption = d["newUVoption"]
        bpy.context.scene.SimpleBake_Props.newUVmethod = d["newUVmethod"]
        bpy.context.scene.SimpleBake_Props.restoreOrigUVmap = d["restoreOrigUVmap"]
        bpy.context.scene.SimpleBake_Props.uvpackmargin = d["uvpackmargin"]
        bpy.context.scene.SimpleBake_Props.averageUVsize = d["averageUVsize"]
        bpy.context.scene.SimpleBake_Props.expand_mat_uvs = d["expand_mat_uvs"]
        bpy.context.scene.SimpleBake_Props.uv_mode = d["uv_mode"]
        bpy.context.scene.SimpleBake_Props.udim_tiles = d["udim_tiles"]
        bpy.context.scene.SimpleBake_Props.unwrapmargin = d["unwrapmargin"]
        bpy.context.scene.SimpleBake_Props.channelpackfileformat = d["channelpackfileformat"]
        bpy.context.scene.SimpleBake_Props.saveExternal = d["saveExternal"]
        bpy.context.scene.SimpleBake_Props.exportFolderPerObject = d["exportFolderPerObject"]
        bpy.context.scene.SimpleBake_Props.saveObj = d["saveObj"]
        bpy.context.scene.SimpleBake_Props.fbxName = d["fbxName"]
        bpy.context.scene.SimpleBake_Props.prepmesh = d["prepmesh"]
        bpy.context.scene.SimpleBake_Props.hidesourceobjects = d["hidesourceobjects"]
        bpy.context.scene.SimpleBake_Props.preserve_materials = d["preserve_materials"]
        bpy.context.scene.SimpleBake_Props.everything16bit = d["everything16bit"]
        bpy.context.scene.SimpleBake_Props.exportfileformat = d["exportfileformat"]
        bpy.context.scene.SimpleBake_Props.saveFolder = d["saveFolder"]
        bpy.context.scene.SimpleBake_Props.selected_applycolmantocol = d["selected_applycolmantocol"]
        bpy.context.scene.SimpleBake_Props.exportcyclescolspace = d["exportcyclescolspace"]
        bpy.context.scene.SimpleBake_Props.folderdatetime = d["folderdatetime"]
        bpy.context.scene.SimpleBake_Props.rundenoise = d["rundenoise"]
        bpy.context.scene.SimpleBake_Props.applymodsonmeshexport = d["applymodsonmeshexport"]
        bpy.context.scene.SimpleBake_Props.advancedobjectselection = d["advancedobjectselection"]
        bpy.context.scene.SimpleBake_Props.bakeobjs_advanced_list_index = d["bakeobjs_advanced_list_index"]
        bpy.context.scene.SimpleBake_Props.bgbake = d["bgbake"]
        bpy.context.scene.SimpleBake_Props.memLimit = d["memLimit"]
        bpy.context.scene.SimpleBake_Props.batchName = d["batchName"]
        bpy.context.scene.SimpleBake_Props.first_texture_show = d["first_texture_show"]
        bpy.context.scene.SimpleBake_Props.bgbake_name = d["bgbake_name"]
        bpy.context.scene.SimpleBake_Props.prefer_existing_sbmap = d["prefer_existing_sbmap"]

        #Non-SimpleBake Settings
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

        #Show/Hide
        bpy.context.scene.SimpleBake_Props.showtips = d["showtips"]
        bpy.context.scene.SimpleBake_Props.presets_show = d["presets_show"]
        bpy.context.scene.SimpleBake_Props.bake_objects_show = d["bake_objects_show"]
        bpy.context.scene.SimpleBake_Props.pbr_settings_show = d["pbr_settings_show"]
        bpy.context.scene.SimpleBake_Props.cyclesbake_settings_show = d["cyclesbake_settings_show"]
        bpy.context.scene.SimpleBake_Props.specials_show = d["specials_show"]
        bpy.context.scene.SimpleBake_Props.textures_show = d["textures_show"]
        bpy.context.scene.SimpleBake_Props.export_show = d["export_show"]
        bpy.context.scene.SimpleBake_Props.uv_show = d["uv_show"]
        bpy.context.scene.SimpleBake_Props.other_show = d["other_show"]
        bpy.context.scene.SimpleBake_Props.channelpacking_show = d["channelpacking_show"]

        #Channel packing images
        if "channel_packed_images" in d:
            channel_packed_images = d["channel_packed_images"]

            if len(channel_packed_images) > 0:
                bpy.context.scene.SimpleBake_Props.cp_list.clear()

            for imgname in channel_packed_images:

                thiscpi_dict = channel_packed_images[imgname]

                #Create the list item
                li = bpy.context.scene.SimpleBake_Props.cp_list.add()
                li.name = imgname

                #Set the list item properies
                li.R = thiscpi_dict["R"]
                li.G = thiscpi_dict["G"]
                li.B = thiscpi_dict["B"]
                li.A = thiscpi_dict["A"]

                li.file_format = thiscpi_dict["file_format"]

        #And now the objects, if they are here
        for obj_name in d["object_list"]:
            if obj_name in bpy.data.objects:
                #Find where name attribute of each object in the advanced selection list matches the name
                l = [o.name for o in bpy.context.scene.SimpleBake_Props.bakeobjs_advanced_list if o.name == obj_name]
                if len(l) == 0:
                    #Not already in the list
                    i = bpy.context.scene.SimpleBake_Props.bakeobjs_advanced_list.add()
                    i.name = obj_name #Advanced object list has a name and pointers arritbute
                    i.obj_point = bpy.data.objects[obj_name]

        if d["pbr_target_obj"] != None and d["pbr_target_obj"] in bpy.data.objects:
            bpy.context.scene.SimpleBake_Props.targetobj = bpy.data.objects[d["pbr_target_obj"]]
        if d["cycles_target_obj"] != None and d["cycles_target_obj"] in bpy.data.objects:
            bpy.context.scene.SimpleBake_Props.targetobj_cycles = bpy.data.objects[d["cycles_target_obj"]]
        #Cage object
        if d["cage_object"] != None and d["cage_object"] in bpy.data.objects:
            bpy.context.scene.render.bake.cage_object = bpy.data.objects[d["cage_object"]]

        self.report({"INFO"}, f"Preset {loadname} loaded")

        return {'FINISHED'}

class OBJECT_OT_simple_bake_preset_refresh(bpy.types.Operator):
    """Refresh list of SimpleBake presets"""
    bl_idname = "object.simple_bake_preset_refresh"
    bl_label = "Refresh"

    def execute(self, context):

        bpy.context.scene.SimpleBake_Props.presets_list.clear()

        p = Path(bpy.utils.script_path_user())
        p = p.parents[1]
        p = p /  "data" / "SimpleBake"

        try:
            presets = os.listdir(str(p))
        except:
            self.report({"INFO"}, "No presets found")
            return {'CANCELLED'}

        if len(presets) == 0:
            self.report({"INFO"}, "No presets found")
            return {'CANCELLED'}




        for preset in presets:
            #List should be clear
            i = bpy.context.scene.SimpleBake_Props.presets_list.add()
            i.name = preset



        return {'FINISHED'}

class OBJECT_OT_simple_bake_preset_delete(bpy.types.Operator):
    """Delete selected SimpleBake preset"""
    bl_idname = "object.simple_bake_preset_delete"
    bl_label = "Delete"

    @classmethod
    def poll(cls,context):
        try:
            bpy.context.scene.SimpleBake_Props.presets_list[bpy.context.scene.SimpleBake_Props.presets_list_index].name
            return True
        except:
            return False


    def execute(self, context):

        p = Path(bpy.utils.script_path_user())
        p = p.parents[1]
        p = p /  "data" / "SimpleBake"

        index = context.scene.SimpleBake_Props.presets_list_index
        item = context.scene.SimpleBake_Props.presets_list[index]
        p = p / item.name

        os.remove(str(p))

        #Refreh the list

        bpy.ops.object.simple_bake_preset_refresh()


        return {'FINISHED'}


#---------Show hide------------------------------------------

class OBJECT_OT_simple_bake_show_all(bpy.types.Operator):
    """Show all SimpleBake panel items"""
    bl_idname = "object.simple_bake_show_all"
    bl_label = "Show all"


    def execute(self, context):

        bpy.context.scene.SimpleBake_Props.showtips = True
        bpy.context.scene.SimpleBake_Props.presets_show = True
        bpy.context.scene.SimpleBake_Props.bake_objects_show = True
        bpy.context.scene.SimpleBake_Props.pbr_settings_show = True
        bpy.context.scene.SimpleBake_Props.cyclesbake_settings_show = True
        bpy.context.scene.SimpleBake_Props.specials_show = True
        bpy.context.scene.SimpleBake_Props.textures_show = True
        bpy.context.scene.SimpleBake_Props.export_show = True
        bpy.context.scene.SimpleBake_Props.uv_show = True
        bpy.context.scene.SimpleBake_Props.other_show = True
        bpy.context.scene.SimpleBake_Props.channelpacking_show = True

        return {'FINISHED'}

class OBJECT_OT_simple_bake_hide_all(bpy.types.Operator):
    """Hide all SimpleBake panel items"""
    bl_idname = "object.simple_bake_hide_all"
    bl_label = "Hide all"


    def execute(self, context):

        bpy.context.scene.SimpleBake_Props.showtips = False
        bpy.context.scene.SimpleBake_Props.presets_show = False
        bpy.context.scene.SimpleBake_Props.bake_objects_show = False
        bpy.context.scene.SimpleBake_Props.pbr_settings_show = False
        bpy.context.scene.SimpleBake_Props.cyclesbake_settings_show = False
        bpy.context.scene.SimpleBake_Props.specials_show = False
        bpy.context.scene.SimpleBake_Props.textures_show = False
        bpy.context.scene.SimpleBake_Props.export_show = False
        bpy.context.scene.SimpleBake_Props.uv_show = False
        bpy.context.scene.SimpleBake_Props.other_show = False
        bpy.context.scene.SimpleBake_Props.channelpacking_show = False

        functions.auto_set_bake_margin()

        return {'FINISHED'}


class OBJECT_OT_simple_bake_increase_texture_res(bpy.types.Operator):
    """Increase texture resolution by 1k"""
    bl_idname = "object.simple_bake_increase_texture_res"
    bl_label = "+1k"


    def execute(self, context):

        x = bpy.context.scene.SimpleBake_Props.imgwidth
        bpy.context.scene.SimpleBake_Props.imgwidth = x + 1024
        y = bpy.context.scene.SimpleBake_Props.imgheight
        bpy.context.scene.SimpleBake_Props.imgheight = y + 1024

        while bpy.context.scene.SimpleBake_Props.imgheight % 1024 != 0:
            bpy.context.scene.SimpleBake_Props.imgheight -= 1

        while bpy.context.scene.SimpleBake_Props.imgwidth % 1024 != 0:
            bpy.context.scene.SimpleBake_Props.imgwidth -= 1

        result = min(bpy.context.scene.SimpleBake_Props.imgwidth, bpy.context.scene.SimpleBake_Props.imgheight)
        bpy.context.scene.SimpleBake_Props.imgwidth = result
        bpy.context.scene.SimpleBake_Props.imgheight = result

        functions.auto_set_bake_margin()

        return {'FINISHED'}

class OBJECT_OT_simple_bake_decrease_texture_res(bpy.types.Operator):
    """Decrease texture resolution by 1k"""
    bl_idname = "object.simple_bake_decrease_texture_res"
    bl_label = "-1k"


    def execute(self, context):

        x = bpy.context.scene.SimpleBake_Props.imgwidth
        bpy.context.scene.SimpleBake_Props.imgwidth = x - 1024
        y = bpy.context.scene.SimpleBake_Props.imgheight
        bpy.context.scene.SimpleBake_Props.imgheight = y - 1024

        if bpy.context.scene.SimpleBake_Props.imgheight < 1:
            bpy.context.scene.SimpleBake_Props.imgheight = 1024

        if bpy.context.scene.SimpleBake_Props.imgwidth < 1:
            bpy.context.scene.SimpleBake_Props.imgwidth = 1024

        while bpy.context.scene.SimpleBake_Props.imgheight % 1024 != 0:
            bpy.context.scene.SimpleBake_Props.imgheight += 1

        while bpy.context.scene.SimpleBake_Props.imgwidth % 1024 != 0:
            bpy.context.scene.SimpleBake_Props.imgwidth += 1

        result = max(bpy.context.scene.SimpleBake_Props.imgwidth, bpy.context.scene.SimpleBake_Props.imgheight)
        bpy.context.scene.SimpleBake_Props.imgwidth = result
        bpy.context.scene.SimpleBake_Props.imgheight = result


        functions.auto_set_bake_margin()

        return {'FINISHED'}

class OBJECT_OT_simple_bake_increase_output_res(bpy.types.Operator):
    """Increase output resolution by 1k"""
    bl_idname = "object.simple_bake_increase_output_res"
    bl_label = "+1k"


    def execute(self, context):

        x = bpy.context.scene.SimpleBake_Props.outputwidth
        bpy.context.scene.SimpleBake_Props.outputwidth = x + 1024
        y = bpy.context.scene.SimpleBake_Props.outputheight
        bpy.context.scene.SimpleBake_Props.outputheight = y + 1024

        while bpy.context.scene.SimpleBake_Props.outputheight % 1024 != 0:
            bpy.context.scene.SimpleBake_Props.outputheight -= 1

        while bpy.context.scene.SimpleBake_Props.outputwidth % 1024 != 0:
            bpy.context.scene.SimpleBake_Props.outputwidth -= 1

        result = min(bpy.context.scene.SimpleBake_Props.outputwidth, bpy.context.scene.SimpleBake_Props.outputheight)
        bpy.context.scene.SimpleBake_Props.outputwidth = result
        bpy.context.scene.SimpleBake_Props.outputheight = result

        functions.auto_set_bake_margin()

        return {'FINISHED'}

class OBJECT_OT_simple_bake_decrease_output_res(bpy.types.Operator):
    """Decrease output resolution by 1k"""
    bl_idname = "object.simple_bake_decrease_output_res"
    bl_label = "-1k"


    def execute(self, context):

        x = bpy.context.scene.SimpleBake_Props.outputwidth
        bpy.context.scene.SimpleBake_Props.outputwidth = x - 1024
        y = bpy.context.scene.SimpleBake_Props.outputheight
        bpy.context.scene.SimpleBake_Props.outputheight = y - 1024

        if bpy.context.scene.SimpleBake_Props.outputheight < 1:
            bpy.context.scene.SimpleBake_Props.outputheight = 1024

        if bpy.context.scene.SimpleBake_Props.outputwidth < 1:
            bpy.context.scene.SimpleBake_Props.outputwidth = 1024


        while bpy.context.scene.SimpleBake_Props.outputheight % 1024 != 0:
            bpy.context.scene.SimpleBake_Props.outputheight += 1

        while bpy.context.scene.SimpleBake_Props.outputwidth % 1024 != 0:
            bpy.context.scene.SimpleBake_Props.outputwidth += 1

        result = max(bpy.context.scene.SimpleBake_Props.outputwidth, bpy.context.scene.SimpleBake_Props.outputheight)
        bpy.context.scene.SimpleBake_Props.outputwidth = result
        bpy.context.scene.SimpleBake_Props.outputheight = result

        functions.auto_set_bake_margin()

        return {'FINISHED'}


#-------------------------------------Channel packing
class OBJECT_OT_simple_bake_cptex_add(bpy.types.Operator):
    """Add a SimpleBake CP Texture item"""
    bl_idname = "object.simple_bake_cptex_add"
    bl_label = "Add"

    @classmethod
    def poll(cls,context):
        return bpy.context.scene.SimpleBake_Props.cp_name != ""

    def execute(self, context):
        cp_list = bpy.context.scene.SimpleBake_Props.cp_list
        name = functions.cleanFileName(bpy.context.scene.SimpleBake_Props.cp_name)

        if name in cp_list:
            #Delete it
            index = bpy.context.scene.SimpleBake_Props.cp_list.find(name)
            bpy.context.scene.SimpleBake_Props.cp_list.remove(index)

        li = cp_list.add()
        li.name = name

        li.R = bpy.context.scene.SimpleBake_Props.cptex_R
        li.G = bpy.context.scene.SimpleBake_Props.cptex_G
        li.B = bpy.context.scene.SimpleBake_Props.cptex_B
        li.A = bpy.context.scene.SimpleBake_Props.cptex_A
        li.file_format = bpy.context.scene.SimpleBake_Props.channelpackfileformat

        bpy.context.scene.SimpleBake_Props.cp_list_index = bpy.context.scene.SimpleBake_Props.cp_list.find(name)

        self.report({"INFO"}, "CP texture saved")
        return {'FINISHED'}

class OBJECT_OT_simple_bake_cptex_delete(bpy.types.Operator):
    """Delete the selected channel pack texture"""
    bl_idname = "object.simple_bake_cptex_delete"
    bl_label = "Delete"

    @classmethod
    def poll(cls,context):
        try:
            bpy.context.scene.SimpleBake_Props.cp_list[bpy.context.scene.SimpleBake_Props.cp_list_index].name
            return True
        except:
            return False

    def execute(self, context):
        bpy.context.scene.SimpleBake_Props.cp_list.remove(bpy.context.scene.SimpleBake_Props.cp_list_index)

        self.report({"INFO"}, "CP texture deleted")
        return {'FINISHED'}

class OBJECT_OT_simple_bake_cptex_setdefaults(bpy.types.Operator):
    """Add some example channel pack textures"""
    bl_idname = "object.simple_bake_cptex_setdefaults"
    bl_label = "Add examples"

    @classmethod
    def poll(cls,context):
        return True

    def execute(self, context):

        cp_list = bpy.context.scene.SimpleBake_Props.cp_list

        # bpy.context.scene.SimpleBake_Props.selected_col = True
        # bpy.context.scene.SimpleBake_Props.selected_metal = True
        # bpy.context.scene.SimpleBake_Props.selected_rough = True
        # bpy.context.scene.SimpleBake_Props.selected_ao = True
        # bpy.context.scene.SimpleBake_Props.selected_alpha = True
        # bpy.context.scene.SimpleBake_Props.selected_specular = True

        #Unity Lit shader. R=metalness, G=AO, B=N/A, A=Glossy.
        li = cp_list.add()
        li.name = "Unity Lit Shader"
        li.file_format = "OPEN_EXR"
        li.R = "metalness"
        li.G = SimpleBakeConstants.AO
        li.B = "none"
        li.A = "glossy"

        #Unity Legacy Standard Diffuse. RGB=diffuse, A=alpha.
        li = cp_list.add()
        li.name = "Unity Legacy Shader"
        li.file_format = "OPEN_EXR"
        li.R = "diffuse"
        li.G = "diffuse"
        li.B = "diffuse"
        li.A = "alpha"

        #ORM format. R=AO, G=Roughness, B=Metalness, A=N/A.
        li = cp_list.add()
        li.name = "ORM"
        li.file_format = "OPEN_EXR"
        li.R = SimpleBakeConstants.AO
        li.G = "roughness"
        li.B = "metalness"
        li.A = "none"

        #diffuse plus specular in the alpha channel.
        li = cp_list.add()
        li.name = "Diffuse and Spec in alpha"
        li.file_format = "OPEN_EXR"
        li.R = "diffuse"
        li.G = "diffuse"
        li.B = "diffuse"
        li.A = "specular"


        self.report({"INFO"}, "Default textures added")
        return {'FINISHED'}

class OBJECT_OT_simple_bake_popnodegroups(bpy.types.Operator):
    """Move an object with the mouse, example"""
    bl_idname = "object.simple_bake_popnodegroups"
    bl_label = "Pop all node groups"

    index = 0
    _timer = None
    original_uitype = None


    def modal(self, context, event):

        if event.type == 'TIMER': #Only respond to timer events

            obj = bpy.data.objects["Cube"]#Need to figure out how we will get this in here

            l = len(obj.material_slots)

            if OBJECT_OT_simple_bake_popnodegroups.index == l:
                #We are done
                wm = context.window_manager
                wm.event_timer_remove(self._timer)
                OBJECT_OT_simple_bake_popnodegroups.index = 0

                bpy.context.area.ui_type = OBJECT_OT_simple_bake_popnodegroups.original_uitype

                return {'FINISHED'}

            elif obj.active_material_index == OBJECT_OT_simple_bake_popnodegroups.index:
                #Do it

                mat = obj.material_slots[OBJECT_OT_simple_bake_popnodegroups.index].material
                nodes = mat.node_tree.nodes

                for node in nodes:
                    if node.bl_idname == "ShaderNodeGroup":
                        #Here's one
                        node.select = True
                        nodes.active = node
                        bpy.ops.node.group_ungroup('INVOKE_DEFAULT')

                OBJECT_OT_simple_bake_popnodegroups.index += 1

            else:
                #Change active slot and do it next time
                obj.active_material_index = OBJECT_OT_simple_bake_popnodegroups.index

        return {'PASS_THROUGH'}

    def execute(self, context  ):
        OBJECT_OT_simple_bake_popnodegroups.original_uitype = bpy.context.area.ui_type
        bpy.context.area.ui_type = "ShaderNodeTree"

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)

        return {'RUNNING_MODAL'}

