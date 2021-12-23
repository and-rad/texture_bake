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
from . import functions
import os
import shutil
import sys
from. import post_processing
from pathlib import Path
from .bake_operation import BakeOperation, MasterOperation, BakeStatus, TextureBakeConstants


def optimize():

    current_bake_op = MasterOperation.current_bake_operation

    imgwidth = bpy.context.scene.TextureBake_Props.imgwidth
    imgheight = bpy.context.scene.TextureBake_Props.imgheight

    #Store the current tile sizes and sample count
    MasterOperation.orig_tile_size = bpy.context.scene.cycles.tile_size
    MasterOperation.orig_sample_count = bpy.context.scene.cycles.samples


    #Apparently small tile sizes are now always better for baking on CPU
    if bpy.context.scene.cycles.device == "CPU":
        bpy.context.scene.cycles.use_auto_tile = True
        bpy.context.scene.cycles.tile_size = 64
        functions.printmsg("Setting tile size to 64 for baking on CPU")

    #Otherwise, let's do what we've always done and optimise for GPU
    else:

        #Get the max tile size we are working with
        if(bpy.context.scene.TextureBake_Props.memLimit == "Off"):
            bpy.context.scene.cycles.use_auto_tile = False
        else:
            bpy.context.scene.cycles.use_auto_tile = True
            maxtile = int(bpy.context.scene.TextureBake_Props.memLimit)

            #Set x tile size to greater of imgwidth and maxtile
            if(imgwidth <= maxtile):
                bpy.context.scene.cycles.tile_size = imgwidth
            else:
                bpy.context.scene.cycles.tile_size = maxtile


        functions.printmsg(f"Setting tile size to {bpy.context.scene.cycles.tile_size} for baking on GPU")

    if(current_bake_op.bake_mode == TextureBakeConstants.CYCLESBAKE):
        functions.printmsg(f"Honouring user set sample count of {bpy.context.scene.cycles.samples} for Cycles bake")
    else:
        functions.printmsg("Reducing sample count to 16 for more efficient baking")
        bpy.context.scene.cycles.samples = 16

    return True

def undo_optimize():
    #Restore sample count
    bpy.context.scene.cycles.samples = MasterOperation.orig_sample_count

    #Restore tile sizes
    bpy.context.scene.cycles.tile_size = MasterOperation.orig_tile_size


def common_bake_prep():

    #--------------Set Bake Operation Variables----------------------------

    current_bake_op = MasterOperation.current_bake_operation

    functions.printmsg("================================")
    functions.printmsg("--------SIMPLEBAKE Start--------")
    functions.printmsg(f"{current_bake_op.bake_mode}")
    functions.printmsg("================================")

    #Record if a textures folder existed at start of the bake
    fullpath = bpy.data.filepath
    pathelements = os.path.split(fullpath)
    workingdir = Path(pathelements[0])
    if os.path.isdir(str(workingdir / "textures")):
        MasterOperation.orig_textures_folder = True

    #Run information
    op_num = MasterOperation.this_bake_operation_num
    firstop = False
    lastop = False
    if op_num == 1: firstop = True
    if op_num == MasterOperation.total_bake_operations: lastop = True


    #If this is a pbr bake, gather the selected maps
    if current_bake_op.bake_mode in {TextureBakeConstants.PBR, TextureBakeConstants.PBRS2A}:
        current_bake_op.assemble_pbr_bake_list()

    #Record batch name
    MasterOperation.batch_name = bpy.context.scene.TextureBake_Props.batchName

    #Set values based on viewport selection
    current_bake_op.orig_objects = bpy.context.selected_objects.copy()
    current_bake_op.orig_active_object = bpy.context.active_object
    current_bake_op.bake_objects = bpy.context.selected_objects.copy()
    current_bake_op.active_object = bpy.context.active_object


    #If using advanced selection mode, override the viewport selection
    if bpy.context.scene.TextureBake_Props.advancedobjectselection:

        functions.printmsg("We are using advanced object selection")
        current_bake_op.bake_objects = functions.advanced_object_selection_to_list()

    #Record the target objects if relevant
    if bpy.context.scene.TextureBake_Props.targetobj != None:
        current_bake_op.sb_target_object = bpy.context.scene.TextureBake_Props.targetobj
    if bpy.context.scene.TextureBake_Props.targetobj_cycles != None:
        current_bake_op.sb_target_object_cycles = bpy.context.scene.TextureBake_Props.targetobj_cycles

    current_bake_op.orig_s2A = bpy.context.scene.render.bake.use_selected_to_active
    current_bake_op.orig_engine = bpy.context.scene.render.engine

    #Create a new collection, and add selected objects and target objects to it
    #Just in case of a previous crash
    for c in bpy.data.collections:
        if "TextureBake_Working" in c.name:
            bpy.data.collections.remove(c)

    c = bpy.data.collections.new("TextureBake_Working")
    bpy.context.scene.collection.children.link(c)
    for obj in current_bake_op.bake_objects:
        if obj.name not in c:
            c.objects.link(obj)
    if bpy.context.scene.TextureBake_Props.targetobj != None and bpy.context.scene.TextureBake_Props.targetobj.name not in c.objects:
        c.objects.link(bpy.context.scene.TextureBake_Props.targetobj)
    if bpy.context.scene.TextureBake_Props.targetobj_cycles != None and bpy.context.scene.TextureBake_Props.targetobj_cycles.name not in c.objects:
        c.objects.link(bpy.context.scene.TextureBake_Props.targetobj_cycles)

    #Every object must have at least camera ray visibility
    for obj in current_bake_op.bake_objects:
        obj.visible_camera = True
    if bpy.context.scene.TextureBake_Props.targetobj != None:
        bpy.context.scene.TextureBake_Props.targetobj.visible_camera = True
    if bpy.context.scene.TextureBake_Props.targetobj_cycles != None:
        bpy.context.scene.TextureBake_Props.targetobj_cycles.visible_camera = True



    #Record original UVs for everyone
    if firstop:

        for obj in current_bake_op.bake_objects:
            try:
                MasterOperation.orig_UVs_dict[obj.name] = obj.data.uv_layers.active.name
            except AttributeError:
                MasterOperation.orig_UVs_dict[obj.name] = False

        #Although starting checks will stop if no UVs, New UVs gets a pass so we need to be careful here
        if current_bake_op.sb_target_object != None:
            obj = current_bake_op.sb_target_object
            if obj.data.uv_layers.active != None:
                MasterOperation.orig_UVs_dict[obj.name] = obj.data.uv_layers.active.name
        if current_bake_op.sb_target_object_cycles != None:
            obj = current_bake_op.sb_target_object_cycles
            if obj.data.uv_layers.active != None:
                MasterOperation.orig_UVs_dict[obj.name] = obj.data.uv_layers.active.name


    #Record the rendering engine
    if firstop:
        MasterOperation.orig_engine = bpy.context.scene.render.engine


    if bpy.context.scene.TextureBake_Props.uv_mode == "udims": current_bake_op.uv_mode = "udims"
    else: current_bake_op.uv_mode = "normal"

    #Record the Cycles bake mode (actually redundant as this is the default anyway)
    current_bake_op.cycles_bake_type = bpy.context.scene.cycles.bake_type

    #----------------------------------------------------------------------

    #Force it to cycles
    bpy.context.scene.render.engine = "CYCLES"

    #If this is a selected to active bake (PBR or cycles), turn it on
    if current_bake_op.bake_mode==TextureBakeConstants.PBRS2A and bpy.context.scene.TextureBake_Props.selected_s2a:
        bpy.context.scene.render.bake.use_selected_to_active = True
        functions.printmsg(f"Setting ray distance to {round(bpy.context.scene.TextureBake_Props.ray_distance, 2)}")
        bpy.context.scene.render.bake.max_ray_distance = bpy.context.scene.TextureBake_Props.ray_distance
        functions.printmsg(f"Setting cage extrusion to {round(bpy.context.scene.TextureBake_Props.cage_extrusion, 2)}")
        bpy.context.scene.render.bake.cage_extrusion = bpy.context.scene.TextureBake_Props.cage_extrusion

    elif current_bake_op.bake_mode==TextureBakeConstants.CYCLESBAKE and bpy.context.scene.TextureBake_Props.cycles_s2a:
        bpy.context.scene.render.bake.use_selected_to_active = True
        functions.printmsg(f"Setting ray distance to {round(bpy.context.scene.TextureBake_Props.ray_distance, 2)}")
        bpy.context.scene.render.bake.max_ray_distance = bpy.context.scene.TextureBake_Props.ray_distance
        functions.printmsg(f"Setting cage extrusion to {round(bpy.context.scene.TextureBake_Props.cage_extrusion, 2)}")
        bpy.context.scene.render.bake.cage_extrusion = bpy.context.scene.TextureBake_Props.cage_extrusion

    elif current_bake_op.bake_mode in [TextureBakeConstants.SPECIALS, TextureBakeConstants.SPECIALS_CYCLES_TARGET_ONLY, TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY]:
        bpy.context.scene.render.bake.use_selected_to_active = False
    else:
        bpy.context.scene.render.bake.use_selected_to_active = False

    functions.printmsg(f"Selected to active is now {bpy.context.scene.render.bake.use_selected_to_active}")

    #If the user doesn't have a GPU, but has still set the render device to GPU, set it to CPU
    if not bpy.context.preferences.addons["cycles"].preferences.has_active_device():
        bpy.context.scene.cycles.device = "CPU"

    #Reset the UDIM counters to 0
    current_bake_op.udim_counter = 1001
    functions.currentUDIMtile = {}

    #If baking S2A, and the user has selected a cage object, there are extra steps to turn it on
    if bpy.context.scene.TextureBake_Props.selected_s2a or bpy.context.scene.TextureBake_Props.cycles_s2a:
        if bpy.context.scene.render.bake.cage_object == None:
            bpy.context.scene.render.bake.use_cage = False
        else:
            bpy.context.scene.render.bake.use_cage = True

    #Initialise the save folder in case we need it
    functions.getSaveFolder(initialise = True)

    #Clear the trunc num for this session
    functions.trunc_num = 0
    functions.trunc_dict = {}

    #Turn off that dam use clear.
    bpy.context.scene.render.bake.use_clear = False

    #Do what we are doing with UVs (only if we are the primary op)
    if firstop:
        functions.processUVS()

    #Optimize
    optimize()

    #Make sure the normal y setting is at default
    bpy.context.scene.render.bake.normal_g = "POS_Y"

    return True


