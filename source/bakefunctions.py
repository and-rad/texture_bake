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
import random
import shutil
import sys
from pathlib import Path

from. import (
    constants,
    post_processing,
)

from .bake_operation import (
    BakeOperation,
    MasterOperation,
    BakeStatus,
)


def optimize():
    current_bake_op = MasterOperation.bake_op

    input_width = bpy.context.scene.TextureBake_Props.input_width
    input_height = bpy.context.scene.TextureBake_Props.input_height

    # Apparently small tile sizes are now always better for baking on CPU
    if bpy.context.scene.cycles.device == "CPU":
        bpy.context.scene.cycles.use_auto_tile = True
        bpy.context.scene.cycles.tile_size = 64
        functions.print_msg("Setting tile size to 64 for baking on CPU")

    # Otherwise, let's do what we've always done and optimise for GPU
    else:
        # Get the max tile size we are working with
        if(bpy.context.scene.TextureBake_Props.memory_limit == "Off"):
            bpy.context.scene.cycles.use_auto_tile = False
        else:
            bpy.context.scene.cycles.use_auto_tile = True
            maxtile = int(bpy.context.scene.TextureBake_Props.memory_limit)

            # Set x tile size to greater of input_width and maxtile
            if(input_width <= maxtile):
                bpy.context.scene.cycles.tile_size = input_width
            else:
                bpy.context.scene.cycles.tile_size = maxtile


        functions.print_msg(f"Setting tile size to {bpy.context.scene.cycles.tile_size} for baking on GPU")
        functions.print_msg("Reducing sample count to 16 for more efficient baking")
        bpy.context.scene.cycles.samples = 16


def common_bake_prep():
    # --------------Set Bake Operation Variables----------------------------

    current_bake_op = MasterOperation.bake_op

    functions.print_msg("==================================")
    functions.print_msg("--------Texture Bake Start--------")
    functions.print_msg(f"{current_bake_op.bake_mode}")
    functions.print_msg("==================================")

    # If this is a pbr bake, gather the selected maps
    if current_bake_op.bake_mode in {constants.BAKE_MODE_PBR, constants.BAKE_MODE_S2A}:
        current_bake_op.assemble_pbr_bake_list()

    # Record batch name
    MasterOperation.batch_name = bpy.context.scene.TextureBake_Props.batch_name

    # Set values based on viewport selection
    current_bake_op.bake_objects = bpy.context.selected_objects.copy()
    current_bake_op.active_object = bpy.context.active_object

    if bpy.context.scene.TextureBake_Props.use_object_list:
        current_bake_op.bake_objects = functions.advanced_object_selection_to_list()
    if bpy.context.scene.TextureBake_Props.target_object != None:
        current_bake_op.sb_target_object = bpy.context.scene.TextureBake_Props.target_object

    # Create a new collection, and add selected objects and target objects to it
    for c in bpy.data.collections:
        if "TextureBake_Working" in c.name:
            bpy.data.collections.remove(c)

    c = bpy.data.collections.new("TextureBake_Working")
    bpy.context.scene.collection.children.link(c)
    for obj in current_bake_op.bake_objects:
        if obj.name not in c:
            c.objects.link(obj)
    if bpy.context.scene.TextureBake_Props.target_object and bpy.context.scene.TextureBake_Props.target_object.name not in c.objects:
        c.objects.link(bpy.context.scene.TextureBake_Props.target_object)

    # Every object must have at least camera ray visibility
    for obj in current_bake_op.bake_objects:
        obj.visible_camera = True
    if bpy.context.scene.TextureBake_Props.target_object:
        bpy.context.scene.TextureBake_Props.target_object.visible_camera = True

    # Although starting checks will stop if no UVs, New UVs gets a pass so we need to be careful here
    if current_bake_op.sb_target_object != None:
        obj = current_bake_op.sb_target_object

    if bpy.context.scene.TextureBake_Props.uv_mode == "udims":
        current_bake_op.uv_mode = "udims"
    else:
        current_bake_op.uv_mode = "normal"

    # Force it to cycles
    bpy.context.scene.render.engine = 'CYCLES'

    # If this is a selected to active bake (PBR or cycles), turn it on
    if current_bake_op.bake_mode == constants.BAKE_MODE_S2A and bpy.context.scene.TextureBake_Props.selected_to_target:
        bpy.context.scene.render.bake.use_selected_to_active = True
        functions.print_msg(f"Setting ray distance to {round(bpy.context.scene.TextureBake_Props.ray_distance, 2)}")
        bpy.context.scene.render.bake.max_ray_distance = bpy.context.scene.TextureBake_Props.ray_distance
        functions.print_msg(f"Setting cage extrusion to {round(bpy.context.scene.TextureBake_Props.cage_extrusion, 2)}")
        bpy.context.scene.render.bake.cage_extrusion = bpy.context.scene.TextureBake_Props.cage_extrusion
    else:
        bpy.context.scene.render.bake.use_selected_to_active = False

    # If the user doesn't have a GPU, but has still set the render device to GPU, set it to CPU
    if not bpy.context.preferences.addons["cycles"].preferences.has_active_device():
        bpy.context.scene.cycles.device = "CPU"

    # Reset the UDIM counters to 0
    current_bake_op.udim_counter = 1001
    functions.currentUDIMtile = {}

    # If baking S2A, and the user has selected a cage object, there are extra steps to turn it on
    if bpy.context.scene.TextureBake_Props.selected_to_target:
        if bpy.context.scene.render.bake.cage_object:
            bpy.context.scene.render.bake.use_cage = False
        else:
            bpy.context.scene.render.bake.use_cage = True

    # Clear the trunc num for this session
    functions.trunc_num = 0
    functions.trunc_dict = {}

    bpy.context.scene.render.bake.use_clear = False

    # Do what we are doing with UVs (only if we are the primary op)
    functions.process_uvs()

    optimize()

    # Make sure the normal y setting is at default
    bpy.context.scene.render.bake.normal_g = "POS_Y"


