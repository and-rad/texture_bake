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
from .bake_operation import BakeOperation, MasterOperation, TextureBakeConstants
from .bake_operation import bakes_to_list


# Global variables
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

def print_msg(msg):
    print(f"TEXTUREBAKE: {msg}")

def does_object_have_bakes(obj):
    for img in bpy.data.images:
        return "SB_objname" in img # SB_objname is always set. Even for merged_bake


def gen_image_name(obj_name, baketype):
    current_bake_op = MasterOperation.current_bake_operation
    prefs = bpy.context.preferences.addons[__package__].preferences
    image_name = prefs.img_name_format

    # The easy ones
    image_name = image_name.replace("%OBJ%", obj_name)
    image_name = image_name.replace("%BATCH%", bpy.context.scene.TextureBake_Props.batch_name)
    image_name = image_name.replace("%BAKEMODE%", current_bake_op.bake_mode)

    # The hard ones
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
    elif baketype == TextureBakeConstants.AO:
        image_name = image_name.replace("%BAKETYPE%", prefs.ao_alias)
    elif baketype == TextureBakeConstants.LIGHTMAP:
        image_name = image_name.replace("%BAKETYPE%", prefs.lightmap_alias)
    elif baketype == TextureBakeConstants.COLORID:
        image_name = image_name.replace("%BAKETYPE%", prefs.colid_alias)
    elif baketype == TextureBakeConstants.CURVATURE:
        image_name = image_name.replace("%BAKETYPE%", prefs.curvature_alias)
    elif baketype == TextureBakeConstants.THICKNESS:
        image_name = image_name.replace("%BAKETYPE%", prefs.thickness_alias)
    elif baketype == TextureBakeConstants.VERTEXCOL:
        image_name = image_name.replace("%BAKETYPE%", prefs.vertexcol_alias)
    elif baketype == "sss":
        image_name = image_name.replace("%BAKETYPE%", prefs.sss_alias)
    elif baketype == "ssscol":
        image_name = image_name.replace("%BAKETYPE%", prefs.ssscol_alias)
    else:
        image_name = image_name.replace("%BAKETYPE%", baketype)

    return image_name


def remove_disconnected_nodes(nodetree):
    nodes = nodetree.nodes

    # Loop through nodes
    repeat = False
    for node in nodes:
        if node.type == "BSDF_PRINCIPLED" and len(node.outputs[0].links) == 0:
            # Not a player, delete node
            nodes.remove(node)
            repeat = True
        elif node.type == "EMISSION" and len(node.outputs[0].links) == 0:
            # Not a player, delete node
            nodes.remove(node)
            repeat = True
        elif node.type == "MIX_SHADER" and len(node.outputs[0].links) == 0:
            # Not a player, delete node
            nodes.remove(node)
            repeat = True

    # If we removed any nodes, we need to do this again
    if repeat:
        remove_disconnected_nodes(nodetree)


def restore_all_materials():
    for obj in bpy.data.objects:
        if (obj.material_slots != None) and (len(obj.material_slots) > 0):# Stop the error where Nonetype not iterable
            # Get all slots that are using a dup mat
            dup_mats_slots_list = [slot for slot in obj.material_slots if slot.material != None and "SB_dupmat" in slot.material]

            # Swap those slos back to the original version of their material
            for dup_mat_slot in dup_mats_slots_list:
                dup_mat = dup_mat_slot.material
                orig_mat_name = dup_mat["SB_dupmat"]
                orig_mat = [mat for mat in bpy.data.materials if "SB_originalmat" in mat and mat["SB_originalmat"] == orig_mat_name][0] # Should only be one
                dup_mat_slot.material = orig_mat

    # Delete all duplicates (should no longet be any in use)
    del_list = [mat for mat in bpy.data.materials if "SB_dupmat" in mat]
    for mat in del_list:
        bpy.data.materials.remove(mat)


def is_blend_saved():
    path = bpy.data.filepath
    return path!="/" and path!=""


def create_images(imgname, thisbake, objname):
    # thisbake is subtype e.g. diffuse, ao, etc.
    current_bake_op = MasterOperation.current_bake_operation
    global_mode = current_bake_op.bake_mode
    cycles_mode = bpy.context.scene.cycles.bake_type
    batch = MasterOperation.batch_name

    print_msg(f"Creating image {imgname}")

    # Get the image height and width from the interface
    input_height = bpy.context.scene.TextureBake_Props.input_height
    input_width = bpy.context.scene.TextureBake_Props.input_width

    # If it already exists, remove it.
    if(imgname in bpy.data.images):
        bpy.data.images.remove(bpy.data.images[imgname])

    # Either way, create the new image
    alpha = bpy.context.scene.TextureBake_Props.use_alpha

    all32 = bpy.context.scene.TextureBake_Props.bake_32bit_float
    export = bpy.context.scene.TextureBake_Props.export_textures
    all16 = bpy.context.scene.TextureBake_Props.export_16bit

    # Create image 32 bit or not 32 bit
    if thisbake == "normal" or (global_mode == TextureBakeConstants.CYCLESBAKE and bpy.context.scene.cycles.bake_type == "NORMAL"):
        image = bpy.data.images.new(imgname, input_width, input_height, alpha=alpha, float_buffer=True)
    elif all32:
        image = bpy.data.images.new(imgname, input_width, input_height, alpha=alpha, float_buffer=True)
    else:
        image = bpy.data.images.new(imgname, input_width, input_height, alpha=alpha, float_buffer=False)

    if alpha:
        image.generated_color = (0,0,0,0)

    # Set tags
    image["SB_objname"] = objname
    image["SB_batch"] = batch
    image["SB_globalmode"] = global_mode
    image["SB_thisbake"] = thisbake
    if MasterOperation.merged_bake:
        image["SB_merged_bake_name"] = MasterOperation.merged_bake_name
    else:
        image["SB_merged_bake_name"] = None
    if current_bake_op.uv_mode == "udims":
        image["SB_udims"] = True
    else:
        image["SB_udims"] = False

    # Always mark new iages fake user when generated in the background
    if "--background" in sys.argv:
        image.use_fake_user = True

    # Store it at bake operation level
    MasterOperation.baked_textures.append(image)


def deselect_all_nodes(nodes):
    for node in nodes:
        node.select = False


def find_socket_connected_to_pnode(pnode, thisbake):
    # Get socket name for this bake mode
    socketname = psocketname[thisbake]

    # Get socket of the pnode
    socket = pnode.inputs[socketname]
    fromsocket = socket.links[0].from_socket

    # Return the socket connected to the pnode
    return fromsocket


def create_dummy_nodes(nodetree, thisbake):
    # Loop through pnodes
    nodes = nodetree.nodes

    for node in nodes:
        if node.type == "BSDF_PRINCIPLED":
            pnode = node
            # Get socket name for this bake mode
            socketname = psocketname[thisbake]

            # Get socket of the pnode
            psocket = pnode.inputs[socketname]

            # If it has something plugged in, we can leave it here
            if(len(psocket.links) > 0):
                continue

            # Get value of the unconnected socket
            val = psocket.default_value

            # If this is base col or ssscol, add an RGB node and set it's value to that of the socket
            if(socketname == "Base Color" or socketname == "Subsurface Color"):
                rgb = nodetree.nodes.new("ShaderNodeRGB")
                rgb.outputs[0].default_value = val
                rgb.label = "TextureBake"
                nodetree.links.new(rgb.outputs[0], psocket)

            # If this is anything else, use a value node
            else:
                vnode = nodetree.nodes.new("ShaderNodeValue")
                vnode.outputs[0].default_value = val
                vnode.label = "TextureBake"
                nodetree.links.new(vnode.outputs[0], psocket)