def do_post_processing(thisbake, IMGNAME):

    functions.printmsg("Doing post processing")

    #DirectX vs OpenGL normal map format

    if thisbake == "normal" and bpy.context.scene.TextureBake_Props.normal_format_switch == "directx":
        post_processing.post_process(internal_img_name="SB_Temp_Img",\
        save=False, mode="1to1",\
            input_img=bpy.data.images[IMGNAME],\
            invert_g_input=True\
            )

        #Replace our existing image with the processed one
        old = bpy.data.images[IMGNAME]
        name = old.name
        new = bpy.data.images["SB_Temp_Img"]
        #Transfer tags
        new["SB_objname"] = old["SB_objname"]
        new["SB_batch"] = old["SB_batch"]
        new["SB_globalmode"] = old["SB_globalmode"]
        new["SB_thisbake"] = old["SB_thisbake"]
        new["SB_mergedbakename"] = old["SB_mergedbakename"]
        new["SB_udims"] = old["SB_udims"]

        #Remove from the MasterOp baked list
        MasterOperation.baked_textures.remove(old)
        bpy.data.images.remove(old)
        new.name = name

        #Add to master list
        MasterOperation.baked_textures.append(new)


    #Roughness vs Glossy

    if thisbake == "roughness" and bpy.context.scene.TextureBake_Props.rough_glossy_switch == "glossy":
        post_processing.post_process(internal_img_name="SB_Temp_Img",\
        save=False, mode="1to1",\
            input_img=bpy.data.images[IMGNAME],\
            invert_combined=True\
            )

        #Replace our existing image with the processed one
        old = bpy.data.images[IMGNAME]
        name = old.name
        new = bpy.data.images["SB_Temp_Img"]
        #Transfer tags
        new["SB_objname"] = old["SB_objname"]
        new["SB_batch"] = old["SB_batch"]
        new["SB_globalmode"] = old["SB_globalmode"]
        #new["SB_thisbake"] = old["SB_thisbake"]
        new["SB_mergedbakename"] = old["SB_mergedbakename"]
        new["SB_udims"] = old["SB_udims"]

        new["SB_thisbake"] = "glossy"



        #Remove from the MasterOp baked list
        MasterOperation.baked_textures.remove(old)
        bpy.data.images.remove(old)
        new.name = name

        #Change roughness alias to glossy alias
        prefs = bpy.context.preferences.addons[__package__].preferences
        proposed_name = IMGNAME.replace(prefs.roughness_alias, prefs.glossy_alias)
        if proposed_name in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[proposed_name])

        bpy.data.images[IMGNAME].name = proposed_name
        IMGNAME = proposed_name

        #Add to master list
        MasterOperation.baked_textures.append(new)


    return IMGNAME

def channel_packing(objects):

    current_bake_op = MasterOperation.current_bake_operation

    #Are we doing this at all?
    if not bpy.context.scene.TextureBake_Props.saveExternal:
        functions.printmsg("No channel packing")
        return False
    if len(bpy.context.scene.TextureBake_Props.cp_list) == 0:
        functions.printmsg("No channel packing")
        return False

    functions.printmsg("Creating channel packed images")

    #Figure out the save folder for each object
    efpo = bpy.context.scene.TextureBake_Props.exportFolderPerObject
    mb = bpy.context.scene.TextureBake_Props.mergedBake
    mbn = bpy.context.scene.TextureBake_Props.mergedBakeName

    obj_savefolders = {}

    for obj in objects:
        if efpo and mb:
            savefolder = Path(str(functions.getSaveFolder()) + "/" + mbn)
            obj_savefolders[obj.name] = savefolder #Ever object gets the same based on merged bake name
        elif efpo:
            savefolder = Path(str(functions.getSaveFolder()) + "/" + obj.name)
            obj_savefolders[obj.name] = savefolder
        else:
            savefolder = Path(str(functions.getSaveFolder()))
            obj_savefolders[obj.name] = savefolder

    #We need the find images from tag function from the material setup code
    from .material_setup import get_image_from_tag

    #Need to look at all baked textures
    baked_textures = MasterOperation.baked_textures

    #Work though each requested CP texture for each object
    cp_list = bpy.context.scene.TextureBake_Props.cp_list

    for obj in objects:

        #Hacky
        if bpy.context.scene.TextureBake_Props.mergedBake:
            objname = bpy.context.scene.TextureBake_Props.mergedBakeName
        else:
            objname = obj.name

        for cpt in cp_list:
            file_format = cpt.file_format
            cpt_name = cpt.name

            functions.printmsg(f"Creating packed texture \"{cpt_name}\" for object \"{objname}\" with format {file_format}")
            r_type = cpt.R
            g_type = cpt.G
            b_type = cpt.B
            a_type = cpt.A

            #Hacky
            #if bpy.context.scene.TextureBake_Props.rough_glossy_switch == "glossy":
                #if r_type == "roughness": r_type = "glossy"
                #if g_type == "roughness": g_type = "glossy"
                #if b_type == "roughness": b_type = "glossy"
                #if a_type == "roughness": a_type = "glossy"


            #Find the actual images that we need
            if r_type == "none": r_img = None
            else: r_img = [img for img in baked_textures if img["SB_thisbake"] == r_type and img["SB_objname"] == objname][0] #Should be a list of 1
            if g_type == "none": g_img = None
            else: g_img = [img for img in baked_textures if img["SB_thisbake"] == g_type and img["SB_objname"] == objname][0] #Should be a list of 1
            if b_type == "none": b_img = None
            else: b_img = [img for img in baked_textures if img["SB_thisbake"] == b_type and img["SB_objname"] == objname][0] #Should be a list of 1
            if a_type == "none": a_img = None
            else: a_img = [img for img in baked_textures if img["SB_thisbake"] == a_type and img["SB_objname"] == objname][0] #Should be a list of 1

            #Determine transparency mode
            if file_format == "PNG" or file_format == "TARGA":
                alpha_convert = "premul"
            else:
                alpha_convert = False

            #Create the texture
            imgname = f"{objname}_{cpt.name}_ChannelPack"

            #Isolate
            if r_type == "diffuse" and g_type == "diffuse" and b_type == "diffuse":
                isolate_input_r=True
                isolate_input_g=True
                isolate_input_b=True
            else:
                isolate_input_r=False
                isolate_input_g=False
                isolate_input_b=False


            post_processing.post_process(imgname, input_r=r_img, input_g=g_img, input_b=b_img,\
                input_a=a_img, save=True, mode="3to1", path_dir=obj_savefolders[obj.name],\
                path_filename=Path(imgname), file_format=file_format, alpha_convert=alpha_convert,\
                isolate_input_r=isolate_input_r, isolate_input_g=isolate_input_g, isolate_input_b=isolate_input_b,\
                remove_internal=True)


            #Hacky - If this is a mergedbake, break out of the loop
            if bpy.context.scene.TextureBake_Props.mergedBake:
                break


