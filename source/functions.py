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
import datetime
import os
import base64
import sys
import tempfile

from . import (
    constants,
    material_setup,
)

from .bake_operation import (
    BakeOperation,
    MasterOperation,
)


# Global variables
psocketname = {
    constants.PBR_DIFFUSE: "Base Color",
    constants.PBR_METAL: "Metallic",
    constants.PBR_ROUGHNESS: "Roughness",
    constants.PBR_NORMAL_DX: "Normal",
    constants.PBR_NORMAL_OGL: "Normal",
    constants.PBR_TRANSMISSION: "Transmission",
    constants.PBR_TRANSMISSION_ROUGH: "Transmission Roughness",
    constants.PBR_CLEARCOAT: "Clearcoat",
    constants.PBR_CLEARCOAT_ROUGH: "Clearcoat Roughness",
    constants.PBR_SPECULAR: "Specular",
    constants.PBR_OPACITY: "Alpha",
    constants.PBR_SSS: "Subsurface",
    constants.PBR_SSS_COL: "Subsurface Color"
}

def print_msg(msg):
    print(f"TEXTUREBAKE: {msg}")


def does_object_have_bakes(obj):
    for img in bpy.data.images:
        return "SB_objname" in img # SB_objname is always set. Even for merged_bake


def gen_export_texture_name(name_format, obj_name):
    name_format = name_format.replace("%OBJ%", obj_name)

    batch_name = bpy.context.scene.TextureBake_Props.batch_name
    if batch_name:
        name_format = name_format.replace("%BATCH%", batch_name)

    return name_format


def gen_image_name(obj_name, baketype):
    parts = [obj_name]
    if bpy.context.scene.TextureBake_Props.batch_name:
        parts.append(bpy.context.scene.TextureBake_Props.batch_name)

    prefs = bpy.context.preferences.addons[__package__].preferences
    if baketype == constants.PBR_DIFFUSE:
        parts.append(prefs.diffuse_alias)
    elif baketype == constants.PBR_METAL:
        parts.append(prefs.metal_alias)
    elif baketype == constants.PBR_ROUGHNESS:
        parts.append(prefs.roughness_alias)
    elif baketype == constants.PBR_NORMAL_DX or baketype == constants.PBR_NORMAL_OGL:
        parts.append(prefs.normal_alias)
    elif baketype == constants.PBR_TRANSMISSION:
        parts.append(prefs.transmission_alias)
    elif baketype == constants.PBR_TRANSMISSION_ROUGH:
        parts.append(prefs.transmissionrough_alias)
    elif baketype == constants.PBR_CLEARCOAT:
        parts.append(prefs.clearcoat_alias)
    elif baketype == constants.PBR_CLEARCOAT_ROUGH:
        parts.append(prefs.clearcoatrough_alias)
    elif baketype == constants.PBR_EMISSION:
        parts.append(prefs.emission_alias)
    elif baketype == constants.PBR_SPECULAR:
        parts.append(prefs.specular_alias)
    elif baketype == constants.PBR_OPACITY:
        parts.append(prefs.alpha_alias)
    elif baketype == constants.TEX_AO or baketype == constants.PBR_AO:
        parts.append(prefs.ao_alias)
    elif baketype == constants.TEX_MAT_ID:
        parts.append(prefs.colid_alias)
    elif baketype == constants.TEX_CURVATURE:
        parts.append(prefs.curvature_alias)
    elif baketype == constants.TEX_THICKNESS:
        parts.append(prefs.thickness_alias)
    elif baketype == constants.TEX_VERT_COLOR:
        parts.append(prefs.vertexcol_alias)
    elif baketype == constants.PBR_SSS:
        parts.append(prefs.sss_alias)
    elif baketype == constants.PBR_SSS_COL:
        parts.append(prefs.ssscol_alias)
    else:
        parts.append(baketype)

    return "_".join(parts)


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
    return path != "/" and path != ""