def do_post_processing(thisbake, IMGNAME):
    functions.print_msg("Doing post processing")

    # DirectX vs OpenGL normal map format
    if thisbake == constants.PBR_NORMAL_DX:
        post_processing.post_process(
            internal_img_name="SB_Temp_Img",
            input_img=bpy.data.images[IMGNAME],
            mode="1to1",
            invert_g=True,
        )

        # Replace our existing image with the processed one
        old = bpy.data.images[IMGNAME]
        name = old.name
        new = bpy.data.images["SB_Temp_Img"]
        # Transfer tags
        new["SB_objname"] = old["SB_objname"]
        new["SB_batch"] = old["SB_batch"]
        new["SB_globalmode"] = old["SB_globalmode"]
        new["SB_thisbake"] = old["SB_thisbake"]
        new["SB_merged_bake_name"] = old["SB_merged_bake_name"]
        new["SB_udims"] = old["SB_udims"]

        # Remove from the MasterOp baked list
        MasterOperation.baked_textures.remove(old)
        bpy.data.images.remove(old)
        new.name = name

        # Add to master list
        MasterOperation.baked_textures.append(new)

    # Roughness vs Glossy
    if thisbake == constants.PBR_ROUGHNESS and bpy.context.scene.TextureBake_Props.rough_glossy_switch == "glossy":
        post_processing.post_process(
            internal_img_name="SB_Temp_Img",
            input_img=bpy.data.images[IMGNAME],
            mode="1to1",
            invert_all=True,
        )

        # Replace our existing image with the processed one
        old = bpy.data.images[IMGNAME]
        name = old.name
        new = bpy.data.images["SB_Temp_Img"]
        # Transfer tags
        new["SB_objname"] = old["SB_objname"]
        new["SB_batch"] = old["SB_batch"]
        new["SB_globalmode"] = old["SB_globalmode"]
        # new["SB_thisbake"] = old["SB_thisbake"]
        new["SB_merged_bake_name"] = old["SB_merged_bake_name"]
        new["SB_udims"] = old["SB_udims"]

        new["SB_thisbake"] = "glossy"

        # Remove from the MasterOp baked list
        MasterOperation.baked_textures.remove(old)
        bpy.data.images.remove(old)
        new.name = name

        # Change roughness alias to glossy alias
        prefs = bpy.context.preferences.addons[__package__].preferences
        proposed_name = IMGNAME.replace(prefs.roughness_alias, prefs.glossy_alias)
        if proposed_name in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[proposed_name])

        bpy.data.images[IMGNAME].name = proposed_name
        IMGNAME = proposed_name

        # Add to master list
        MasterOperation.baked_textures.append(new)