def common_bake_finishing():

    #Run information
    current_bake_op = MasterOperation.current_bake_operation
    op_num = MasterOperation.this_bake_operation_num

    firstop = False
    lastop = False
    if op_num == 1: firstop = True
    if op_num == MasterOperation.total_bake_operations: lastop = True


    #Restore the original rendering engine
    if lastop:
        bpy.context.scene.render.engine = MasterOperation.orig_engine

    #Reset the UDIM focus tile of all objects
    if current_bake_op.bake_mode in [TextureBakeConstants.PBRS2A, TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY]:
        #This was some kind of S2A bake
        functions.UDIM_focustile(current_bake_op.sb_target_object, 0)
    elif bpy.context.scene.TextureBake_Props.cycles_s2a:
        functions.UDIM_focustile(current_bake_op.sb_target_object_cycles, 0)


    else:
        for obj in current_bake_op.bake_objects:
            functions.UDIM_focustile(obj, 0)


    bpy.context.scene.render.bake.use_selected_to_active = current_bake_op.orig_s2A

    undo_optimize()

    #If prep mesh, or save object is selected, or running in the background, then do it
    #We do this on primary run only
    if firstop:
        if(bpy.context.scene.TextureBake_Props.saveObj or bpy.context.scene.TextureBake_Props.prepmesh or "--background" in sys.argv):
            if current_bake_op.bake_mode == TextureBakeConstants.PBRS2A:
                functions.prepObjects([current_bake_op.sb_target_object], current_bake_op.bake_mode)
            elif current_bake_op.bake_mode == TextureBakeConstants.CYCLESBAKE and bpy.context.scene.TextureBake_Props.cycles_s2a:
                functions.prepObjects([current_bake_op.sb_target_object_cycles], current_bake_op.bake_mode)
            else:
                functions.prepObjects(current_bake_op.bake_objects, current_bake_op.bake_mode)

    #If the user wants it, restore the original active UV map so we don't confuse anyone
    if bpy.context.scene.TextureBake_Props.restoreOrigUVmap and lastop:
        functions.restore_Original_UVs()

    #Restore the original object selection so we don't confuse anyone
    bpy.ops.object.select_all(action="DESELECT")
    for obj in current_bake_op.orig_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = current_bake_op.orig_active_object


    #Hide all the original objects
    if bpy.context.scene.TextureBake_Props.prepmesh and bpy.context.scene.TextureBake_Props.hidesourceobjects and lastop:
        for obj in current_bake_op.bake_objects:
            obj.hide_set(True)
        if bpy.context.scene.TextureBake_Props.selected_s2a:
            current_bake_op.sb_target_object.hide_set(True)
        if bpy.context.scene.TextureBake_Props.cycles_s2a:
            current_bake_op.sb_target_object_cycles.hide_set(True)


    #Delete placeholder material
    if lastop and "TextureBake_Placeholder" in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials["TextureBake_Placeholder"])


    #If we baked specials, add the specials to the materials, but we won't hook them up (except for glTF)
    if current_bake_op.bake_mode in [TextureBakeConstants.SPECIALS, TextureBakeConstants.SPECIALS_CYCLES_TARGET_ONLY, TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY]:
        #Not a merged bake
        if MasterOperation.merged_bake:
            nametag = "SB_mergedbakename"
        else:
            nametag = "SB_objname"

        mats_done = []
        for obj in MasterOperation.prepared_mesh_objects:

            positions = [(-1116.65, 339.7911), (-1116.65, 280.8774), (-1116.65, 228.8141), (-1116.65, 163.0499), (-1116.65, 396.6267), (-1116.65,  454.67)]

            if MasterOperation.merged_bake:
                name = MasterOperation.merged_bake_name
            else:
                name = obj.name.replace("_Baked", "")

            image_list = [img for img in bpy.data.images \
                if nametag in img and "SB_globalmode" in img and  \
                img[nametag] == name and \
                img["SB_globalmode"] in [TextureBakeConstants.SPECIALS, TextureBakeConstants.SPECIALS_CYCLES_TARGET_ONLY, TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY] ]

            print(image_list)

            mat = obj.material_slots[0].material
            if mat.name not in mats_done:
                mats_done.append(mat.name)
                for img in image_list:
                    nodes = obj.material_slots[0].material.node_tree.nodes
                    node = nodes.new("ShaderNodeTexImage")
                    node.hide = True
                    node.location = positions[0]
                    positions.remove(positions[0])
                    node.image = img

                    #If this is ambient occlusion, and that's our selection, also hook it up to the glTF Settings node
                    if bpy.context.scene.TextureBake_Props.createglTFnode:

                        gltf_node = [n for n in nodes if n.label=="glTF Settings"]
                        gltf_node = gltf_node[0]

                        if img["SB_thisbake"] == TextureBakeConstants.AO and bpy.context.scene.TextureBake_Props.glTFselection == TextureBakeConstants.AO:
                            mat.node_tree.links.new(node.outputs["Color"], gltf_node.inputs[0])

                        if img["SB_thisbake"] == TextureBakeConstants.LIGHTMAP and bpy.context.scene.TextureBake_Props.glTFselection == TextureBakeConstants.LIGHTMAP:
                            mat.node_tree.links.new(node.outputs["Color"], gltf_node.inputs[0])


    if "--background" in sys.argv:
        #for img in bpy.data.images:
            #if "SB_objname" in img:
                #img.pack()
        bpy.ops.wm.save_mainfile()

    #Remove the temp collection
    if "TextureBake_Working" in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections["TextureBake_Working"])

    #If we didn't have one before, and we do now, remove the confusing textures folder on last run
    if lastop:
        fullpath = bpy.data.filepath
        pathelements = os.path.split(fullpath)
        workingdir = Path(pathelements[0])
        if not MasterOperation.orig_textures_folder and os.path.isdir(str(workingdir / "textures")):
            shutil.rmtree(str(workingdir / "textures"))



