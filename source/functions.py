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

import urllib.request
from pathlib import Path
import shutil
import bpy
import os
import base64
import sys
import tempfile
from . import material_setup
from .bake_operation import BakeOperation, MasterOperation, SimpleBakeConstants
from .ui import SimpleBake_Previews
from .bake_operation import bakestolist


#Global variables
psocketname = {
    "diffuse": "Base Color",
    "metalness": "Metallic",
    "roughness": "Roughness",
    "normal": "Normal",
    "transparency": "Transmission",
    "transparencyroughness": "Transmission Roughness",
    "clearcoat": "Clearcoat",
    "clearcoatroughness": "Clearcoat Roughness",
    "specular": "Specular",
    "alpha": "Alpha",
    "sss": "Subsurface",
    "ssscol": "Subsurface Color"
    }

def printmsg(msg):
    print(f"SIMPLEBAKE: {msg}")


def does_object_have_bakes(obj):

    for img in bpy.data.images:
        if "SB_objname" in img: #SB_objname is always set. Even for mergedbake
            return True
        else:
            return False


def gen_image_name(obj_name, baketype, demo=False):
    print(baketype)

    if not demo:
        current_bake_op = MasterOperation.current_bake_operation

    #First, let's get the format string we are working with

    prefs = bpy.context.preferences.addons[__package__].preferences
    image_name = prefs.img_name_format

    #"%OBJ%_%BATCH%_%BAKETYPE%"

    #The easy ones
    image_name = image_name.replace("%OBJ%", obj_name)
    image_name = image_name.replace("%BATCH%", bpy.context.scene.SimpleBake_Props.batchName)

    #Bake mode
    if not demo:
        image_name = image_name.replace("%BAKEMODE%", current_bake_op.bake_mode)
    else:
        image_name = image_name.replace("%BAKEMODE%", "pbr")


    #The hard ones
    if baketype == "diffuse":
        image_name = image_name.replace("%BAKETYPE%", prefs.diffuse_alias)

    elif baketype == "metalness":
        image_name = image_name.replace("%BAKETYPE%", prefs.metal_alias)

    elif baketype == "roughness":
        image_name = image_name.replace("%BAKETYPE%", prefs.roughness_alias)

    elif baketype == "normal":
        image_name = image_name.replace("%BAKETYPE%", prefs.normal_alias)

    elif baketype == "transparency":
        image_name = image_name.replace("%BAKETYPE%", prefs.transmission_alias)

    elif baketype == "transparencyroughness":
        image_name = image_name.replace("%BAKETYPE%", prefs.transmissionrough_alias)

    elif baketype == "clearcoat":
        image_name = image_name.replace("%BAKETYPE%", prefs.clearcoat_alias)

    elif baketype == "clearcoatroughness":
        image_name = image_name.replace("%BAKETYPE%", prefs.clearcoatrough_alias)

    elif baketype == "emission":
        image_name = image_name.replace("%BAKETYPE%", prefs.emission_alias)

    elif baketype == "specular":
        image_name = image_name.replace("%BAKETYPE%", prefs.specular_alias)

    elif baketype == "alpha":
        image_name = image_name.replace("%BAKETYPE%", prefs.alpha_alias)

    elif baketype == SimpleBakeConstants.AO:
        image_name = image_name.replace("%BAKETYPE%", prefs.ao_alias)
    elif baketype == SimpleBakeConstants.LIGHTMAP:
        image_name = image_name.replace("%BAKETYPE%", prefs.lightmap_alias)
    elif baketype == SimpleBakeConstants.COLOURID:
        image_name = image_name.replace("%BAKETYPE%", prefs.colid_alias)
    elif baketype == SimpleBakeConstants.CURVATURE:
        image_name = image_name.replace("%BAKETYPE%", prefs.curvature_alias)

    elif baketype == SimpleBakeConstants.THICKNESS:
        image_name = image_name.replace("%BAKETYPE%", prefs.thickness_alias)

    elif baketype == SimpleBakeConstants.VERTEXCOL:
        image_name = image_name.replace("%BAKETYPE%", prefs.vertexcol_alias)

    elif baketype == "sss":
        image_name = image_name.replace("%BAKETYPE%", prefs.sss_alias)
    elif baketype == "ssscol":
        image_name = image_name.replace("%BAKETYPE%", prefs.ssscol_alias)

    else:
        image_name = image_name.replace("%BAKETYPE%", baketype)

    return image_name

def removeDisconnectedNodes(nodetree):
    nodes = nodetree.nodes

    #Loop through nodes
    repeat = False
    for node in nodes:
        if node.type == "BSDF_PRINCIPLED" and len(node.outputs[0].links) == 0:
            #Not a player, delete node
            nodes.remove(node)
            repeat = True
        elif node.type == "EMISSION" and len(node.outputs[0].links) == 0:
            #Not a player, delete node
            nodes.remove(node)
            repeat = True
        elif node.type == "MIX_SHADER" and len(node.outputs[0].links) == 0:
            #Not a player, delete node
            nodes.remove(node)
            repeat = True

    #If we removed any nodes, we need to do this again
    if repeat:
        removeDisconnectedNodes(nodetree)


def restoreAllMaterials():

    for obj in bpy.data.objects:
        if (obj.material_slots != None) and (len(obj.material_slots) > 0):#Stop the error where Nonetype not iterable
            #Get all slots that are using a dup mat
            dup_mats_slots_list = [slot for slot in obj.material_slots if slot.material != None and "SB_dupmat" in slot.material]

            #Swap those slos back to the original version of their material
            for dup_mat_slot in dup_mats_slots_list:

                dup_mat = dup_mat_slot.material
                orig_mat_name = dup_mat["SB_dupmat"]

                orig_mat = [mat for mat in bpy.data.materials if "SB_originalmat" in mat and mat["SB_originalmat"] == orig_mat_name][0] #Should only be one
                dup_mat_slot.material = orig_mat

    #Delete all duplicates (should no longet be any in use)
    del_list = [mat for mat in bpy.data.materials if "SB_dupmat" in mat]
    for mat in del_list:
        bpy.data.materials.remove(mat)



def install_addon_update():

    try:
        #Current ver URL
        current_ver_url = base64.b64decode("aHR0cDovL3d3dy50b29oZXkuY28udWsvU2ltcGxlQmFrZS9TaW1wbGVCYWtlX0N1cnJlbnQzLnppcA==").decode("utf-8")
        current_ver_zip_name = "SimpleBake_Curent3.zip"
        addon_dir_name =  "SimpleBake"

        import zipfile #only needed here

        #Get the path where the addons are kept
        if bpy.utils.script_path_pref() != None:
            addons_path = Path(bpy.utils.script_path_pref())
        else:
            addons_path = Path(bpy.utils.script_path_user())
        addons_path = addons_path / "addons"

        #Make our current directory the addons directory
        os.chdir(str(addons_path))

        #Download new SimbleBake_Current.zip to addons folder
        printmsg("Starting download")
        urllib.request.urlretrieve(current_ver_url, current_ver_zip_name)
        current_ver_zip_name = "SimpleBake_Curent3.zip"
        printmsg("Download complete")

        #Delete current SimpleBake folder
        addon_dir = addons_path / addon_dir_name
        shutil.rmtree(str(addon_dir))

        #Unzip
        current_ver_zip = zipfile.ZipFile(current_ver_zip_name, "r")
        current_ver_zip.extractall()
        current_ver_zip.close()

        #Delete the zip file we downlaoded
        downloaded_zip = addons_path / current_ver_zip_name
        downloaded_zip.unlink()

        return [True]

    except Exception as e:
        return [False, e]

def isBlendSaved():
    path = bpy.data.filepath
    if(path=="/" or path==""):
        #Not saved
        return False
    else:
        return True

def create_Images(imgname, thisbake, objname):
    #thisbake is subtype e.g. diffuse, ao, etc.

    current_bake_op = MasterOperation.current_bake_operation
    global_mode = current_bake_op.bake_mode
    cycles_mode = bpy.context.scene.cycles.bake_type
    batch = MasterOperation.batch_name

    printmsg(f"Creating image {imgname}")

    #Get the image height and width from the interface
    IMGHEIGHT = bpy.context.scene.SimpleBake_Props.imgheight
    IMGWIDTH = bpy.context.scene.SimpleBake_Props.imgwidth

    #If it already exists, remove it.
    if(imgname in bpy.data.images):
        bpy.data.images.remove(bpy.data.images[imgname])

    #Either way, create the new image
    alpha = bpy.context.scene.SimpleBake_Props.useAlpha

    all32 = bpy.context.scene.SimpleBake_Props.everything32bitfloat
    export = bpy.context.scene.SimpleBake_Props.saveExternal
    all16 = bpy.context.scene.SimpleBake_Props.everything16bit


    #Create image 32 bit or not 32 bit
    if thisbake == "normal" or (global_mode == SimpleBakeConstants.CYCLESBAKE and bpy.context.scene.cycles.bake_type == "NORMAL"):
        image = bpy.data.images.new(imgname, IMGWIDTH, IMGHEIGHT, alpha=alpha, float_buffer=True)
    elif all32:
        image = bpy.data.images.new(imgname, IMGWIDTH, IMGHEIGHT, alpha=alpha, float_buffer=True)
    else:
        image = bpy.data.images.new(imgname, IMGWIDTH, IMGHEIGHT, alpha=alpha, float_buffer=False)

    if alpha:
        image.generated_color = (0,0,0,0)


    #Set tags
    image["SB_objname"] = objname
    image["SB_batch"] = batch
    image["SB_globalmode"] = global_mode
    image["SB_thisbake"] = thisbake
    if MasterOperation.merged_bake:
        image["SB_mergedbakename"] = MasterOperation.merged_bake_name
    else:
        image["SB_mergedbakename"] = None
    if current_bake_op.uv_mode == "udims":
        image["SB_udims"] = True
    else:
        image["SB_udims"] = False



    #Always mark new iages fake user when generated in the background
    if "--background" in sys.argv:
        image.use_fake_user = True

    #Store it at bake operation level
    MasterOperation.baked_textures.append(image)




def deselectAllNodes(nodes):
    for node in nodes:
        node.select = False


def findSocketConnectedtoP(pnode, thisbake):
    #Get socket name for this bake mode
    socketname = psocketname[thisbake]

    #Get socket of the pnode
    socket = pnode.inputs[socketname]
    fromsocket = socket.links[0].from_socket

    #Return the socket connected to the pnode
    return fromsocket