def channel_packing(objects):
    current_bake_op = MasterOperation.bake_op
    props = bpy.context.scene.TextureBake_Props

    # Figure out the save folder for each object
    efpo = props.export_folder_per_object
    mb = props.merged_bake
    mbn = props.merged_bake_name

    obj_export_folder_names = {}

    for obj in objects:
        if efpo and mb:
            export_folder_name = Path(str(functions.get_export_folder_name()) + "/" + mbn)
            obj_export_folder_names[obj.name] = export_folder_name
        elif efpo:
            export_folder_name = Path(str(functions.get_export_folder_name()) + "/" + obj.name)
            obj_export_folder_names[obj.name] = export_folder_name
        else:
            export_folder_name = Path(str(functions.get_export_folder_name()))
            obj_export_folder_names[obj.name] = export_folder_name

    baked_textures = MasterOperation.baked_textures
    prefs = bpy.context.preferences.addons[__package__].preferences
    preset_id = props.export_preset
    preset = ([p for p in prefs.export_presets if p.uid == preset_id])[0]

    for obj in objects:
        objname = obj.name
        if props.merged_bake:
            objname = props.merged_bake_name

        for tex in preset.textures:
            # Find the actual images that we need
            red = None
            if tex.red.info != 'NONE':
                red = [img for img in baked_textures if img["SB_thisbake"] == tex.red.info and img["SB_objname"] == objname][0]

            green = None
            if tex.green.info != 'NONE':
                green = [img for img in baked_textures if img["SB_thisbake"] == tex.green.info and img["SB_objname"] == objname][0]

            blue = None
            if tex.blue.info != 'NONE':
                blue = [img for img in baked_textures if img["SB_thisbake"] == tex.blue.info and img["SB_objname"] == objname][0]

            alpha = None
            if tex.alpha.info != 'NONE':
                alpha = [img for img in baked_textures if img["SB_thisbake"] == tex.alpha.info and img["SB_objname"] == objname][0]

            # Determine transparency mode
            alpha_convert = False
            file_format = tex.file_format
            if file_format == 'PNG' or file_format == 'TARGA':
                alpha_convert = "premul"

            # Create the texture
            imgname = functions.gen_export_texture_name(tex.name, objname)
            functions.print_msg(f"Creating packed texture {imgname} for object {objname} with format {file_format}")

            # Isolate
            if tex.red.info == 'DIFFUSE' and tex.green.info == 'DIFFUSE' and tex.blue.info == 'DIFFUSE':
                isolate_input_r=True
                isolate_input_g=True
                isolate_input_b=True
            else:
                isolate_input_r=False
                isolate_input_g=False
                isolate_input_b=False

            post_processing.post_process(
                internal_img_name = imgname,
                save = props.export_textures,
                mode = "3to1",
                input_r = red,
                input_g = green,
                input_b = blue,
                input_a = alpha,
                alpha_convert = alpha_convert,
                isolate_input_r = isolate_input_r,
                isolate_input_g = isolate_input_g,
                isolate_input_b = isolate_input_b,
                path_dir = obj_export_folder_names[obj.name],
                path_filename = Path(imgname),
                file_format = file_format,
            )

            functions.write_baked_texture(imgname)

            # Hacky - If this is a merged_bake, break out of the loop TODO: this looks like it belongs in the outer loop
            if props.merged_bake:
                break


def common_bake_finishing():
    # Run information
    current_bake_op = MasterOperation.bake_op

    # Reset the UDIM focus tile of all objects
    if current_bake_op.bake_mode in [constants.BAKE_MODE_S2A, constants.BAKE_MODE_INPUTS_S2A]:
        # This was some kind of S2A bake
        functions.focus_UDIM_tile(current_bake_op.sb_target_object, 0)
    elif bpy.context.scene.TextureBake_Props.selected_to_target:
        functions.focus_UDIM_tile(current_bake_op.sb_target_object, 0)

    else:
        for obj in current_bake_op.bake_objects:
            functions.focus_UDIM_tile(obj, 0)

    # Delete placeholder material
    if "TextureBake_Placeholder" in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials["TextureBake_Placeholder"])

    # If we baked specials, add the specials to the materials, but we won't hook them up
    if current_bake_op.bake_mode in [constants.BAKE_MODE_INPUTS, constants.BAKE_MODE_INPUTS_S2A]:
        # Not a merged bake
        if MasterOperation.merged_bake:
            nametag = "SB_merged_bake_name"
        else:
            nametag = "SB_objname"

        mats_done = []
        for obj in MasterOperation.prepared_mesh_objects:
            if MasterOperation.merged_bake:
                name = MasterOperation.merged_bake_name
            else:
                name = obj.name.replace("_Baked", "")

            image_list = [img for img in bpy.data.images \
                if nametag in img and "SB_globalmode" in img and  \
                img[nametag] == name and \
                img["SB_globalmode"] in [constants.BAKE_MODE_INPUTS, constants.BAKE_MODE_INPUTS_S2A] ]

            print(image_list)

            mat = obj.material_slots[0].material
            if mat.name not in mats_done:
                mats_done.append(mat.name)
                for img in image_list:
                    nodes = obj.material_slots[0].material.node_tree.nodes
                    node = nodes.new("ShaderNodeTexImage")
                    node.hide = True
                    node.image = img

    if "--background" in sys.argv:
        # for img in bpy.data.images:
            # if "SB_objname" in img:
                # img.pack()
        bpy.ops.wm.save_mainfile()

    # Remove the temp collection
    if "TextureBake_Working" in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections["TextureBake_Working"])


