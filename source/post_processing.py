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
import tempfile
import shutil
import os
from pathlib import Path


def post_process(internal_img_name, mode="3to1", save=False, **args):
    # Import the compositing scene that we need
    path = os.path.dirname(__file__) + "/compositing/compositing.blend\\Scene\\"

    if mode == "1to1":
        if "TBCompositing_1to1" in bpy.data.scenes:
            bpy.data.scenes.remove(bpy.data.scenes["TBCompositing_1to1"])
        bpy.ops.wm.append(filename="TBCompositing_1to1", directory=path)

        scene = bpy.data.scenes["TBCompositing_1to1"]
        nodes = scene.node_tree.nodes

        # Set the input
        nodes["input_img"].image = args["input_img"]

        # The inverts all start muted
        if "invert_r" in args and args["invert_r"]: nodes["invert_r"].mute = False
        if "invert_g" in args and args["invert_g"]: nodes["invert_g"].mute = False
        if "invert_b" in args and args["invert_b"]: nodes["invert_b"].mute = False
        if "invert_a" in args and args["invert_a"]: nodes["invert_a"].mute = False
        if "invert_all" in args and args["invert_all"]: nodes["invert_all"].mute=False

    if mode == "3to1":
        if "TBCompositing_3to1" in bpy.data.scenes:
            bpy.data.scenes.remove(bpy.data.scenes["TBCompositing_3to1"])
        bpy.ops.wm.append(filename="TBCompositing_3to1", directory=path)

        scene = bpy.data.scenes["TBCompositing_3to1"]
        node_tree = scene.node_tree
        nodes = node_tree.nodes

        # Set the inputs
        if ("input_r" in args) and args["input_r"]!=None:
            nodes["input_r"].image = args["input_r"]
            input_r_orig_colspace = args["input_r"].colorspace_settings.name
            if args["file_format"] == "PNG":
                args["input_r"].colorspace_settings.name = "sRGB"

        if ("input_g" in args) and args["input_g"]!=None:
            nodes["input_g"].image = args["input_g"]
            input_g_orig_colspace = args["input_g"].colorspace_settings.name
            if args["file_format"] == "PNG":
                args["input_g"].colorspace_settings.name = "sRGB"

        if ("input_b" in args) and args["input_b"]!=None:
            nodes["input_b"].image = args["input_b"]
            input_b_orig_colspace = args["input_b"].colorspace_settings.name
            if args["file_format"] == "PNG":
                args["input_b"].colorspace_settings.name = "sRGB"

        if ("input_a" in args) and args["input_a"]!=None:
            nodes["input_a"].image = args["input_a"]
            input_a_orig_colspace = args["input_a"].colorspace_settings.name
            if args["file_format"] == "PNG":
                args["input_a"].colorspace_settings.name = "sRGB"

        # Clear the alpha connection unless we have an alpha texture
        if (not "input_a" in args) or args["input_a"]==None: node_tree.links.remove(nodes["Combine RGBA"].inputs[3].links[0])

        # Alpha Premul
        if "alpha_convert" in args and args["alpha_convert"] == "straight":
            nodes["alpha_convert"].mute = False
            nodes["alpha_convert"].mapping = "PREMUL_TO_STRAIGHT"
        elif "alpha_convert" in args and args["alpha_convert"] == "premul":
            nodes["alpha_convert"].mute = False
            nodes["alpha_convert"].mapping = "STRAIGHT_TO_PREMUL"

        # The inverts all start muted
        if "invert_r_input_r" in args and args["invert_r_input_r"]: nodes["invert_r_input_r"].mute = False
        if "invert_r_input_g" in args and args["invert_r_input_g"]: nodes["invert_r_input_g"].mute = False
        if "invert_r_input_b" in args and args["invert_r_input_b"]: nodes["invert_r_input_b"].mute = False
        if "invert_r_input_a" in args and args["invert_r_input_a"]: nodes["invert_r_input_a"].mute = False

        if "invert_g_input_r" in args and args["invert_g_input_r"]: nodes["invert_g_input_r"].mute = False
        if "invert_g_input_g" in args and args["invert_g_input_g"]: nodes["invert_g_input_g"].mute = False
        if "invert_g_input_b" in args and args["invert_g_input_b"]: nodes["invert_g_input_b"].mute = False
        if "invert_g_input_a" in args and args["invert_g_input_a"]: nodes["invert_g_input_a"].mute = False

        if "invert_b_input_r" in args and args["invert_b_input_r"]: nodes["invert_b_input_r"].mute = False
        if "invert_b_input_g" in args and args["invert_b_input_g"]: nodes["invert_b_input_g"].mute = False
        if "invert_b_input_b" in args and args["invert_b_input_b"]: nodes["invert_b_input_b"].mute = False
        if "invert_b_input_a" in args and args["invert_b_input_a"]: nodes["invert_b_input_a"].mute = False

        if "invert_a_input_r" in args and args["invert_a_input_r"]: nodes["invert_a_input_r"].mute = False
        if "invert_a_input_g" in args and args["invert_a_input_g"]: nodes["invert_a_input_g"].mute = False
        if "invert_a_input_b" in args and args["invert_a_input_b"]: nodes["invert_a_input_b"].mute = False
        if "invert_a_input_a" in args and args["invert_a_input_a"]: nodes["invert_a_input_a"].mute = False

        # Isolate the input channels
        if "isolate_input_r" in args and args["isolate_input_r"]:
            node_tree.links.remove(nodes["Combine RGBA.002"].inputs["G"].links[0])
            node_tree.links.remove(nodes["Combine RGBA.002"].inputs["B"].links[0])
            node_tree.links.remove(nodes["Combine RGBA.002"].inputs["A"].links[0])
            nodes["Combine RGBA.002"].mute=True
        if "isolate_input_g" in args and args["isolate_input_g"]:
            node_tree.links.remove(nodes["Combine RGBA.003"].inputs["R"].links[0])
            node_tree.links.remove(nodes["Combine RGBA.003"].inputs["B"].links[0])
            node_tree.links.remove(nodes["Combine RGBA.003"].inputs["A"].links[0])
            nodes["Combine RGBA.003"].mute=True
        if "isolate_input_b" in args and args["isolate_input_b"]:
            node_tree.links.remove(nodes["Combine RGBA.004"].inputs["R"].links[0])
            node_tree.links.remove(nodes["Combine RGBA.004"].inputs["G"].links[0])
            node_tree.links.remove(nodes["Combine RGBA.004"].inputs["A"].links[0])
            nodes["Combine RGBA.004"].mute=True

    # Disable the BW nodes
    if "mute_bws" in args and args["mute_bws"]:
        bw_nodes = [node for node in nodes if node.bl_idname == "CompositorNodeRGBToBW"]
        for node in bw_nodes:
            node.mute=True

    # Set the output resolution of the scene to the texture size we are using
    scene.render.resolution_y = bpy.context.scene.TextureBake_Props.input_height
    scene.render.resolution_x = bpy.context.scene.TextureBake_Props.input_width
    scene.render.filepath = tempfile.mkdtemp()
    scene.render.image_settings.file_format = "OPEN_EXR"
    bpy.ops.render.render(animation=False, write_still=True, use_viewport=False, scene=scene.name)

    # Reload the temp file into an internal image again
    img = bpy.data.images.load(scene.render.filepath+"."+"exr")
    img.colorspace_settings.name = "Non-Color"
    img.name = internal_img_name
    img.use_fake_user = True
    img.pack()

    # Delete the external tmp file
    shutil.rmtree(scene.render.filepath)

    if save:
        scene.render.filepath = str(args["path_dir"] / args["path_filename"])
        scene.render.image_settings.file_format = args["file_format"]
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.image_settings.compression = 0
        scene.render.image_settings.color_depth = args["color_depth"]
        if args["file_format"] == "OPEN_EXR":
            scene.render.image_settings.color_depth = "32"
        elif args["file_format"] in ["JPEG", "TARGA"]:
            scene.render.image_settings.color_depth = "8"

        # Save
        bpy.ops.render.render(animation=False, write_still=True, use_viewport=False, scene=scene.name)

    if mode == "3to1":
        # Restore original image color spaces
        if "input_r" in args and args["input_r"] != None: args["input_r"].colorspace_settings.name = input_r_orig_colspace
        if "input_g" in args and args["input_g"] != None: args["input_g"].colorspace_settings.name = input_g_orig_colspace
        if "input_b" in args and args["input_b"] != None: args["input_b"].colorspace_settings.name = input_b_orig_colspace
        if "input_a" in args and args["input_a"] != None: args["input_a"].colorspace_settings.name = input_a_orig_colspace

    # Delete the new scene
    bpy.data.scenes.remove(scene)
