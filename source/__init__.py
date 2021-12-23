bl_info = {
    "name": "SimpleBake",
    "author": "Lewis <Contact via Blender Market or BLENDERender>",
    "version": (1, 2, 8),
    "blender": (3, 0, 0),
    "location": "Properties Panel -> Render Settings Tab",
    "description": "Simple baking of PBR maps",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Object",
}



import bpy
import os
import signal
from . import bakefunctions
from . import functions
from . import bg_bake
from pathlib import Path
from bpy.types import PropertyGroup
from .bake_operation import BakeOperation, SimpleBakeConstants


#Import classes
from .operators import(
    OBJECT_OT_simple_bake_mapbake,
    OBJECT_OT_simple_bake_sketchfabupload,
    OBJECT_OT_simple_bake_selectall,
    OBJECT_OT_simple_bake_selectnone,
    OBJECT_OT_simple_bake_installupdate,
    OBJECT_OT_simple_bake_default_imgname_string,
    OBJECT_OT_simple_bake_default_aliases,
    OBJECT_OT_simple_bake_bgbake_status,
    OBJECT_OT_simple_bake_bgbake_import,
    OBJECT_OT_simple_bake_bgbake_delete_individual,
    OBJECT_OT_simple_bake_bgbake_import_individual,
    OBJECT_OT_simple_bake_bgbake_clear,
    OBJECT_OT_simple_bake_protect_clear,
    OBJECT_OT_simple_bake_import_special_mats,
    OBJECT_OT_simple_bake_preset_save,
    OBJECT_OT_simple_bake_preset_load,
    OBJECT_OT_simple_bake_preset_refresh,
    OBJECT_OT_simple_bake_preset_delete,
    OBJECT_OT_simple_bake_show_all,
    OBJECT_OT_simple_bake_hide_all,
    OBJECT_OT_simple_bake_increase_texture_res,
    OBJECT_OT_simple_bake_decrease_texture_res,
    OBJECT_OT_simple_bake_increase_output_res,
    OBJECT_OT_simple_bake_decrease_output_res,
    OBJECT_OT_simple_bake_cptex_add,
    OBJECT_OT_simple_bake_cptex_delete,
    OBJECT_OT_simple_bake_cptex_setdefaults,
    OBJECT_OT_simple_bake_popnodegroups
    )
from .ui import (
    OBJECT_PT_simple_bake_panel,
    OBJECT_PT_simple_bake_panel,
    SimpleBakePreferences,
    OBJECT_OT_simple_bake_releasenotes,
    ListItem,
    BAKEOBJECTS_UL_List,
    LIST_OT_NewItem,
    LIST_OT_DeleteItem,
    LIST_OT_MoveItem,
    LIST_OT_ClearAll,
    LIST_OT_Refresh,
    PRESETS_UL_List,
    CPTEX_UL_List,
    PresetItem,
    CPTexItem
    
    )            

#Classes list for register
#List of all classes that will be registered
classes = ([
    OBJECT_OT_simple_bake_mapbake,
    OBJECT_OT_simple_bake_sketchfabupload,
    OBJECT_OT_simple_bake_selectall,
    OBJECT_OT_simple_bake_selectnone,
    OBJECT_OT_simple_bake_installupdate,
    OBJECT_PT_simple_bake_panel,
    OBJECT_OT_simple_bake_releasenotes,
    SimpleBakePreferences,
    OBJECT_OT_simple_bake_default_imgname_string, 
    OBJECT_OT_simple_bake_default_aliases,
    OBJECT_OT_simple_bake_bgbake_status,
    OBJECT_OT_simple_bake_bgbake_import,
    OBJECT_OT_simple_bake_bgbake_delete_individual,
    OBJECT_OT_simple_bake_bgbake_import_individual,
    OBJECT_OT_simple_bake_bgbake_clear,
    OBJECT_OT_simple_bake_protect_clear,
    ListItem,
    BAKEOBJECTS_UL_List,
    LIST_OT_NewItem,
    LIST_OT_DeleteItem,
    LIST_OT_MoveItem,
    LIST_OT_ClearAll,
    LIST_OT_Refresh,
    OBJECT_OT_simple_bake_import_special_mats,
    OBJECT_OT_simple_bake_preset_save,
    OBJECT_OT_simple_bake_preset_load,
    OBJECT_OT_simple_bake_preset_refresh,
    PresetItem,
    CPTexItem,
    PRESETS_UL_List,
    OBJECT_OT_simple_bake_preset_delete,
    OBJECT_OT_simple_bake_show_all,
    OBJECT_OT_simple_bake_hide_all,
    OBJECT_OT_simple_bake_increase_texture_res,
    OBJECT_OT_simple_bake_decrease_texture_res,
    OBJECT_OT_simple_bake_increase_output_res,
    OBJECT_OT_simple_bake_decrease_output_res,
    OBJECT_OT_simple_bake_cptex_add,
    OBJECT_OT_simple_bake_cptex_delete,
    CPTEX_UL_List,
    OBJECT_OT_simple_bake_cptex_setdefaults,
    OBJECT_OT_simple_bake_popnodegroups
    ])




