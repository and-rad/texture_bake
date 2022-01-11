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

from . import (
    constants,
    functions,
)

from .bake_operation import (
    BakeOperation,
    MasterOperation,
)


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
    if fromnode == False:
        return
    fromsocket = find_osocket_from_identifier(f_node_ident, fromnode)
    tonode = find_node_from_label(to_node_label, nodetree.nodes)
    if tonode == False:
        return
    tosocket = find_isocket_from_identifier(to_node_ident, tonode)
    nodetree.links.new(fromsocket, tosocket)


def wipe_labels(nodes):
    for node in nodes:
        node.label = ""


def get_image_from_tag(thisbake, objname):
    current_bake_op = MasterOperation.bake_op
    global_mode = current_bake_op.bake_mode
    objname = functions.untrunc_if_needed(objname)
    batch_name = bpy.context.scene.TextureBake_Props.batch_name
    results = []
    if current_bake_op.uv_mode == "udims":
        results = [img for img in bpy.data.images if\
            ("SB_objname" in img and img["SB_objname"] == objname) and\
            ("SB_batch" in img and img["SB_batch"] == batch_name) and\
            ("SB_globalmode" in img and img["SB_globalmode"] == global_mode) and\
            ("SB_thisbake" in img and img["SB_thisbake"] == thisbake) and\
            ("SB_udims" in img and img["SB_udims"])\
        ]
    else:
         results = [img for img in bpy.data.images if\
            ("SB_objname" in img and img["SB_objname"] == objname) and\
            ("SB_batch" in img and img["SB_batch"] == batch_name) and\
            ("SB_globalmode" in img and img["SB_globalmode"] == global_mode) and\
            ("SB_thisbake" in img and img["SB_thisbake"] == thisbake)\
        ]

    if results:
        return results[0]

    functions.print_msg(f"ERROR: No image with matching tag ({thisbake}) found for object {objname}");
    return False