def specials_bake():
    functions.print_msg("Specials Bake")

    input_width = bpy.context.scene.TextureBake_Props.input_width
    input_height = bpy.context.scene.TextureBake_Props.input_height

    current_bake_op = MasterOperation.bake_op

    # If we are baking S2A as the primary bake, this should focus on the target object
    if current_bake_op.bake_mode == constants.BAKE_MODE_INPUTS_S2A:
        objects = [bpy.context.scene.TextureBake_Props.target_object]
    else:
        objects = current_bake_op.bake_objects

    # Firstly, let's bake the colid maps if they have been asked for
    if bpy.context.scene.TextureBake_Props.selected_col_mats:
        col_id_map(input_width, input_height, objects, constants.TEX_MAT_ID)
    if bpy.context.scene.TextureBake_Props.selected_col_vertex:
        col_id_map(input_width, input_height, objects, constants.TEX_VERT_COLOR)

    # Import the materials that we need, and save the returned list of specials
    ordered_specials = functions.import_needed_specials_materials()

    def specials_bake_actual():
        # Loop over the selected specials and bake them
        for special in ordered_specials:
            functions.print_msg(f"Baking {special}")

            # If we are doing a merged bake, just create one image here
            if(bpy.context.scene.TextureBake_Props.merged_bake):
                functions.print_msg("We are doing a merged bake")
                IMGNAME = functions.gen_image_name(bpy.context.scene.TextureBake_Props.merged_bake_name, special)

                # UDIMs
                if current_bake_op.uv_mode == "udims":
                    IMGNAME = IMGNAME+f".{udim_counter}"

                # TODO - May want to change the tag when can apply specials bakes
                functions.create_images(IMGNAME, special, bpy.context.scene.TextureBake_Props.merged_bake_name)

            for obj in objects:
                OBJNAME = obj.name

                # If we are not doing a merged bake, create the image to bake to
                if not bpy.context.scene.TextureBake_Props.merged_bake:
                    IMGNAME = functions.gen_image_name(OBJNAME, special)

                    # UDIMs
                    if current_bake_op.uv_mode == "udims":
                        IMGNAME = IMGNAME+f".{current_bake_op.udim_counter}"

                    # TODO - May want to change the tag when can apply specials bakes
                    functions.create_images(IMGNAME, special, obj.name)

                # Apply special material to all slots
                materials = obj.material_slots
                for matslot in materials:
                    name = matslot.name

                    # If we already copied the imported special material for this material, use that. If not, copy it and use that
                    if name + "_sbspectmp_" + special in bpy.data.materials:
                        matslot.material = bpy.data.materials[name + "_sbspectmp_" + special]
                    else:
                        newmat = bpy.data.materials["TextureBake_" + special].copy()
                        matslot.material = newmat
                        newmat.name = name + "_sbspectmp_" + special

                    # Create the image node and set to the bake texutre we are using
                    thismat = matslot.material
                    nodes = thismat.node_tree.nodes
                    imgnode = nodes.new("ShaderNodeTexImage")
                    imgnode.image = bpy.data.images[IMGNAME]
                    imgnode.label = "TextureBake"
                    functions.deselect_all_nodes(nodes)
                    imgnode.select = True
                    nodes.active = imgnode

                # Prior to bake, set image color space
                functions.set_image_internal_col_space(bpy.data.images[IMGNAME], special)

                # Bake this object
                functions.select_only_this(obj)
                functions.bake_operation("special", bpy.data.images[IMGNAME])

                # Scale if needed
                functions.sacle_image_if_needed(bpy.data.images[IMGNAME])

                # Update tracking
                BakeStatus.current_map+=1
                functions.print_msg(f"Bake maps {BakeStatus.current_map} of {BakeStatus.total_maps} complete")
                functions.write_bake_progress(BakeStatus.current_map, BakeStatus.total_maps)
                functions.write_baked_texture(IMGNAME)

                # Restore all materials
                for matslot in materials:
                    if "_sbspectmp_" + special in matslot.name:
                        matslot.material = bpy.data.materials[matslot.name.replace("_sbspectmp_" + special, "")]

    # Bake at least once
    specials_bake_actual()
    current_bake_op.udim_counter = current_bake_op.udim_counter + 1

    # If we are doing UDIMs, we need to go back in
    if current_bake_op.uv_mode == "udims":
        while current_bake_op.udim_counter < bpy.context.scene.TextureBake_Props.udim_tiles + 1001:
            functions.print_msg(f"Going back in for tile {current_bake_op.udim_counter}")
            for obj in objects:
                functions.focus_UDIM_tile(obj,current_bake_op.udim_counter - 1001)

            specials_bake_actual()
            current_bake_op.udim_counter = current_bake_op.udim_counter + 1

    # Delete the special placeholders
    for mat in bpy.data.materials:
        if "_sbspectmp_" in mat.name:
            bpy.data.materials.remove(mat)