def ShowMessageBox(message = "", title = "Message Box", icon = 'INFO'):

    def draw(self, context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)


#---------------------UPDATE FUNCTIONS--------------------------------------------

def tex_per_mat_update(self, context):
    if context.scene.SimpleBake_Props.tex_per_mat == True:
        context.scene.SimpleBake_Props.prepmesh = False
        context.scene.SimpleBake_Props.hidesourceobjects = False
        #context.scene.SimpleBake_Props.mergedBake = False
        context.scene.SimpleBake_Props.expand_mat_uvs = False
        
    
def expand_mat_uvs_update(self, context):
    context.scene.SimpleBake_Props.newUVoption = False
    context.scene.SimpleBake_Props.prefer_existing_sbmap = False

def prepmesh_update(self, context):
    if context.scene.SimpleBake_Props.prepmesh == False:
        context.scene.SimpleBake_Props.hidesourceobjects = False
        bpy.context.scene.SimpleBake_Props.createglTFnode = False
    else:
        context.scene.SimpleBake_Props.hidesourceobjects = True
    
def exportfileformat_update(self,context):
    if context.scene.SimpleBake_Props.exportfileformat == "JPEG" or context.scene.SimpleBake_Props.exportfileformat == "TARGA":
        context.scene.SimpleBake_Props.everything16bit = False
    
def s2a_update(self, context):
    #bpy.context.scene.SimpleBake_Props.mergedBake = False
    pass
    
def saveExternal_update(self, context):
    if bpy.context.scene.SimpleBake_Props.saveExternal == False:
        bpy.context.scene.SimpleBake_Props.everything16bit = False
        bpy.context.scene.SimpleBake_Props.rundenoise = False
        bpy.context.scene.SimpleBake_Props.selected_lightmap_denoise = False
        bpy.context.scene.SimpleBake_Props.exportFolderPerObject = False
        
        bpy.context.scene.SimpleBake_Props.uv_mode = "normal"

    else:
        pass
        #bpy.context.scene.SimpleBake_Props.everything32bitfloat = False
        
def repackUVs_update(self, context):
    pass

def newUVoption_update(self, context):
    if bpy.context.scene.SimpleBake_Props.newUVoption == True:
        bpy.context.scene.SimpleBake_Props.prefer_existing_sbmap = False
        #bpy.context.scene.repackUVs = False
        
def prefer_existing_sbmap_update(self, context):
    pass
        

def mergedBake_update(self, context):
    #if bpy.context.scene.SimpleBake_Props.newUVmethod == "SmartUVProject_Individual" and bpy.context.scene.SimpleBake_Props.mergedBake:
        #ShowMessageBox("This combination of options probably isn't what you want. You are unwrapping multiple objects individually, and then baking them all to one texture. The bakes will be on top of each other.", "Warning", "MONKEY")
    pass

def newUVmethod_update(self, context):
    pass
    #if bpy.context.scene.SimpleBake_Props.newUVmethod == "SmartUVProject_Individual" and bpy.context.scene.SimpleBake_Props.mergedBake:
        #ShowMessageBox("This combination of options probably isn't what you want. You are unwrapping multiple objects individually, and then baking them all to one texture. The bakes will be on top of each other.", "Warning", "MONKEY")


def global_mode_update(self, context):
    
    if not bpy.context.scene.SimpleBake_Props.global_mode == "cycles_bake":
        bpy.context.scene.SimpleBake_Props.tex_per_mat = False
        bpy.context.scene.SimpleBake_Props.expand_mat_uvs = False
        bpy.context.scene.SimpleBake_Props.cycles_s2a = False
        bpy.context.scene.SimpleBake_Props.targetobj_cycles = None
    
    if not bpy.context.scene.SimpleBake_Props.global_mode == "pbr_bake":
        bpy.context.scene.SimpleBake_Props.selected_s2a = False
        bpy.context.scene.SimpleBake_Props.selected_lightmap_denoise = False
        bpy.context.scene.SimpleBake_Props.targetobj = None