def create_principled_setup(nodetree, obj):
    functions.print_msg("Creating principled material")

    if(bpy.context.scene.TextureBake_Props.merged_bake):
        obj_name = bpy.context.scene.TextureBake_Props.merged_bake_name
    else:
        obj_name = obj.name.replace("_TextureBake", "")

    # First we wipe out any existing nodes
    nodes = nodetree.nodes
    for node in nodes:
        nodes.remove(node)

    # Now create the Principled BSDF
    pnode = nodes.new("ShaderNodeBsdfPrincipled")
    pnode.location = (212.270004, 359.531708)
    pnode.label = "pnode"

    # And the output node
    node = nodes.new("ShaderNodeOutputMaterial")
    node.location = (659.590027, 192.059998)
    node.label = "monode"

    maps = functions.get_maps_to_bake()
    if constants.PBR_EMISSION in maps:
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, -87.645897)
        node.label = "emission_tex"
        image = get_image_from_tag(constants.PBR_EMISSION, obj_name)
        node.image = image

    # OpenGL Normal Map
    if constants.PBR_NORMAL_OGL in maps:
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, -374.788513)
        node.label = "normal_tex"
        image = get_image_from_tag(constants.PBR_NORMAL_OGL, obj_name)
        node.image = image

    # DirectX Normal Map
    if constants.PBR_NORMAL_DX in maps:
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-1087.9599609375, -374.78851318359375)
        node.label = "normal_tex"
        image = get_image_from_tag(constants.PBR_NORMAL_DX, obj_name)
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

    if constants.PBR_OPACITY in maps:
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, -190.841217)
        node.label = "alpha_tex"
        image = get_image_from_tag(constants.PBR_OPACITY, obj_name)
        node.image = image

    if constants.PBR_TRANSMISSION_ROUGH in maps:
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 45.946487)
        node.label = "transmissionrough_tex"
        image = get_image_from_tag(constants.PBR_TRANSMISSION_ROUGH, obj_name)
        node.image = image

    if constants.PBR_TRANSMISSION in maps:
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 101.945831)
        node.label = "transmission_tex"
        image = get_image_from_tag(constants.PBR_TRANSMISSION, obj_name)
        node.image = image

    if constants.PBR_DIFFUSE in maps:
        image = get_image_from_tag(constants.PBR_DIFFUSE, obj_name)
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 612.749451)
        node.label = "col_tex"
        node.image = image

    # Roughness
    if constants.PBR_ROUGHNESS in maps and bpy.context.scene.TextureBake_Props.rough_glossy_switch == "rough":
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 411.958191)
        node.label = "roughness_tex"
        image = get_image_from_tag(constants.PBR_ROUGHNESS, obj_name)
        node.image = image

    # Glossy
    if constants.PBR_ROUGHNESS in maps and bpy.context.scene.TextureBake_Props.rough_glossy_switch == "glossy":
        # We need an invert node
        node = nodes.new("ShaderNodeInvert")
        node.hide = True
        node.location = (-238.3250732421875, 344.98126220703125)
        node.label = "roughness_invert"

        # Now the image node
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 411.958191)
        node.label = "roughness_tex"
        image = get_image_from_tag(constants.PBR_GLOSSY, obj_name)
        node.image = image

    if constants.PBR_METAL in maps:
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 521.816956)
        node.label = "metal_tex"
        image = get_image_from_tag(constants.PBR_METAL, obj_name)
        node.image = image

    if constants.PBR_CLEARCOAT in maps:
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 281.322052)
        node.label = "clearcoat_tex"
        image = get_image_from_tag(constants.PBR_CLEARCOAT, obj_name)
        node.image = image

    if constants.PBR_CLEARCOAT_ROUGH in maps:
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 224.522537)
        node.label = "clearcoatrough_tex"
        image = get_image_from_tag(constants.PBR_CLEARCOAT_ROUGH, obj_name)
        node.image = image

    if constants.PBR_SPECULAR in maps:
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-566.83667, 472.24707)
        node.label = "specular_tex"
        image = get_image_from_tag(constants.PBR_SPECULAR, obj_name)
        node.image = image

    if constants.PBR_SSS in maps:
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-862.2991943359375, 375.0651550292969)
        node.label = "sss_tex"
        image = get_image_from_tag(constants.PBR_SSS, obj_name)
        node.image = image

    if constants.PBR_SSS_COL in maps:
        node = nodes.new("ShaderNodeTexImage")
        node.hide = True
        node.location = (-862.2991943359375, 327.94659423828125)
        node.label = "ssscol_tex"
        image = get_image_from_tag(constants.PBR_SSS_COL, obj_name)
        node.image = image

    if constants.PBR_NORMAL_OGL in maps or constants.PBR_NORMAL_DX in maps:
        node = nodes.new("ShaderNodeNormalMap")
        node.location = (-118.290894, -295.719452)
        node.label = "normalmap"

    make_link("emission_tex", "Color", "pnode", "Emission", nodetree)
    make_link("col_tex", "Color", "pnode", "Base Color", nodetree)
    make_link("metal_tex", "Color", "pnode", "Metallic", nodetree)

    if constants.PBR_ROUGHNESS in maps and bpy.context.scene.TextureBake_Props.rough_glossy_switch == "glossy":
        # Need the invert for glossy
        make_link("roughness_tex", "Color", "roughness_invert", "Color", nodetree)
        make_link("roughness_invert", "Color", "pnode", "Roughness", nodetree)
    else:
        # Hook up directly
        make_link("roughness_tex", "Color", "pnode", "Roughness", nodetree)

    make_link("transmission_tex", "Color", "pnode", "Transmission", nodetree)
    make_link("transmissionrough_tex", "Color", "pnode", "Transmission Roughness", nodetree)

    # OpenGL Normal Map
    if constants.PBR_NORMAL_OGL in maps:
        make_link("normal_tex", "Color", "normalmap", "Color", nodetree)
        make_link("normalmap", "Normal", "pnode", "Normal", nodetree)

    # DirectX Normal Map
    if constants.PBR_NORMAL_OGL in maps:
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