def bake_operation(thisbake, img):
    if(thisbake == "cyclesbake"):
        # If we are doing an old fashioned cycles bake, do that and then exit
        print_msg(f"Beginning bake based on Cycles settings: {bpy.context.scene.cycles.bake_type}")

        bpy.ops.object.bake(type=bpy.context.scene.cycles.bake_type)
        # Always pack the image for now
        img.pack()

        return True

    print_msg(f"Beginning bake for {thisbake}")

    use_clear = False
    if(thisbake != "normal"):
        bpy.ops.object.bake(type="EMIT", save_mode="INTERNAL", use_clear=use_clear)
    else:
        bpy.ops.object.bake(type="NORMAL", save_mode="INTERNAL", use_clear=use_clear)

    # Always pack the image for now
    img.pack()


def check_scene(objects, bakemode):
    messages = []

    # Check if in object mode
    if(bpy.context.mode != "OBJECT"):
        messages.append("ERROR: Not in object mode")
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    # This is hacky. A better way to do this needs to be found TODO: why?
    advancedobj = bpy.context.scene.TextureBake_Props.use_object_list
    if advancedobj:
        objects = advanced_object_selection_to_list()

    # Check no cp textures rely on bakes that are no longer enabled
    # Hacky
    if bpy.context.scene.TextureBake_Props.global_mode == "pbr_bake":
        pbr_bakes = bakes_to_list()
        if bpy.context.scene.TextureBake_Props.rough_glossy_switch == "glossy":
            pbr_bakes = ["glossy" if bake == "roughness" else bake for bake in pbr_bakes]
        special_bakes = []
        special_bakes.append(TextureBakeConstants.COLORID) if bpy.context.scene.TextureBake_Props.selected_col_mats else False
        special_bakes.append(TextureBakeConstants.VERTEXCOL) if bpy.context.scene.TextureBake_Props.selected_col_vertex else False
        special_bakes.append(TextureBakeConstants.AO) if bpy.context.scene.TextureBake_Props.selected_ao else False
        special_bakes.append(TextureBakeConstants.THICKNESS) if bpy.context.scene.TextureBake_Props.selected_thickness else False
        special_bakes.append(TextureBakeConstants.CURVATURE) if bpy.context.scene.TextureBake_Props.selected_curvature else False
        special_bakes.append(TextureBakeConstants.LIGHTMAP) if bpy.context.scene.TextureBake_Props.selected_lightmap else False
        bakes = pbr_bakes + special_bakes
        bakes.append("none")
        for cpt in bpy.context.scene.TextureBake_Props.cp_list:
            if cpt.R not in bakes:
                messages.append(f"ERROR: Channel packed texture \"{cpt.name}\" depends on {cpt.R}, but you are no longer baking it")
            if cpt.G not in bakes:
                messages.append(f"ERROR: Channel packed texture \"{cpt.name}\" depends on {cpt.G}, but you are no longer baking it")
            if cpt.B not in bakes:
                messages.append(f"ERROR: Channel packed texture \"{cpt.name}\" depends on {cpt.B}, but you are no longer baking it")
            if cpt.A not in bakes:
                messages.append(f"ERROR: Channel packed texture \"{cpt.name}\" depends on {cpt.A}, but you are no longer baking it")
        if len(messages) >0:
            show_message_box(messages, "Errors occured", "ERROR")
            return False

    # Is anything seleccted at all for bake?
    if len(objects) == 0:
        messages.append("ERROR: Nothing selected for bake")
        if advancedobj:
            messages.append("NOTE: You have advanced object selection turned on, so you have to add bake objects at the top of the TextureBake panel")
            messages.append("If you want to select objects for baking in the viewport, turn off advanced object selection")
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    # Check everything selected (or target) is mesh
    for obj in objects:
        if obj.type != "MESH":
            messages.append(f"ERROR: Object '{obj.name}' is not mesh")
    if bpy.context.scene.TextureBake_Props.selected_to_target and bpy.context.scene.TextureBake_Props.target_object != None:
        if bpy.context.scene.TextureBake_Props.target_object.type != "MESH":
            messages.append(f"ERROR: Object '{bpy.context.scene.TextureBake_Props.target_object.name}' (your target object) is not mesh")
    if len(messages) > 1:
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    # Output folder cannot be called textures
    if bpy.context.scene.TextureBake_Props.export_folder_name.lower() == "textures":
        messages.append(f"ERROR: Unfortunately, your save folder cannot be called \"textures\" for technical reasons. Please change the name to proceed.")
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    # Check object visibility
    obj_test_list = objects.copy()
    if bpy.context.scene.TextureBake_Props.selected_to_target and bpy.context.scene.TextureBake_Props.target_object != None:
        obj_test_list.append(bpy.context.scene.TextureBake_Props.target_object)

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
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    # None of the objects can have zero faces
    for obj in objects:
        if len(obj.data.polygons) < 1:
            messages.append(f"ERROR: Object '{obj.name}' has no faces")
    if bpy.context.scene.TextureBake_Props.selected_to_target and bpy.context.scene.TextureBake_Props.target_object != None:
        obj = bpy.context.scene.TextureBake_Props.target_object
        if len(obj.data.polygons) < 1:
            messages.append(f"ERROR: Object '{obj.name}' has no faces")
    if len(messages) > 1:
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    # Check for viewer nodes still connected
    for obj in objects:
        for slot in obj.material_slots:
            mat = slot.material
            if mat != None: # It'll get a placeholder material later on if it's none
                if check_for_connected_viewer_node(mat):
                    messages.append(f"ERROR: Material '{mat.name}' on object '{obj.name}' has a Viewer node connected to the Material Output")
                    show_message_box(messages, "Errors occured", "ERROR")
                    return False
    # glTF
    if bpy.context.scene.TextureBake_Props.create_gltf_node:
        if bpy.context.scene.TextureBake_Props.gltf_selection == TextureBakeConstants.AO and not bpy.context.scene.TextureBake_Props.selected_ao:
            messages.append(f"ERROR: You have selected AO for glTF settings (in the 'Other Settings' section), but you aren't baking AO")
        if bpy.context.scene.TextureBake_Props.gltf_selection == TextureBakeConstants.LIGHTMAP and not bpy.context.scene.TextureBake_Props.selected_lightmap:
            messages.append(f"ERROR: You have selected Lightmap for glTF settings (in the 'Other Settings' section), but you aren't baking Lightmap")
    if len(messages)>1:
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    for obj in objects:
        if obj.name != clean_file_name(obj.name) and bpy.context.scene.TextureBake_Props.export_textures:
            prefs = bpy.context.preferences.addons[__package__].preferences
            image_name = prefs.img_name_format
            if "%OBJ%" in image_name:
                messages.append(f"ERROR: You are trying to save external images, but object with name \"{obj.name}\" contains invalid characters for saving externally.")


    if bpy.context.scene.TextureBake_Props.merged_bake and bpy.context.scene.TextureBake_Props.merged_bake_name == "":
        messages.append(f"ERROR: You are baking multiple objects to one texture set, but the texture name is blank")

    if (bpy.context.scene.TextureBake_Props.merged_bake_name != clean_file_name(bpy.context.scene.TextureBake_Props.merged_bake_name)) and bpy.context.scene.TextureBake_Props.export_textures:
        messages.append(f"ERROR: The texture name you inputted for baking multiple objects to one texture set (\"{bpy.context.scene.TextureBake_Props.merged_bake_name}\") contains invalid characters for saving externally.")

    # Merged bake stuff
    if bpy.context.scene.TextureBake_Props.merged_bake:
        if bpy.context.scene.TextureBake_Props.selected_to_target: messages.append("You can't use the Bake Multiple Objects to One Texture Set option when baking to target")
        if bpy.context.scene.TextureBake_Props.tex_per_mat: messages.append("You can't use the Bake Multiple Objects to One Texture Set option with the Texture Per Material option")

        if (bpy.context.scene.TextureBake_Props.use_object_list and len(bpy.context.scene.TextureBake_Props.object_list)<2) or ((not bpy.context.scene.TextureBake_Props.use_object_list) and len(bpy.context.selected_objects)<2):
            messages.append("You have selected the Multiple Objeccts to One Texture Set option (under Texture Settings) but you don't have multiple objects selected")

    # PBR Bake Checks - No S2A
    if bakemode == TextureBakeConstants.PBR:
        for obj in objects:
            # Are UVs OK?
            if len(obj.data.uv_layers) == 0:
                messages.append(f"ERROR: Object {obj.name} has no UVs")
                continue

            # Are materials OK? Fix if not
            if not check_object_valid_material_config(obj):
                fix_invalid_material_config(obj)

            # Do all materials have valid PBR config?
            for slot in obj.material_slots:
                mat = slot.material
                result = check_mats_valid_for_pbr(mat)
                if len(result) > 0:
                    for node_name in result:
                        messages.append(f"ERROR: Node '{node_name}' in material '{mat.name}' on object '{obj.name}' is not valid for PBR bake. Principled BSDFs and/or Emission only!")

    # PBR Bake - S2A
    if bakemode == TextureBakeConstants.PBRS2A:
        # These checkes are done on all selected objects (not just the target)-----------

        # Are materials OK? Fix if not
        for obj in objects:
            if not check_object_valid_material_config(obj):
                print_msg(f"{obj.name} has invalid material config - fixing")
                fix_invalid_material_config(obj)
        # Check the taget object too
        target = bpy.context.scene.TextureBake_Props.target_object
        if not check_object_valid_material_config(target):
            fix_invalid_material_config(target)

        # Do all materials have valid PBR config?
        if len(messages) == 0:
            for obj in objects:
                for slot in obj.material_slots:
                    mat = slot.material
                    result = check_mats_valid_for_pbr(mat)
                    if len(result) > 0:
                        for node_name in result:
                            messages.append(f"ERROR: Node '{node_name}' in material '{mat.name}' on object '{obj.name}' is not valid for PBR bake. Principled BSDFs and/or Emission only!")

        # -------------------------------------------------------------------------

        if len(messages) == 0:
            # From this point onward, we only care about the target object
            obj = bpy.context.scene.TextureBake_Props.target_object

            # Do we have a target object?
            if bpy.context.scene.TextureBake_Props.target_object == None:
                messages.append("ERROR: You are trying to bake to a target object with PBR Bake, but you have not selected one in the TextureBake panel")
                show_message_box(messages, "Errors occured", "ERROR")
                return False

            # Have we got more selected than just the target object?
            if len(objects) == 1 and objects[0] == obj:
                messages.append("ERROR: You are trying to bake to a target object with PBR Bake, but the only object you have selected is your target")
                show_message_box(messages, "Errors occured", "ERROR")
                return False

            # Are UVs OK?
            if len(obj.data.uv_layers) == 0:
                messages.append(f"ERROR: Object {obj.name} has no UVs")
                show_message_box(messages, "Errors occured", "ERROR")
                return False

            # All existing materials must use nodes
            for slot in obj.material_slots:
                if slot.material != None:
                    if not slot.material.use_nodes:
                        slot.material.use_nodes = True

                # Are materials OK? Fix if not
                if not check_object_valid_material_config(obj):
                    print_msg(f"{obj.name} (target) has invalid material config - fixing")
                    fix_invalid_material_config(obj)

    # Cycles Bake - No S2A
    if bakemode == TextureBakeConstants.CYCLESBAKE and not bpy.context.scene.TextureBake_Props.selected_to_target:
        # First lets check for old users using the old method
        if bpy.context.scene.render.bake.use_selected_to_active:
            messages.append(f"ERROR: It looks like you are trying to bake selected to active. To do this with TextureBake, use the option on the TextureBake panel. You don’t need to worry about the setting in the Blender bake panel.")

        for obj in objects:
            # Are UVs OK?
            if not bpy.context.scene.TextureBake_Props.tex_per_mat:
                if len(obj.data.uv_layers) == 0:
                    messages.append(f"ERROR: Object {obj.name} has no UVs")
                    show_message_box(messages, "Errors occured", "ERROR")
                    return False
            else:
                if len(obj.data.uv_layers) == 0:
                    messages.append(f"ERROR: Object {obj.name} has no UVs")
                    show_message_box(messages, "Errors occured", "ERROR")
                    return False

            # Are materials OK?
            if not check_object_valid_material_config(obj):
                fix_invalid_material_config(obj)

    # Cycles Bake - S2A
    if bakemode == TextureBakeConstants.CYCLESBAKE and bpy.context.scene.TextureBake_Props.selected_to_target:
        # We only care about the target object
        obj = bpy.context.scene.TextureBake_Props.target_object

        # Do we actually have an active object?
        if obj == None:
            messages.append(f"ERROR: You are trying to bake selected to active with CyclesBake, but there is no active object")
            show_message_box(messages, "Errors occured", "ERROR")
            return False

        # Have we got more selected than just the target object?
        elif len(objects) == 1 and objects[0] == obj:
            messages.append("ERROR: You are trying to bake selected to active with CyclesBake, but the only object you have selected is your active (target) object")
            show_message_box(messages, "Errors occured", "ERROR")
            return False

        # Are UVs OK?
        elif len(obj.data.uv_layers) == 0:
            messages.append(f"ERROR: Object {obj.name} has no UVs")
            show_message_box(messages, "Errors occured", "ERROR")
            return False

        if not check_object_valid_material_config(obj):
            fix_invalid_material_config(obj)

    # Specials Bake
    if bpy.context.scene.TextureBake_Props.selected_col_vertex:
        if bakemode == TextureBakeConstants.SPECIALS:
            for obj in objects:
                if len(obj.data.vertex_colors) == 0:
                    messages.append(f"You are trying to bake the active vertex colors, but object {obj.name} doesn't have vertex colors")
                    show_message_box(messages, "Errors occured", "ERROR")
                    return False

        if bakemode == TextureBakeConstants.SPECIALS_CYCLES_TARGET_ONLY or bakemode == TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY:
            t = bpy.context.scene.TextureBake_Props.target_object
            if len(t.data.vertex_colors) == 0:
                messages.append(f"You are trying to bake the active vertex colors, but object {t.name} doesn't have vertex colors")
                show_message_box(messages, "Errors occured", "ERROR")
                return False

    # Let's report back (if we haven't already)
    if len(messages) != 0:
        show_message_box(messages, "Errors occured", "ERROR")
        return False
    else:
        # If we get here then everything looks good
        return True


