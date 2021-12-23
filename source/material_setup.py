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
from .bake_operation import BakeOperation, MasterOperation

def find_node_from_label(label, nodes):
    for node in nodes:
        if node.label == label:
            return node

    return False

def find_isocket_from_identifier(idname, node):
    for inputsocket in node.inputs:
        if inputsocket.identifier == idname:
            return inputsocket

    return False

def find_osocket_from_identifier(idname, node):
    for outputsocket in node.outputs:
        if outputsocket.identifier == idname:
            return outputsocket

    return False

def make_link(f_node_label, f_node_ident, to_node_label, to_node_ident, nodetree):

    fromnode = find_node_from_label(f_node_label, nodetree.nodes)
    if(fromnode == False):
        return False
    fromsocket = find_osocket_from_identifier(f_node_ident, fromnode)
    tonode = find_node_from_label(to_node_label, nodetree.nodes)
    if(tonode == False):
        return False
    tosocket = find_isocket_from_identifier(to_node_ident, tonode)

    nodetree.links.new(fromsocket, tosocket)
    return True

def wipe_labels(nodes):
    for node in nodes:
        node.label = ""

def get_image_from_tag(thisbake, objname):

    current_bake_op = MasterOperation.current_bake_operation
    global_mode = current_bake_op.bake_mode

    objname = functions.untrunc_if_needed(objname)

    batch_name = bpy.context.scene.SimpleBake_Props.batchName

    result = []
    if current_bake_op.uv_mode == "udims":

        result = [img for img in bpy.data.images if\
            ("SB_objname" in img and img["SB_objname"] == objname) and\
            ("SB_batch" in img and img["SB_batch"] == batch_name) and\
            ("SB_globalmode" in img and img["SB_globalmode"] == global_mode) and\
            ("SB_thisbake" in img and img["SB_thisbake"] == thisbake) and\
            ("SB_udims" in img and img["SB_udims"])\
            ]
    else:
         result = [img for img in bpy.data.images if\
            ("SB_objname" in img and img["SB_objname"] == objname) and\
            ("SB_batch" in img and img["SB_batch"] == batch_name) and\
            ("SB_globalmode" in img and img["SB_globalmode"] == global_mode) and\
            ("SB_thisbake" in img and img["SB_thisbake"] == thisbake)\
            ]


    if len(result) > 0:
        return result[0]


    functions.printmsg(f"ERROR: No image with matching tag ({thisbake}) found for object {objname}");
    return False

def create_cyclesbake_setup(nodetree, obj):

    current_bake_op = MasterOperation.current_bake_operation


    if MasterOperation.merged_bake:
        name = MasterOperation.merged_bake_name
    else:
        name = obj.name.replace("_SimpleBake", "")
    nodes = nodetree.nodes

    #First we wipe out any existing nodes
    for node in nodes:
        nodes.remove(node)

    node = nodes.new("ShaderNodeBsdfPrincipled")
    node.location = (414, 6)
    node.label = "pnode"

    node = nodes.new("ShaderNodeTexImage")
    node.location = (270, -10)
    node.label = "emmision_tex"
    node.image = get_image_from_tag(current_bake_op.cycles_bake_type, name)

    node = nodes.new("ShaderNodeOutputMaterial")
    node.location = (813, 270)
    node.label = "monode"

    make_link("emmision_tex", "Color", "pnode", "Base Color", nodetree)
    make_link("pnode", "BSDF", "monode", "Surface", nodetree)

    wipe_labels(nodes)

        #Create node group if we want it
    if bpy.context.scene.SimpleBake_Props.createglTFnode:

        if "glTF Settings" not in bpy.data.node_groups:
            g = bpy.data.node_groups.new("glTF Settings", "ShaderNodeTree")
            #Create a group input (not sure we really need this)
            g.nodes.new("NodeGroupInput")
            #Create input socket
            g.inputs.new("NodeSocketFloat", "Occlusion")
        else:
            g = bpy.data.node_groups["glTF Settings"]


        #Create the node group material node
        n = nodes.new("ShaderNodeGroup")
        n.node_tree = bpy.data.node_groups["glTF Settings"]
        n.label = "glTF Settings"
        n.location = (659.0382690429688, 30.21734619140625)



# def create_colmap_setup(nodetree, obj):

    # if(bpy.context.scene.SimpleBake_Props.mergedBake):
        # obj_name = "MergedBake"
    # else:
        # obj_name = obj.name.replace("_SimpleBake", "")
    # nodes = nodetree.nodes

    # #First we wipe out any existing nodes
    # for node in nodes:
        # nodes.remove(node)

    # node = nodes.new("ShaderNodeEmission")
    # node.location = (414, 6)
    # node.label = "enode"

    # node = nodes.new("ShaderNodeTexImage")
    # node.location = (270, -10)
    # node.label = "emmision_tex"
    # node.image = bpy.data.images[obj_name + "_ColMap"]

    # node = nodes.new("ShaderNodeOutputMaterial")
    # node.location = (813, 270)
    # node.label = "monode"

    # make_link("emmision_tex", "Color", "enode", "Color", nodetree)
    # make_link("enode", "Emission", "monode", "Surface", nodetree)

    # wipe_labels(nodes)