def col_id_map(input_width, input_height, objects, mode="random"):
    current_bake_op = MasterOperation.bake_op

    functions.print_msg(f"Baking ColorID map")

    IMGNAME = ""
    merged_bake = bpy.context.scene.TextureBake_Props.merged_bake

    udim_counter = 1001# Exception to the rule?

    def col_id_map_actual():
        # If we are doing a merged bake, just create one image here
        if merged_bake:
            functions.print_msg("We are doing a merged bake")
            IMGNAME = functions.gen_image_name(bpy.context.scene.TextureBake_Props.merged_bake_name, f"{mode}")
            # UDIMs
            if current_bake_op.uv_mode == "udims":
                IMGNAME = IMGNAME+f".{udim_counter}"
            functions.create_images(IMGNAME, mode, bpy.context.scene.TextureBake_Props.merged_bake_name)

        for obj in objects:
            OBJNAME = functions.trunc_if_needed(obj.name)
            materials = obj.material_slots

            if not merged_bake:
                IMGNAME = functions.gen_image_name(OBJNAME, mode)
                if current_bake_op.uv_mode == "udims":
                    IMGNAME = IMGNAME+f".{udim_counter}"
                functions.create_images(IMGNAME, mode, obj.name)

            for matslot in materials:
                mat = bpy.data.materials.get(matslot.name)

                # Duplicate material to work on it
                functions.print_msg("Duplicating material")
                mat["SB_originalmat"] = mat.name
                dup = mat.copy()
                dup["SB_dupmat"] = mat.name
                matslot.material = dup
                # We want to work on dup from now on
                mat = dup
                mat.use_nodes = True

                nodetree = mat.node_tree
                nodes = nodetree.nodes
                links = nodetree.links

                m_output_node = functions.find_onode(nodetree)

                # Create emission shader and connect to material output
                emissnode = nodes.new("ShaderNodeEmission")
                emissnode.label = "TextureBake"
                fromsocket = emissnode.outputs[0]
                tosocket = m_output_node.inputs[0]
                nodetree.links.new(fromsocket, tosocket)

                if mode == constants.TEX_MAT_ID:
                    # Have we already generated a color for this mat?
                    if mat.name in current_bake_op.mat_col_dict:
                        col = current_bake_op.mat_col_dict[mat.name]
                        emissnode.inputs["Color"].default_value = (col[0], col[1], col[2], 1.0)
                    else:
                        r = random.random()
                        g = random.random()
                        b = random.random()
                        emissnode.inputs["Color"].default_value = (r, g, b, 1.0)
                        current_bake_op.mat_col_dict[mat.name] = [r, g, b]
                else:
                    # Using vertex colors
                    # Get name of active vertex colors for this object
                    col_name = obj.data.vertex_colors.active.name
                    # Create attribute node
                    attrnode = nodes.new("ShaderNodeAttribute")
                    # Set it to the active vertex cols
                    attrnode.attribute_name = col_name
                    # Connect
                    fromsocket = attrnode.outputs[0]
                    tosocket = emissnode.inputs[0]
                    nodetree.links.new(fromsocket, tosocket)

                # Create the image node and set to the bake texutre we are using
                imgnode = nodes.new("ShaderNodeTexImage")
                imgnode.image = bpy.data.images[IMGNAME]
                imgnode.label = "TextureBake"
                functions.deselect_all_nodes(nodes)
                imgnode.select = True
                nodetree.nodes.active = imgnode

            # Make sure only the object we want is selected (unless we are doing selected to active
            functions.select_only_this(obj)

            # Prior to bake set col space
            # if not MasterOperation.merged_bake:
            functions.set_image_internal_col_space(bpy.data.images[IMGNAME], "special")

            # Bake
            functions.bake_operation("Emission", bpy.data.images[IMGNAME])

            # Scale if needed
            functions.sacle_image_if_needed(bpy.data.images[IMGNAME])

            # Update tracking
            BakeStatus.current_map+=1
            functions.print_msg(f"Bake maps {BakeStatus.current_map} of {BakeStatus.total_maps} complete")
            functions.write_bake_progress(BakeStatus.current_map, BakeStatus.total_maps)
            functions.write_baked_texture(IMGNAME)

            # Restore the original materials
            functions.restore_all_materials()

    # Bake at least once
    col_id_map_actual()
    udim_counter = udim_counter + 1

    # If we are doing UDIMs, we need to go back in
    if current_bake_op.uv_mode == "udims":

        while udim_counter < bpy.context.scene.TextureBake_Props.udim_tiles + 1001:
            functions.print_msg(f"Going back in for tile {udim_counter}")
            for obj in objects:
                functions.focus_UDIM_tile(obj,udim_counter - 1001)

            col_id_map_actual()
            udim_counter = udim_counter + 1

    # Manually reset the UDIM tile. We don't run common finishing here, and we might end up going back to bake more specials
    for obj in current_bake_op.bake_objects:
        functions.focus_UDIM_tile(obj, 0)