def process_uvs():
    original_uvs = {}
    current_bake_op = MasterOperation.current_bake_operation

    if bpy.context.scene.TextureBake_Props.prefer_existing_uvmap:
        print_msg("We are preferring existing UV maps called TextureBake. Setting them to active")
        for obj in current_bake_op.bake_objects:
            if("TextureBake" in obj.data.uv_layers):
                obj.data.uv_layers["TextureBake"].active = True

    # Before we finish, restore the original selected and active objects
    bpy.ops.object.select_all(action="DESELECT")
    for obj in current_bake_op.orig_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = current_bake_op.orig_active_object


def restore_original_uvs():
    current_bake_op = MasterOperation.current_bake_operation

    # First the bake objects
    for obj in current_bake_op.bake_objects:
        if MasterOperation.orig_UVs_dict[obj.name]: # Will be false if none
            original_uv = MasterOperation.orig_UVs_dict[obj.name]
            obj.data.uv_layers.active = obj.data.uv_layers[original_uv]

    # Now the target objects (if any)
    pbr_target = current_bake_op.sb_target_object
    if pbr_target != None:
        try:
            original_uv = MasterOperation.orig_UVs_dict[pbr_target.name]
            pbr_target.data.uv_layers.active = pbr_target.data.uv_layers[original_uv]
        except KeyError:
            print_msg(f"No original UV map found for {pbr_target.name}")

    cycles_target = current_bake_op.sb_target_object
    if cycles_target != None and MasterOperation.orig_UVs_dict[cycles_target.name] != None:
        try:
            original_uv = MasterOperation.orig_UVs_dict[cycles_target.name]
            cycles_target.data.uv_layers.active = cycles_target.data.uv_layers[original_uv]
        except KeyError:
            print_msg(f"No original UV map found for {cycles_target.name}")


