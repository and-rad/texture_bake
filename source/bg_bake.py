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
import os


class background_bake_ops():
    bgops_list = []
    bgops_list_last = []
    bgops_list_finished = []


def remove_dead():
    # Remove dead processes from current list
    for p in background_bake_ops.bgops_list:
        if p[0].poll() == 0:
            background_bake_ops.bgops_list_finished.append(p)
            background_bake_ops.bgops_list.remove(p)
    return 1


def check_export_col_setting():
    if (bpy.context.scene.cycles.bake_type == "NORMAL" or not bpy.context.scene.TextureBake_Props.export_textures) and bpy.context.scene.TextureBake_Props.export_color_space:
        bpy.context.scene.TextureBake_Props.export_color_space = False
    return 1


bpy.app.timers.register(remove_dead, persistent=True)
bpy.app.timers.register(check_export_col_setting, persistent=True)