def create_principled_setup(nodetree, obj):

    functions.printmsg("Creating principled material")

    #Take note of whether or not the images were saved externally
    save_external = bpy.context.scene.SimpleBake_Props.saveExternal

    nodes = nodetree.nodes

    if(bpy.context.scene.SimpleBake_Props.mergedBake):
        obj_name = bpy.context.scene.SimpleBake_Props.mergedBakeName
    else:
        obj_name = obj.name.replace("_SimpleBake", "")


    #First we wipe out any existing nodes
    for node in nodes:
        nodes.remove(node)


    #Now create the Principled BSDF
    pnode = nodes.new("ShaderNodeBsdfPrincipled")
    pnode.location = (212.270004, 359.531708)
    pnode.label = "pnode"


    #And the output node
    node = nodes.new("ShaderNodeOutputMaterial")
    node.location = (659.590027, 192.059998)
    node.label = "monode"

    if(bpy.context.scene.SimpleBake_Props.selected_emission):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, -87.645897)
        node.label = "emission_tex"
        image = get_image_from_tag("emission", obj_name)
        node.image = image

    #OpenGL Normal Map
    if(bpy.context.scene.SimpleBake_Props.selected_normal and bpy.context.scene.SimpleBake_Props.normal_format_switch == "opengl"):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, -374.788513)
        node.label = "normal_tex"
        image = get_image_from_tag("normal", obj_name)
        node.image = image

    #DirectX Normal Map
    if(bpy.context.scene.SimpleBake_Props.selected_normal and bpy.context.scene.SimpleBake_Props.normal_format_switch == "directx"):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-1087.9599609375, -374.78851318359375)
        node.label = "normal_tex"
        image = get_image_from_tag("normal", obj_name)
        node.image = image

        node = nodes.new("ShaderNodeSeparateRGB")
        node.location = (-767.9599609375, -315.6215515136719)
        node.hide = True
        node.label = "normal_RGBsep"

        node = nodes.new("ShaderNodeCombineRGB")
        node.location = (-343.26007080078125, -313.1299743652344)
        node.hide = True
        node.label = "normal_RGBcombine"

        node = nodes.new("ShaderNodeInvert")
        node.location = (-550.9630737304688, -476.3309631347656)
        node.hide = True
        node.label = "normal_Yinvert"

    if(bpy.context.scene.SimpleBake_Props.selected_alpha):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, -190.841217)
        node.label = "alpha_tex"
        image = get_image_from_tag("alpha", obj_name)
        node.image = image

    if(bpy.context.scene.SimpleBake_Props.selected_transrough):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 45.946487)
        node.label = "transmissionrough_tex"
        image = get_image_from_tag("transparencyroughness", obj_name)
        node.image = image

    if(bpy.context.scene.SimpleBake_Props.selected_trans):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 101.945831)
        node.label = "transmission_tex"
        image = get_image_from_tag("transparency", obj_name)
        node.image = image

    if(bpy.context.scene.SimpleBake_Props.selected_col):
        image = get_image_from_tag("diffuse", obj_name)
        #if functions.is_image_single_colour(image):
            #functions.printmsg("Single col detected")

        #functions.printmsg("Multi col detected")
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 612.749451)
        node.label = "col_tex"
        node.image = image


    #Roughness
    if(bpy.context.scene.SimpleBake_Props.selected_rough and bpy.context.scene.SimpleBake_Props.rough_glossy_switch == "rough"):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 411.958191)
        node.label = "roughness_tex"
        image = get_image_from_tag("roughness", obj_name)
        node.image = image

    #Glossy
    if(bpy.context.scene.SimpleBake_Props.selected_rough and bpy.context.scene.SimpleBake_Props.rough_glossy_switch == "glossy"):
        #We need an invert node
        node = nodes.new("ShaderNodeInvert")
        node.hide = True
        node.location = (-238.3250732421875, 344.98126220703125)
        node.label = "roughness_invert"

        #Now the image node
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 411.958191)
        node.label = "roughness_tex"
        image = get_image_from_tag("glossy", obj_name)
        node.image = image


    if(bpy.context.scene.SimpleBake_Props.selected_metal):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 521.816956)
        node.label = "metal_tex"
        image = get_image_from_tag("metalness", obj_name)
        node.image = image

    if(bpy.context.scene.SimpleBake_Props.selected_clearcoat):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 281.322052)
        node.label = "clearcoat_tex"
        image = get_image_from_tag("clearcoat", obj_name)
        node.image = image

    if(bpy.context.scene.SimpleBake_Props.selected_clearcoat_rough):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 224.522537)
        node.label = "clearcoatrough_tex"
        image = get_image_from_tag("clearcoatroughness", obj_name)
        node.image = image


    if(bpy.context.scene.SimpleBake_Props.selected_specular):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 472.24707)
        node.label = "specular_tex"
        image = get_image_from_tag("specular", obj_name)
        node.image = image

    if(bpy.context.scene.SimpleBake_Props.selected_sss):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-862.2991943359375, 375.0651550292969)
        node.label = "sss_tex"
        image = get_image_from_tag("sss", obj_name)
        node.image = image

    if(bpy.context.scene.SimpleBake_Props.selected_ssscol):
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-862.2991943359375, 327.94659423828125)
        node.label = "ssscol_tex"
        image = get_image_from_tag("ssscol", obj_name)
        node.image = image