def createdummynodes(nodetree, thisbake):
    #Loop through pnodes
    nodes = nodetree.nodes

    for node in nodes:
        if node.type == "BSDF_PRINCIPLED":
            pnode = node
            #Get socket name for this bake mode
            socketname = psocketname[thisbake]

            #Get socket of the pnode
            psocket = pnode.inputs[socketname]

            #If it has something plugged in, we can leave it here
            if(len(psocket.links) > 0):
                continue

            #Get value of the unconnected socket
            val = psocket.default_value

            #If this is base col or ssscol, add an RGB node and set it's value to that of the socket
            if(socketname == "Base Color" or socketname == "Subsurface Color"):
                rgb = nodetree.nodes.new("ShaderNodeRGB")
                rgb.outputs[0].default_value = val
                rgb.label = "SimpleBake"
                nodetree.links.new(rgb.outputs[0], psocket)

            #If this is anything else, use a value node
            else:
                vnode = nodetree.nodes.new("ShaderNodeValue")
                vnode.outputs[0].default_value = val
                vnode.label = "SimpleBake"
                nodetree.links.new(vnode.outputs[0], psocket)

def bakeoperation(thisbake, img):


    if(thisbake == "cyclesbake"):
        #If we are doing an old fashioned cycles bake, do that and then exit
        printmsg(f"Beginning bake based on Cycles settings: {bpy.context.scene.cycles.bake_type}")

        bpy.ops.object.bake(type=bpy.context.scene.cycles.bake_type)
        #Always pack the image for now
        img.pack()

        #Not COMBINED or DIFFUSE
        #if bpy.context.scene.cycles.bake_type not in ["COMBINED", "DIFFUSE"]:
            #img.colorspace_settings.name = "Non-Color"

        return True

    printmsg(f"Beginning bake for {thisbake}")

    use_clear = False

    if(thisbake != "normal"):
        bpy.ops.object.bake(type="EMIT", save_mode="INTERNAL", use_clear=use_clear)
    else:
        bpy.ops.object.bake(type="NORMAL", save_mode="INTERNAL", use_clear=use_clear)



    #Always pack the image for now
    img.pack()


    #Adjust colour space settings (PBR only at this point)
    #export = bpy.context.scene.SimpleBake_Props.saveExternal
    #if thisbake != "diffuse":
        #img.colorspace_settings.name = "Non-Color"

def find_collection_parent(col_name):

    for col in bpy.data.collections:
        children = col.children

        if len(children) == 0:
            break

        for child in children:
            if child.name == col_name:
                return col.name # Assumes a collection can only have one parent... think this is right

    return None