def create_images(imgname, thisbake, objname):
    # thisbake is subtype e.g. diffuse, ao, etc.
    current_bake_op = MasterOperation.bake_op
    global_mode = current_bake_op.bake_mode
    batch = MasterOperation.batch_name

    print_msg(f"Creating image {imgname}")

    # Get the image height and width from the interface
    input_height = bpy.context.scene.TextureBake_Props.input_height
    input_width = bpy.context.scene.TextureBake_Props.input_width

    # If it already exists, remove it.
    if imgname in bpy.data.images:
        bpy.data.images.remove(bpy.data.images[imgname])

    # Either way, create the new image
    alpha = bpy.context.scene.TextureBake_Props.use_alpha
    all32 = bpy.context.scene.TextureBake_Props.bake_32bit_float

    # Create image 32 bit or not 32 bit
    if thisbake == constants.PBR_NORMAL_DX or thisbake == constants.PBR_NORMAL_OGL:
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

    # Always mark new images fake user when generated in the background
    if "--background" in sys.argv:
        image.use_fake_user = True

    # Store it at bake operation level
    MasterOperation.baked_textures.append(image)


def deselect_all_nodes(nodes):
    for node in nodes:
        node.select = False


def find_socket_connected_to_pnode(pnode, thisbake):
    socketname = psocketname[thisbake]
    socket = pnode.inputs[socketname]
    return socket.links[0].from_socket


def create_dummy_nodes(nodetree, thisbake):
    for node in nodetree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            socketname = psocketname[thisbake]
            psocket = node.inputs[socketname]

            # If it has something plugged in, we can leave it here
            if(len(psocket.links) > 0):
                continue

            # Get value of the unconnected socket
            val = psocket.default_value

            # If this is base col or ssscol, add an RGB node and set its value to that of the socket
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
    print_msg(f"Beginning bake for {thisbake}")

    use_clear = False
    if thisbake not in [constants.PBR_NORMAL_DX, constants.PBR_NORMAL_OGL]:
        bpy.ops.object.bake(type="EMIT", save_mode="INTERNAL", use_clear=use_clear)
    else:
        bpy.ops.object.bake(type="NORMAL", save_mode="INTERNAL", use_clear=use_clear)

    # Always pack the image for now
    img.pack()