def find_pnode(nodetree):
    nodes = nodetree.nodes
    for node in nodes:
        if(node.type == "BSDF_PRINCIPLED"):
            return node
    # We never found it
    return False


def find_enode(nodetree):
    nodes = nodetree.nodes
    for node in nodes:
        if(node.type == "EMISSION"):
            return node
    # We never found it
    return False


def find_mnode(nodetree):
    nodes = nodetree.nodes
    for node in nodes:
        if(node.type == "MIX_SHADER"):
            return node
    # We never found it
    return False


def find_onode(nodetree):
    nodes = nodetree.nodes
    for node in nodes:
        if(node.type == "OUTPUT_MATERIAL"):
            return node
    # We never found it
    return False


def check_object_valid_material_config(obj):
    # Firstly, check it actually has material slots
    if len(obj.material_slots) == 0:
        return False

    # Check the material slots all have a material assigned
    for slot in obj.material_slots:
        if slot.material == None:
            return False

    # All materials must be using nodes
    for slot in obj.material_slots:
        if slot.material.use_nodes == False:
            return False
    # If we get here, everything looks good
    return True


def get_export_folder_name(initialise = False, relative = False):
    g_save_folder = ""
    g_rel_save_folder = ""

    if initialise:
        fullpath = bpy.data.filepath
        pathelements = os.path.split(fullpath)
        workingdir = Path(pathelements[0])

        if bpy.context.scene.TextureBake_Props.export_datetime:
            from datetime import datetime
            now = datetime.now()
            d1 = now.strftime("%d%m%Y-%H%M")

            g_rel_save_folder = clean_file_name(bpy.context.scene.TextureBake_Props.export_folder_name) + f"_{d1}"
            savedir = workingdir / g_rel_save_folder

        else:
            g_rel_save_folder = clean_file_name(bpy.context.scene.TextureBake_Props.export_folder_name)
            savedir = workingdir / g_rel_save_folder

        g_save_folder = savedir
        return g_save_folder

    elif relative:
        # Called for just the relative reference
        return "//" + g_rel_save_folder
    else:
        # Called for full path, time to create folder
        try:
            os.mkdir(g_save_folder)
        except FileExistsError:
            pass

        return g_save_folder


def get_mat_type(nodetree):
    if (find_pnode(nodetree) and find_mnode(nodetree)):
        return "MIX"
    elif(find_pnode(nodetree)):
        return "PURE_P"
    elif(find_enode(nodetree)):
        return "PURE_E"
    return "INVALID"


def clean_file_name(filename):
    keepcharacters = (' ','.','_','~',"-")
    return "".join(c for c in filename if c.isalnum() or c in keepcharacters).rstrip()