def startingChecks(objects, bakemode):

    messages = []

    #Check if in object mode
    if(bpy.context.mode != "OBJECT"):
        messages.append("ERROR: Not in object mode")
        ShowMessageBox(messages, "Errors occured", "ERROR")
        return False

    #Refresh the list before we do anything else
    update_advanced_object_list()

    #This is hacky. A better way to do this needs to be found
    advancedobj = bpy.context.scene.SimpleBake_Props.advancedobjectselection
    if advancedobj:
        objects = advanced_object_selection_to_list()

    #Check no cp textures rely on bakes that are no longer enabled
    #Hacky
    if bpy.context.scene.SimpleBake_Props.global_mode == "pbr_bake":
        pbr_bakes = bakestolist()
        if bpy.context.scene.SimpleBake_Props.rough_glossy_switch == "glossy":
            pbr_bakes = ["glossy" if bake == "roughness" else bake for bake in pbr_bakes]
        special_bakes = []
        special_bakes.append(SimpleBakeConstants.COLOURID) if bpy.context.scene.SimpleBake_Props.selected_col_mats else False
        special_bakes.append(SimpleBakeConstants.VERTEXCOL) if bpy.context.scene.SimpleBake_Props.selected_col_vertex else False
        special_bakes.append(SimpleBakeConstants.AO) if bpy.context.scene.SimpleBake_Props.selected_ao else False
        special_bakes.append(SimpleBakeConstants.THICKNESS) if bpy.context.scene.SimpleBake_Props.selected_thickness else False
        special_bakes.append(SimpleBakeConstants.CURVATURE) if bpy.context.scene.SimpleBake_Props.selected_curvature else False
        special_bakes.append(SimpleBakeConstants.LIGHTMAP) if bpy.context.scene.SimpleBake_Props.selected_lightmap else False
        bakes = pbr_bakes + special_bakes
        bakes.append("none")
        for cpt in bpy.context.scene.SimpleBake_Props.cp_list:
            if cpt.R not in bakes:
                messages.append(f"ERROR: Channel packed texture \"{cpt.name}\" depends on {cpt.R}, but you are no longer baking it")
            if cpt.G not in bakes:
                messages.append(f"ERROR: Channel packed texture \"{cpt.name}\" depends on {cpt.G}, but you are no longer baking it")
            if cpt.B not in bakes:
                messages.append(f"ERROR: Channel packed texture \"{cpt.name}\" depends on {cpt.B}, but you are no longer baking it")
            if cpt.A not in bakes:
                messages.append(f"ERROR: Channel packed texture \"{cpt.name}\" depends on {cpt.A}, but you are no longer baking it")
        if len(messages) >0:
            ShowMessageBox(messages, "Errors occured", "ERROR")
            return False

    #Is anything seleccted at all for bake?
    if len(objects) == 0:
        messages.append("ERROR: Nothing selected for bake")
        if advancedobj:
            messages.append("NOTE: You have advanced object selection turned on, so you have to add bake objects at the top of the SimpleBake panel")
            messages.append("If you want to select objects for baking in the viewport, turn off advanced object selection")
        ShowMessageBox(messages, "Errors occured", "ERROR")
        return False

    #Check everything selected (or target) is mesh
    for obj in objects:
        if obj.type != "MESH":
            messages.append(f"ERROR: Object '{obj.name}' is not mesh")
    if bpy.context.scene.SimpleBake_Props.selected_s2a and bpy.context.scene.SimpleBake_Props.targetobj != None:
        if bpy.context.scene.SimpleBake_Props.targetobj.type != "MESH":
            messages.append(f"ERROR: Object '{bpy.context.scene.SimpleBake_Props.targetobj.name}' (your target object) is not mesh")
    if bpy.context.scene.SimpleBake_Props.cycles_s2a and bpy.context.scene.SimpleBake_Props.targetobj_cycles != None:
        if bpy.context.scene.SimpleBake_Props.targetobj_cycles.type != "MESH":
            messages.append(f"ERROR: Object '{bpy.context.scene.SimpleBake_Props.targetobj_cycles.name}' (your target object) is not mesh")
    if len(messages) > 1:
        ShowMessageBox(messages, "Errors occured", "ERROR")
        return False

    #Output folder cannot be called textures
    if bpy.context.scene.SimpleBake_Props.saveFolder.lower() == "textures":
        messages.append(f"ERROR: Unfortunately, your save folder cannot be called \"textures\" for technical reasons. Please change the name to proceed.")
        ShowMessageBox(messages, "Errors occured", "ERROR")
        return False

    #Check object visibility
    obj_test_list = objects.copy()
    if bpy.context.scene.SimpleBake_Props.selected_s2a and bpy.context.scene.SimpleBake_Props.targetobj != None:
        obj_test_list.append(bpy.context.scene.SimpleBake_Props.targetobj)
    if bpy.context.scene.SimpleBake_Props.cycles_s2a and bpy.context.scene.SimpleBake_Props.targetobj_cycles != None:
        obj_test_list.append(bpy.context.scene.SimpleBake_Props.targetobj_cycles)

    for obj in obj_test_list:
        if obj.hide_viewport == True:
            messages.append(f"Object '{obj.name}' is hidden in viewport (monitor icon in outliner)")
        if obj.hide_render == True:
            messages.append(f"Object '{obj.name}' is hidden for render (camera icon in outliner)")
        if obj.hide_get() == True:
            messages.append(f"Object '{obj.name}' is hidden in viewport eye (eye icon in outliner)")
        if obj.hide_select == True:
            messages.append(f"Object '{obj.name}' is hidden for selection (arrow icon in outliner)")
    if len(messages)>0:
        ShowMessageBox(messages, "Errors occured", "ERROR")
        return False


    #None of the objects can have zero faces
    for obj in objects:
        if len(obj.data.polygons) < 1:
            messages.append(f"ERROR: Object '{obj.name}' has no faces")
    if bpy.context.scene.SimpleBake_Props.selected_s2a and bpy.context.scene.SimpleBake_Props.targetobj != None:
        obj = bpy.context.scene.SimpleBake_Props.targetobj
        if len(obj.data.polygons) < 1:
            messages.append(f"ERROR: Object '{obj.name}' has no faces")
    if bpy.context.scene.SimpleBake_Props.cycles_s2a and bpy.context.scene.SimpleBake_Props.targetobj_cycles != None:
        obj = bpy.context.scene.SimpleBake_Props.targetobj_cycles
        if len(obj.data.polygons) < 1:
            messages.append(f"ERROR: Object '{obj.name}' has no faces")
    if len(messages) > 1:
        ShowMessageBox(messages, "Errors occured", "ERROR")
        return False

    #Check for viewer nodes still connected
    for obj in objects:
        for slot in obj.material_slots:
            mat = slot.material
            if mat != None: #It'll get a placeholder material later on if it's none
                if check_for_connected_viewer_node(mat):
                    messages.append(f"ERROR: Material '{mat.name}' on object '{obj.name}' has a Viewer node connected to the Material Output")
                    ShowMessageBox(messages, "Errors occured", "ERROR")
                    return False
    #glTF
    if bpy.context.scene.SimpleBake_Props.createglTFnode:
        if bpy.context.scene.SimpleBake_Props.glTFselection == SimpleBakeConstants.AO and not bpy.context.scene.SimpleBake_Props.selected_ao:
            messages.append(f"ERROR: You have selected AO for glTF settings (in the 'Other Settings' section), but you aren't baking AO")
        if bpy.context.scene.SimpleBake_Props.glTFselection == SimpleBakeConstants.LIGHTMAP and not bpy.context.scene.SimpleBake_Props.selected_lightmap:
            messages.append(f"ERROR: You have selected Lightmap for glTF settings (in the 'Other Settings' section), but you aren't baking Lightmap")
    if len(messages)>1:
        ShowMessageBox(messages, "Errors occured", "ERROR")
        return False

    for obj in objects:
        if obj.name != cleanFileName(obj.name) and bpy.context.scene.SimpleBake_Props.saveExternal:
            prefs = bpy.context.preferences.addons[__package__].preferences
            image_name = prefs.img_name_format
            if "%OBJ%" in image_name:
                messages.append(f"ERROR: You are trying to save external images, but object with name \"{obj.name}\" contains invalid characters for saving externally.")


    if bpy.context.scene.SimpleBake_Props.mergedBake and bpy.context.scene.SimpleBake_Props.mergedBakeName == "":
        messages.append(f"ERROR: You are baking multiple objects to one texture set, but the texture name is blank")

    if (bpy.context.scene.SimpleBake_Props.mergedBakeName != cleanFileName(bpy.context.scene.SimpleBake_Props.mergedBakeName)) and bpy.context.scene.SimpleBake_Props.saveExternal:
        messages.append(f"ERROR: The texture name you inputted for baking multiple objects to one texture set (\"{bpy.context.scene.SimpleBake_Props.mergedBakeName}\") contains invalid characters for saving externally.")

    #Merged bake stuff
    if bpy.context.scene.SimpleBake_Props.mergedBake:
        if bpy.context.scene.SimpleBake_Props.selected_s2a: messages.append("You can't use the Bake Multiple Objects to One Texture Set option when baking to target")
        if bpy.context.scene.SimpleBake_Props.tex_per_mat: messages.append("You can't use the Bake Multiple Objects to One Texture Set option with the Texture Per Material option")

        if (bpy.context.scene.SimpleBake_Props.advancedobjectselection and len(bpy.context.scene.SimpleBake_Props.bakeobjs_advanced_list)<2) or ((not bpy.context.scene.SimpleBake_Props.advancedobjectselection) and len(bpy.context.selected_objects)<2):
            messages.append("You have selected the Multiple Objeccts to One Texture Set option (under Texture Settings) but you don't have multiple objects selected")


    #PBR Bake Checks - No S2A
    if bakemode == SimpleBakeConstants.PBR:

        for obj in objects:

            #Are UVs OK?
            if bpy.context.scene.SimpleBake_Props.newUVoption == False and len(obj.data.uv_layers) == 0:
                messages.append(f"ERROR: Object {obj.name} has no UVs, and you aren't generating new ones")
                continue

            #Are materials OK? Fix if not
            if not checkObjectValidMaterialConfig(obj):
                fix_invalid_material_config(obj)

            #Do all materials have valid PBR config?
            for slot in obj.material_slots:
                mat = slot.material
                result = checkMatsValidforPBR(mat)
                if len(result) > 0:
                    for node_name in result:
                        messages.append(f"ERROR: Node '{node_name}' in material '{mat.name}' on object '{obj.name}' is not valid for PBR bake. Principled BSDFs and/or Emission only!")

            # #TEMP###
            # import time
            # node_groups_present = True #Need to run at least once
            # op_running = False
            # while node_groups_present:
                # print("loop")
                # node_groups_present = False #Assume no node groups
                # for slot in obj.material_slots:
                    # mat = slot.material
                    # result = checkMatsValidforPBR(mat)
                    # if len(result) > 0:
                        # print("Found some node groups")
                        # node_groups_present = True
                        # #Try and fix if we aren't already
                        # if not op_running:
                            # op_running = True
                            # bpy.ops.object.simple_bake_popnodegroups()
                            # print("Operator just ran")
                            # time.sleep(3)

    #PBR Bake - S2A
    if bakemode == SimpleBakeConstants.PBRS2A:

        #These checkes are done on all selected objects (not just the target)-----------

        #Are materials OK? Fix if not
        for obj in objects:
            if not checkObjectValidMaterialConfig(obj):
                printmsg(f"{obj.name} has invalid material config - fixing")
                fix_invalid_material_config(obj)
        #Check the taget object too
        target = bpy.context.scene.SimpleBake_Props.targetobj
        if not checkObjectValidMaterialConfig(target):
            fix_invalid_material_config(target)


        #Do all materials have valid PBR config?
        if len(messages) == 0:
            for obj in objects:
                for slot in obj.material_slots:
                    mat = slot.material
                    result = checkMatsValidforPBR(mat)
                    if len(result) > 0:
                        for node_name in result:
                            messages.append(f"ERROR: Node '{node_name}' in material '{mat.name}' on object '{obj.name}' is not valid for PBR bake. Principled BSDFs and/or Emission only!")


        #-------------------------------------------------------------------------

        if len(messages) == 0:

            #From this point onward, we only care about the target object
            obj = bpy.context.scene.SimpleBake_Props.targetobj


            #Do we have a target object?
            if bpy.context.scene.SimpleBake_Props.targetobj == None:
                messages.append("ERROR: You are trying to bake to a target object with PBR Bake, but you have not selected one in the SimpleBake panel")
                ShowMessageBox(messages, "Errors occured", "ERROR")
                return False

            #Have we got more selected than just the target object?
            if len(objects) == 1 and objects[0] == obj:
                messages.append("ERROR: You are trying to bake to a target object with PBR Bake, but the only object you have selected is your target")
                ShowMessageBox(messages, "Errors occured", "ERROR")
                return False


            #Are UVs OK?
            if bpy.context.scene.SimpleBake_Props.newUVoption == False and len(obj.data.uv_layers) == 0:
                messages.append(f"ERROR: Object {obj.name} has no UVs, and you aren't generating new ones")
                ShowMessageBox(messages, "Errors occured", "ERROR")
                return False

            #All existing materials must use nodes
            for slot in obj.material_slots:
                if slot.material != None:
                    if not slot.material.use_nodes:
                        slot.material.use_nodes = True

                #Are materials OK? Fix if not
                if not checkObjectValidMaterialConfig(obj):
                    printmsg(f"{obj.name} (target) has invalid material config - fixing")
                    fix_invalid_material_config(obj)


    #Cycles Bake - No S2A
    if bakemode == SimpleBakeConstants.CYCLESBAKE and not bpy.context.scene.SimpleBake_Props.cycles_s2a:

        #First lets check for old users using the old method
        if bpy.context.scene.render.bake.use_selected_to_active:
            messages.append(f"ERROR: It looks like you are trying to bake selected to active. To do this with SimpleBake, use the option on the SimpleBake panel. You don’t need to worry about the setting in the Blender bake panel.")

        for obj in objects:

            #Are UVs OK?
            if not bpy.context.scene.SimpleBake_Props.tex_per_mat:
                if bpy.context.scene.SimpleBake_Props.newUVoption == False and len(obj.data.uv_layers) == 0:
                    messages.append(f"ERROR: Object {obj.name} has no UVs, and you aren't generating new ones")
                    ShowMessageBox(messages, "Errors occured", "ERROR")
                    return False
            else:
                if bpy.context.scene.SimpleBake_Props.expand_mat_uvs == False and len(obj.data.uv_layers) == 0:
                    messages.append(f"ERROR: Object {obj.name} has no UVs, and you aren't generating new ones")
                    ShowMessageBox(messages, "Errors occured", "ERROR")
                    return False


            #Are materials OK?
            if not checkObjectValidMaterialConfig(obj):
                fix_invalid_material_config(obj)


    #Cycles Bake - S2A
    if bakemode == SimpleBakeConstants.CYCLESBAKE and bpy.context.scene.SimpleBake_Props.cycles_s2a:


        #We only care about the target object
        obj = bpy.context.scene.SimpleBake_Props.targetobj_cycles

        #Do we actually have an active object?
        if obj == None:
            messages.append(f"ERROR: You are trying to bake selected to active with CyclesBake, but there is no active object")
            ShowMessageBox(messages, "Errors occured", "ERROR")
            return False

        #Have we got more selected than just the target object?
        elif len(objects) == 1 and objects[0] == obj:
            messages.append("ERROR: You are trying to bake selected to active with CyclesBake, but the only object you have selected is your active (target) object")
            ShowMessageBox(messages, "Errors occured", "ERROR")
            return False

        #Are UVs OK?
        elif bpy.context.scene.SimpleBake_Props.newUVoption == False and len(obj.data.uv_layers) == 0:
            messages.append(f"ERROR: Object {obj.name} has no UVs, and you aren't generating new ones")
            ShowMessageBox(messages, "Errors occured", "ERROR")
            return False


        if not checkObjectValidMaterialConfig(obj):
            fix_invalid_material_config(obj)


    #Specials Bake
    if bpy.context.scene.SimpleBake_Props.selected_col_vertex:

        if bakemode == SimpleBakeConstants.SPECIALS:
            for obj in objects:
                if len(obj.data.vertex_colors) == 0:
                    messages.append(f"You are trying to bake the active vertex colours, but object {obj.name} doesn't have vertex colours")
                    ShowMessageBox(messages, "Errors occured", "ERROR")
                    return False

        if bakemode == SimpleBakeConstants.SPECIALS_CYCLES_TARGET_ONLY:
            t = bpy.context.scene.SimpleBake_Props.targetobj_cycles
            if len(t.data.vertex_colors) == 0:
                messages.append(f"You are trying to bake the active vertex colours, but object {t.name} doesn't have vertex colours")
                ShowMessageBox(messages, "Errors occured", "ERROR")
                return False

        if bakemode == SimpleBakeConstants.SPECIALS_PBR_TARGET_ONLY:
            t = bpy.context.scene.SimpleBake_Props.targetobj
            if len(t.data.vertex_colors) == 0:
                messages.append(f"You are trying to bake the active vertex colours, but object {t.name} doesn't have vertex colours")
                ShowMessageBox(messages, "Errors occured", "ERROR")
                return False



    #Let's report back (if we haven't already)
    if len(messages) != 0:
        ShowMessageBox(messages, "Errors occured", "ERROR")
        return False
    else:
        #If we get here then everything looks good
        return True

     #CAGE OBJECT BROKEN? CHECK IF NOT NONE AND, IF NOT, FLIP THE SWITCH TO USE CAGE




