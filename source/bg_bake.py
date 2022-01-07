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
import tempfile
from pathlib import Path
from . import functions


class background_bake_ops():
    bgops_list = []
    bgops_list_last = []
    bgops_list_finished = []


class BackgroundBakeParams:
    def __init__(self, proc, name, cp_obj, hide_src):
        self.process = proc
        self.name = name if name else "Untitled"
        self.copy_objects = cp_obj
        self.hide_source = hide_src
        self.progress = 0


def refresh_bake_progress():
    """Updates baking progress for all active background bake processes"""
    if not background_bake_ops.bgops_list:
        bpy.app.timers.unregister(refresh_bake_progress)
        return None

    for p in background_bake_ops.bgops_list:
        t = Path(tempfile.gettempdir())
        t = t / f"TextureBake_background_bake_{str(p.process.pid)}"
        try:
            with open(str(t), "r") as progfile:
                p.progress = int(progfile.readline())
        except:
            pass

        if p.process.poll() == 0:
            background_bake_ops.bgops_list_finished.append(p)
            background_bake_ops.bgops_list.remove(p)

    functions.redraw_property_panel()
    return 1


def check_export_col_setting():
    if (bpy.context.scene.cycles.bake_type == "NORMAL" or not bpy.context.scene.TextureBake_Props.export_textures) and bpy.context.scene.TextureBake_Props.export_color_space:
        bpy.context.scene.TextureBake_Props.export_color_space = False
    return 1


def clean_object_list():
    """Removes deleted objects from the list of objects to bake"""
    object_list = bpy.context.scene.TextureBake_Props.object_list
    old_size = len(object_list)
    for i in range(old_size-1, -1, -1):
        item = object_list[i]
        if item.obj is None or not item.obj.users_scene:
            object_list.remove(i)

    new_size = len(object_list)
    if old_size != new_size:
        functions.redraw_property_panel()

    return 1


bpy.app.timers.register(check_export_col_setting, persistent=True)
bpy.app.timers.register(clean_object_list, persistent=True)