def cyclesBake():

    current_bake_op = MasterOperation.current_bake_operation

    common_bake_prep()

    #If this is selected to active, make that the only object
    objects = []
    if bpy.context.scene.TextureBake_Props.cycles_s2a:
        objects = [current_bake_op.sb_target_object_cycles]
    else:
        objects = current_bake_op.bake_objects


    functions.printmsg(f"Baking from cycles settings")

    IMGNAME = ""

    def cycles_bake_actual():

        IMGS_TO_SAVE = []

        #If we are doing a merged bake, just create one image here
        if(MasterOperation.merged_bake):
            functions.printmsg("We are doing a merged bake")
            IMGNAME = functions.gen_image_name(bpy.context.scene.TextureBake_Props.mergedBakeName, bpy.context.scene.cycles.bake_type)

            #UDIMs
            if current_bake_op.uv_mode == "udims":
                    IMGNAME = IMGNAME+f".{current_bake_op.udim_counter}"

            functions.create_Images(IMGNAME, bpy.context.scene.cycles.bake_type, bpy.context.scene.TextureBake_Props.mergedBakeName)
            IMGS_TO_SAVE.append(IMGNAME)


        for obj in objects:
            #We will save per object if doing normal or tex per mat bake
            if not MasterOperation.merged_bake:
                IMGS_TO_SAVE = []


            #Reset the already processed list
            mats_done = []
            OBJNAME = functions.trunc_if_needed(obj.name)
            materials = obj.material_slots

            #If not merged and not bake per mat, create the image we need for this bake (Delete if exists)
            if(not MasterOperation.merged_bake and not bpy.context.scene.TextureBake_Props.tex_per_mat):
                IMGNAME = functions.gen_image_name(OBJNAME, bpy.context.scene.cycles.bake_type)

                #UDIMS
                if current_bake_op.uv_mode == "udims":
                    IMGNAME = IMGNAME+f".{current_bake_op.udim_counter}"

                functions.create_Images(IMGNAME, bpy.context.scene.cycles.bake_type, obj.name)
                IMGS_TO_SAVE.append(IMGNAME)

            for matslot in materials:
                mat = bpy.data.materials.get(matslot.name)

                #If we are baking tex per mat, then we need an image for each mat
                if bpy.context.scene.TextureBake_Props.tex_per_mat:
                    functions.printmsg(f"Creating image for material; {matslot.name}")
                    IMGNAME = functions.gen_image_name(OBJNAME, bpy.context.scene.cycles.bake_type)
                    IMGNAME = IMGNAME + "_" + matslot.name
                    functions.create_Images(IMGNAME, bpy.context.scene.cycles.bake_type, obj.name)
                    IMGS_TO_SAVE.append(IMGNAME)

                if mat.name in mats_done:
                    functions.printmsg(f"Skipping material {mat.name}, already processed")
                    #Set the slot to the already created duplicate material and leave
                    dupmat = [m for m in bpy.data.materials if "SB_dupmat" in m and m["SB_dupmat"] == mat.name][0] # Should only be one
                    matslot.material = dupmat
                    continue
                else:
                    #Append but also continue
                    mats_done.append(mat.name)

                #Duplicate material to work on it
                functions.printmsg("Duplicating material")
                mat["SB_originalmat"] = mat.name
                dup = mat.copy()
                dup["SB_dupmat"] = mat.name
                matslot.material = dup
                #We want to work on dup from now on
                mat = dup

                #Make sure we are using nodes
                if not mat.use_nodes:
                    functions.printmsg(f"Material {mat.name} wasn't using nodes. Have enabled nodes")
                    mat.use_nodes = True

                nodetree = mat.node_tree
                nodes = nodetree.nodes
                links = nodetree.links

                #Create the image node and set to the bake texutre we are using
                imgnode = nodes.new("ShaderNodeTexImage")
                imgnode.image = bpy.data.images[IMGNAME]
                imgnode.label = "TextureBake"
                functions.deselectAllNodes(nodes)
                imgnode.select = True
                nodetree.nodes.active = imgnode

            #Make sure only the object we want is selected - unless selected to active
            if not bpy.context.scene.TextureBake_Props.cycles_s2a:
                functions.selectOnlyThis(obj)
            else:
                #If this is CyclesBake and S2A, we need to actually force the selection in the viewport

                bpy.ops.object.select_all(action="DESELECT")
                for obj in current_bake_op.bake_objects:
                    obj.select_set(True)
                bpy.context.view_layer.objects.active = current_bake_op.sb_target_object_cycles

            #Prior to bake, set the colour space of this image
            #if not MasterOperation.merged_bake:
            functions.set_image_internal_col_space(bpy.data.images[IMGNAME], TextureBakeConstants.CYCLESBAKE)

            #Bake
            functions.bakeoperation("cyclesbake", bpy.data.images[IMGNAME])

            #Update tracking
            BakeStatus.current_map+=1
            functions.printmsg(f"Bake maps {BakeStatus.current_map} of {BakeStatus.total_maps} complete")
            functions.write_bake_progress(BakeStatus.current_map, BakeStatus.total_maps)

            #Restore the original materials
            functions.restoreAllMaterials()

            #If this isn't a merged bake, we are done with the image. Scale if needed
            if not MasterOperation.merged_bake:
                functions.sacle_image_if_needed(bpy.data.images[IMGNAME])


            #If we are saving externally, and this isn't a merged bake, save all files after each object complete
            if(bpy.context.scene.TextureBake_Props.saveExternal and not MasterOperation.merged_bake):
                functions.printmsg("Saving baked images externally")
                for img in IMGS_TO_SAVE:
                    functions.printmsg(f"Saving {img}")
                    functions.saveExternal(bpy.data.images[img], "cyclesbake", obj)


        #If merged bake, we are done with the image. So scale if needed
        if MasterOperation.merged_bake:
            functions.sacle_image_if_needed(bpy.data.images[IMGNAME])


        #If we did a merged bake, and we are saving externally, then save here
        if MasterOperation.merged_bake and bpy.context.scene.TextureBake_Props.saveExternal:

            functions.printmsg("Saving merged baked image externally")
            functions.saveExternal(bpy.data.images[IMGNAME], "cyclesbake", None)

    #Bake at least once
    cycles_bake_actual()
    current_bake_op.udim_counter = current_bake_op.udim_counter + 1

    #If we are doing UDIMs, we need to go back in
    if current_bake_op.uv_mode == "udims":

        while current_bake_op.udim_counter < bpy.context.scene.TextureBake_Props.udim_tiles + 1001:
            functions.printmsg(f"Going back in for tile {current_bake_op.udim_counter}")

            #If S2A, shift UVs for the target object only
            if bpy.context.scene.TextureBake_Props.cycles_s2a:
                obj = current_bake_op.sb_target_object_cycles
                functions.UDIM_focustile(obj,current_bake_op.udim_counter - 1001)

            else:
                for obj in current_bake_op.bake_objects:
                    functions.UDIM_focustile(obj,current_bake_op.udim_counter - 1001)

            cycles_bake_actual()

            current_bake_op.udim_counter = current_bake_op.udim_counter + 1


    #Finished baking. Perform wind down actions
    common_bake_finishing()