def processUVS():

    original_uvs = {}
    current_bake_op = MasterOperation.current_bake_operation

    #Loops over UVs. If it has one, record the active UV map for later restoration
    #for obj in objects:
        #try:
            #original_uvs[obj.name] = obj.data.uv_layers.active.name
        #except AttributeError:
            #original_uvs[obj.name] = False

    #Generating new UVs


    #------------------NEW UVS ------------------------------------------------------------

    if bpy.context.scene.SimpleBake_Props.expand_mat_uvs:
        printmsg("We are expanding the UVs for each material into a new UV map")
        bpy.ops.object.select_all(action="DESELECT")

        for obj in current_bake_op.bake_objects:

            if("SimpleBake" in obj.data.uv_layers):
                obj.data.uv_layers.remove(obj.data.uv_layers["SimpleBake"])

            obj.data.uv_layers.new(name="SimpleBake")
            obj.data.uv_layers["SimpleBake"].active = True
            obj.select_set(state=True)

            selectOnlyThis(obj)

            bpy.ops.object.mode_set(mode='EDIT', toggle=False)
            #Unhide any geo that's hidden in edit mode or it'll cause issues.
            bpy.ops.mesh.reveal()


            i=0
            for slot in obj.material_slots:
                obj.active_material_index = i
                bpy.ops.mesh.select_all(action="DESELECT")
                bpy.ops.object.material_slot_select()
                bpy.ops.uv.smart_project(island_margin=bpy.context.scene.SimpleBake_Props.unwrapmargin)
                i += 1

            bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

    elif bpy.context.scene.SimpleBake_Props.newUVoption:
        printmsg("We are generating new UVs")
        #Slight hack. Single object must always be Smart UV Project (nothing else makes sense)
        if len(current_bake_op.bake_objects) < 2 or (bpy.context.scene.SimpleBake_Props.selected_s2a or bpy.context.scene.SimpleBake_Props.cycles_s2a):
            bpy.context.scene.SimpleBake_Props.newUVmethod = "SmartUVProject_Individual"

        #If we are using the combine method, the process is the same for merged and non-merged
        if bpy.context.scene.SimpleBake_Props.newUVmethod == "CombineExisting":
            printmsg("We are combining all existing UVs into one big atlas map")
            for obj in current_bake_op.bake_objects:
                #If there is already an old map, remove it
                if "SimpleBake_Old" in obj.data.uv_layers:
                    obj.data.uv_layers.remove(obj.data.uv_layers["SimpleBake_Old"])
                #If we already have a map called SimpleBake, rename it.
                if("SimpleBake" in obj.data.uv_layers):
                    obj.data.uv_layers["SimpleBake"].name = "SimpleBake_Old"
                #Create a new UVMap called SimpleBake based on whatever was active
                obj.data.uv_layers.new(name="SimpleBake")
                obj.data.uv_layers["SimpleBake"].active = True

            bpy.ops.object.select_all(action="DESELECT")
            for obj in current_bake_op.bake_objects:
                obj.select_set(state=True)

            #Check we have an active object:
            #Older versions of Blender (may not be set at all)
            try:
                bpy.context.active_object.type
            except AttributeError:
                #We do need an active object, or we can't enter edit mode
                bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]
            #Newer versions of Blender (always has an active object, but may not be mesh)
            if bpy.context.active_object.type != "MESH":
                bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]



            #With everything selected, pack into one big map
            bpy.ops.object.mode_set(mode="EDIT", toggle=False)
            #Unhide any geo that's hidden in edit mode or it'll cause issues.
            bpy.ops.mesh.reveal()

            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.select_all(action="SELECT")
            if bpy.context.scene.SimpleBake_Props.averageUVsize:
                bpy.ops.uv.average_islands_scale()
            bpy.ops.uv.pack_islands(rotate=True, margin=bpy.context.scene.SimpleBake_Props.uvpackmargin)
            bpy.ops.object.mode_set(mode="OBJECT", toggle=False)

        elif bpy.context.scene.SimpleBake_Props.newUVmethod == "SmartUVProject_Individual":
            printmsg("We are unwrapping each object individually with Smart UV Project")
            obs = []
            if bpy.context.scene.SimpleBake_Props.selected_s2a:
                objs = [current_bake_op.sb_target_object]
            elif bpy.context.scene.SimpleBake_Props.cycles_s2a:
                objs = [current_bake_op.sb_target_object_cycles]
            else:
                objs = current_bake_op.bake_objects

            for obj in objs:
                if("SimpleBake" in obj.data.uv_layers):
                    obj.data.uv_layers.remove(obj.data.uv_layers["SimpleBake"])
                obj.data.uv_layers.new(name="SimpleBake")
                obj.data.uv_layers["SimpleBake"].active = True
                #Will set active object
                selectOnlyThis(obj)

                #Blender 2.91 kindly breaks Smart UV Project in object mode so... yeah... thanks
                bpy.ops.object.mode_set(mode="EDIT", toggle=False)
                #Unhide any geo that's hidden in edit mode or it'll cause issues.
                bpy.ops.mesh.reveal()
                bpy.ops.mesh.select_all(action="SELECT")
                bpy.ops.mesh.reveal()

                bpy.ops.uv.smart_project(island_margin=bpy.context.scene.SimpleBake_Props.unwrapmargin)

                bpy.ops.object.mode_set(mode="OBJECT", toggle=False)

        elif bpy.context.scene.SimpleBake_Props.newUVmethod == "SmartUVProject_Atlas":
            printmsg("We are unwrapping all objects into an atlas map with Smart UV Project")
            bpy.ops.object.select_all(action="DESELECT")
            for obj in current_bake_op.bake_objects:
                if("SimpleBake" in obj.data.uv_layers):
                    obj.data.uv_layers.remove(obj.data.uv_layers["SimpleBake"])
                obj.data.uv_layers.new(name="SimpleBake")
                obj.data.uv_layers["SimpleBake"].active = True
                obj.select_set(state=True)
            #With everything now selected, UV project into one big map

            #Check we have an active object:
            #Older versions of Blender (may not be set at all)
            try:
                bpy.context.active_object.type
            except AttributeError:
                #We do need an active object, or we can't enter edit mode
                bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]
            #Newer versions of Blender (always has an active object, but may not be mesh)
            if bpy.context.active_object.type != "MESH":
                bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]


            bpy.ops.object.mode_set(mode="EDIT", toggle=False) #Enter edit mode
            #Unhide any geo that's hidden in edit mode or it'll cause issues.
            bpy.ops.mesh.reveal()

            bpy.ops.mesh.select_all(action="SELECT")
            o =  bpy.context.scene.tool_settings.use_uv_select_sync

            bpy.ops.uv.smart_project(island_margin=bpy.context.scene.SimpleBake_Props.unwrapmargin)

            #Pack islands one last time as the aspect ratio can throw it off
            bpy.context.scene.tool_settings.use_uv_select_sync = True
            bpy.ops.uv.pack_islands()

            bpy.ops.object.mode_set(mode="OBJECT", toggle=False)# Back to object mode, as it's expected later on


     #------------------END NEW UVS ------------------------------------------------------------

    else: #i.e. New UV Option was not selected
        printmsg("We are working with the existing UVs")

        if bpy.context.scene.SimpleBake_Props.prefer_existing_sbmap:
            printmsg("We are preferring existing UV maps called SimpleBake. Setting them to active")
            for obj in current_bake_op.bake_objects:
                if("SimpleBake" in obj.data.uv_layers):
                    obj.data.uv_layers["SimpleBake"].active = True


    #Before we finish, restore the original selected and active objects
    bpy.ops.object.select_all(action="DESELECT")
    for obj in current_bake_op.orig_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = current_bake_op.orig_active_object

    #Done
    return True

def restore_Original_UVs():

    current_bake_op = MasterOperation.current_bake_operation


    #First the bake objects
    for obj in current_bake_op.bake_objects:
        if MasterOperation.orig_UVs_dict[obj.name]: #Will be false if none
            original_uv = MasterOperation.orig_UVs_dict[obj.name]
            obj.data.uv_layers.active = obj.data.uv_layers[original_uv]

    #Now the target objects (if any)
    pbr_target = current_bake_op.sb_target_object
    if pbr_target != None:
        try:
            original_uv = MasterOperation.orig_UVs_dict[pbr_target.name]
            pbr_target.data.uv_layers.active = pbr_target.data.uv_layers[original_uv]
        except KeyError:
            printmsg(f"No original UV map found for {pbr_target.name}")

    cycles_target = current_bake_op.sb_target_object_cycles
    if cycles_target != None and MasterOperation.orig_UVs_dict[cycles_target.name] != None:
        try:
            original_uv = MasterOperation.orig_UVs_dict[cycles_target.name]
            cycles_target.data.uv_layers.active = cycles_target.data.uv_layers[original_uv]
        except KeyError:
            printmsg(f"No original UV map found for {cycles_target.name}")


def setupEmissionRunThrough(nodetree, m_output_node, thisbake, ismix=False):

    nodes = nodetree.nodes
    pnode = find_pnode(nodetree)

    #Create emission shader
    emissnode = nodes.new("ShaderNodeEmission")
    emissnode.label = "SimpleBake"

    #Connect to output
    if(ismix):
        #Find the existing mix node before we create a new one
        existing_m_node = find_mnode(nodetree)

        #Add a mix shader node and label it
        mnode = nodes.new("ShaderNodeMixShader")
        mnode.label = "SimpleBake"

        #Connect new mix node to the output
        fromsocket = mnode.outputs[0]
        tosocket = m_output_node.inputs[0]
        nodetree.links.new(fromsocket, tosocket)

        #Connect new emission node to the first mix slot (leaving second empty)
        fromsocket = emissnode.outputs[0]
        tosocket = mnode.inputs[1]
        nodetree.links.new(fromsocket, tosocket)

        #If there is one, plug the factor from the original mix node into our new mix node
        if(len(existing_m_node.inputs[0].links) > 0):
            fromsocket = existing_m_node.inputs[0].links[0].from_socket
            tosocket = mnode.inputs[0]
            nodetree.links.new(fromsocket, tosocket)
        #If no input, add a value node set to same as the mnode factor
        else:
            val = existing_m_node.inputs[0].default_value
            vnode = nodes.new("ShaderNodeValue")
            vnode.label = "SimpleBake"
            vnode.outputs[0].default_value = val

            fromsocket = vnode.outputs[0]
            tosocket = mnode.inputs[0]
            nodetree.links.new(fromsocket, tosocket)

    else:
        #Just connect our new emission to the output
        fromsocket = emissnode.outputs[0]
        tosocket = m_output_node.inputs[0]
        nodetree.links.new(fromsocket, tosocket)

    #Create dummy nodes for the socket for this bake if needed
    createdummynodes(nodetree, pnode, thisbake)

    #Connect whatever is in Principled Shader for this bakemode to the emission
    fromsocket = findSocketConnectedtoP(pnode, thisbake)
    tosocket = emissnode.inputs[0]
    nodetree.links.new(fromsocket, tosocket)

def find_pnode(nodetree):
    nodes = nodetree.nodes
    for node in nodes:
        if(node.type == "BSDF_PRINCIPLED"):
            return node
    #We never found it
    return False

def find_enode(nodetree):
    nodes = nodetree.nodes
    for node in nodes:
        if(node.type == "EMISSION"):
            return node
    #We never found it
    return False

def find_mnode(nodetree):
    nodes = nodetree.nodes
    for node in nodes:
        if(node.type == "MIX_SHADER"):
            return node
    #We never found it
    return False

