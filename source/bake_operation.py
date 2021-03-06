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


class BakeOperation:
    def __init__(self):
        self.udim_counter = 0

        # Mapping of object name to active UVs
        self.bake_mode = ""
        self.bake_objects = []
        self.active_object = None
        self.sb_target_object = None
        self.bake_udims = False

        # pbr stuff
        self.pbr_selected_bake_types = []

        # Material id map stuff
        self.mat_col_dict = {} #{matname, [r,g,b]

    def assemble_pbr_bake_list(self):
        self.pbr_selected_bake_types = functions.get_maps_to_bake()


class MasterOperation:
    bake_op = None

    baked_textures = []
    prepared_mesh_objects = []

    merged_bake = False
    merged_bake_name = ""
    batch_name = ""

    def clear():
        MasterOperation.bake_op = None
        MasterOperation.prepared_mesh_objects = []
        MasterOperation.baked_textures = []
        MasterOperation.merged_bake = False
        MasterOperation.merged_bake_name = ""
        MasterOperation.batch_name = ""


class BakeStatus:
    total_maps = 0
    current_map = 0