def check_scene(objects, bakemode):
    messages = []
    props = bpy.context.scene.TextureBake_Props

    # Are objects selected for baking?
    if props.use_object_list:
        objects = advanced_object_selection_to_list()
    if len(objects) == 0:
        messages.append("ERROR: Nothing selected for bake")
        if props.use_object_list:
            messages.append("Add objects to the list in the Objects panel or deactivate advanced object selection.")
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    # Check everything selected (or target) is mesh
    for obj in objects:
        if obj.type != "MESH":
            messages.append(f"ERROR: Object '{obj.name}' is not a mesh")
    if props.selected_to_target and props.target_object and props.target_object.type != "MESH":
        messages.append(f"ERROR: Target object '{props.target_object.name}' is not a mesh")
    if len(messages) > 1:
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    # Check object visibility
    obj_test_list = objects.copy()
    if props.selected_to_target and props.target_object:
        obj_test_list.append(props.target_object)

    for obj in obj_test_list:
        if obj.hide_viewport == True:
            messages.append(f"Object '{obj.name}' is hidden in viewport")
        if obj.hide_render == True:
            messages.append(f"Object '{obj.name}' is hidden for render")
        if obj.hide_get() == True:
            messages.append(f"Object '{obj.name}' is hidden in viewport eye")
        if obj.hide_select == True:
            messages.append(f"Object '{obj.name}' is hidden for selection")
    if len(messages)>0:
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    # None of the objects can have zero faces
    for obj in objects:
        if len(obj.data.polygons) < 1:
            messages.append(f"ERROR: Object '{obj.name}' has no faces")
    if props.selected_to_target and props.target_object:
        obj = props.target_object
        if len(obj.data.polygons) < 1:
            messages.append(f"ERROR: Object '{obj.name}' has no faces")
    if len(messages) > 1:
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    # Check for viewer nodes still connected
    for obj in objects:
        for slot in obj.material_slots:
            mat = slot.material
            if mat != None:
                if check_for_connected_viewer_node(mat):
                    messages.append(f"ERROR: Material '{mat.name}' on object '{obj.name}' has a Viewer node connected to the Material Output")
                    show_message_box(messages, "Errors occured", "ERROR")
                    return False
    if len(messages) > 1:
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    # Invalid character in exported names
    for obj in objects:
        if props.export_textures and obj.name != clean_file_name(obj.name):
            prefs = bpy.context.preferences.addons[__package__].preferences
            presets = [p for p in prefs.export_presets if p.uid == props.export_preset]
            if presets and [t for t in presets[0].textures if "%OBJ" in t.name]:
                messages.append(f"ERROR: You are trying to save external images, but \"{obj.name}\" contains invalid characters for saving externally.")
                break

    if props.merged_bake and props.merged_bake_name == "":
        messages.append(f"ERROR: You are baking multiple objects to one texture set, but the texture name is blank")

    if props.merged_bake_name != clean_file_name(props.merged_bake_name) and props.export_textures:
        messages.append(f"ERROR: The texture name for baking multiple objects to one texture set \"{props.merged_bake_name}\" contains invalid characters for saving externally.")

    # Merged bakes
    if props.merged_bake:
        if props.selected_to_target:
            messages.append("You can't use the Bake Multiple Objects to One Texture Set option when baking to target")
        if props.tex_per_mat:
            messages.append("You can't use the Bake Multiple Objects to One Texture Set option with the Texture Per Material option")

    # PBR Bake Checks - No S2A
    if bakemode == constants.BAKE_MODE_PBR:
        for obj in objects:
            if len(obj.data.uv_layers) == 0:
                messages.append(f"ERROR: Object {obj.name} has no UVs")
                continue

            # Are materials OK?
            if not check_object_valid_material_config(obj):
                messages.append(f"ERROR: Object {obj.name} has invalid material setup. Check that there is a material in every slot and all of them use nodes")

            # Do all materials have valid PBR config?
            for mat in [slot.material for slot in obj.material_slots if slot.material]:
                result = check_mats_valid_for_pbr(mat)
                if len(result) > 0:
                    for node_name in result:
                        messages.append(f"ERROR: Node '{node_name}' in material '{mat.name}' on object '{obj.name}' is not valid for PBR bake. Principled BSDFs and/or Emission only!")

    # PBR Bake - S2A
    if bakemode == constants.BAKE_MODE_S2A:
        # Are materials OK?
        for obj in objects:
            if not check_object_valid_material_config(obj):
                messages.append(f"ERROR: Object {obj.name} has invalid material setup. Check that there is a material in every slot and all of them use nodes")

            for mat in [slot.material for slot in obj.material_slots if slot.material]:
                result = check_mats_valid_for_pbr(mat)
                if len(result) > 0:
                    for node_name in result:
                        messages.append(f"ERROR: Node '{node_name}' in material '{mat.name}' on object '{obj.name}' is not valid for PBR bake. Principled BSDFs and/or Emission only!")

        # Check the taget object too
        target = props.target_object
        if not target:
            messages.append("ERROR: You are trying to bake to a target object, but you have not selected one in the Texture Bake panel")
            show_message_box(messages, "Errors occured", "ERROR")
            return False

        # Do we have selected more than just the target object?
        if len(objects) == 1 and objects[0] == target:
            messages.append("ERROR: You are trying to bake to a target object, but the only object you have selected is your target")
            show_message_box(messages, "Errors occured", "ERROR")
            return False

        # Are UVs OK?
        if len(target.data.uv_layers) == 0:
            messages.append(f"ERROR: Object {target.name} has no UVs")
            show_message_box(messages, "Errors occured", "ERROR")
            return False

        if not check_object_valid_material_config(target):
            messages.append(f"ERROR: Object {obj.name} has invalid material setup. Check that there is a material in every slot and all of them use nodes")
            show_message_box(messages, "Errors occured", "ERROR")
            return False

    # Input textures
    if props.selected_col_vertex:
        if bakemode == constants.BAKE_MODE_INPUTS:
            for obj in objects:
                if not obj.data.vertex_colors:
                    messages.append(f"You are trying to bake the active vertex colors, but {obj.name} doesn't have vertex colors")
                    show_message_box(messages, "Errors occured", "ERROR")
                    return False

        if bakemode == constants.BAKE_MODE_INPUTS_S2A:
            t = props.target_object
            if not t.data.vertex_colors:
                messages.append(f"You are trying to bake the active vertex colors, but {t.name} doesn't have vertex colors")
                show_message_box(messages, "Errors occured", "ERROR")
                return False

    if len(messages) != 0:
        show_message_box(messages, "Errors occured", "ERROR")
        return False

    return True