def find_onode(nodetree):
    nodes = nodetree.nodes
    for node in nodes:
        if(node.type == "OUTPUT_MATERIAL"):
            return node
    #We never found it
    return False

def checkObjectValidMaterialConfig(obj):
    #Firstly, check it actually has material slots
    if len(obj.material_slots) == 0:
        return False

    #Check the material slots all have a material assigned
    for slot in obj.material_slots:
        if slot.material == None:
            return False

    #All materials must be using nodes
    for slot in obj.material_slots:
        if slot.material.use_nodes == False:
            return False
    #If we get here, everything looks good
    return True

# def getMergedSaveName():
    # import datetime
    # now = datetime.datetime.now()
    # timestring = now.strftime("%Y-%m-%d %H:%M")

    # if isBlendSaved():
        # fullpath = bpy.data.filepath
        # import os
        # pathelements = os.path.split(fullpath)
        # return pathelements[1].replace(".blend", "") + "-" + timestring
    # else:
        # return timestring

g_save_folder = ""
g_rel_save_folder = ""
def getSaveFolder(initialise = False, relative = False):

    global g_save_folder
    global g_rel_save_folder

    if initialise:
        fullpath = bpy.data.filepath
        pathelements = os.path.split(fullpath)
        workingdir = Path(pathelements[0])

        if bpy.context.scene.SimpleBake_Props.folderdatetime:
            from datetime import datetime
            now = datetime.now()
            d1 = now.strftime("%d%m%Y-%H%M")

            g_rel_save_folder = cleanFileName(bpy.context.scene.SimpleBake_Props.saveFolder) + f"_{d1}"
            savedir = workingdir / g_rel_save_folder

        else:
            g_rel_save_folder = cleanFileName(bpy.context.scene.SimpleBake_Props.saveFolder)
            savedir = workingdir / g_rel_save_folder

        g_save_folder = savedir
        return g_save_folder

    elif relative:
        #Called for just the relative reference
        return "//" + g_rel_save_folder

    else:
        #Called for full path, time to create folder
        try:
            os.mkdir(g_save_folder)
        except FileExistsError:
            pass

        return g_save_folder


def getFileName():
    fullpath = bpy.data.filepath
    pathelements = os.path.split(fullpath)
    return pathelements[1]

def checkAtCurrentVersion(v):
    v = v.replace(".","")
    v = int(v)

    #Grab the most recent version from my website
    from urllib.request import urlopen
    link = "http://www.toohey.co.uk/SimpleBake/currentversion3"

    try:
        f = urlopen(link, timeout=2)
        cver = f.read()
        cver = cver.decode("utf-8")
        cver = cver.replace(".","")
        cver = int(cver)

    except:
        printmsg("Unable to check for latest version of SimpleBake - are you online?")
        cver = v
        return "ERROR"

    if cver > v:
        return False
    else:
        return True



def getMatType(nodetree):
    if (find_pnode(nodetree) and find_mnode(nodetree)):
        return "MIX"
    elif(find_pnode(nodetree)):
        return "PURE_P"
    elif(find_enode(nodetree)):
        return "PURE_E"
    else:
        return "INVALID"

def cleanFileName(filename):
    keepcharacters = (' ','.','_','~',"-")
    return "".join(c for c in filename if c.isalnum() or c in keepcharacters).rstrip()


def saveExternal(image, baketype, obj):

    originally_float = image.is_float


    def apply_scene_col_settings(scene):
        scene.display_settings.display_device = bpy.context.scene.display_settings.display_device
        scene.view_settings.view_transform = bpy.context.scene.view_settings.view_transform
        scene.view_settings.look = bpy.context.scene.view_settings.look
        scene.view_settings.exposure = bpy.context.scene.view_settings.exposure
        scene.view_settings.gamma = bpy.context.scene.view_settings.gamma
        scene.sequencer_colorspace_settings.name = bpy.context.scene.sequencer_colorspace_settings.name


    current_bake_op = MasterOperation.current_bake_operation

    #Firstly, work out if we want denoising or not
    if current_bake_op.bake_mode == SimpleBakeConstants.CYCLESBAKE and bpy.context.scene.SimpleBake_Props.rundenoise:
        need_denoise = True
    elif current_bake_op.bake_mode in [SimpleBakeConstants.SPECIALS, SimpleBakeConstants.SPECIALS_CYCLES_TARGET_ONLY, \
        SimpleBakeConstants.SPECIALS_PBR_TARGET_ONLY] and \
        baketype == SimpleBakeConstants.LIGHTMAP and bpy.context.scene.SimpleBake_Props.selected_lightmap_denoise:
        need_denoise = True
    else:
        need_denoise = False

    #We want to control the bit depth, so we need a new scene
    scene = bpy.data.scenes.new('SimpleBakeTempScene')
    settings = scene.render.image_settings


    #Colour management settings
    dcm_opt = bpy.context.scene.SimpleBake_Props.selected_applycolmantocol

    if current_bake_op.bake_mode in [SimpleBakeConstants.PBR, SimpleBakeConstants.PBRS2A] and (baketype == "diffuse" or baketype == "emission") :
        if dcm_opt:
            printmsg("Applying colour management settings from current scene for PBR diffuse or emission")
            apply_scene_col_settings(scene)
        else:
            printmsg("Applying standard colour management for PBR diffuse or emission")
            scene.view_settings.view_transform = "Standard"

    elif current_bake_op.bake_mode in [SimpleBakeConstants.PBR, SimpleBakeConstants.PBRS2A]:
        printmsg("Applying raw colour space for PBR non-diffuse texture")
        scene.view_settings.view_transform = "Raw"
        scene.sequencer_colorspace_settings.name = "Non-Color"

    elif current_bake_op.bake_mode == SimpleBakeConstants.CYCLESBAKE:
        if bpy.context.scene.cycles.bake_type == "NORMAL":
            printmsg("Raw colour space for CyclesBake normal map")
            scene.view_settings.view_transform = "Raw"
            scene.sequencer_colorspace_settings.name = "Non-Color"

        elif bpy.context.scene.SimpleBake_Props.exportcyclescolspace:
            printmsg("Applying colour management settings from current scene for CyclesBake")
            apply_scene_col_settings(scene)
        else:
            #Just standard
            printmsg("Applying standard colour management for CyclesBake")
            scene.view_settings.view_transform = "Standard"

    elif baketype == SimpleBakeConstants.LIGHTMAP and bpy.context.scene.SimpleBake_Props.lightmap_apply_colman:
        printmsg("Applying colour management settings from current scene for Lightmap")
        apply_scene_col_settings(scene)


    elif current_bake_op.bake_mode in [SimpleBakeConstants.SPECIALS, SimpleBakeConstants.SPECIALS_PBR_TARGET_ONLY, SimpleBakeConstants.SPECIALS_CYCLES_TARGET_ONLY]:
        printmsg("Raw colour space for Specials")
        scene.view_settings.view_transform = "Raw"
        scene.sequencer_colorspace_settings.name = "Non-Color"


    else:
        printmsg("Applying standard colour management as a default")
        scene.view_settings.view_transform = "Standard"


    #Set the scene file format. Variable contains valid internal names for Blender file formats, so this is OK
    settings.file_format = bpy.context.scene.SimpleBake_Props.exportfileformat

    #Now, work out the file extension we need to use
    #Adjust file extension if needed (plus some extra options for EXR)
    if settings.file_format.lower() == "jpeg":
        file_extension = "jpg"
    elif settings.file_format.lower() == "tiff":
        file_extension = "tif"
    elif settings.file_format.lower() == "targa":
        file_extension = "tga"
    elif settings.file_format.lower() == "open_exr":
        file_extension = "exr"
    else:
        file_extension = settings.file_format.lower()


    #Set the bit depth we want (plus extra compression setting for exr
    if file_extension == "tga" or file_extension == "jpg":
        #Only one option
        settings.color_depth = '8'
    elif (baketype == "normal" or baketype == "cyclesbake" and bpy.context.scene.cycles.bake_type == "NORMAL") and file_extension != "exr":
        settings.color_depth = '16'
    elif bpy.context.scene.SimpleBake_Props.everything16bit and file_extension != "exr":
        settings.color_depth = '16'
    elif file_extension == "exr":
        settings.color_depth = '32'
        settings.exr_codec = "ZIP"
    else:
        #Should never really get here
        settings.color_depth = '8'


    #Work out path to save to, and remove previous file if there is one
    if bpy.context.scene.SimpleBake_Props.exportFolderPerObject and bpy.context.scene.SimpleBake_Props.mergedBake and bpy.context.scene.SimpleBake_Props.mergedBakeName != "":
        savepath = Path(str(getSaveFolder()) + "/" + bpy.context.scene.SimpleBake_Props.mergedBakeName + "/" + (cleanFileName(image.name) + "." + file_extension))

    elif bpy.context.scene.SimpleBake_Props.exportFolderPerObject and obj != None:
        savepath = Path(str(getSaveFolder()) + "/" + obj.name + "/" + (cleanFileName(image.name) + "." + file_extension))

    else:
        savepath = Path(str(getSaveFolder()) + "/" + (cleanFileName(image.name) + "." + file_extension))

    try:
        os.remove(str(savepath))
    except FileNotFoundError:
        pass

    #Set the image file format. Variable contains valid internal names for Blender file formats, so this is OK
    image.file_format = bpy.context.scene.SimpleBake_Props.exportfileformat


    #Time to save

    #First, some setup
    #Set the path to save to
    scene.render.filepath = str(savepath)

    #Use nodes as we will need the compositor no matter what
    scene.use_nodes = True

    #Prepare compositor nodes
    if "Render Layers" in scene.node_tree.nodes:
        scene.node_tree.nodes.remove(scene.node_tree.nodes["Render Layers"])

    composite_n = scene.node_tree.nodes["Composite"]
    img_n = scene.node_tree.nodes.new("CompositorNodeImage")
    img_n.image = image

    links = scene.node_tree.links

    #Set the output resolution of the scene to the texture size we are using
    scene.render.resolution_y = bpy.context.scene.SimpleBake_Props.outputheight
    scene.render.resolution_x = bpy.context.scene.SimpleBake_Props.outputwidth

    #No denoising, minimal setup
    if not need_denoise:

        links.new(img_n.outputs[0], composite_n.inputs[0])


    #If donoising, we need a compositing setup.
    else:
        denoise_n = scene.node_tree.nodes.new("CompositorNodeDenoise")

        links.new(denoise_n.outputs[0], composite_n.inputs[0])
        links.new(img_n.outputs[0], denoise_n.inputs[0])

    #In both cases render out
    bpy.ops.render.render(animation=False, write_still=True, use_viewport=False, scene=scene.name)

    #And remove scene
    bpy.data.scenes.remove(scene)


    #Now we have saved the image externally, update the internal reference to refer to the external file
    try:
        image.unpack(method="REMOVE")
    except:
        pass
    image.source = "FILE"
    #Let's use a relative path. Shouldn't matter in the end.
    if bpy.context.scene.SimpleBake_Props.exportFolderPerObject and bpy.context.scene.SimpleBake_Props.mergedBake and bpy.context.scene.SimpleBake_Props.mergedBakeName != "":
        image.filepath = str(getSaveFolder(relative=True)) +"/" + bpy.context.scene.SimpleBake_Props.mergedBakeName + "/" + image.name + "." + file_extension
    elif bpy.context.scene.SimpleBake_Props.exportFolderPerObject and obj != None:
        image.filepath = str(getSaveFolder(relative=True)) +"/" + obj.name + "/" + image.name + "." + file_extension
    else:
        image.filepath = str(getSaveFolder(relative=True)) +"/" + image.name + "." + file_extension


    #UDIMS
    if bpy.context.scene.SimpleBake_Props.uv_mode == "udims":

        #Is this the last one?
        if int(image.name[-3:]) == bpy.context.scene.SimpleBake_Props.udim_tiles:
            #This is the last one

            #We will need the tags later
            SB_objname = image["SB_objname"]
            SB_batch = image["SB_batch"]
            SB_globalmode = image["SB_globalmode"]
            SB_thisbake = image["SB_thisbake"]
            SB_mergedbakename = image["SB_mergedbakename"]
            SB_udims = image["SB_udims"]

            #Delete all images indiviudally baked UDIM tiles
            counter = int(image.name[-3:])
            imgrootname = image.name[0:-4]
            while counter > 0:
                bpy.data.images.remove(bpy.data.images[f"{imgrootname}{1000+ counter}"])
                counter = counter - 1


            #Get the current (final) UDIM number
            imgudimnum = str(savepath)[-8:-4]

            #There can only be one!
            prposed_img_name = savepath.parts[-1].replace(imgudimnum, "1001")
            if prposed_img_name in bpy.data.images:
                bpy.data.images.remove(bpy.data.images[prposed_img_name])


            #Open the UDIM image
            bpy.ops.image.open(filepath=str(savepath).replace(imgudimnum, "1001"), directory= str(getSaveFolder()) + "/", use_udim_detecting=True, relative_path=True)
            image = bpy.data.images[savepath.parts[-1].replace(imgudimnum, "1001")]

            #Set all the tags on the new image
            image["SB_objname"] = SB_objname
            image["SB_batch"] = SB_batch
            image["SB_globalmode"] = SB_globalmode
            image["SB_thisbake"] = SB_thisbake
            image["SB_mergedbakename"] = SB_mergedbakename
            image["SB_udims"] = SB_udims


    #Col management
    if file_extension == "exr":
        image.colorspace_settings.name = "Non-Color"

    elif originally_float and\
     (image["SB_thisbake"] == "diffuse" or\
     current_bake_op.bake_mode == SimpleBakeConstants.CYCLESBAKE and bpy.context.scene.cycles.bake_type in ["COMBINED", "DIFFUSE"]):
        image.colorspace_settings.name = "sRGB"


    return file_extension