def export_textures(image, baketype, obj):
    originally_float = image.is_float

    def apply_scene_col_settings(scene):
        scene.display_settings.display_device = bpy.context.scene.display_settings.display_device
        scene.view_settings.view_transform = bpy.context.scene.view_settings.view_transform
        scene.view_settings.look = bpy.context.scene.view_settings.look
        scene.view_settings.exposure = bpy.context.scene.view_settings.exposure
        scene.view_settings.gamma = bpy.context.scene.view_settings.gamma
        scene.sequencer_colorspace_settings.name = bpy.context.scene.sequencer_colorspace_settings.name

    current_bake_op = MasterOperation.current_bake_operation

    # Firstly, work out if we want denoising or not
    if current_bake_op.bake_mode == TextureBakeConstants.CYCLESBAKE and bpy.context.scene.TextureBake_Props.run_denoise:
        need_denoise = True
    elif current_bake_op.bake_mode in [TextureBakeConstants.SPECIALS, TextureBakeConstants.SPECIALS_CYCLES_TARGET_ONLY, \
        TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY] and \
        baketype == TextureBakeConstants.LIGHTMAP and bpy.context.scene.TextureBake_Props.selected_lightmap_denoise:
        need_denoise = True
    else:
        need_denoise = False

    # We want to control the bit depth, so we need a new scene
    scene = bpy.data.scenes.new('TextureBakeTempScene')
    settings = scene.render.image_settings

    # Color management settings
    dcm_opt = bpy.context.scene.TextureBake_Props.export_color_space
    if current_bake_op.bake_mode in [TextureBakeConstants.PBR, TextureBakeConstants.PBRS2A] and (baketype == "diffuse" or baketype == "emission") :
        if dcm_opt:
            print_msg("Applying color management settings from current scene for PBR diffuse or emission")
            apply_scene_col_settings(scene)
        else:
            print_msg("Applying standard color management for PBR diffuse or emission")
            scene.view_settings.view_transform = "Standard"

    elif current_bake_op.bake_mode in [TextureBakeConstants.PBR, TextureBakeConstants.PBRS2A]:
        print_msg("Applying raw color space for PBR non-diffuse texture")
        scene.view_settings.view_transform = "Raw"
        scene.sequencer_colorspace_settings.name = "Non-Color"

    elif current_bake_op.bake_mode == TextureBakeConstants.CYCLESBAKE:
        if bpy.context.scene.cycles.bake_type == "NORMAL":
            print_msg("Raw color space for CyclesBake normal map")
            scene.view_settings.view_transform = "Raw"
            scene.sequencer_colorspace_settings.name = "Non-Color"
        elif bpy.context.scene.TextureBake_Props.export_color_space:
            print_msg("Applying color management settings from current scene for CyclesBake")
            apply_scene_col_settings(scene)
        else:
            # Just standard
            print_msg("Applying standard color management for CyclesBake")
            scene.view_settings.view_transform = "Standard"

    elif baketype == TextureBakeConstants.LIGHTMAP and bpy.context.scene.TextureBake_Props.lightmap_apply_colman:
        print_msg("Applying color management settings from current scene for Lightmap")
        apply_scene_col_settings(scene)

    elif current_bake_op.bake_mode in [TextureBakeConstants.SPECIALS, TextureBakeConstants.SPECIALS_PBR_TARGET_ONLY, TextureBakeConstants.SPECIALS_CYCLES_TARGET_ONLY]:
        print_msg("Raw color space for Specials")
        scene.view_settings.view_transform = "Raw"
        scene.sequencer_colorspace_settings.name = "Non-Color"
    else:
        print_msg("Applying standard color management as a default")
        scene.view_settings.view_transform = "Standard"

    # Set the scene file format. Variable contains valid internal names for Blender file formats, so this is OK
    settings.file_format = bpy.context.scene.TextureBake_Props.export_file_format

    # Now, work out the file extension we need to use
    # Adjust file extension if needed (plus some extra options for EXR)
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

    # Set the bit depth we want (plus extra compression setting for exr
    if file_extension == "tga" or file_extension == "jpg":
        # Only one option
        settings.color_depth = '8'
    elif (baketype == "normal" or baketype == "cyclesbake" and bpy.context.scene.cycles.bake_type == "NORMAL") and file_extension != "exr":
        settings.color_depth = '16'
    elif bpy.context.scene.TextureBake_Props.export_16bit and file_extension != "exr":
        settings.color_depth = '16'
    elif file_extension == "exr":
        settings.color_depth = '32'
        settings.exr_codec = "ZIP"
    else:
        # Should never really get here
        settings.color_depth = '8'

    # Work out path to save to, and remove previous file if there is one
    if bpy.context.scene.TextureBake_Props.export_folder_per_object and bpy.context.scene.TextureBake_Props.merged_bake and bpy.context.scene.TextureBake_Props.merged_bake_name != "":
        savepath = Path(str(get_export_folder_name()) + "/" + bpy.context.scene.TextureBake_Props.merged_bake_name + "/" + (clean_file_name(image.name) + "." + file_extension))

    elif bpy.context.scene.TextureBake_Props.export_folder_per_object and obj != None:
        savepath = Path(str(get_export_folder_name()) + "/" + obj.name + "/" + (clean_file_name(image.name) + "." + file_extension))

    else:
        savepath = Path(str(get_export_folder_name()) + "/" + (clean_file_name(image.name) + "." + file_extension))

    try:
        os.remove(str(savepath))
    except FileNotFoundError:
        pass

    # Set the image file format. Variable contains valid internal names for Blender file formats, so this is OK
    image.file_format = bpy.context.scene.TextureBake_Props.export_file_format

    # Time to save
    scene.render.filepath = str(savepath)

    # Use nodes as we will need the compositor no matter what
    scene.use_nodes = True

    # Prepare compositor nodes
    if "Render Layers" in scene.node_tree.nodes:
        scene.node_tree.nodes.remove(scene.node_tree.nodes["Render Layers"])

    composite_n = scene.node_tree.nodes["Composite"]
    img_n = scene.node_tree.nodes.new("CompositorNodeImage")
    img_n.image = image

    links = scene.node_tree.links

    # Set the output resolution of the scene to the texture size we are using
    scene.render.resolution_y = bpy.context.scene.TextureBake_Props.output_height
    scene.render.resolution_x = bpy.context.scene.TextureBake_Props.output_width

    # No denoising, minimal setup
    if not need_denoise:
        links.new(img_n.outputs[0], composite_n.inputs[0])

    # If donoising, we need a compositing setup.
    else:
        denoise_n = scene.node_tree.nodes.new("CompositorNodeDenoise")
        links.new(denoise_n.outputs[0], composite_n.inputs[0])
        links.new(img_n.outputs[0], denoise_n.inputs[0])

    # In both cases render out
    bpy.ops.render.render(animation=False, write_still=True, use_viewport=False, scene=scene.name)

    # And remove scene
    bpy.data.scenes.remove(scene)

    # Now we have saved the image externally, update the internal reference to refer to the external file
    try:
        image.unpack(method="REMOVE")
    except:
        pass
    image.source = "FILE"
    # Let's use a relative path. Shouldn't matter in the end.
    if bpy.context.scene.TextureBake_Props.export_folder_per_object and bpy.context.scene.TextureBake_Props.merged_bake and bpy.context.scene.TextureBake_Props.merged_bake_name != "":
        image.filepath = str(get_export_folder_name(relative=True)) +"/" + bpy.context.scene.TextureBake_Props.merged_bake_name + "/" + image.name + "." + file_extension
    elif bpy.context.scene.TextureBake_Props.export_folder_per_object and obj != None:
        image.filepath = str(get_export_folder_name(relative=True)) +"/" + obj.name + "/" + image.name + "." + file_extension
    else:
        image.filepath = str(get_export_folder_name(relative=True)) +"/" + image.name + "." + file_extension

    # UDIMS
    if bpy.context.scene.TextureBake_Props.uv_mode == "udims":
        # Is this the last one?
        if int(image.name[-3:]) == bpy.context.scene.TextureBake_Props.udim_tiles:
            # This is the last one

            # We will need the tags later
            SB_objname = image["SB_objname"]
            SB_batch = image["SB_batch"]
            SB_globalmode = image["SB_globalmode"]
            SB_thisbake = image["SB_thisbake"]
            SB_merged_bake_name = image["SB_merged_bake_name"]
            SB_udims = image["SB_udims"]

            # Delete all images indiviudally baked UDIM tiles
            counter = int(image.name[-3:])
            imgrootname = image.name[0:-4]
            while counter > 0:
                bpy.data.images.remove(bpy.data.images[f"{imgrootname}{1000+ counter}"])
                counter = counter - 1

            # Get the current (final) UDIM number
            imgudimnum = str(savepath)[-8:-4]

            # There can only be one!
            prposed_img_name = savepath.parts[-1].replace(imgudimnum, "1001")
            if prposed_img_name in bpy.data.images:
                bpy.data.images.remove(bpy.data.images[prposed_img_name])

            # Open the UDIM image
            bpy.ops.image.open(filepath=str(savepath).replace(imgudimnum, "1001"), directory= str(get_export_folder_name()) + "/", use_udim_detecting=True, relative_path=True)
            image = bpy.data.images[savepath.parts[-1].replace(imgudimnum, "1001")]

            # Set all the tags on the new image
            image["SB_objname"] = SB_objname
            image["SB_batch"] = SB_batch
            image["SB_globalmode"] = SB_globalmode
            image["SB_thisbake"] = SB_thisbake
            image["SB_merged_bake_name"] = SB_merged_bake_name
            image["SB_udims"] = SB_udims

    # Col management
    if file_extension == "exr":
        image.colorspace_settings.name = "Non-Color"

    elif originally_float and\
     (image["SB_thisbake"] == "diffuse" or\
     current_bake_op.bake_mode == TextureBakeConstants.CYCLESBAKE and bpy.context.scene.cycles.bake_type in ["COMBINED", "DIFFUSE"]):
        image.colorspace_settings.name = "sRGB"

    return file_extension