def cycles_s2a_update(self, context):
    if context.scene.SimpleBake_Props.cycles_s2a:
        #context.scene.SimpleBake_Props.mergedBake = False  
        pass
        
def bgbake_update(self,context):
    pass
    
    
def uv_mode_update(self, context):
    if context.scene.SimpleBake_Props.uv_mode == "udims":
        context.scene.SimpleBake_Props.newUVoption = False
        
        
def exportcyclescolspace_update(self, context):
    pass
 
          
def presets_list_update(self,context):
    
    index = context.scene.SimpleBake_Props.presets_list_index
    item = context.scene.SimpleBake_Props.presets_list[index]
    
    context.scene.SimpleBake_Props.preset_name = item.name
    
def presets_show_update(self,context):
    bpy.ops.object.simple_bake_preset_refresh()
 
def imgheight_update(self,context):
    bpy.context.scene.SimpleBake_Props.outputheight = bpy.context.scene.SimpleBake_Props.imgheight
 
def imgwidth_update(self,context):
    bpy.context.scene.SimpleBake_Props.outputwidth = bpy.context.scene.SimpleBake_Props.imgwidth


def textures_show_update(self,context):
    
    if context.scene.SimpleBake_Props.first_texture_show:
        functions.auto_set_bake_margin()
        context.scene.SimpleBake_Props.first_texture_show = False
        
def bake_objects_show_update(self,context):
    if context.scene.SimpleBake_Props.first_texture_show:
        functions.auto_set_bake_margin()
        context.scene.SimpleBake_Props.first_texture_show = False

def cp_list_index_update(self, context):
    index = bpy.context.scene.SimpleBake_Props.cp_list_index
    cpt = bpy.context.scene.SimpleBake_Props.cp_list[index]
    
    
    messages = []
    bpy.context.scene.SimpleBake_Props.channelpackfileformat = cpt.file_format
    try:
        bpy.context.scene.SimpleBake_Props.cptex_R = cpt.R
    except:
        messages.append(f"WARNING: {cpt.name} depends on {cpt.R} for the Red channel, but you are not baking it")
        messages.append("You can enable the required bake, or change the bake for that channel")
    try:    
        bpy.context.scene.SimpleBake_Props.cptex_G = cpt.G
    except:
        messages.append(f"WARNING: {cpt.name} depends on {cpt.G} for the Green channel, but you are not baking it")
        messages.append("You can enable the required bake, or change the bake for that channel")
    try:
        bpy.context.scene.SimpleBake_Props.cptex_B = cpt.B
    except:
        messages.append(f"WARNING: {cpt.name} depends on {cpt.B} for the Blue channel, but you are not baking it")
        messages.append("You can enable the required bake, or change the bake for that channel")
    try:
        bpy.context.scene.SimpleBake_Props.cptex_A = cpt.A
    except:
        messages.append(f"WARNING: {cpt.name} depends on {cpt.A} for the Alpha channel, but you are not baking it")
        messages.append("You can enable the required bake, or change the bake for that channel")
    
    bpy.context.scene.SimpleBake_Props.cp_name = cpt.name
    
    #Show messages
    if len(messages)>0:
        functions.ShowMessageBox(messages, title = "Warning", icon = "ERROR")
    
    