def process_uvs():
    original_uvs = {}
    current_bake_op = MasterOperation.bake_op

    if bpy.context.scene.TextureBake_Props.prefer_existing_uvmap:
        print_msg("We are preferring existing UV maps called TextureBake. Setting them to active")
        for obj in current_bake_op.bake_objects:
            if("TextureBake" in obj.data.uv_layers):
                obj.data.uv_layers["TextureBake"].active = True


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

    return True


def get_export_folder_name(initialise = False, relative = False):
    props = bpy.context.scene.TextureBake_Props
    folder = props.export_folder_name
    if props.export_datetime:
        now = datetime.datetime.now()
        folder += now.strftime("_%d%m%Y-%H%M")
    return folder


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

    current_bake_op = MasterOperation.bake_op

    # We want to control the bit depth, so we need a new scene
    scene = bpy.data.scenes.new('TextureBakeTempScene')
    settings = scene.render.image_settings

    # Color management settings
    dcm_opt = bpy.context.scene.TextureBake_Props.export_color_space
    if current_bake_op.bake_mode in [constants.BAKE_MODE_PBR, constants.BAKE_MODE_S2A] and (baketype == constants.PBR_DIFFUSE or baketype == constants.PBR_EMISSION) :
        if dcm_opt:
            print_msg("Applying color management settings from current scene for PBR diffuse or emission")
            apply_scene_col_settings(scene)
        else:
            print_msg("Applying standard color management for PBR diffuse or emission")
            scene.view_settings.view_transform = "Standard"

    elif current_bake_op.bake_mode in [constants.BAKE_MODE_PBR, constants.BAKE_MODE_S2A]:
        print_msg("Applying raw color space for PBR non-diffuse texture")
        scene.view_settings.view_transform = "Raw"
        scene.sequencer_colorspace_settings.name = "Non-Color"

    elif current_bake_op.bake_mode in [constants.BAKE_MODE_INPUTS, constants.BAKE_MODE_INPUTS_S2A]:
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
    elif (baketype == constants.PBR_NORMAL_DX or baketype == constants.PBR_NORMAL_OGL) and file_extension != "exr":
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

    links.new(img_n.outputs[0], composite_n.inputs[0])

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
    if bpy.context.scene.TextureBake_Props.export_folder_per_object and bpy.context.scene.TextureBake_Props.merged_bake and bpy.context.scene.TextureBake_Props.merged_bake_name != "":
        image.filepath = str(get_export_folder_name()) +"/" + bpy.context.scene.TextureBake_Props.merged_bake_name + "/" + image.name + "." + file_extension
    elif bpy.context.scene.TextureBake_Props.export_folder_per_object and obj != None:
        image.filepath = str(get_export_folder_name()) +"/" + obj.name + "/" + image.name + "." + file_extension
    else:
        image.filepath = str(get_export_folder_name()) +"/" + image.name + "." + file_extension

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
    elif originally_float and image["SB_thisbake"] == constants.PBR_DIFFUSE:
        image.colorspace_settings.name = "sRGB"

    return file_extension


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
        for node in nodetree.nodes:
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
def import_needed_specials_materials():
    ordered_specials = []
    path = os.path.dirname(__file__) + "/materials/materials.blend\\Material\\"
    if bpy.context.scene.TextureBake_Props.selected_thickness:
        if "TextureBake_" + constants.TEX_THICKNESS not in bpy.data.materials:
            material_name = "TextureBake_" + constants.TEX_THICKNESS
            bpy.ops.wm.append(filename=material_name, directory=path)
        ordered_specials.append(constants.TEX_THICKNESS)

    if bpy.context.scene.TextureBake_Props.selected_ao:
        if "TextureBake_" + constants.TEX_AO not in bpy.data.materials:
            material_name = "TextureBake_" + constants.TEX_AO
            bpy.ops.wm.append(filename=material_name, directory=path)
        ordered_specials.append(constants.TEX_AO)

    if bpy.context.scene.TextureBake_Props.selected_curvature:
        if "TextureBake" + constants.TEX_CURVATURE not in bpy.data.materials:
            material_name = "TextureBake_" + constants.TEX_CURVATURE
            bpy.ops.wm.append(filename=material_name, directory=path)
        ordered_specials.append(constants.TEX_CURVATURE)

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
    t = t / f"TextureBake_propgress_{os.getpid()}"
    with open(str(t), "w") as progfile:
        progfile.write(str(progress))


