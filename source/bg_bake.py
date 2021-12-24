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

#p list
#   object representing the OS process
#   bool copy object and apply
#   bool hide objects


class bgbake_ops():
    bgops_list = []
    bgops_list_last = []
    bgops_list_finished = []


def remove_dead():
    #Remove dead processes from current list
    for p in bgbake_ops.bgops_list:
        if p[0].poll() == 0:
            #if p[1] is True:
                #Only go to finished list if true (i.e. prepmesh was selected)
                #bgbake_ops.bgops_list_finished.append(p)

            bgbake_ops.bgops_list_finished.append(p)
            bgbake_ops.bgops_list.remove(p)

    return 1 #1 second timer


bpy.app.timers.register(remove_dead, persistent=True)


# def check_merged_bake_setting():

    # if bpy.context.scene.TextureBake_Props.advancedobjectselection:
        # if len(bpy.context.scene.TextureBake_Props.bakeobjs_advanced_list) < 2 and bpy.context.scene.TextureBake_Props.mergedBake == True:
            # bpy.context.scene.TextureBake_Props.mergedBake = False


    # else:
        # if len(bpy.context.selected_objects)<2 and bpy.context.scene.TextureBake_Props.mergedBake == True:
            # bpy.context.scene.TextureBake_Props.mergedBake = False

    # return 1 #1 second timer

# bpy.app.timers.register(check_merged_bake_setting, persistent=True)


def check_export_col_setting():
    if (bpy.context.scene.cycles.bake_type == "NORMAL" or not bpy.context.scene.TextureBake_Props.saveExternal) and bpy.context.scene.TextureBake_Props.exportcyclescolspace:
        bpy.context.scene.TextureBake_Props.exportcyclescolspace = False

    return 1 #1 second timer


bpy.app.timers.register(check_export_col_setting, persistent=True)