def do_bake():
    current_bake_op = MasterOperation.bake_op

    # Loop over the bake modes we are using
    def do_bake_actual():
        IMGNAME = ""

        for thisbake in current_bake_op.pbr_selected_bake_types:
            # If we are doing a merged bake, just create one image here
            if(MasterOperation.merged_bake):
                functions.print_msg("We are doing a merged bake")
                IMGNAME = functions.gen_image_name(bpy.context.scene.TextureBake_Props.merged_bake_name, thisbake)

                # UDIM testing
                if current_bake_op.uv_mode == "udims":
                    IMGNAME = IMGNAME+f".{current_bake_op.udim_counter}"

                functions.create_images(IMGNAME, thisbake, bpy.context.scene.TextureBake_Props.merged_bake_name)

            for obj in current_bake_op.bake_objects:
                # Reset the already processed list
                mats_done = []

                functions.print_msg(f"Baking object: {obj.name}")

                # Truncate if needed from this point forward
                OBJNAME = functions.trunc_if_needed(obj.name)

                # If we are not doing a merged bake
                # Create the image we need for this bake (Delete if exists)
                if(not MasterOperation.merged_bake):
                    IMGNAME = functions.gen_image_name(obj.name, thisbake)

                    # UDIM testing
                    if current_bake_op.uv_mode == "udims":
                        IMGNAME = IMGNAME+f".{current_bake_op.udim_counter}"

                    functions.create_images(IMGNAME, thisbake, obj.name)

                # Prep the materials one by one
                materials = obj.material_slots
                for matslot in materials:
                    mat = bpy.data.materials.get(matslot.name)

                    if mat.name in mats_done:
                        functions.print_msg(f"Skipping material {mat.name}, already processed")
                        # Set the slot to the already created duplicate material and leave
                        dupmat = [m for m in bpy.data.materials if "SB_dupmat" in m and m["SB_dupmat"] == mat.name][0] # Should only be one
                        matslot.material = dupmat
                        continue
                    else:
                        mats_done.append(mat.name)

                    # Duplicate material to work on it
                    functions.print_msg("Duplicating material")
                    mat["SB_originalmat"] = mat.name
                    dup = mat.copy()
                    dup["SB_dupmat"] = mat.name
                    matslot.material = dup
                    # We want to work on dup from now on
                    mat = dup

                    # Make sure we are using nodes
                    if not mat.use_nodes:
                        functions.print_msg(f"Material {mat.name} wasn't using nodes. Have enabled nodes")
                        mat.use_nodes = True

                    nodetree = mat.node_tree
                    nodes = nodetree.nodes

                    # Create the image node and set to the bake texutre we are using
                    imgnode = nodes.new("ShaderNodeTexImage")
                    imgnode.image = bpy.data.images[IMGNAME]
                    imgnode.label = "TextureBake"

                    # Remove all disconnected nodes so don't interfere with typing the material
                    functions.remove_disconnected_nodes(nodetree)

                    # AO, normal, and emission require no further material prep
                    if(thisbake not in [constants.PBR_AO, constants.PBR_EMISSION, constants.PBR_NORMAL_DX, constants.PBR_NORMAL_OGL]):
                        # Work out what type of material we are dealing with here and take correct action
                        mat_type = functions.get_mat_type(nodetree)

                        if(mat_type == "MIX"):
                            functions.setup_mix_material(nodetree, thisbake)
                        elif(mat_type == "PURE_E"):
                            functions.setup_pure_e_material(nodetree, thisbake)
                        elif(mat_type == "PURE_P"):
                            functions.setup_pure_p_material(nodetree, thisbake)

                    # Last action before leaving this material, make the image node selected and active
                    functions.deselect_all_nodes(nodes)
                    imgnode.select = True
                    nodetree.nodes.active = imgnode

                # Select only this object
                functions.select_only_this(obj)
                functions.set_image_internal_col_space(bpy.data.images[IMGNAME], thisbake)

                # Bake the object for this bake mode
                functions.bake_operation(thisbake, bpy.data.images[IMGNAME])

                # Update tracking
                BakeStatus.current_map+=1
                functions.print_msg(f"Bake maps {BakeStatus.current_map} of {BakeStatus.total_maps} complete")
                functions.write_bake_progress(BakeStatus.current_map, BakeStatus.total_maps)
                functions.write_baked_texture(IMGNAME)

                # Restore the original materials
                functions.print_msg("Restoring original materials")
                functions.restore_all_materials()
                functions.print_msg("Restore complete")

                if not MasterOperation.merged_bake:
                    functions.sacle_image_if_needed(bpy.data.images[IMGNAME])
                    do_post_processing(thisbake=thisbake, IMGNAME=IMGNAME)

            # If we did a merged bake, and we are saving externally, then save here
            if MasterOperation.merged_bake:
                functions.sacle_image_if_needed(bpy.data.images[IMGNAME])
                do_post_processing(thisbake=thisbake, IMGNAME=IMGNAME)

    # Do the bake at least once
    do_bake_actual()
    current_bake_op.udim_counter = current_bake_op.udim_counter + 1

    # If we are doing UDIMs, we need to go back in
    if current_bake_op.uv_mode == "udims":

        while current_bake_op.udim_counter < bpy.context.scene.TextureBake_Props.udim_tiles + 1001:
            functions.print_msg(f"Going back in for tile {current_bake_op.udim_counter}")
            for obj in current_bake_op.bake_objects:
                functions.focus_UDIM_tile(obj,current_bake_op.udim_counter - 1001)

            do_bake_actual()

            current_bake_op.udim_counter = current_bake_op.udim_counter + 1