def get_selected_bakes_dropdown(self, context):
    items = []
    
    items.append(("none", "None",""))
    
    if bpy.context.scene.SimpleBake_Props.selected_col:
        items.append(("diffuse", "Diffuse",""))
    if bpy.context.scene.SimpleBake_Props.selected_metal:
        items.append(("metalness", "Metal",""))

    if bpy.context.scene.SimpleBake_Props.selected_sss:
        items.append(("sss", "SSS",""))
    if bpy.context.scene.SimpleBake_Props.selected_ssscol:
        items.append(("ssscol", "SSS Colour",""))
        
    if bpy.context.scene.SimpleBake_Props.selected_rough:
        if bpy.context.scene.SimpleBake_Props.rough_glossy_switch == "glossy":
            items.append(("glossy", "Glossy",""))
        else:
            items.append(("roughness", "Rouchness",""))
        
        
    if bpy.context.scene.SimpleBake_Props.selected_normal:
        items.append(("normal", "Normal",""))
    if bpy.context.scene.SimpleBake_Props.selected_trans:
        items.append(("transparency", "Transmission",""))
    if bpy.context.scene.SimpleBake_Props.selected_transrough:
        items.append(("transparencyroughness", "Transmission Rough",""))
    if bpy.context.scene.SimpleBake_Props.selected_clearcoat:
        items.append(("clearcoat", "Clearcoat",""))
    if bpy.context.scene.SimpleBake_Props.selected_clearcoat_rough:
        items.append(("clearcoatroughness", "ClearcoatRough",""))
    if bpy.context.scene.SimpleBake_Props.selected_emission:
        items.append(("emission", "Emission",""))
    if bpy.context.scene.SimpleBake_Props.selected_specular:
        items.append(("specular", "Specular",""))
    if bpy.context.scene.SimpleBake_Props.selected_alpha:
        items.append(("alpha", "Alpha",""))
        
    if bpy.context.scene.SimpleBake_Props.selected_col_mats:
        items.append((SimpleBakeConstants.COLOURID, SimpleBakeConstants.COLOURID,""))
    if bpy.context.scene.SimpleBake_Props.selected_col_vertex:
        items.append((SimpleBakeConstants.VERTEXCOL, SimpleBakeConstants.VERTEXCOL,""))
    if bpy.context.scene.SimpleBake_Props.selected_ao:
        items.append((SimpleBakeConstants.AO, SimpleBakeConstants.AO,""))
    if bpy.context.scene.SimpleBake_Props.selected_thickness:
        items.append((SimpleBakeConstants.THICKNESS, SimpleBakeConstants.THICKNESS,""))
    if bpy.context.scene.SimpleBake_Props.selected_curvature:
        items.append((SimpleBakeConstants.CURVATURE, SimpleBakeConstants.CURVATURE,""))
    if bpy.context.scene.SimpleBake_Props.selected_lightmap:
        items.append((SimpleBakeConstants.LIGHTMAP, SimpleBakeConstants.LIGHTMAP,""))


    return items
    
 
#-------------------END UPDATE FUNCTIONS----------------------------------------------


#-------------------PROPERTY GROUP----------------------------------------------