def write_baked_texture(texture_name):
    t = Path(tempfile.gettempdir())
    t = t / f"TextureBake_bakes_{os.getpid()}"
    with open(str(t), "a") as progfile:
        progfile.write(f"{texture_name}\n")


def read_baked_textures(pid):
    textures = []
    t = Path(tempfile.gettempdir()) / f"TextureBake_bakes_{str(pid)}"
    with open(str(t), "r") as texfile:
        textures = texfile.readlines()
        textures = [tex.rstrip() for tex in textures]
    return textures


# Dict obj name to tile
currentUDIMtile = {}
def focus_UDIM_tile(obj,desiredUDIMtile):
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


def scale_image_if_needed(img):
    print_msg("Scaling images if needed")

    context = bpy.context
    width = img.size[0]
    height = img.size[1]

    proposed_width = bpy.context.scene.TextureBake_Props.output_width
    proposed_height = bpy.context.scene.TextureBake_Props.output_height

    if width != proposed_width or height != proposed_height:
        img.scale(proposed_width, proposed_height)


def set_image_internal_col_space(image, thisbake):
    if thisbake != constants.PBR_DIFFUSE and thisbake != constants.PBR_EMISSION:
        image.colorspace_settings.name = "Non-Color"


def any_specials():
    return (bpy.context.scene.TextureBake_Props.selected_col_mats
        or bpy.context.scene.TextureBake_Props.selected_col_vertex
        or bpy.context.scene.TextureBake_Props.selected_ao
        or bpy.context.scene.TextureBake_Props.selected_thickness
        or bpy.context.scene.TextureBake_Props.selected_curvature)


def auto_set_bake_margin():
    context = bpy.context
    current_width = context.scene.TextureBake_Props.input_width
    context.scene.render.bake.margin = round((current_width / 1024) * 4)


def redraw_property_panel():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "PROPERTIES":
                area.tag_redraw()


def get_maps_to_bake():
    """Returns the maps that should be baked under the selected export preset"""
    uid = bpy.context.scene.TextureBake_Props.export_preset
    prefs = bpy.context.preferences.addons[__package__].preferences
    preset = [p for p in prefs.export_presets if p.uid == uid][0]

    maps = set()
    for texture in preset.textures:
        maps.add(texture.red.info)
        maps.add(texture.green.info)
        maps.add(texture.blue.info)
        maps.add(texture.alpha.info)
    maps = maps - {'NONE'}

    return list(maps)


def get_num_maps_to_bake():
    """Returns the number of maps that should be baked under the selected export preset"""
    return len(get_maps_to_bake())


def get_num_input_maps_to_bake():
    props = bpy.context.scene.TextureBake_Props
    total = 0

    if props.selected_thickness:
        total += 1
    if props.selected_ao:
        total += 1
    if props.selected_curvature:
        total += 1
    if props.selected_col_mats:
        total += 1
    if props.selected_col_vertex:
        total += 1

    return total


def replace_image(old_img, new_img):
    def traverse(tree, img_name):
        for node in tree.nodes:
            if hasattr(node, "node_tree"):
                yield from traverse(node.node_tree, img_name)
            if hasattr(node, "image"):
                if node.image and node.image.name == img_name:
                    yield node

    old_name = old_img.name
    if old_img.users:
        for mat in bpy.data.materials:
            if mat.use_nodes:
                for node in traverse(mat.node_tree, old_name):
                    node.image = new_img

    bpy.data.images.remove(old_img)
    new_img.name = old_name