def do_bake_selected_to_target():
    current_bake_op = MasterOperation.bake_op

    # Info
    functions.print_msg("Baking PBR maps to target mesh: " + current_bake_op.sb_target_object.name)

    # Loop over the bake modes we are using
    def do_bake_selected_to_target_actual():
        IMGNAME = ""

        for thisbake in current_bake_op.pbr_selected_bake_types:
            # We just need the one image for each bake mode, created at the target object
            functions.print_msg("We are bakikng PBR maps to target mesh")
            IMGNAME = functions.gen_image_name(current_bake_op.sb_target_object.name, thisbake)

            # UDIM testing
            if current_bake_op.uv_mode == "udims":
                IMGNAME = IMGNAME+f".{current_bake_op.udim_counter}"

            functions.create_images(IMGNAME, thisbake, current_bake_op.sb_target_object.name)

            # Prep the target object
            materials = current_bake_op.sb_target_object.material_slots
            for matslot in materials:
                mat = bpy.data.materials.get(matslot.name)

                # First, check if the material is using nodes. If not, enable
                if not mat.use_nodes:
                    functions.print_msg(f"Material {mat.name} wasn't using nodes. Have enabled nodes")
                    mat.use_nodes = True

                nodetree = mat.node_tree
                nodes = nodetree.nodes

                # Create the image node and set to the bake texutre we are using
                imgnode = nodes.new("ShaderNodeTexImage")
                imgnode.image = bpy.data.images[IMGNAME]
                imgnode.label = "TextureBake"

                # Make the image node selected and active
                functions.deselect_all_nodes(nodes)
                imgnode.select = True
                nodetree.nodes.active = imgnode

            # Reset the already processed list before loop
            mats_done = []

            # Now prep all the objects for this bake mode
            for obj in current_bake_op.bake_objects:

                # Skip this if it is the target object
                if obj == current_bake_op.sb_target_object:
                    continue

                # Update
                functions.print_msg(f"Preparing object: {obj.name}")
                OBJNAME = functions.trunc_if_needed(obj.name)

                # Prep the materials one by one
                materials = obj.material_slots
                for matslot in materials:
                    mat = bpy.data.materials.get(matslot.name)

                    # Skip if in done list, else record in done list
                    if mat.name in mats_done:
                        functions.print_msg(f"Skipping material {mat.name}, already processed")
                        # Set the slot to the already created duplicate material and leave
                        dupmat = [m for m in bpy.data.materials if "SB_dupmat" in m and m["SB_dupmat"] == mat.name][0] # Should only be one
                        matslot.material = dupmat
                        continue

                    else:
                        mats_done.append(mat.name)

                    # Duplicate material to work on it
                    functions.print_msg("Duplicating material")
                    mat["SB_originalmat"] = mat.name
                    dup = mat.copy()
                    dup["SB_dupmat"] = mat.name
                    matslot.material = dup
                    # We want to work on dup from now on
                    mat = dup

                    nodetree = mat.node_tree
                    nodes = nodetree.nodes

                    # Remove all disconnected nodes so don't interfere with typing the material
                    functions.remove_disconnected_nodes(nodetree)

                    # Normal and emission bakes require no further material prep. Just skip the rest
                    if(thisbake not in [constants.PBR_EMISSION, constants.PBR_NORMAL_DX, constants.PBR_NORMAL_OGL]):
                        # Work out what type of material we are dealing with here and take correct action
                        mat_type = functions.get_mat_type(nodetree)

                        if(mat_type == "MIX"):
                            functions.setup_mix_material(nodetree, thisbake)
                        elif(mat_type == "PURE_E"):
                            functions.setup_pure_e_material(nodetree, thisbake)
                        elif(mat_type == "PURE_P"):
                            functions.setup_pure_p_material(nodetree, thisbake)

                # Make sure that correct objects are selected right before bake
                bpy.ops.object.select_all(action="DESELECT")
                for obj in current_bake_op.bake_objects:
                    obj.select_set(True)
                current_bake_op.sb_target_object.select_set(True)
                bpy.context.view_layer.objects.active = current_bake_op.sb_target_object

            # We are done with this image, set color space
            functions.set_image_internal_col_space(bpy.data.images[IMGNAME], thisbake)

            # Bake the object for this bake mode
            functions.bake_operation(thisbake, bpy.data.images[IMGNAME])

            # Update tracking
            BakeStatus.current_map+=1
            functions.print_msg(f"Bake maps {BakeStatus.current_map} of {BakeStatus.total_maps} complete")
            functions.write_bake_progress(BakeStatus.current_map, BakeStatus.total_maps)
            functions.write_baked_texture(IMGNAME)

            # Restore the original materials
            functions.restore_all_materials()

            # Delete that image node we created at the target object
            materials = current_bake_op.sb_target_object.material_slots
            for matslot in materials:
                mat = bpy.data.materials.get(matslot.name)
                for node in mat.node_tree.nodes:
                    if node.label == "TextureBake":
                        mat.node_tree.nodes.remove(node)

            functions.sacle_image_if_needed(bpy.data.images[IMGNAME])
            do_post_processing(thisbake=thisbake, IMGNAME=IMGNAME)

    # Do the bake at least once
    do_bake_selected_to_target_actual()
    current_bake_op.udim_counter = current_bake_op.udim_counter + 1

    # If we are doing UDIMs, we need to go back in
    if current_bake_op.uv_mode == "udims":

        while current_bake_op.udim_counter < bpy.context.scene.TextureBake_Props.udim_tiles + 1001:
            functions.print_msg(f"Going back in for tile {current_bake_op.udim_counter}")
            for obj in current_bake_op.bake_objects:
                functions.focus_UDIM_tile(current_bake_op.sb_target_object,current_bake_op.udim_counter - 1001)

            do_bake_selected_to_target_actual()
            current_bake_op.udim_counter = current_bake_op.udim_counter + 1