def specialsBake():

    functions.printmsg("Specials Bake")

    IMGWIDTH = bpy.context.scene.TextureBake_Props.imgwidth
    IMGHEIGHT = bpy.context.scene.TextureBake_Props.imgheight

    current_bake_op = MasterOperation.current_bake_operation

    #Common bake prep
    common_bake_prep()

    #If we are baking S2A as the primary bake, this should focus on the target object
    if current_bake_op.bake_mode == TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY:
        objects = [bpy.context.scene.TextureBake_Props.targetobj]
    elif current_bake_op.bake_mode == TextureBakeConstants.SPECIALS_CYCLES_TARGET_ONLY:
        objects = [bpy.context.scene.TextureBake_Props.targetobj_cycles]
    else:
        objects = current_bake_op.bake_objects



    #Firstly, let's bake the coldid maps if they have been asked for
    if bpy.context.scene.TextureBake_Props.selected_col_mats:
        colIDMap(IMGWIDTH, IMGHEIGHT, objects, TextureBakeConstants.COLOURID)
    if bpy.context.scene.TextureBake_Props.selected_col_vertex:
        colIDMap(IMGWIDTH, IMGHEIGHT, objects, TextureBakeConstants.VERTEXCOL)

    #Import the materials that we need, and save the returned list of specials
    ordered_specials = functions.import_needed_specials_materials()

    def specialsBake_actual():

        #Loop over the selected specials and bake them
        for special in ordered_specials:
            functions.printmsg(f"Baking {special}")

            #If we are doing a merged bake, just create one image here
            if(bpy.context.scene.TextureBake_Props.mergedBake):
                functions.printmsg("We are doing a merged bake")
                IMGNAME = functions.gen_image_name(bpy.context.scene.TextureBake_Props.mergedBakeName, special)

                #UDIMs
                if current_bake_op.uv_mode == "udims":
                    IMGNAME = IMGNAME+f".{udim_counter}"

                #TODO - May want to change the tag when can apply specials bakes
                functions.create_Images(IMGNAME, special, bpy.context.scene.TextureBake_Props.mergedBakeName)


            for obj in objects:
                OBJNAME = obj.name

                #If we are not doing a merged bake, create the image to bake to
                if not bpy.context.scene.TextureBake_Props.mergedBake:
                    IMGNAME = functions.gen_image_name(OBJNAME, special)

                    #UDIMs
                    if current_bake_op.uv_mode == "udims":
                        IMGNAME = IMGNAME+f".{current_bake_op.udim_counter}"

                    #TODO - May want to change the tag when can apply specials bakes
                    functions.create_Images(IMGNAME, special, obj.name)

                #Apply special material to all slots
                materials = obj.material_slots
                for matslot in materials:
                    name = matslot.name


                    #If we already copied the imported special material for this material, use that. If not, copy it and use that
                    if name + "_sbspectmp_" + special in bpy.data.materials:
                        matslot.material = bpy.data.materials[name + "_sbspectmp_" + special]
                    else:
                        newmat = bpy.data.materials["TextureBake_" + special].copy()
                        matslot.material = newmat
                        newmat.name = name + "_sbspectmp_" + special

                    #Create the image node and set to the bake texutre we are using
                    thismat = matslot.material
                    nodes = thismat.node_tree.nodes
                    imgnode = nodes.new("ShaderNodeTexImage")
                    imgnode.image = bpy.data.images[IMGNAME]
                    imgnode.label = "TextureBake"
                    functions.deselectAllNodes(nodes)
                    imgnode.select = True
                    nodes.active = imgnode

                #Prior to bake, set image colour space
                functions.set_image_internal_col_space(bpy.data.images[IMGNAME], special)

                #Bake this object
                functions.selectOnlyThis(obj)

                #If this is the lightmap, we need to do some extra stuff
                if special == TextureBakeConstants.LIGHTMAP:
                    functions.printmsg("Setting up for lightmap")
                    #Record what we have now
                    by = bpy.context.scene.cycles.bake_type
                    ud = bpy.context.scene.render.bake.use_pass_direct
                    ui = bpy.context.scene.render.bake.use_pass_indirect
                    udiff = bpy.context.scene.render.bake.use_pass_diffuse
                    ugloss = bpy.context.scene.render.bake.use_pass_glossy
                    utrans = bpy.context.scene.render.bake.use_pass_transmission
                    uemit = bpy.context.scene.render.bake.use_pass_emit
                    sc = bpy.context.scene.cycles.samples

                    #Set up for lightmap
                    bpy.context.scene.cycles.bake_type = "COMBINED"
                    bpy.context.scene.render.bake.use_pass_direct = True
                    bpy.context.scene.render.bake.use_pass_indirect = True
                    bpy.context.scene.render.bake.use_pass_diffuse = True
                    bpy.context.scene.render.bake.use_pass_glossy = True
                    bpy.context.scene.render.bake.use_pass_transmission = True
                    bpy.context.scene.render.bake.use_pass_emit = True
                    #Temporarily restore the sample count
                    functions.printmsg(f"Temporarily increasing sample count to user set {MasterOperation.orig_sample_count} for lightmap bake")
                    bpy.context.scene.cycles.samples = MasterOperation.orig_sample_count

                    #Call as though it was a CyclesBake, as Lightmap material is not emission
                    functions.bakeoperation("cyclesbake", bpy.data.images[IMGNAME])

                    #Restore the original stuff
                    bpy.context.scene.cycles.bake_type = by
                    bpy.context.scene.render.bake.use_pass_direct = ud
                    bpy.context.scene.render.bake.use_pass_indirect = ui
                    bpy.context.scene.render.bake.use_pass_diffuse = udiff
                    bpy.context.scene.render.bake.use_pass_glossy = ugloss
                    bpy.context.scene.render.bake.use_pass_transmission = utrans
                    bpy.context.scene.render.bake.use_pass_emit = uemit
                    bpy.context.scene.cycles.samples = sc

                else:
                    #This is much easier
                    functions.bakeoperation("special", bpy.data.images[IMGNAME])

                #Scale if needed
                functions.sacle_image_if_needed(bpy.data.images[IMGNAME])

                #Update tracking
                BakeStatus.current_map+=1
                functions.printmsg(f"Bake maps {BakeStatus.current_map} of {BakeStatus.total_maps} complete")
                functions.write_bake_progress(BakeStatus.current_map, BakeStatus.total_maps)

                #Restore all materials
                for matslot in materials:
                    if "_sbspectmp_" + special in matslot.name:
                        matslot.material = bpy.data.materials[matslot.name.replace("_sbspectmp_" + special, "")]


                #We are done with this image, set colour space
                #if not MasterOperation.merged_bake:
                    #functions.set_image_internal_col_space(bpy.data.images[IMGNAME], special)

                #If we are saving per object (not merged bake) - do that here
                if(bpy.context.scene.TextureBake_Props.saveExternal and not MasterOperation.merged_bake):
                    functions.printmsg("Saving baked images externally")
                    functions.saveExternal(bpy.data.images[IMGNAME], special, obj)


            #We are done with this image, set colour space
            #if MasterOperation.merged_bake:
                #functions.set_image_internal_col_space(bpy.data.images[IMGNAME], special)

            #If we did a merged bake, and we are saving externally, then save here
            if MasterOperation.merged_bake and bpy.context.scene.TextureBake_Props.saveExternal:
                functions.printmsg("Saving merged baked image externally")
                functions.saveExternal(bpy.data.images[IMGNAME], special, None)


    #Bake at least once
    specialsBake_actual()
    current_bake_op.udim_counter = current_bake_op.udim_counter + 1

    #If we are doing UDIMs, we need to go back in
    if current_bake_op.uv_mode == "udims":

        while current_bake_op.udim_counter < bpy.context.scene.TextureBake_Props.udim_tiles + 1001:
            functions.printmsg(f"Going back in for tile {current_bake_op.udim_counter}")
            for obj in objects:
                functions.UDIM_focustile(obj,current_bake_op.udim_counter - 1001)

            specialsBake_actual()

            current_bake_op.udim_counter = current_bake_op.udim_counter + 1


    #Delete the special placeholders
    for mat in bpy.data.materials:
        if "_sbspectmp_" in mat.name:
            bpy.data.materials.remove(mat)



    #Call common finishing
    #TODO===----
    common_bake_finishing()