class SimpleBakePropGroup(bpy.types.PropertyGroup):
    
    from bpy.props import FloatProperty
    from bpy.props import StringProperty
    from bpy.props import BoolProperty
    from bpy.props import EnumProperty
    from bpy.props import PointerProperty
    from bpy.props import IntProperty
    from bpy.props import CollectionProperty
    
    var_master_list = []
    
    des = "Global Baking Mode"
    global_mode: EnumProperty(name="Bake Mode", default="pbr_bake", description="", items=[(
    "pbr_bake", "PBR Bake", "Bake PBR maps from materials created around the Principled BSDF and Emission shaders"),
    ("cycles_bake", "Cycles Bake", "Bake the 'traditional' cycles bake modes")
    ], update = global_mode_update)
    var_master_list.append("global_mode")
    
    
    des = "Distance to cast rays from target object to selected object(s)"
    ray_distance: FloatProperty(name="Ray Distance", default = 0.0, description=des)
    
    des = "Inflate the target object by specified value for baking"
    cage_extrusion: FloatProperty(name="Cage Extrusion", default = 0.0, description=des)
    
    
    #Bake mechanics (S2A etc)
    des = "Bake maps from one or more  source objects (usually high poly) to a single target object (usually low poly). Source and target objects must be in the same location (overlapping). See Blender documentation on selected to active baking for more details"
    selected_s2a: BoolProperty(name="Bake selected objects to target object", update = s2a_update, description=des)
    des = "Specify the target object for the baking. Note, this need not be part of your selection in the viewport (though it can be)"
    targetobj: PointerProperty(name="Target Object", description=des, type=bpy.types.Object)
    des = "Bake multiple objects to one set of textures. Not available with 'Bake maps to target object' (would not make sense). You must have more than one object selected for baking"
    mergedBake: BoolProperty(name="Multiple objects to one texture set", default = False, description=des, update = mergedBake_update)
    des = "When baking one object at a time, the object's name is used in the texture name. Baking multiple objects to one texture set, however requires you to proivde a name for the textures"
    mergedBakeName: StringProperty(name="Texture name for multiple bake", default = "MergedBake", description=des)
    des = "Bake using the Cycles selected to active option"
    cycles_s2a: BoolProperty(name="Selected to Active", description=des, update = cycles_s2a_update)
    des = "Specify the target object to bake to (this would be the active object with vanilla Blender baking)"
    targetobj_cycles: PointerProperty(name="Target Object", description=des, type=bpy.types.Object)
    
    #Texture settings related
    des = "Set the height of the baked image that will be produced"
    imgheight: IntProperty(name="Bake height", default=1024, description=des, update=imgheight_update)
    des = "Set the width of the baked image that will be produced"
    imgwidth: IntProperty(name="Bake width", default=1024, description=des, update=imgwidth_update)
    des = "Set the height of the baked image that will be ouput"
    outputheight: IntProperty(name="Output Height", default=1024, description=des)
    des = "Set the width of the baked image that will be output"
    outputwidth: IntProperty(name="Output Width", default=1024, description=des)
    des = "Normal maps are always created as 32bit float images, but this option causes all images to be created as 32bit float. Image quality is theoretically increased, but often it will not be noticable."
    everything32bitfloat: BoolProperty(name="All internal 32bit float", default = False, description=des)
    des = "Baked images have a transparent background (else Black)"
    useAlpha: BoolProperty(name="Use Alpha", default = False, description=des)
    des="Switch between roughness and glossiness (inverts of each other). NOTE: Roughness is the default for Blender so, if you change this, texture probably won't look right when used in Blender"
    rough_glossy_switch: EnumProperty(name="", default="rough", 
        description=des, items=[
            ("rough", "Rough", ""),
            ("glossy", "Glossy", "")
            ])
    des="Switch between OpenGL and DirectX formats for normal map. NOTE: Opengl is the default for Blender so, if you change this, texture probably won't look right when used in Blender"
    normal_format_switch: EnumProperty(name="", default="opengl", 
        description=des, items=[
            ("opengl", "OpenGL", ""),
            ("directx", "DirectX", "")
            ])
    des = "Bake each material into its own texture (for export to virtual worlds like Second Life"
    tex_per_mat: BoolProperty(name="Texture per material", description=des, update=tex_per_mat_update)
    
    #PBR bake types selection
    des = "Bake a PBR Colour map"
    selected_col: BoolProperty(name="Diffuse", default = True, description=des)
    des = "Bake a PBR Metalness map"
    selected_metal: BoolProperty(name="Metal", description=des)
    des = "Bake a PBR Roughness or Glossy map"
    selected_rough: BoolProperty(name="Roughness/Glossy", description=des)
    des = "Bake a Normal map"
    selected_normal: BoolProperty(name="Normal", description=des)
    des = "Bake a PBR Transmission map"
    selected_trans: BoolProperty(name="Transmission", description=des)
    des = "Bake a PBR Transmission Roughness map"
    selected_transrough: BoolProperty(name="Transmission Rough", description=des)
    des = "Bake an Emission map"
    selected_emission: BoolProperty(name="Emission", description=des)
    des = "Bake a Subsurface map"
    selected_sss: BoolProperty(name="SSS", description=des)
    des = "Bake a Subsurface colour map"
    selected_ssscol: BoolProperty(name="SSS Col", description=des)
    des = "Bake a PBR Clearcoat Map"
    selected_clearcoat: BoolProperty(name="Clearcoat", description=des)
    des = "Bake a PBR Clearcoat Roughness map"
    selected_clearcoat_rough: BoolProperty(name="Clearcoat Roughness", description=des)
    des = "Bake a Specular/Reflection map"
    selected_specular: BoolProperty(name="Specular", description=des)
    des = "Bake a PBR Alpha map"
    selected_alpha: BoolProperty(name="Alpha", description=des)
    
    #Specials bake types selection
    des = "ColourID Map based on random colour per material"
    selected_col_mats: BoolProperty(name=SimpleBakeConstants.COLOURID, description=des)
    des = "Bake the active vertex colours to a texture"
    selected_col_vertex: BoolProperty(name=SimpleBakeConstants.VERTEXCOL, description=des)
    des = "Ambient Occlusion"
    selected_ao: BoolProperty(name=SimpleBakeConstants.AO, description=des)
    des = "Thickness map"
    selected_thickness: BoolProperty(name=SimpleBakeConstants.THICKNESS, description=des)
    des = "Curvature map"
    selected_curvature: BoolProperty(name=SimpleBakeConstants.CURVATURE, description=des)
    des = "Lightmap map"
    selected_lightmap: BoolProperty(name=SimpleBakeConstants.LIGHTMAP, description=des)
    des = "Apply the colour management settings you have set in the render properties panel to the lightmap. Only available when you are exporting your bakes. Will be ignored if exporting to EXR files as these don't support colour management"
    lightmap_apply_colman: BoolProperty(name="Export with colour management settings", default=False, description=des)
    des = "Run lightmap through the compositor denoise node, only available when you are exporting you bakes"
    selected_lightmap_denoise: BoolProperty(name="Denoise Lightmap", description=des)
    
    #UV related
    des = "Use Smart UV Project to create a new UV map for your objects (or target object if baking to a target). See Blender Market FAQs for more details"
    newUVoption: BoolProperty(name="New UV Map(s)", description=des, update=newUVoption_update)
    des = "If one exists for the object being baked, use any existing UV maps called 'SimpleBake' for baking (rather than the active UV map)"
    prefer_existing_sbmap: BoolProperty(name="Prefer existing UV maps called SimpleBake", description=des, update=prefer_existing_sbmap_update)
    des = "New UV Method"
    newUVmethod: EnumProperty(name="New UV Method", default="SmartUVProject_Atlas", description=des, items=[
    ("SmartUVProject_Individual", "Smart UV Project (Individual)", "Each object gets a new UV map using Smart UV Project"),
    ("SmartUVProject_Atlas", "Smart UV Project (Atlas)", "Create a combined UV map (atlas map) using Smart UV Project"),
    ("CombineExisting", "Combine Active UVs (Atlas)", "Create a combined UV map (atlas map) by combining the existing, active UV maps on each object")
    ], update=newUVmethod_update)
    des = "If you are creating new UVs, or preferring an existing UV map called SimpleBake, the UV map used for baking may not be the one you had displayed in the viewport before baking. This option restores what you had active before baking"
    restoreOrigUVmap: BoolProperty(name="Restore originally active UV map at end", description=des, default=True)
    des = "Margin to use when packing combined UVs into Atlas map"
    uvpackmargin: FloatProperty(name="Pack Margin", default=0.1, description=des)
    des = "Average the size of the UV islands when combining them into the atlas map"
    averageUVsize: BoolProperty(name="Average UV Island Size", default=True, description=des)
    des = "When using 'Texture per material', Create a new UV map, and expand the UVs from each material to fill that map using Smart UV Project"
    expand_mat_uvs: BoolProperty(name="New UVs per material, expanded to bounds", description=des, update=expand_mat_uvs_update)
    des = "Bake to UDIMs or normal UVs. You must be exporting your bakes to use UDIMs. You must manually create your UDIM UVs (this cannot be automated)"
    uv_mode: EnumProperty(name="UV Mode", default="normal", description=des, items=[
    ("normal", "Normal", "Normal UV maps"),
    ("udims", "UDIMs", "UDIM UV maps")
    ], update = uv_mode_update)
    des = "Set the number of tiles that your UV map has used"
    udim_tiles: IntProperty(name="UDIM Tiles", default=2, description=des)
    des = "Margin between islands to use for Smart UV Project"
    unwrapmargin: FloatProperty(name="UV Unwrap Margin", default=0.1, description=des)
    
    #Export related
    des = "Export your bakes to the folder specified below, under the same folder where your .blend file is saved. Not available if .blend file not saved"
    saveExternal: BoolProperty(name="Export bakes", default = False, description=des, update = saveExternal_update)
    des = "Create a sub-folder for the textures and FBX of each baked object. Only available if you are exporting bakes."
    exportFolderPerObject: BoolProperty(name="Sub-folder per object", default = False, description=des)
    des = "Export your mesh as a .fbx file with a single texture and the UV map used for baking (i.e. ready for import somewhere else. File is saved in the folder specified below, under the folder where your blend file is saved. Not available if .blend file not saved"
    saveObj: BoolProperty(name="Export mesh", default = False, description=des)
    des = "File name of the fbx. NOTE: To maintain compatibility, only MS Windows acceptable characters will be used"
    fbxName: StringProperty(name="FBX name", description=des, default="Export", maxlen=20)
    des = "Create a copy of your selected objects in Blender (or target object if baking to a target) and apply the baked textures to it. If you are baking in the background, this happens after you import"
    prepmesh: BoolProperty(name="Copy objects and apply bakes", default = False, description=des, update=prepmesh_update)
    des = "Hide the source object that you baked from in the viewport after baking. If you are baking in the background, this happens after you import"
    hidesourceobjects: BoolProperty(name="Hide source objects after bake", default = False, description=des)
    des="Preserve original material assignments for baked objects (NOTE: all materials will be identical, and point to the baked texture set, but face assignments for each material will be preserved)"
    preserve_materials: BoolProperty(name="Preserve object original materials (BETA)", description=des)
    des = "Normal maps are always exported as 16bit, but this option causes all images to be exported 16bit. This should probably stay enabled unless file sizes are an issue"
    everything16bit: BoolProperty(name="All exports 16bit", default = True, description=des)
    des="Select the file format for exported bakes. Also applies to Sketchfab upload images"
    exportfileformat: EnumProperty(name="Export File Format", update=exportfileformat_update, default="PNG", 
    description=des, items=[
        ("PNG", "PNG", ""),
        ("JPEG", "JPG", ""),
        ("TIFF", "TIFF", ""),
        ("TARGA", "TGA", ""),
        ("OPEN_EXR", "Open EXR", "")
        ])
    des="Name of the folder to create and save the bakes/mesh into. Created in the folder where you blend file is saved. NOTE: To maintain compatibility, only MS Windows acceptable characters will be used"
    saveFolder: StringProperty(name="Save folder name", description=des, default="SimpleBake_Bakes", maxlen=20)
    des = "Apply colour space settings (exposure, gamma etc.) from current scene when saving the diffuse image externally. Only available if you are exporting baked images. Will be ignored if exporting to EXR files as these don't support colour management"
    selected_applycolmantocol: BoolProperty(name="Export diffuse with col management settings", default = False, description=des)
    des = "Apply colour space settings (exposure, gamma etc.) from current scene when saving the image externally. Only available if you are exporting baked images. Not available if you have Cycles bake mode set to Normal.  Will be ignored if exporting to EXR files as these don't support colour management"
    exportcyclescolspace: BoolProperty(name="Export with col management settings", default = True, description=des, update=exportcyclescolspace_update)
    des="Append date and time to folder name. If you turn this off there is a risk that you will accidentally overwrite bakes you did before if you forget to change the folder name"
    folderdatetime: BoolProperty(name="Append date and time to folder", description=des, default=True)
    des="Run baked images through the compositor. Your blend file must be saved, and you must be exporting your bakes"
    rundenoise: BoolProperty(name="Denoise", description=des, default=False)
    des = "Apply modifiers to object on export of the mesh to FBX"
    applymodsonmeshexport: BoolProperty(name="Apply object modifiers", description=des, default=True)
    des = "Use the 'Apply Transformation' option when exporting to FBX"
    applytransformation: BoolProperty(name="Apply transformation", description=des, default=False)
    
    
    #Advanced object selection list
    des="When turned on, you will bake the objects added to the bake list. When turned off, you will bake objects selected in the viewport"
    advancedobjectselection: BoolProperty(name="Use advanced object selection", default=True, description=des)
    bakeobjs_advanced_list: CollectionProperty(type = ListItem)
    bakeobjs_advanced_list_index: IntProperty(name = "Index for bake objects list", default = 0)
    
    #Background baking
    bgbake: EnumProperty(name="Background Bake", default="fg", items=[
    ("fg", "Foreground", "Perform baking in the foreground. Blender will lock up until baking is complete"),
    ("bg", "Background", "Perform baking in the background, leaving you free to continue to work in Blender while the baking is being carried out")
    ], update=bgbake_update)
    des="Name to help you identify the background bake task. This can be anything, and is only to help keep track of multiple background bake tasks. The name will show in the list below."
    bgbake_name: StringProperty(name="Background bake task name", description=des) 
    
    
    #Misc
    memLimit: EnumProperty(name="GPU Memory Limit", default="4096", 
    description="Limit memory usage by limiting render tile size. More memory means faster bake times, but it is possible to exceed the capabilities of your computer which will lead to a crash or slow bake times", items=[
        ("512", "Ultra Low", "Ultra Low memory usage (max 512 tile size)"),
        ("1024", "Low", "Low memory usage (max 1024 tile size)"),
        ("2048", "Medium", "Medium memory usage (max 2048 tile size)"),
        ("4096", "Normal", "Normal memory usage, for a reasonably modern computer (max 4096 tile size)"),
        ("Off", "No Limit", "Don't limit memory usage (tile size matches render image size)")
        ])
    des="Name to apply to these bakes (is incorporated into the bakes file name, provided you have included this in the image format string - see addon preferences). NOTE: To maintain compatibility, only MS Windows acceptable characters will be used"
    batchName: StringProperty(name="Batch name", description=des, default="Bake1", maxlen=20)
    des="Create the glTF settings node group"
    createglTFnode: BoolProperty(name="Create glTF settings", description=des, default=False)
    glTFselection: EnumProperty(name="glTF selection", default=SimpleBakeConstants.AO, 
    description="Which map should be plugged into the glTF settings node", items=[
        (SimpleBakeConstants.AO, SimpleBakeConstants.AO, "Use ambient occlusion"),
        (SimpleBakeConstants.LIGHTMAP, SimpleBakeConstants.LIGHTMAP, "Use lightmap")
        ])
    
    
    #Presets
    des="List of presets"
    presets_list: CollectionProperty(type=PresetItem, name="Presets", description="Presets")
    presets_list_index: IntProperty(name = "Index for bake presets list", default = 0, update=presets_list_update)
    des = "Name to save this preset under"
    preset_name: StringProperty(name="Name: ", description=des, default="Preset Name", maxlen=20)
    
    #Show/Hide
    showtips: BoolProperty(name="", default=False)
    des = "Show SimpleBake presets"
    presets_show: BoolProperty(name="", description=des, default=False, update=presets_show_update)
    des = "Show bake objects"
    bake_objects_show: BoolProperty(name="", description=des, default=False, update=bake_objects_show_update)
    des = "Show PBR settings"
    pbr_settings_show: BoolProperty(name="", description=des, default=False)
    des = "Show CyclesBake settings"
    cyclesbake_settings_show: BoolProperty(name="", description=des, default=False)
    des = "Show Specials settings"
    specials_show: BoolProperty(name="", description=des, default=False)
    des = "Show Texture settings"
    textures_show: BoolProperty(name="", description=des, default=False, update=textures_show_update)
    des = "Show Export settings"
    export_show: BoolProperty(name="", description=des, default=False)
    des = "Show UV settings"
    uv_show: BoolProperty(name="", description=des, default=False)
    des = "Show Other settings"
    other_show: BoolProperty(name="", description=des, default=False)
    des = "Show Channel Packing settings"
    channelpacking_show: BoolProperty(name="", description=des, default=False)
    des = "Show status of currently running background bakes"
    bg_status_show: BoolProperty(name="BG Bakes Status", description=des, default=True)
    
    #Behind the scenes
    first_texture_show: BoolProperty(name="", description=des, default=True)
    
    #Channel packing
    des = "Bake type to use for the Red channel of the channel packed image"
    cptex_R: EnumProperty(items=get_selected_bakes_dropdown, description=des)
    des = "Bake type to use for the Greeb channel of the channel packed image"
    cptex_G: EnumProperty(items=get_selected_bakes_dropdown, description=des)
    des = "Bake type to use for the Blue channel of the channel packed image"
    cptex_B: EnumProperty(items=get_selected_bakes_dropdown, description=des)
    des = "Bake type to use for the Alpha channel of the channel packed image"
    cptex_A: EnumProperty(items=get_selected_bakes_dropdown, description=des)
    cp_name: StringProperty(name="Name: ", default="PackedTex", maxlen=30, description=des)
    
    des="List of Channel Packed Textures"
    cp_list: CollectionProperty(type=CPTexItem, name="CP Textures", description="CP Textures")
    cp_list_index: IntProperty(name = "Index for CP Textures list", default = 0, update=cp_list_index_update)
    
    channelpackfileformat: EnumProperty(name="Export File Format for Channel Packing", default="OPEN_EXR", 
    description=des, items=[
        ("PNG", "PNG", ""),
        ("TARGA", "TGA", ""),
        ("OPEN_EXR", "Open EXR", "")
        ])    