def prepObjects(objs, baketype):


    current_bake_op = MasterOperation.current_bake_operation

    printmsg("Creating prepared object")
    #First we prepare objectes
    export_objects = []
    for obj in objs:


        #-------------Create the prepared mesh----------------------------------------

        #Object might have a truncated name. Should use this if it's there
        objname = trunc_if_needed(obj.name)

        new_obj = obj.copy()
        new_obj.data = obj.data.copy()
        new_obj["SB_createdfrom"] = obj.name

        #Unless we are baking tex per mat OR we want to preserve the materials, clear all materials
        if bpy.context.scene.SimpleBake_Props.preserve_materials:
            pass

        else:
            if not bpy.context.scene.SimpleBake_Props.tex_per_mat:
                new_obj.data.materials.clear()


        #Set the name of our new object
        new_obj.name = objname + "_SimpleBake"


        #Create a collection for our baked objects if it doesn't exist
        if "SimpleBake_Bakes" not in bpy.data.collections:
            c = bpy.data.collections.new("SimpleBake_Bakes")
            bpy.context.scene.collection.children.link(c)
            try:
                c.color_tag = "COLOR_05"
            except AttributeError:
                pass


        #Make sure it's visible and enabled for current view laywer or it screws things up
        bpy.context.view_layer.layer_collection.children["SimpleBake_Bakes"].exclude = False
        bpy.context.view_layer.layer_collection.children["SimpleBake_Bakes"].hide_viewport = False
        c = bpy.data.collections["SimpleBake_Bakes"]


        #Link object to our new collection
        c.objects.link(new_obj)


        #Append this object to the export list
        export_objects.append(new_obj)


        #---------------------------------UVS--------------------------------------

        uvlayers = new_obj.data.uv_layers
        #If we generated new UVs, it will be called "SimpleBake" and we are using that. End of.
        #Same if we are being called for Sketchfab upload, and last bake used new UVs
        if bpy.context.scene.SimpleBake_Props.newUVoption:
            pass

        #If there is an existing map called SimpleBake, and we are preferring it, use that
        elif ("SimpleBake" in uvlayers) and bpy.context.scene.SimpleBake_Props.prefer_existing_sbmap:
            pass

        #Even if we are not preferring it, if there is just one map called SimpleBake, we are using that
        elif ("SimpleBake" in uvlayers) and len(uvlayers) <2:
            pass

        #If there is an existing map called SimpleBake, and we are not preferring it, it has to go
        #Active map becommes SimpleBake
        elif ("SimpleBake" in uvlayers) and not bpy.context.scene.SimpleBake_Props.prefer_existing_sbmap:
            uvlayers.remove(uvlayers["SimpleBake"])
            active_layer = uvlayers.active
            active_layer.name = "SimpleBake"

        #Finally, if none of the above apply, we are just using the active map
        #Active map becommes SimpleBake
        else:
            active_layer = uvlayers.active
            active_layer.name = "SimpleBake"

        #In all cases, we can now delete everything other than SimpleBake
        deletelist = []
        for uvlayer in uvlayers:
            if (uvlayer.name != "SimpleBake"):
                deletelist.append(uvlayer.name)
        for uvname in deletelist:
            uvlayers.remove(uvlayers[uvname])

    #---------------------------------END UVS--------------------------------------

        #Tex per mat will preserve existing materials
        if not bpy.context.scene.SimpleBake_Props.tex_per_mat:

            if bpy.context.scene.SimpleBake_Props.preserve_materials:
                #Copy existing materials, and rename them
                for slot in new_obj.material_slots:
                    mat_name = slot.material.name

                    mat = slot.material
                    new_mat = mat.copy()

                    #Empty all materials of all nodes
                    nodes = new_mat.node_tree.nodes
                    for node in nodes:
                        nodes.remove(node)

                    new_mat.name = mat_name + "_baked"

                    slot.material = new_mat

            else:

                #Create a new material
                #If not mergedbake, call it same as object + batchname + baked
                if not bpy.context.scene.SimpleBake_Props.mergedBake:
                    mat = bpy.data.materials.get(objname + "_" + bpy.context.scene.SimpleBake_Props.batchName + "_baked")
                    if mat is None:
                        mat = bpy.data.materials.new(name=objname + "_" + bpy.context.scene.SimpleBake_Props.batchName +"_baked")
                #For merged bake, it's the user specified name + batchname.
                else:
                    mat = bpy.data.materials.get(bpy.context.scene.SimpleBake_Props.mergedBakeName + "_" + bpy.context.scene.SimpleBake_Props.batchName)
                    if mat is None:
                        mat = bpy.data.materials.new(bpy.context.scene.SimpleBake_Props.mergedBakeName + "_" + bpy.context.scene.SimpleBake_Props.batchName)

                # Assign it to object
                mat.use_nodes = True
                new_obj.data.materials.append(mat)


    #Tex per material should have no material setup (as prepare objects is not an option)
    if not bpy.context.scene.SimpleBake_Props.tex_per_mat:

        #Set up the materials for each object
        for obj in export_objects:


            if bpy.context.scene.SimpleBake_Props.preserve_materials: #Object will have multiple materials
                for slot in obj.material_slots:
                    mat = slot.material
                    nodetree = mat.node_tree

                    if(baketype in {SimpleBakeConstants.PBR, SimpleBakeConstants.PBRS2A}):
                        material_setup.create_principled_setup(nodetree, obj)
                    if baketype == SimpleBakeConstants.CYCLESBAKE:
                        material_setup.create_cyclesbake_setup(nodetree, obj)
            else: #Should only have one material
                mat = obj.material_slots[0].material
                nodetree = mat.node_tree

                if(baketype in {SimpleBakeConstants.PBR, SimpleBakeConstants.PBRS2A}):
                    material_setup.create_principled_setup(nodetree, obj)
                if baketype == SimpleBakeConstants.CYCLESBAKE:
                    material_setup.create_cyclesbake_setup(nodetree, obj)

            #Change object name to avoid collisions
            obj.name = obj.name.replace("_SimpleBake", "_Baked")


    #Deselect all objects
    bpy.ops.object.select_all(action="DESELECT")


    #If we are exporting to FBX, do that now
    if(bpy.context.scene.SimpleBake_Props.saveObj):
        mod_option = bpy.context.scene.SimpleBake_Props.applymodsonmeshexport
        applytransform_option = bpy.context.scene.SimpleBake_Props.applytransformation

        #Single FBX
        if not bpy.context.scene.SimpleBake_Props.exportFolderPerObject:
            for obj in export_objects:
                obj.select_set(state=True)

            #Use the file name that the user defined
            filepath = getSaveFolder() / (cleanFileName(bpy.context.scene.SimpleBake_Props.fbxName) + ".fbx")
            bpy.ops.export_scene.fbx(filepath=str(filepath), check_existing=False, use_selection=True,
                use_mesh_modifiers=mod_option, bake_space_transform=applytransform_option, path_mode="STRIP")

        #Folder per FBX
        else:
            if bpy.context.scene.SimpleBake_Props.mergedBake:
                bpy.ops.object.select_all(action="DESELECT")
                for obj in export_objects:
                    obj.select_set(state=True)
                filepath = getSaveFolder() / (cleanFileName(bpy.context.scene.SimpleBake_Props.mergedBakeName)) / (cleanFileName(bpy.context.scene.SimpleBake_Props.mergedBakeName) + ".fbx")
                bpy.ops.export_scene.fbx(filepath=str(filepath), check_existing=False, use_selection=True,
                    use_mesh_modifiers=mod_option, path_mode="STRIP", bake_space_transform=applytransform_option)

            else:
                for obj in export_objects:
                    bpy.ops.object.select_all(action="DESELECT")
                    obj.select_set(state=True)
                    filepath = getSaveFolder() / obj.name.replace("_Baked", "") / (obj.name.replace("_Baked", "") + ".fbx")
                    bpy.ops.export_scene.fbx(filepath=str(filepath), check_existing=False, use_selection=True,
                        use_mesh_modifiers=mod_option, path_mode="STRIP", bake_space_transform=applytransform_option)


    if (not bpy.context.scene.SimpleBake_Props.prepmesh) and (not "--background" in sys.argv):
        #Deleted duplicated objects
        for obj in export_objects:
            bpy.data.objects.remove(obj)
    #Add the created objects to the bake operation list to keep track of them
    else:
        for obj in export_objects:
            MasterOperation.prepared_mesh_objects.append(obj)