def prep_objects(objs, baketype):
    current_bake_op = MasterOperation.current_bake_operation

    print_msg("Creating prepared object")
    # First we prepare objectes
    export_objects = []
    for obj in objs:
        # Object might have a truncated name. Should use this if it's there
        objname = trunc_if_needed(obj.name)

        new_obj = obj.copy()
        new_obj.data = obj.data.copy()
        new_obj["SB_createdfrom"] = obj.name

        # Unless we are baking tex per mat OR we want to preserve the materials, clear all materials
        if not bpy.context.scene.TextureBake_Props.preserve_materials:
            if not bpy.context.scene.TextureBake_Props.tex_per_mat:
                new_obj.data.materials.clear()

        # Set the name of our new object
        new_obj.name = objname + "_TextureBake"

        # Create a collection for our baked objects if it doesn't exist
        if "TextureBake_Bakes" not in bpy.data.collections:
            c = bpy.data.collections.new("TextureBake_Bakes")
            bpy.context.scene.collection.children.link(c)
            try:
                c.color_tag = "COLOR_05"
            except AttributeError:
                pass

        # Make sure it's visible and enabled for current view laywer or it screws things up
        bpy.context.view_layer.layer_collection.children["TextureBake_Bakes"].exclude = False
        bpy.context.view_layer.layer_collection.children["TextureBake_Bakes"].hide_viewport = False
        c = bpy.data.collections["TextureBake_Bakes"]

        # Link object to our new collection
        c.objects.link(new_obj)

        # Append this object to the export list
        export_objects.append(new_obj)

        uvlayers = new_obj.data.uv_layers
        # If there is an existing map called TextureBake, and we are preferring it, use that
        if ("TextureBake" in uvlayers) and bpy.context.scene.TextureBake_Props.prefer_existing_uvmap:
            pass

        # Even if we are not preferring it, if there is just one map called TextureBake, we are using that
        elif ("TextureBake" in uvlayers) and len(uvlayers) <2:
            pass

        # If there is an existing map called TextureBake, and we are not preferring it, it has to go
        # Active map becommes TextureBake
        elif ("TextureBake" in uvlayers) and not bpy.context.scene.TextureBake_Props.prefer_existing_uvmap:
            uvlayers.remove(uvlayers["TextureBake"])
            active_layer = uvlayers.active
            active_layer.name = "TextureBake"

        # Finally, if none of the above apply, we are just using the active map
        # Active map becommes TextureBake
        else:
            active_layer = uvlayers.active
            active_layer.name = "TextureBake"

        # In all cases, we can now delete everything other than TextureBake
        deletelist = []
        for uvlayer in uvlayers:
            if (uvlayer.name != "TextureBake"):
                deletelist.append(uvlayer.name)
        for uvname in deletelist:
            uvlayers.remove(uvlayers[uvname])

        # Tex per mat will preserve existing materials
        if not bpy.context.scene.TextureBake_Props.tex_per_mat:

            if bpy.context.scene.TextureBake_Props.preserve_materials:
                # Copy existing materials, and rename them
                for slot in new_obj.material_slots:
                    mat_name = slot.material.name

                    mat = slot.material
                    new_mat = mat.copy()

                    # Empty all materials of all nodes
                    nodes = new_mat.node_tree.nodes
                    for node in nodes:
                        nodes.remove(node)

                    new_mat.name = mat_name + "_baked"
                    slot.material = new_mat
            else:
                # Create a new material
                # If not merged_bake, call it same as object + batch_name + baked
                if not bpy.context.scene.TextureBake_Props.merged_bake:
                    mat = bpy.data.materials.get(objname + "_" + bpy.context.scene.TextureBake_Props.batch_name + "_baked")
                    if mat is None:
                        mat = bpy.data.materials.new(name=objname + "_" + bpy.context.scene.TextureBake_Props.batch_name +"_baked")
                # For merged bake, it's the user specified name + batch_name.
                else:
                    mat = bpy.data.materials.get(bpy.context.scene.TextureBake_Props.merged_bake_name + "_" + bpy.context.scene.TextureBake_Props.batch_name)
                    if mat is None:
                        mat = bpy.data.materials.new(bpy.context.scene.TextureBake_Props.merged_bake_name + "_" + bpy.context.scene.TextureBake_Props.batch_name)

                # Assign it to object
                mat.use_nodes = True
                new_obj.data.materials.append(mat)

    # Tex per material should have no material setup (as prepare objects is not an option)
    if not bpy.context.scene.TextureBake_Props.tex_per_mat:
        # Set up the materials for each object
        for obj in export_objects:
            if bpy.context.scene.TextureBake_Props.preserve_materials: # Object will have multiple materials
                for slot in obj.material_slots:
                    mat = slot.material
                    nodetree = mat.node_tree

                    if(baketype in {TextureBakeConstants.PBR, TextureBakeConstants.PBRS2A}):
                        material_setup.create_principled_setup(nodetree, obj)
                    if baketype == TextureBakeConstants.CYCLESBAKE:
                        material_setup.create_cyclesbake_setup(nodetree, obj)
            else: # Should only have one material
                mat = obj.material_slots[0].material
                nodetree = mat.node_tree

                if(baketype in {TextureBakeConstants.PBR, TextureBakeConstants.PBRS2A}):
                    material_setup.create_principled_setup(nodetree, obj)
                if baketype == TextureBakeConstants.CYCLESBAKE:
                    material_setup.create_cyclesbake_setup(nodetree, obj)

            # Change object name to avoid collisions
            obj.name = obj.name.replace("_TextureBake", "_Baked")

    # Deselect all objects
    bpy.ops.object.select_all(action="DESELECT")

    # If we are exporting to FBX, do that now
    if(bpy.context.scene.TextureBake_Props.export_mesh):
        mod_option = bpy.context.scene.TextureBake_Props.export_apply_modifiers
        applytransform_option = bpy.context.scene.TextureBake_Props.export_apply_transforms

        # Single FBX
        if not bpy.context.scene.TextureBake_Props.export_folder_per_object:
            for obj in export_objects:
                obj.select_set(state=True)

            # Use the file name that the user defined
            filepath = get_export_folder_name() / (clean_file_name(bpy.context.scene.TextureBake_Props.fbx_name) + ".fbx")
            bpy.ops.export_scene.fbx(filepath=str(filepath), check_existing=False, use_selection=True,
                use_mesh_modifiers=mod_option, bake_space_transform=applytransform_option, path_mode="STRIP")

        # Folder per FBX
        else:
            if bpy.context.scene.TextureBake_Props.merged_bake:
                bpy.ops.object.select_all(action="DESELECT")
                for obj in export_objects:
                    obj.select_set(state=True)
                filepath = get_export_folder_name() / (clean_file_name(bpy.context.scene.TextureBake_Props.merged_bake_name)) / (clean_file_name(bpy.context.scene.TextureBake_Props.merged_bake_name) + ".fbx")
                bpy.ops.export_scene.fbx(filepath=str(filepath), check_existing=False, use_selection=True,
                    use_mesh_modifiers=mod_option, path_mode="STRIP", bake_space_transform=applytransform_option)
            else:
                for obj in export_objects:
                    bpy.ops.object.select_all(action="DESELECT")
                    obj.select_set(state=True)
                    filepath = get_export_folder_name() / obj.name.replace("_Baked", "") / (obj.name.replace("_Baked", "") + ".fbx")
                    bpy.ops.export_scene.fbx(filepath=str(filepath), check_existing=False, use_selection=True,
                        use_mesh_modifiers=mod_option, path_mode="STRIP", bake_space_transform=applytransform_option)

    if (not bpy.context.scene.TextureBake_Props.prep_mesh) and (not "--background" in sys.argv):
        # Deleted duplicated objects
        for obj in export_objects:
            bpy.data.objects.remove(obj)
    # Add the created objects to the bake operation list to keep track of them
    else:
        for obj in export_objects:
            MasterOperation.prepared_mesh_objects.append(obj)