#-----------------------------------------------------------------

    if(bpy.context.scene.SimpleBake_Props.selected_normal):

        node = nodes.new("ShaderNodeNormalMap")
        node.location = (-118.290894, -295.719452)
        node.label = "normalmap"



    make_link("emission_tex", "Color", "pnode", "Emission", nodetree)
    make_link("col_tex", "Color", "pnode", "Base Color", nodetree)
    make_link("metal_tex", "Color", "pnode", "Metallic", nodetree)

    if(bpy.context.scene.SimpleBake_Props.selected_rough and bpy.context.scene.SimpleBake_Props.rough_glossy_switch == "glossy"):
        #Need the invert for glossy
        make_link("roughness_tex", "Color", "roughness_invert", "Color", nodetree)
        make_link("roughness_invert", "Color", "pnode", "Roughness", nodetree)
    else:
        #Hook up directly
        make_link("roughness_tex", "Color", "pnode", "Roughness", nodetree)

    make_link("transmission_tex", "Color", "pnode", "Transmission", nodetree)
    make_link("transmissionrough_tex", "Color", "pnode", "Transmission Roughness", nodetree)

    #OpenGL Normal Map
    if(bpy.context.scene.SimpleBake_Props.selected_normal and bpy.context.scene.SimpleBake_Props.normal_format_switch == "opengl"):
        make_link("normal_tex", "Color", "normalmap", "Color", nodetree)
        make_link("normalmap", "Normal", "pnode", "Normal", nodetree)

    #DirectX Normal Map
    if(bpy.context.scene.SimpleBake_Props.selected_normal and bpy.context.scene.SimpleBake_Props.normal_format_switch == "directx"):
        make_link("normal_tex", "Color", "normal_RGBsep", "Image", nodetree)
        make_link("normal_RGBsep", "R", "normal_RGBcombine", "R", nodetree)
        make_link("normal_RGBsep", "B", "normal_RGBcombine", "B", nodetree)
        make_link("normal_RGBsep", "G", "normal_Yinvert", "Color", nodetree)
        make_link("normal_Yinvert", "Color", "normal_RGBcombine", "G", nodetree)
        make_link("normal_RGBcombine", "Image", "normalmap", "Color", nodetree)
        make_link("normalmap", "Normal", "pnode", "Normal", nodetree)


    make_link("clearcoat_tex", "Color", "pnode", "Clearcoat", nodetree)
    make_link("clearcoatrough_tex", "Color", "pnode", "Clearcoat Roughness", nodetree)
    make_link("specular_tex", "Color", "pnode", "Specular", nodetree)
    make_link("alpha_tex", "Color", "pnode", "Alpha", nodetree)

    make_link("sss_tex", "Color", "pnode", "Subsurface", nodetree)
    make_link("ssscol_tex", "Color", "pnode", "Subsurface Color", nodetree)

    make_link("pnode", "BSDF", "monode", "Surface", nodetree)

    wipe_labels(nodes)

    #glTF Settings Node

    #Create node group if we want it
    if bpy.context.scene.SimpleBake_Props.createglTFnode:

        if "glTF Settings" not in bpy.data.node_groups:
            g = bpy.data.node_groups.new("glTF Settings", "ShaderNodeTree")
            #Create a group input (not sure we really need this)
            g.nodes.new("NodeGroupInput")
            #Create input socket
            g.inputs.new("NodeSocketFloat", "Occlusion")
        else:
            g = bpy.data.node_groups["glTF Settings"]


        #Create the node group material node
        n = nodes.new("ShaderNodeGroup")
        n.node_tree = bpy.data.node_groups["glTF Settings"]
        n.label = "glTF Settings"
        n.location = (659.0382690429688, 30.21734619140625)