def selectOnlyThis(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(state=True)
    bpy.context.view_layer.objects.active = obj


def setup_pure_p_material(nodetree, thisbake):
    #Create dummy nodes as needed
    createdummynodes(nodetree, thisbake)

    #Create emission shader
    nodes = nodetree.nodes
    m_output_node = find_onode(nodetree)
    loc = m_output_node.location

    #Create an emission shader
    emissnode = nodes.new("ShaderNodeEmission")
    emissnode.label = "SimpleBake"
    emissnode.location = loc
    emissnode.location.y = emissnode.location.y + 200

    #Connect our new emission to the output
    fromsocket = emissnode.outputs[0]
    tosocket = m_output_node.inputs[0]
    nodetree.links.new(fromsocket, tosocket)

    #Connect whatever is in Principled Shader for this bakemode to the emission
    fromsocket = findSocketConnectedtoP(find_pnode(nodetree), thisbake)
    tosocket = emissnode.inputs[0]
    nodetree.links.new(fromsocket, tosocket)

def setup_pure_e_material(nodetree, thisbake):
    #If baking something other than emission, mute the emission modes so they don't contaiminate our bake
    if thisbake != "Emission":
        nodes = nodetree.nodes
        for node in nodes:
            if node.type == "EMISSION":
                node.mute = True
                node.label = "SimpleBakeMuted"

def setup_mix_material(nodetree, thisbake):
    #No need to mute emission nodes. They are automuted by setting the RGBMix to black
    nodes = nodetree.nodes

    #Create dummy nodes as needed
    createdummynodes(nodetree, thisbake)

    #For every mix shader, create a mixrgb above it
    #Also connect the factor input to the same thing
    created_mix_nodes = {}
    for node in nodes:
        if node.type == "MIX_SHADER":
            loc = node.location
            rgbmix = nodetree.nodes.new("ShaderNodeMixRGB")
            rgbmix.label = "SimpleBake"
            rgbmix.location = loc
            rgbmix.location.y = rgbmix.location.y + 200


            #If there is one, plug the factor from the original mix node into our new mix node
            if(len(node.inputs[0].links) > 0):
                fromsocket = node.inputs[0].links[0].from_socket
                tosocket = rgbmix.inputs["Fac"]
                nodetree.links.new(fromsocket, tosocket)
            #If no input, add a value node set to same as the mnode factor
            else:
                val = node.inputs[0].default_value
                vnode = nodes.new("ShaderNodeValue")
                vnode.label = "SimpleBake"
                vnode.outputs[0].default_value = val

                fromsocket = vnode.outputs[0]
                tosocket = rgbmix.inputs[0]
                nodetree.links.new(fromsocket, tosocket)

            #Keep a dictionary with paired shader mix node
            created_mix_nodes[node.name] = rgbmix.name

    #Loop over the RGBMix nodes that we created
    for node in created_mix_nodes:
        mshader = nodes[node]
        rgb = nodes[created_mix_nodes[node]]

        #Mshader - Socket 1
        #First, check if there is anything plugged in at all
        if len(mshader.inputs[1].links) > 0:
            fromnode = mshader.inputs[1].links[0].from_node

            if fromnode.type == "BSDF_PRINCIPLED":
                #Get the socket we are looking for, and plug it into RGB socket 1
                fromsocket = findSocketConnectedtoP(fromnode, thisbake)
                nodetree.links.new(fromsocket, rgb.inputs[1])
            elif fromnode.type == "MIX_SHADER":
                #If it's a mix shader on the other end, connect the equivilent RGB node
                #Get the RGB node for that mshader
                fromrgb = nodes[created_mix_nodes[fromnode.name]]
                fromsocket = fromrgb.outputs[0]
                nodetree.links.new(fromsocket, rgb.inputs[1])
            elif fromnode.type == "EMISSION":
                #Set this input to black
                rgb.inputs[1].default_value = (0.0, 0.0, 0.0, 1)
            else:
                printmsg("Error, invalid node config")
        else:
            rgb.inputs[1].default_value = (0.0, 0.0, 0.0, 1)

        #Mshader - Socket 2
        if len(mshader.inputs[2].links) > 0:
            fromnode = mshader.inputs[2].links[0].from_node
            if fromnode.type == "BSDF_PRINCIPLED":
                #Get the socket we are looking for, and plug it into RGB socket 2
                fromsocket = findSocketConnectedtoP(fromnode, thisbake)
                nodetree.links.new(fromsocket, rgb.inputs[2])
            elif fromnode.type == "MIX_SHADER":
                #If it's a mix shader on the other end, connect the equivilent RGB node
                #Get the RGB node for that mshader
                fromrgb = nodes[created_mix_nodes[fromnode.name]]
                fromsocket = fromrgb.outputs[0]
                nodetree.links.new(fromsocket, rgb.inputs[2])
            elif fromnode.type == "EMISSION":
                #Set this input to black
                rgb.inputs[2].default_value = (0.0, 0.0, 0.0, 1)
            else:
                printmsg("Error, invalid node config")
        else:
            rgb.inputs[2].default_value = (0.0, 0.0, 0.0, 1)

    #Find the output node with location
    m_output_node = find_onode(nodetree)
    loc = m_output_node.location

    #Create an emission shader
    emissnode = nodes.new("ShaderNodeEmission")
    emissnode.label = "SimpleBake"
    emissnode.location = loc
    emissnode.location.y = emissnode.location.y + 200

    #Get the original mix node that was connected to the output node
    socket = m_output_node.inputs["Surface"]
    fromnode = socket.links[0].from_node

    #Find our created mix node that is paired with it
    rgbmix = nodes[created_mix_nodes[fromnode.name]]

    #Plug rgbmix into emission
    nodetree.links.new(rgbmix.outputs[0], emissnode.inputs[0])

    #Plug emission into output
    nodetree.links.new(emissnode.outputs[0], m_output_node.inputs[0])

def is_image_single_colour(img):
    pixels = img.pixels[:]
    if not pixels.count(pixels[0]) == len(pixels)/4:
        return False
    if not pixels.count(pixels[1]) == len(pixels)/4:
        return False
    if not pixels.count(pixels[2]) == len(pixels)/4:
        return False
    if not pixels.count(pixels[3]) == len(pixels)/4:
        return False

    return True


#----------------Specials---------------------------------
def import_needed_specials_materials(justcount = False):
    ordered_specials = []
    path = os.path.dirname(__file__) + "/materials/materials.blend\\Material\\"
    if(bpy.context.scene.SimpleBake_Props.selected_thickness):
        if "SimpleBake_"+SimpleBakeConstants.THICKNESS not in bpy.data.materials:
            material_name = "SimpleBake_"+SimpleBakeConstants.THICKNESS
            if not justcount:
                bpy.ops.wm.append(filename=material_name, directory=path)
            ordered_specials.append(SimpleBakeConstants.THICKNESS)
        else:
            ordered_specials.append(SimpleBakeConstants.THICKNESS)

    if(bpy.context.scene.SimpleBake_Props.selected_ao):
        if "SimpleBake_"+SimpleBakeConstants.AO not in bpy.data.materials:
            material_name = "SimpleBake_"+SimpleBakeConstants.AO
            if not justcount:
                bpy.ops.wm.append(filename=material_name, directory=path)
            ordered_specials.append(SimpleBakeConstants.AO)
        else:
            ordered_specials.append(SimpleBakeConstants.AO)

    if(bpy.context.scene.SimpleBake_Props.selected_curvature):
        if "SimpleBake"+SimpleBakeConstants.CURVATURE not in bpy.data.materials:
            material_name = "SimpleBake_"+SimpleBakeConstants.CURVATURE
            if not justcount:
                bpy.ops.wm.append(filename=material_name, directory=path)
            ordered_specials.append(SimpleBakeConstants.CURVATURE)
        else:
            ordered_specials.append(SimpleBakeConstants.CURVATURE)

    if(bpy.context.scene.SimpleBake_Props.selected_lightmap):
        if "SimpleBake_"+SimpleBakeConstants.LIGHTMAP not in bpy.data.materials:
            material_name = "SimpleBake_"+SimpleBakeConstants.LIGHTMAP
            if not justcount:
                bpy.ops.wm.append(filename=material_name, directory=path)
            ordered_specials.append(SimpleBakeConstants.LIGHTMAP)
        else:
            ordered_specials.append(SimpleBakeConstants.LIGHTMAP)


    #return the list of specials
    if justcount:
        return len(ordered_specials)
    else:
        return ordered_specials



#------------Long Name Truncation-----------------------
trunc_num = 0
trunc_dict = {}
def trunc_if_needed(objectname):

    global trunc_num
    global trunc_dict

    #If we already truncated this, just return that
    if objectname in trunc_dict:
        printmsg(f"Object name {objectname} was previously truncated. Returning that.")
        return trunc_dict[objectname]

    #If not, let's see if we have to truncate it
    elif len(objectname) >= 38:
        printmsg(f"Object name {objectname} is too long and will be truncated")
        trunc_num += 1
        truncdobjectname = objectname[0:34] + "~" + str(trunc_num)
        trunc_dict[objectname] = truncdobjectname
        return truncdobjectname

    #If nothing else, just return the original name
    else:
        return objectname

def untrunc_if_needed(objectname):

    global trunc_num
    global trunc_dict

    for t in trunc_dict:
        if trunc_dict[t] == objectname:
            printmsg(f"Returning untruncated value {t}")
            return t

    return objectname

def ShowMessageBox(messageitems_list, title, icon = 'INFO'):

    def draw(self, context):
        for m in messageitems_list:
            self.layout.label(text=m)

    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)