def select_only_this(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(state=True)
    bpy.context.view_layer.objects.active = obj


def setup_pure_p_material(nodetree, thisbake):
    # Create dummy nodes as needed
    create_dummy_nodes(nodetree, thisbake)

    # Create emission shader
    nodes = nodetree.nodes
    m_output_node = find_onode(nodetree)
    loc = m_output_node.location

    # Create an emission shader
    emissnode = nodes.new("ShaderNodeEmission")
    emissnode.label = "TextureBake"
    emissnode.location = loc
    emissnode.location.y = emissnode.location.y + 200

    # Connect our new emission to the output
    fromsocket = emissnode.outputs[0]
    tosocket = m_output_node.inputs[0]
    nodetree.links.new(fromsocket, tosocket)

    # Connect whatever is in Principled Shader for this bakemode to the emission
    fromsocket = find_socket_connected_to_pnode(find_pnode(nodetree), thisbake)
    tosocket = emissnode.inputs[0]
    nodetree.links.new(fromsocket, tosocket)


def setup_pure_e_material(nodetree, thisbake):
    # If baking something other than emission, mute the emission modes so they don't contaiminate our bake
    if thisbake != "Emission":
        nodes = nodetree.nodes
        for node in nodes:
            if node.type == "EMISSION":
                node.mute = True
                node.label = "TextureBakeMuted"


def setup_mix_material(nodetree, thisbake):
    # No need to mute emission nodes. They are automuted by setting the RGBMix to black
    nodes = nodetree.nodes

    # Create dummy nodes as needed
    create_dummy_nodes(nodetree, thisbake)

    # For every mix shader, create a mixrgb above it
    # Also connect the factor input to the same thing
    created_mix_nodes = {}
    for node in nodes:
        if node.type == "MIX_SHADER":
            loc = node.location
            rgbmix = nodetree.nodes.new("ShaderNodeMixRGB")
            rgbmix.label = "TextureBake"
            rgbmix.location = loc
            rgbmix.location.y = rgbmix.location.y + 200

            # If there is one, plug the factor from the original mix node into our new mix node
            if(len(node.inputs[0].links) > 0):
                fromsocket = node.inputs[0].links[0].from_socket
                tosocket = rgbmix.inputs["Fac"]
                nodetree.links.new(fromsocket, tosocket)
            # If no input, add a value node set to same as the mnode factor
            else:
                val = node.inputs[0].default_value
                vnode = nodes.new("ShaderNodeValue")
                vnode.label = "TextureBake"
                vnode.outputs[0].default_value = val

                fromsocket = vnode.outputs[0]
                tosocket = rgbmix.inputs[0]
                nodetree.links.new(fromsocket, tosocket)

            # Keep a dictionary with paired shader mix node
            created_mix_nodes[node.name] = rgbmix.name

    # Loop over the RGBMix nodes that we created
    for node in created_mix_nodes:
        mshader = nodes[node]
        rgb = nodes[created_mix_nodes[node]]

        # Mshader - Socket 1
        # First, check if there is anything plugged in at all
        if len(mshader.inputs[1].links) > 0:
            fromnode = mshader.inputs[1].links[0].from_node

            if fromnode.type == "BSDF_PRINCIPLED":
                # Get the socket we are looking for, and plug it into RGB socket 1
                fromsocket = find_socket_connected_to_pnode(fromnode, thisbake)
                nodetree.links.new(fromsocket, rgb.inputs[1])
            elif fromnode.type == "MIX_SHADER":
                # If it's a mix shader on the other end, connect the equivilent RGB node
                # Get the RGB node for that mshader
                fromrgb = nodes[created_mix_nodes[fromnode.name]]
                fromsocket = fromrgb.outputs[0]
                nodetree.links.new(fromsocket, rgb.inputs[1])
            elif fromnode.type == "EMISSION":
                # Set this input to black
                rgb.inputs[1].default_value = (0.0, 0.0, 0.0, 1)
            else:
                print_msg("Error, invalid node config")
        else:
            rgb.inputs[1].default_value = (0.0, 0.0, 0.0, 1)

        # Mshader - Socket 2
        if len(mshader.inputs[2].links) > 0:
            fromnode = mshader.inputs[2].links[0].from_node
            if fromnode.type == "BSDF_PRINCIPLED":
                # Get the socket we are looking for, and plug it into RGB socket 2
                fromsocket = find_socket_connected_to_pnode(fromnode, thisbake)
                nodetree.links.new(fromsocket, rgb.inputs[2])
            elif fromnode.type == "MIX_SHADER":
                # If it's a mix shader on the other end, connect the equivilent RGB node
                # Get the RGB node for that mshader
                fromrgb = nodes[created_mix_nodes[fromnode.name]]
                fromsocket = fromrgb.outputs[0]
                nodetree.links.new(fromsocket, rgb.inputs[2])
            elif fromnode.type == "EMISSION":
                # Set this input to black
                rgb.inputs[2].default_value = (0.0, 0.0, 0.0, 1)
            else:
                print_msg("Error, invalid node config")
        else:
            rgb.inputs[2].default_value = (0.0, 0.0, 0.0, 1)

    # Find the output node with location
    m_output_node = find_onode(nodetree)
    loc = m_output_node.location

    # Create an emission shader
    emissnode = nodes.new("ShaderNodeEmission")
    emissnode.label = "TextureBake"
    emissnode.location = loc
    emissnode.location.y = emissnode.location.y + 200

    # Get the original mix node that was connected to the output node
    socket = m_output_node.inputs["Surface"]
    fromnode = socket.links[0].from_node

    # Find our created mix node that is paired with it
    rgbmix = nodes[created_mix_nodes[fromnode.name]]

    # Plug rgbmix into emission
    nodetree.links.new(rgbmix.outputs[0], emissnode.inputs[0])

    # Plug emission into output
    nodetree.links.new(emissnode.outputs[0], m_output_node.inputs[0])


# ----------------Specials---------------------------------
def import_needed_specials_materials(justcount = False):
    ordered_specials = []
    path = os.path.dirname(__file__) + "/materials/materials.blend\\Material\\"
    if(bpy.context.scene.TextureBake_Props.selected_thickness):
        if "TextureBake_"+TextureBakeConstants.THICKNESS not in bpy.data.materials:
            material_name = "TextureBake_"+TextureBakeConstants.THICKNESS
            if not justcount:
                bpy.ops.wm.append(filename=material_name, directory=path)
            ordered_specials.append(TextureBakeConstants.THICKNESS)
        else:
            ordered_specials.append(TextureBakeConstants.THICKNESS)

    if(bpy.context.scene.TextureBake_Props.selected_ao):
        if "TextureBake_"+TextureBakeConstants.AO not in bpy.data.materials:
            material_name = "TextureBake_"+TextureBakeConstants.AO
            if not justcount:
                bpy.ops.wm.append(filename=material_name, directory=path)
            ordered_specials.append(TextureBakeConstants.AO)
        else:
            ordered_specials.append(TextureBakeConstants.AO)

    if(bpy.context.scene.TextureBake_Props.selected_curvature):
        if "TextureBake"+TextureBakeConstants.CURVATURE not in bpy.data.materials:
            material_name = "TextureBake_"+TextureBakeConstants.CURVATURE
            if not justcount:
                bpy.ops.wm.append(filename=material_name, directory=path)
            ordered_specials.append(TextureBakeConstants.CURVATURE)
        else:
            ordered_specials.append(TextureBakeConstants.CURVATURE)

    if(bpy.context.scene.TextureBake_Props.selected_lightmap):
        if "TextureBake_"+TextureBakeConstants.LIGHTMAP not in bpy.data.materials:
            material_name = "TextureBake_"+TextureBakeConstants.LIGHTMAP
            if not justcount:
                bpy.ops.wm.append(filename=material_name, directory=path)
            ordered_specials.append(TextureBakeConstants.LIGHTMAP)
        else:
            ordered_specials.append(TextureBakeConstants.LIGHTMAP)

    # return the list of specials
    if justcount:
        return len(ordered_specials)
    else:
        return ordered_specials


trunc_num = 0
trunc_dict = {}
def trunc_if_needed(objectname):
    global trunc_num
    global trunc_dict

    # If we already truncated this, just return that
    if objectname in trunc_dict:
        print_msg(f"Object name {objectname} was previously truncated. Returning that.")
        return trunc_dict[objectname]

    # If not, let's see if we have to truncate it
    elif len(objectname) >= 38:
        print_msg(f"Object name {objectname} is too long and will be truncated")
        trunc_num += 1
        truncdobjectname = objectname[0:34] + "~" + str(trunc_num)
        trunc_dict[objectname] = truncdobjectname
        return truncdobjectname

    # If nothing else, just return the original name
    return objectname


def untrunc_if_needed(objectname):
    global trunc_num
    global trunc_dict

    for t in trunc_dict:
        if trunc_dict[t] == objectname:
            print_msg(f"Returning untruncated value {t}")
            return t

    return objectname


def show_message_box(messageitems_list, title, icon = 'INFO'):
    def draw(self, context):
        for m in messageitems_list:
            self.layout.label(text=m)

    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)