def colIDMap(IMGWIDTH, IMGHEIGHT, objects, mode="random"):

    current_bake_op = MasterOperation.current_bake_operation

    functions.printmsg(f"Baking ColourID map")

    IMGNAME = ""
    mergedbake = bpy.context.scene.TextureBake_Props.mergedBake

    udim_counter = 1001# Exception to the rule?

    def colIDMap_actual():
        #If we are doing a merged bake, just create one image here
        if(mergedbake):
            functions.printmsg("We are doing a merged bake")
            IMGNAME = functions.gen_image_name(bpy.context.scene.TextureBake_Props.mergedBakeName, f"{mode}")
            #UDIMs
            if current_bake_op.uv_mode == "udims":
                IMGNAME = IMGNAME+f".{udim_counter}"

            if mode == TextureBakeConstants.COLOURID:
                functions.create_Images(IMGNAME, TextureBakeConstants.COLOURID, bpy.context.scene.TextureBake_Props.mergedBakeName)
            else:
                functions.create_Images(IMGNAME, TextureBakeConstants.VERTEXCOL, bpy.context.scene.TextureBake_Props.mergedBakeName)

        for obj in objects:
            OBJNAME = functions.trunc_if_needed(obj.name)
            materials = obj.material_slots

            if(not mergedbake):
                #Create the image we need for this bake (Delete if exists)
                if mode == TextureBakeConstants.COLOURID:
                    IMGNAME = functions.gen_image_name(OBJNAME, TextureBakeConstants.COLOURID)
                     #UDIMs
                    if current_bake_op.uv_mode == "udims":
                        IMGNAME = IMGNAME+f".{udim_counter}"
                else:
                    IMGNAME = functions.gen_image_name(OBJNAME, TextureBakeConstants.VERTEXCOL)
                     #UDIMs
                    if current_bake_op.uv_mode == "udims":
                        IMGNAME = IMGNAME+f".{udim_counter}"

                if mode == TextureBakeConstants.COLOURID:
                    functions.create_Images(IMGNAME, TextureBakeConstants.COLOURID, obj.name)
                else:
                    functions.create_Images(IMGNAME, TextureBakeConstants.VERTEXCOL, obj.name)

            for matslot in materials:
                mat = bpy.data.materials.get(matslot.name)

                #Duplicate material to work on it
                functions.printmsg("Duplicating material")
                mat["SB_originalmat"] = mat.name
                dup = mat.copy()
                dup["SB_dupmat"] = mat.name
                matslot.material = dup
                #We want to work on dup from now on
                mat = dup

                #Make sure we are using nodes
                if not mat.use_nodes:
                    functions.printmsg(f"Material {mat.name} wasn't using nodes. Have enabled nodes")
                    mat.use_nodes = True

                nodetree = mat.node_tree
                nodes = nodetree.nodes
                links = nodetree.links

                m_output_node = functions.find_onode(nodetree)

                #Create emission shader and connect to material output
                emissnode = nodes.new("ShaderNodeEmission")
                emissnode.label = "TextureBake"
                fromsocket = emissnode.outputs[0]
                tosocket = m_output_node.inputs[0]
                nodetree.links.new(fromsocket, tosocket)

                if mode == TextureBakeConstants.COLOURID:
                    #Have we already generated a colour for this mat?
                    if mat.name in current_bake_op.mat_col_dict:
                        col = current_bake_op.mat_col_dict[mat.name]
                        emissnode.inputs["Color"].default_value = (col[0], col[1], col[2], 1.0)

                    else:

                        import random

                        #First attempt
                        randr = random.randint(0,10) / 10
                        randg = random.randint(0,10) / 10
                        randb = random.randint(0,10) / 10

                        min_diff = 0.6
                        i=0
                        giveup = False
                        while functions.check_col_distance(randr,randg,randb, min_diff) == False and not giveup:
                            randr = random.randint(0,10) / 10
                            randg = random.randint(0,10) / 10
                            randb = random.randint(0,10) / 10
                            i=i+1
                            if i == 100:
                                #We've tried 100 times and got nothing, reduce required min_diff
                                i=0
                                min_diff = round(min_diff - 0.1,1)
                                functions.printmsg(f"Just reduced min_diff to {min_diff}")

                                #If we are now at 0, give up
                                if min_diff == 0:
                                    functions.printmsg("Giving up")
                                    giveup = True


                        emissnode.inputs["Color"].default_value = (randr, randg, randb, 1.0)
                        #Record col for this mat
                        current_bake_op.mat_col_dict[mat.name] = [randr, randg, randb]


                #We are using vertex colours
                else:
                    #Using vertex colours
                    #Get name of active vertex colors for this object
                    col_name = obj.data.vertex_colors.active.name
                    #Create attribute node
                    attrnode = nodes.new("ShaderNodeAttribute")
                    #Set it to the active vertex cols
                    attrnode.attribute_name = col_name
                    #Connect
                    fromsocket = attrnode.outputs[0]
                    tosocket = emissnode.inputs[0]
                    nodetree.links.new(fromsocket, tosocket)

                #Create the image node and set to the bake texutre we are using
                imgnode = nodes.new("ShaderNodeTexImage")
                imgnode.image = bpy.data.images[IMGNAME]
                imgnode.label = "TextureBake"
                functions.deselectAllNodes(nodes)
                imgnode.select = True
                nodetree.nodes.active = imgnode

            #Make sure only the object we want is selected (unless we are doing selected to active
            functions.selectOnlyThis(obj)

            #Prior to bake set col space
            #if not MasterOperation.merged_bake:
            functions.set_image_internal_col_space(bpy.data.images[IMGNAME], "special")

            #Bake
            functions.bakeoperation("Emission", bpy.data.images[IMGNAME])

            #Scale if needed
            functions.sacle_image_if_needed(bpy.data.images[IMGNAME])

            #Update tracking
            BakeStatus.current_map+=1
            functions.printmsg(f"Bake maps {BakeStatus.current_map} of {BakeStatus.total_maps} complete")
            functions.write_bake_progress(BakeStatus.current_map, BakeStatus.total_maps)

            #Restore the original materials
            functions.restoreAllMaterials()


            #If we are saving externally, and this is not a merged bake, save
            if(bpy.context.scene.TextureBake_Props.saveExternal and not mergedbake):
                functions.printmsg("Saving baked images externally")
                functions.saveExternal(bpy.data.images[IMGNAME], "special", obj)

        #We are done with this image, set colour space
        #if MasterOperation.merged_bake:
            #functions.set_image_internal_col_space(bpy.data.images[IMGNAME], "special")

        #If we did a merged bake, and we are saving externally, then save here
        if mergedbake and bpy.context.scene.TextureBake_Props.saveExternal:
            functions.printmsg("Saving merged baked image externally")
            functions.saveExternal(bpy.data.images[IMGNAME], "special", None)


    #Bake at least once
    colIDMap_actual()
    udim_counter = udim_counter + 1

    #If we are doing UDIMs, we need to go back in
    if current_bake_op.uv_mode == "udims":

        while udim_counter < bpy.context.scene.TextureBake_Props.udim_tiles + 1001:
            functions.printmsg(f"Going back in for tile {udim_counter}")
            for obj in objects:
                functions.UDIM_focustile(obj,udim_counter - 1001)

            colIDMap_actual()

            udim_counter = udim_counter + 1

    #Manually reset the UDIM tile. We don't run common finishing here, and we might end up going back to bake more specials
    for obj in current_bake_op.bake_objects:
        functions.UDIM_focustile(obj, 0)




