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


class TextureBakeConstants:
    # Constants
    PBR = "PBR"
    PBRS2A = "PBR StoA"
    SPECIALS = "Specials"
    SPECIALS_PBR_TARGET_ONLY = "specials_pbr_targetonly"

    # Specials names
    THICKNESS = "Thickness"
    CURVATURE = "Curvature"
    COLORID = "Color ID"
    VERTEXCOL = "Vertex Color"


class BakeOperation:
    def __init__(self):
        self.udim_counter = 0

        # Mapping of object name to active UVs
        self.bake_mode = TextureBakeConstants.PBR
        self.bake_objects = []
        self.active_object = None
        self.sb_target_object = None

        # normal, udims
        self.uv_mode = "normal"

        # pbr stuff
        self.pbr_selected_bake_types = []

        # ColIdmap stuff
        self.used_cols = [] #[[r,g,b],[r,g,b],[r,g,b]]
        self.mat_col_dict = {} #{matname, [r,g,b]

    def assemble_pbr_bake_list(self):
        self.pbr_selected_bake_types = functions.get_maps_to_bake()


class MasterOperation:
    current_bake_operation = None
    total_bake_operations = 0
    this_bake_operation_num = 0

    orig_UVs_dict = {}
    baked_textures = []
    prepared_mesh_objects = []

    merged_bake = False
    merged_bake_name = ""
    batch_name = ""

    orig_s2A = False
    orig_objects = []
    orig_active_object = ""
    orig_engine = "CYCLES"
    orig_sample_count = 0
    orig_tile_size = 0

    orig_textures_folder = False

    def clear():
        MasterOperation.orig_UVs_dict = {}
        MasterOperation.total_bake_operations = 0
        MasterOperation.current_bake_operation = None
        MasterOperation.this_bake_operation_num = 0
        MasterOperation.prepared_mesh_objects = []
        MasterOperation.baked_textures = []
        MasterOperation.merged_bake = False
        MasterOperation.merged_bake_name = ""
        MasterOperation.batch_name = ""
        MasterOperation.orig_s2A = False
        MasterOperation.orig_objects = []
        MasterOperation.orig_active_object = ""
        MasterOperation.orig_engine = "CYCLES"
        MasterOperation.orig_sample_count = 0
        MasterOperation.orig_textures_folder = False


class BakeStatus:
    total_maps = 0
    current_map = 0