def write_bake_progress(current_operation, total_operations):
    progress = int((current_operation / total_operations) * 100)
    t = Path(tempfile.gettempdir())
    t = t / f"TextureBake_background_bake_{os.getpid()}"
    with open(str(t), "w") as progfile:
        progfile.write(str(progress))


# Dict obj name to tile
currentUDIMtile = {}
def focus_UDIM_tile(obj,desiredUDIMtile):
    orig_active_object = bpy.context.active_object
    orig_selected_objects = bpy.context.selected_objects

    global currentUDIMtile

    select_only_this(obj)
    bpy.ops.object.editmode_toggle()

    print_msg(f"Shifting UDIM focus tile: Object: {obj.name} Tile: {desiredUDIMtile}")

    import bmesh
    if obj.name not in currentUDIMtile:
        # Must be first time. Set to 0
        currentUDIMtile[obj.name] = 0

    # Difference between desired and current
    tilediff =  desiredUDIMtile - currentUDIMtile[obj.name]

    me = obj.data
    bm = bmesh.new()
    bm = bmesh.from_edit_mesh(me)
    uv_layer = bm.loops.layers.uv.verify()

    # scale UVs x2
    for f in bm.faces:
        for l in f.loops:
            l[uv_layer].uv[0] -= tilediff

    me.update()
    currentUDIMtile[obj.name] = desiredUDIMtile
    bpy.ops.object.editmode_toggle()

    # Restore the original selected and active objects before we leave
    for o in orig_selected_objects:
        o.select_set(state=True)
    bpy.context.view_layer.objects.active = orig_active_object


past_items_dict = {}
def spot_new_items(initialise=True, item_type="images"):
    global past_items_dict

    if item_type == "images":
        source = bpy.data.images
    elif item_type == "objects":
        source = bpy.data.objects
    elif item_type == "collections":
        source = bpy.data.collections

    # First run
    if initialise:
        # Set to empty list for this item type
        past_items_dict[item_type] = []

        for source_item in source:
            past_items_dict[item_type].append(source_item.name)
        return True

    else:
        # Get the list of items for this item type from the dict
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

    # Get all nodes with label "Viewer"
    viewer_nodes = [n for n in nodes if n.label == "Viewer"]

    # Check if any of those viewer nodes are connected to the Material Output
    for n in viewer_nodes:
        if n.name == onode.inputs[0].links[0].from_node.name:
            return True

    return False


def check_mats_valid_for_pbr(mat):
    nodes = mat.node_tree.nodes

    valid = True
    invalid_node_names = []

    for node in nodes:
        if len(node.outputs) > 0:
            if node.outputs[0].type == "SHADER" and not (node.bl_idname == "ShaderNodeBsdfPrincipled" or node.bl_idname == "ShaderNodeMixShader" or node.bl_idname == "ShaderNodeEmission"):
                # But is it actually connected to anything?
                if len(node.outputs[0].links) >0:
                    invalid_node_names.append(node.name)

    return invalid_node_names


def advanced_object_selection_to_list():
    return [i.obj for i in bpy.context.scene.TextureBake_Props.object_list]


def fix_invalid_material_config(obj):
    if "TextureBake_Placeholder" in bpy.data.materials:
        mat = bpy.data.materials["TextureBake_Placeholder"]
    else:
        mat = bpy.data.materials.new("TextureBake_Placeholder")
        bpy.data.materials["TextureBake_Placeholder"].use_nodes = True

    # Assign it to object
    if len(obj.material_slots) > 0:
        # Assign it to every empty slot
        for slot in obj.material_slots:
            if slot.material == None:
                slot.material = mat
    else:
        # no slots
        obj.data.materials.append(mat)

    # All materials must use nodes
    for slot in obj.material_slots:
        mat = slot.material
        if mat.use_nodes == False:
            mat.use_nodes = True


def check_col_distance(r,g,b, min_diff):
    current_bake_op = MasterOperation.current_bake_operation
    used_cols = current_bake_op.used_cols

    # Very first col gets a free pass
    if len(used_cols) < 1:
        # print_msg("First - free pass")
        current_bake_op.used_cols.append([r,g,b])
        return True

    ok = True
    for uc in used_cols:
        if round(abs(r - uc[0]),1) > min_diff or round(abs(g - uc[1]), 1) > min_diff or round(abs(b - uc[2]),1) > min_diff:
            pass # We passed, don't change the value
        else:
            ok = False # At least one rgb was too close

    # If we OKd this. Add it to the used cols list
    if ok:
        current_bake_op.used_cols.append([r,g,b])

    # Return result either way
    return ok


def sacle_image_if_needed(img):
    print_msg("Scaling images if needed")

    context = bpy.context
    width = img.size[0]
    height = img.size[1]

    proposed_width = bpy.context.scene.TextureBake_Props.output_width
    proposed_height = bpy.context.scene.TextureBake_Props.output_height

    if width != proposed_width or height != proposed_height:
        img.scale(proposed_width, proposed_height)


def set_image_internal_col_space(image, thisbake):
    if thisbake == TextureBakeConstants.CYCLESBAKE:
        if bpy.context.scene.cycles.bake_type not in ["COMBINED", "DIFFUSE"]:
            image.colorspace_settings.name = "Non-Color"
    else: # PBR
        if thisbake != "diffuse" and thisbake != "emission":
            image.colorspace_settings.name = "Non-Color"


def any_specials():
    return (bpy.context.scene.TextureBake_Props.selected_col_mats
        or bpy.context.scene.TextureBake_Props.selected_col_vertex
        or bpy.context.scene.TextureBake_Props.selected_ao
        or bpy.context.scene.TextureBake_Props.selected_thickness
        or bpy.context.scene.TextureBake_Props.selected_curvature
        or bpy.context.scene.TextureBake_Props.selected_lightmap)


def auto_set_bake_margin():
    context = bpy.context
    current_width = context.scene.TextureBake_Props.input_width
    context.scene.render.bake.margin = round((current_width / 1024) * 4)