def doBake():

    current_bake_op = MasterOperation.current_bake_operation

    #Do the prep we need to do for all bake types
    common_bake_prep()

    #Loop over the bake modes we are using
    def doBake_actual():

        IMGNAME = ""

        for thisbake in current_bake_op.pbr_selected_bake_types:

            #If we are doing a merged bake, just create one image here
            if(MasterOperation.merged_bake):
                functions.printmsg("We are doing a merged bake")
                IMGNAME = functions.gen_image_name(bpy.context.scene.TextureBake_Props.mergedBakeName, thisbake)

                #UDIM testing
                if current_bake_op.uv_mode == "udims":
                    IMGNAME = IMGNAME+f".{current_bake_op.udim_counter}"

                functions.create_Images(IMGNAME, thisbake, bpy.context.scene.TextureBake_Props.mergedBakeName)


            for obj in current_bake_op.bake_objects:
                #Reset the already processed list
                mats_done = []

                functions.printmsg(f"Baking object: {obj.name}")


                #Truncate if needed from this point forward
                OBJNAME = functions.trunc_if_needed(obj.name)

                #If we are not doing a merged bake
                #Create the image we need for this bake (Delete if exists)
                if(not MasterOperation.merged_bake):
                    IMGNAME = functions.gen_image_name(obj.name, thisbake)

                    #UDIM testing
                    if current_bake_op.uv_mode == "udims":
                        IMGNAME = IMGNAME+f".{current_bake_op.udim_counter}"

                    functions.create_Images(IMGNAME, thisbake, obj.name)


                #Prep the materials one by one
                materials = obj.material_slots
                for matslot in materials:
                    mat = bpy.data.materials.get(matslot.name)

                    if mat.name in mats_done:
                        functions.printmsg(f"Skipping material {mat.name}, already processed")
                        #Set the slot to the already created duplicate material and leave
                        dupmat = [m for m in bpy.data.materials if "SB_dupmat" in m and m["SB_dupmat"] == mat.name][0] # Should only be one
                        matslot.material = dupmat
                        continue
                    else:
                        mats_done.append(mat.name)


                    #Duplicate material to work on it
                    functions.printmsg("Duplicating material")
                    mat["SB_originalmat"] = mat.name
                    dup = mat.copy()
                    dup["SB_dupmat"] = mat.name
                    matslot.material = dup
                    #We want to work on dup from now on
                    mat = dup

                    #Make sure we are using nodes
                    if not mat.use_nodes:
                        functions.printmsg(f"Material {mat.name} wasn't using nodes. Have enabled nodes")
                        mat.use_nodes = True

                    nodetree = mat.node_tree
                    nodes = nodetree.nodes

                    #Create the image node and set to the bake texutre we are using
                    imgnode = nodes.new("ShaderNodeTexImage")
                    imgnode.image = bpy.data.images[IMGNAME]
                    imgnode.label = "TextureBake"

                    #Remove all disconnected nodes so don't interfere with typing the material
                    functions.removeDisconnectedNodes(nodetree)

                    #Normal and emission bakes require no further material prep. Just skip the rest
                    if(thisbake != "normal" and thisbake != "emission"):
                        #Work out what type of material we are dealing with here and take correct action
                        mat_type = functions.getMatType(nodetree)

                        if(mat_type == "MIX"):
                            functions.setup_mix_material(nodetree, thisbake)
                        elif(mat_type == "PURE_E"):
                            functions.setup_pure_e_material(nodetree, thisbake)
                        elif(mat_type == "PURE_P"):
                            functions.setup_pure_p_material(nodetree, thisbake)

                    #Last action before leaving this material, make the image node selected and active
                    functions.deselectAllNodes(nodes)
                    imgnode.select = True
                    nodetree.nodes.active = imgnode


                #Select only this object
                functions.selectOnlyThis(obj)

                #We are done with this image, set colour space
                #if not MasterOperation.merged_bake:
                    #functions.set_image_internal_col_space(bpy.data.images[IMGNAME], thisbake)

                functions.set_image_internal_col_space(bpy.data.images[IMGNAME], thisbake)


                #Bake the object for this bake mode
                functions.bakeoperation(thisbake, bpy.data.images[IMGNAME])

                #Update tracking
                BakeStatus.current_map+=1
                functions.printmsg(f"Bake maps {BakeStatus.current_map} of {BakeStatus.total_maps} complete")
                functions.write_bake_progress(BakeStatus.current_map, BakeStatus.total_maps)

                #Restore the original materials
                functions.printmsg("Restoring original materials")
                functions.restoreAllMaterials()
                functions.printmsg("Restore complete")

                #Last thing we do with this image is scale it (as long as not a merged baked - if it is we will scale later)
                if not MasterOperation.merged_bake:
                    functions.sacle_image_if_needed(bpy.data.images[IMGNAME])

                #If we are saving externally, and this isn't a merged bake
                if not MasterOperation.merged_bake:
                    #Always do post processing
                    IMGNAME = do_post_processing(thisbake=thisbake, IMGNAME=IMGNAME)
                    #Save external if we are saving
                    if bpy.context.scene.TextureBake_Props.saveExternal:
                        functions.printmsg("Saving baked images externally")
                        functions.saveExternal(bpy.data.images[IMGNAME], thisbake, obj)

            #If we did a merged bake, and we are saving externally, then save here
            if MasterOperation.merged_bake:
                #Scale the image now we are done with it
                functions.sacle_image_if_needed(bpy.data.images[IMGNAME])

                #Always do post processing
                IMGNAME = do_post_processing(thisbake=thisbake, IMGNAME=IMGNAME)
                #Save external if we are saving
                if bpy.context.scene.TextureBake_Props.saveExternal:
                    functions.printmsg("Saving merged baked image externally")
                    functions.saveExternal(bpy.data.images[IMGNAME], thisbake, None)

    #Do the bake at least once
    doBake_actual()
    current_bake_op.udim_counter = current_bake_op.udim_counter + 1

    #If we are doing UDIMs, we need to go back in
    if current_bake_op.uv_mode == "udims":

        while current_bake_op.udim_counter < bpy.context.scene.TextureBake_Props.udim_tiles + 1001:
            functions.printmsg(f"Going back in for tile {current_bake_op.udim_counter}")
            for obj in current_bake_op.bake_objects:
                functions.UDIM_focustile(obj,current_bake_op.udim_counter - 1001)

            doBake_actual()

            current_bake_op.udim_counter = current_bake_op.udim_counter + 1


    #Finished baking. Perform wind down actions
    common_bake_finishing()