#-------------------END PROPERTY GROUP----------------------------------------------

#-------------------REGISTER----------------------------------------------



def register():
    
    #Register classes
    global classes
    for cls in classes:
        bpy.utils.register_class(cls)
    
    global bl_info
    version = bl_info["version"]
    version = str(version[0]) + str(version[1]) + str(version[2])
    current = functions.checkAtCurrentVersion(version) 
    
    OBJECT_PT_simple_bake_panel.current = current
    OBJECT_PT_simple_bake_panel.version = f"{str(version[0])}.{str(version[1])}.{str(version[2])}"
    
    bpy.utils.register_class(SimpleBakePropGroup)
    
    #Load previews
    #functions.load_previews()
    
    #Register property group
    bpy.types.Scene.SimpleBake_Props = bpy.props.PointerProperty(type=SimpleBakePropGroup)
    

    
def unregister():
    
    from .bg_bake import bgbake_ops
    
    #Clear the files for any finished background bakes
    bpy.ops.object.simple_bake_bgbake_clear()
    
    #Stop any running and clear files
    running = bgbake_ops.bgops_list
    
    savepath = Path(bpy.data.filepath).parent
    
    for p in running:
        pid_str = str(p[0].pid)
        
        try:
            os.kill(pid_str, signal.SIGKILL)
        except:
            pass
        
        try:
            os.remove(str(savepath / pid_str) + '.blend')
            os.remove(str(savepath / pid_str) + '.blend1')
        except:
            pass
        
    
    #User preferences
    global classes
    for cls in classes:
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.SimpleBake_Props


if __name__ == "__main__":
    register()