#---------------Bake Progress--------------------------------------------
def write_bake_progress(current_operation, total_operations):
    progress = int((current_operation / total_operations) * 100)


    t = Path(tempfile.gettempdir())
    t = t / f"SimpleBake_Bgbake_{os.getpid()}"

    with open(str(t), "w") as progfile:
        progfile.write(str(progress))


#---------------End Bake Progress--------------------------------------------


def diff(li1, li2):
    li_dif = [i for i in li1 + li2 if i not in li1 or i not in li2]
    return li_dif


#--------------UDIMS-------------------------------------


#Dict obj name to tile
currentUDIMtile = {}

def UDIM_focustile(obj,desiredUDIMtile):

    orig_active_object = bpy.context.active_object
    orig_selected_objects = bpy.context.selected_objects

    global currentUDIMtile


    selectOnlyThis(obj)
    bpy.ops.object.editmode_toggle()

    printmsg(f"Shifting UDIM focus tile: Object: {obj.name} Tile: {desiredUDIMtile}")


    import bmesh

    if obj.name not in currentUDIMtile:
        #Must be first time. Set to 0
        currentUDIMtile[obj.name] = 0

    #Difference between desired and current
    tilediff =  desiredUDIMtile - currentUDIMtile[obj.name]

    me = obj.data
    bm = bmesh.new()
    bm = bmesh.from_edit_mesh(me)

    uv_layer = bm.loops.layers.uv.verify()
    #bm.faces.layers.tex.verify()  # currently blender needs both layers.

    # scale UVs x2
    for f in bm.faces:
        for l in f.loops:
            l[uv_layer].uv[0] -= tilediff

    #bm.to_mesh(me)
    me.update()

    currentUDIMtile[obj.name] = desiredUDIMtile

    bpy.ops.object.editmode_toggle()

    #Restore the original selected and active objects before we leave
    for o in orig_selected_objects:
        o.select_set(state=True)
    bpy.context.view_layer.objects.active = orig_active_object

#ZERO Indexed
#UDIM_FocusTile(bpy.data.objects[1],0)


past_items_dict = {}
def spot_new_items(initialise=True, item_type="images"):

    global past_items_dict

    if item_type == "images":
        source = bpy.data.images
    elif item_type == "objects":
        source = bpy.data.objects
    elif item_type == "collections":
        source = bpy.data.collections


    #First run
    if initialise:
        #Set to empty list for this item type
        past_items_dict[item_type] = []

        for source_item in source:
            past_items_dict[item_type].append(source_item.name)
        return True

    else:
        #Get the list of items for this item type from the dict
        past_items_list = past_items_dict[item_type]
        new_item_list_names = []

        for source_item in source:
            if source_item.name not in past_items_list:
                new_item_list_names.append(source_item.name)
        return new_item_list_names


def check_for_connected_viewer_node(mat):

    mat.use_nodes = True

    node_tree = mat.node_tree
    nodes = node_tree.nodes
    onode = find_onode(node_tree)

    #Get all nodes with label "Viewer"
    viewer_nodes = [n for n in nodes if n.label == "Viewer"]

    #Check if any of those viewer nodes are connected to the Material Output
    for n in viewer_nodes:
        if n.name == onode.inputs[0].links[0].from_node.name:
            return True

    return False


def checkMatsValidforPBR(mat):

    nodes = mat.node_tree.nodes

    valid = True
    invalid_node_names = []

    for node in nodes:
        if len(node.outputs) > 0:
            if node.outputs[0].type == "SHADER" and not (node.bl_idname == "ShaderNodeBsdfPrincipled" or node.bl_idname == "ShaderNodeMixShader" or node.bl_idname == "ShaderNodeEmission"):
                #But is it actually connected to anything?
                if len(node.outputs[0].links) >0:
                    invalid_node_names.append(node.name)


    return invalid_node_names


def advanced_object_selection_to_list():
    objs = []
    for li in bpy.context.scene.SimpleBake_Props.bakeobjs_advanced_list:
        objs.append(li.obj_point)

    return objs

def update_advanced_object_list():

    my_list = bpy.context.scene.SimpleBake_Props.bakeobjs_advanced_list

    gone = []
    for li in my_list:
        #Is it empty?
        if li.obj_point == None:
            gone.append(li.name)

        #It it not in use anywhere else?
        elif len(li.obj_point.users_scene) < 1:
            gone.append(li.name)

    for g in gone:
        my_list.remove(my_list.find(g))
        #We were the only user (presumably)
        if g in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[g])

def deselect_all_not_mesh():
    import bpy

    for obj in bpy.context.selected_objects:
        if obj.type != "MESH":
             obj.select_set(False)

    #Do we still have an active object?
    if bpy.context.active_object == None:
        #Pick arbitary
        bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]

def fix_invalid_material_config(obj):

    if "SimpleBake_Placeholder" in bpy.data.materials:
        mat = bpy.data.materials["SimpleBake_Placeholder"]
    else:
        mat = bpy.data.materials.new("SimpleBake_Placeholder")
        bpy.data.materials["SimpleBake_Placeholder"].use_nodes = True

    # Assign it to object
    if len(obj.material_slots) > 0:
        #Assign it to every empty slot
        for slot in obj.material_slots:
            if slot.material == None:
                slot.material = mat
    else:
        # no slots
        obj.data.materials.append(mat)

    #All materials must use nodes
    for slot in obj.material_slots:
        mat = slot.material
        if mat.use_nodes == False:
            mat.use_nodes = True

    return True


def check_col_distance(r,g,b, min_diff):

    current_bake_op = MasterOperation.current_bake_operation
    used_cols = current_bake_op.used_cols


    #printmsg(f"Entering check col with {len(used_cols)} in the used_cols list")
    #printmsg(f"Looking at {r} and {g} and {b}")

    #Very first col gets a free pass
    if len(used_cols) < 1:
        #printmsg("First - free pass")
        current_bake_op.used_cols.append([r,g,b])
        return True

    ok = True


    for uc in used_cols:
        #printmsg(f"UC is {uc[0]} and {uc[1]} and {uc[2]}")
        if round(abs(r - uc[0]),1) > min_diff or round(abs(g - uc[1]), 1) > min_diff or round(abs(b - uc[2]),1) > min_diff:
            #printmsg(f"Distance was {round(abs(r - uc[0]),1)} and {round(abs(g - uc[1]),1)} and {round(abs(b - uc[2]),1)}")
            pass # We passed, don't change the value
        else:
            ok = False #At least one rgb was too close

    #If we OKd this. Add it to the used cols list
    if ok:
        #printmsg(f"Result was ok, adding col to list (now {len(current_bake_op.used_cols)}")
        current_bake_op.used_cols.append([r,g,b])
    else:
        pass
        #printmsg("Failed there was a colour too close")

    #Return result either way
    return ok

def sacle_image_if_needed(img):

    printmsg("Scaling images if needed")

    context = bpy.context
    width = img.size[0]
    height = img.size[1]

    proposed_width = bpy.context.scene.SimpleBake_Props.outputwidth
    proposed_height = bpy.context.scene.SimpleBake_Props.outputheight

    if width != proposed_width or height != proposed_height:
        img.scale(proposed_width, proposed_height)

def set_image_internal_col_space(image, thisbake):

    if thisbake == SimpleBakeConstants.CYCLESBAKE:
        if bpy.context.scene.cycles.bake_type not in ["COMBINED", "DIFFUSE"]:
            image.colorspace_settings.name = "Non-Color"

    else: #PBR
        if thisbake != "diffuse" and thisbake != "emission":
            image.colorspace_settings.name = "Non-Color"

def check_for_render_inactive_modifiers():

    #This is hacky. A better way to do this needs to be found
    advancedobj = bpy.context.scene.SimpleBake_Props.advancedobjectselection
    if advancedobj:
        objects = advanced_object_selection_to_list()
    else:
        objects = bpy.context.selected_objects

    for obj in objects:
        for mod in obj.modifiers:
            if mod.show_render and not mod.show_viewport:
                return True
    if bpy.context.scene.SimpleBake_Props.selected_s2a and bpy.context.scene.SimpleBake_Props.targetobj != None:
        for mod in bpy.context.scene.SimpleBake_Props.targetobj.modifiers:
            if mod.show_render and not mod.show_viewport:
                return True

    if bpy.context.scene.SimpleBake_Props.cycles_s2a and bpy.context.scene.SimpleBake_Props.targetobj_cycles != None:
        for mod in bpy.context.scene.SimpleBake_Props.targetobj_cycles.modifiers:
            if mod.show_render and not mod.show_viewport:
                return True

    return False

def check_for_viewport_inactive_modifiers():

    #This is hacky. A better way to do this needs to be found
    advancedobj = bpy.context.scene.SimpleBake_Props.advancedobjectselection
    if advancedobj:
        objects = advanced_object_selection_to_list()
    else:
        objects = bpy.context.selected_objects

    for obj in objects:
        for mod in obj.modifiers:
            if mod.show_viewport and not mod.show_render:
                return True
    if bpy.context.scene.SimpleBake_Props.selected_s2a and bpy.context.scene.SimpleBake_Props.targetobj != None:
        for mod in bpy.context.scene.SimpleBake_Props.targetobj.modifiers:
            if mod.show_viewport and not mod.show_render:
                return True

    if bpy.context.scene.SimpleBake_Props.cycles_s2a and bpy.context.scene.SimpleBake_Props.targetobj_cycles != None:
        for mod in bpy.context.scene.SimpleBake_Props.targetobj_cycles.modifiers:
            if mod.show_viewport and not mod.show_render:
                return True

    return False


def any_specials():

    if bpy.context.scene.SimpleBake_Props.selected_col_mats: return True
    if bpy.context.scene.SimpleBake_Props.selected_col_vertex: return True
    if bpy.context.scene.SimpleBake_Props.selected_ao: return True
    if bpy.context.scene.SimpleBake_Props.selected_thickness: return True
    if bpy.context.scene.SimpleBake_Props.selected_curvature: return True
    if bpy.context.scene.SimpleBake_Props.selected_lightmap: return True

    return False


def load_previews():
    pcoll = bpy.utils.previews.new()
    my_icons_dir = Path(os.path.dirname(__file__)) / "icons"
    pcoll.load("SimpleBake_Logo", str(my_icons_dir / "logo.png"), 'IMAGE')


    SimpleBake_Previews.pcoll = pcoll

def auto_set_bake_margin():

    context = bpy.context

    multiplier = 4

    current_width = context.scene.SimpleBake_Props.imgwidth
    margin = (current_width / 1024) * multiplier
    margin = round(margin, 0)

    context.scene.render.bake.margin = margin


    return True