def doBakeS2A():

    current_bake_op = MasterOperation.current_bake_operation

    #Do the prep, as usual
    common_bake_prep()

    #Always set the ray distance to the one selected in TextureBake
    #functions.printmsg(f"Setting ray distance to {round(bpy.context.scene.TextureBake_Props.ray_distance, 2)}")
    #bpy.context.scene.render.bake.cage_extrusion = bpy.context.scene.TextureBake_Props.ray_distance

    #Info
    functions.printmsg("Baking PBR maps to target mesh: " + current_bake_op.sb_target_object.name)

    #Loop over the bake modes we are using
    def doBakeS2A_actual():

        IMGNAME = ""

        for thisbake in current_bake_op.pbr_selected_bake_types:
            #We just need the one image for each bake mode, created at the target object
            functions.printmsg("We are bakikng PBR maps to target mesh")
            IMGNAME = functions.gen_image_name(current_bake_op.sb_target_object.name, thisbake)

            #UDIM testing
            if current_bake_op.uv_mode == "udims":
                IMGNAME = IMGNAME+f".{current_bake_op.udim_counter}"

            functions.create_Images(IMGNAME, thisbake, current_bake_op.sb_target_object.name)

            #Prep the target object
            materials = current_bake_op.sb_target_object.material_slots
            for matslot in materials:
                mat = bpy.data.materials.get(matslot.name)

                #First, check if the material is using nodes. If not, enable
                if not mat.use_nodes:
                    functions.printmsg(f"Material {mat.name} wasn't using nodes. Have enabled nodes")
                    mat.use_nodes = True

                nodetree = mat.node_tree
                nodes = nodetree.nodes

                #Create the image node and set to the bake texutre we are using
                imgnode = nodes.new("ShaderNodeTexImage")
                imgnode.image = bpy.data.images[IMGNAME]
                imgnode.label = "TextureBake"

                #Make the image node selected and active
                functions.deselectAllNodes(nodes)
                imgnode.select = True
                nodetree.nodes.active = imgnode

            #Reset the already processed list before loop
            mats_done = []

            #Now prep all the objects for this bake mode
            for obj in current_bake_op.bake_objects:

                #Skip this if it is the target object
                if obj == current_bake_op.sb_target_object:
                    continue

                #Update
                functions.printmsg(f"Preparing object: {obj.name}")
                OBJNAME = functions.trunc_if_needed(obj.name)

                #Prep the materials one by one
                materials = obj.material_slots
                for matslot in materials:
                    mat = bpy.data.materials.get(matslot.name)

                    #Skip if in done list, else record in done list
                    if mat.name in mats_done:
                        functions.printmsg(f"Skipping material {mat.name}, already processed")
                        #Set the slot to the already created duplicate material and leave
                        dupmat = [m for m in bpy.data.materials if "SB_dupmat" in m and m["SB_dupmat"] == mat.name][0] # Should only be one
                        matslot.material = dupmat
                        continue

                    else:
                        mats_done.append(mat.name)

                    #Duplicate material to work on it
                    functions.printmsg("Duplicating material")
                    mat["SB_originalmat"] = mat.name
                    dup = mat.copy()
                    dup["SB_dupmat"] = mat.name
                    matslot.material = dup
                    #We want to work on dup from now on
                    mat = dup

                    nodetree = mat.node_tree
                    nodes = nodetree.nodes

                    #Remove all disconnected nodes so don't interfere with typing the material
                    functions.removeDisconnectedNodes(nodetree)

                    #Normal and emission bakes require no further material prep. Just skip the rest
                    if(thisbake != "normal" and thisbake != "emission"):
                        #Work out what type of material we are dealing with here and take correct action
                        mat_type = functions.getMatType(nodetree)

                        if(mat_type == "MIX"):
                            functions.setup_mix_material(nodetree, thisbake)
                        elif(mat_type == "PURE_E"):
                            functions.setup_pure_e_material(nodetree, thisbake)
                        elif(mat_type == "PURE_P"):
                            functions.setup_pure_p_material(nodetree, thisbake)

                #Make sure that correct objects are selected right before bake
                bpy.ops.object.select_all(action="DESELECT")
                for obj in current_bake_op.bake_objects:
                    obj.select_set(True)
                current_bake_op.sb_target_object.select_set(True)
                bpy.context.view_layer.objects.active = current_bake_op.sb_target_object

            #We are done with this image, set colour space
            functions.set_image_internal_col_space(bpy.data.images[IMGNAME], thisbake)

            #Bake the object for this bake mode
            functions.bakeoperation(thisbake, bpy.data.images[IMGNAME])

            #Scale if needed
            functions.sacle_image_if_needed(bpy.data.images[IMGNAME])

            #Update tracking
            BakeStatus.current_map+=1
            functions.printmsg(f"Bake maps {BakeStatus.current_map} of {BakeStatus.total_maps} complete")
            functions.write_bake_progress(BakeStatus.current_map, BakeStatus.total_maps)

            #Restore the original materials
            functions.restoreAllMaterials()


            #Delete that image node we created at the target object
            materials = current_bake_op.sb_target_object.material_slots
            for matslot in materials:
                mat = bpy.data.materials.get(matslot.name)
                for node in mat.node_tree.nodes:
                    if node.label == "TextureBake":
                        mat.node_tree.nodes.remove(node)

            #Always do post processing
            IMGNAME = do_post_processing(thisbake=thisbake, IMGNAME=IMGNAME)


            #If we are saving externally, save
            if(bpy.context.scene.TextureBake_Props.saveExternal):
                functions.printmsg("Saving baked images externally")
                functions.saveExternal(bpy.data.images[IMGNAME], thisbake, current_bake_op.sb_target_object)

    #Do the bake at least once
    doBakeS2A_actual()
    current_bake_op.udim_counter = current_bake_op.udim_counter + 1

    #If we are doing UDIMs, we need to go back in
    if current_bake_op.uv_mode == "udims":

        while current_bake_op.udim_counter < bpy.context.scene.TextureBake_Props.udim_tiles + 1001:
            functions.printmsg(f"Going back in for tile {current_bake_op.udim_counter}")
            for obj in current_bake_op.bake_objects:
                functions.UDIM_focustile(current_bake_op.sb_target_object,current_bake_op.udim_counter - 1001)

            doBakeS2A_actual()

            current_bake_op.udim_counter = current_bake_op.udim_counter + 1


    #Finished baking all bake modes. Perform wind down actions
    common_bake_finishing()

def sketchfabupload(caller):

    functions.printmsg("Sketchfab Upload Beginning")

    ########################
    #Check SB_createdfrom property. Only upload copied and applied.
    #Change tooltips
    #Change poll (check for above property)
    ########################


    #Get the currently selected objects
    target_objs_list = bpy.context.selected_objects
    images_imgs = []

    #Get all the textures being used by our objects. Should only have one material each
    for obj in target_objs_list:
        nodes = obj.material_slots[0].material.node_tree.nodes
        for node in nodes:
            if node.bl_idname == "ShaderNodeTexImage":
                images_imgs.append(node.image)

    #Create a temp folder for SFUpload in the folder where blend saved
    f = Path(bpy.data.filepath)
    f = f.parents[0]
    f = f / "SFUpload"


    try:
        os.mkdir(str(f))
    except:
        pass #Already exists



    #Save each image into that folder

    writtenfilenames_strlist = []
    for img in images_imgs:

        #If it is internal only
        if img.filepath == "":
            #Just set it's file path and save. This one is easy
            img.filepath = str(f / functions.cleanFileName(img.name))

            if not ".png" in img.filepath:
                img.filepath = img.filepath + ".png"
            img.save()

        #If it's already been saved externally, bit more complicated
        else:
            op = img.filepath
            off = img.file_format

            img.pack() #Or else changing its filepath will screw it up
            img.filepath = str(f / functions.cleanFileName(img.name))

            if not ".png" in img.filepath:
                img.filepath = img.filepath + ".png"

            img.file_format = "PNG"

            img.save()
            img.unpack()
            img.filepath = op
            img.file_format = off

        #In either case, add the image name to our list
        writtenfilenames_strlist.append(Path(img.filepath).parts[-1])



    #Export the fbx (we might have multiple objects)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in target_objs_list:
        obj.select_set(state=True)

    filename = (functions.getFileName()).replace(".blend", "")
    bpy.ops.export_scene.fbx(filepath=str(f / f"{filename}.fbx"), check_existing=False, use_selection=True, use_mesh_modifiers=True, use_mesh_modifiers_render=True, path_mode="STRIP")


    #Zip it up
    from zipfile import ZipFile

    zip_path = str(f / f"{filename}.zip")
    zip = ZipFile(str(zip_path), mode="w")
    for fn in writtenfilenames_strlist:
        zip.write(str(f / fn), arcname=fn)


    #And now the fbx
    zip.write(str(f / f"{filename}.fbx"), arcname=f"{filename}.fbx")
    zip.close()


    #Get Sketchfab API
    preferences = bpy.context.preferences
    addon_prefs = preferences.addons[__package__].preferences
    apikey = addon_prefs.apikey

    #Call Sketchfab Upload
    from . import sketchfabapi
    upload_url = sketchfabapi.upload(zip_path, functions.getFileName(), apikey)

    if not upload_url:
        functions.printmsg("Upload to Sketchfab failed. See console messages for details")
        return False
    else:
        #Open URL that is returned
        import webbrowser
        webbrowser.open(upload_url, new=0, autoraise=True)
        functions.printmsg("Upload complete. Your web broswer should have opened.")

    #Delete Zip file
    #import os
    #os.remove(zip_path)

    #return True

