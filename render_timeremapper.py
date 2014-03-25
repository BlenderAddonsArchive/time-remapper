# ##### BEGIN GPL LICENSE BLOCK #####''
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

#Mostly PEP8-compliant
#  pep8 render_timeremapper.py --ignore=E121,E126,E127,E128,W293

bl_info = {
    "name": "Time Remapper",
    "author": "Garrett",
    "version": (0, 1),
    "blender": (2, 70, 0),
    "location": "Properties > Render > Render Panel",
    "description": "Time remaps whole scene according to an animatable"
                    "speed factor",
    "warning": "beta",
    "category": "Render",
    "wiki_url": "",
    "tracker_url": ""}


import bpy
from os import path, remove
import signal


class OBJECT_OT_render_TR(bpy.types.Operator):
    bl_idname = 'render.render_timeremapper'
    bl_label = "Render using Time Remapper"
    bl_description = "This renders out frames based on your time remapping"
    bl_register = True
    
    #this is only used during rendering frames
    abort_render = bpy.props.BoolProperty(default=False)
    
    def SIGINT_handler(self, signum, frame):
        '''This signal handler will be called when user hits CTL+C
        while rendering'''
        self.abort_render = True
    
    def execute(self, context):
        
        scene = context.scene
        
        #ensure they are using Cycles
        if scene.render.engine != 'CYCLES':
            raise RuntimeError("\n\nYou must be using Cycles Render "
                               "for this script to work properly.\n")
        #ensure they haven't selected a movie format
        if scene.render.is_movie_format:
            file_format = scene.render.image_settings.file_format
            raise RuntimeError("\n\nCannot render movie file, "
                                "you must select an image format"
                                "\n(Current file format: {})"
                                .format(file_format))
        
        print("Getting list of frames to be rendered "
                "(should take <1 second...)")
        TR_frames = get_TR_frames(context)
       
        #total number of frames
        total_num_fr = len(TR_frames)
        
        print("\n\nRendering " + str(total_num_fr) +
                " frames now ... to stop after rendering current frame,"
                "press CTL+C...\n\n")
        
        #store original render path
        orig_render_path = scene.render.filepath
        
        #keep a count for labelling the filenames
        count = 0
        
        first_frame = scene.frame_start

        #before starting loop, set up a signal handler for CTL+C
        #since KeyboardInterrupt doesn't work while rendering
        #(see bit.ly/1cfBmlS)
        self.abort_render = False
        signal.signal(signal.SIGINT, self.SIGINT_handler)
                
        #start loop that renders the frames.
        #(anim_frame is the actual frame in animation we're at, ex: 4.5435)
        for anim_frame in TR_frames:
            
            print('-------------------')
        
            #check for frame step and skip frame if necessary
            if count % scene.frame_step != 0:
                print("Stepping over frame " + str(first_frame+count) +
                        ". (Frame Step is " + str(scene.frame_step) + ")")
                count += 1
                continue

            #render frame, ie. the number we assign this frame
            render_frame = first_frame + count            
            
            #################################
            ## Dealing with Immune Objects ##
            #################################
            
            #list of immune objects that will need to have their inserted
            #keyframes deleted
            immuneObjects = []
            #Minimum frame offset. We don't want to have temporary keyframes
            #placed on integer frames (ex: 4.0, 7.0), since it could mess with
            #original keyframes.  I found this value to work well empirically,
            #any smaller and Blender treats the keyframes (4.00 and 4.01) as
            #the same keyframe.  0.03 is not a perceptible change
            #(this is a bit of a hack)
            min_fr_offset = 0.03
            if using_immune_objects(context):
                #check if anim_frame is too close to being integer frame
                #and if so, push away to have minimum offset
                if 0 <= anim_frame % 1 < min_fr_offset:
                    anim_frame += min_fr_offset - anim_frame % 1
                elif 1-min_fr_offset < anim_frame % 1 < 1:
                    anim_frame -= anim_frame % 1 - (1 - min_fr_offset)
                
                for iobj_name in [scene.timeremap_immuneObject1,
                                  scene.timeremap_immuneObject2,
                                  scene.timeremap_immuneObject3]:
                    #check if this property is set
                    if iobj_name != '':
                        #skip this object if the user has changed the name
                        if iobj_name not in scene.objects.keys():
                            continue
                        iobj = scene.objects[iobj_name]
                        keyframe_locrot_by_target_frame(iobj, render_frame,
                                                        anim_frame)
                        immuneObjects.append(iobj)

            ########################################
            ## End of Dealing with Immune Objects ##
            ########################################
            
            #create filename.
            #Note that Blender expects a four digit integer at the end.
            current_renderpath = orig_render_path + str(render_frame).zfill(4)
               
            #check if file exists, and if so whether we should overwrite it
            #first we get the full current path to image to be rendered by
            #adding the extension if File Extensions is enabled.
            full_current_renderpath = bpy.path.abspath(current_renderpath) + \
                                      scene.render.file_extension * \
                                      (scene.render.use_file_extension is True)
            if path.exists(full_current_renderpath):
                if scene.render.use_overwrite is False:
                    print("Skipping frame " + str(render_frame) +
                            " because there already exists the file: " +
                            full_current_renderpath)
                    count += 1
                    continue
                else:
                    print("File: " + full_current_renderpath +
                            " will be overwritten.")
                    #Wait to overwrite it until last possible moment.
            
            #check if we need Placeholders
            if scene.render.use_placeholder is True:
                #delete the old file if it exists
                if path.exists(full_current_renderpath):
                    remove(full_current_renderpath)
                #create placeholder  (tag 'a' helps prevent race errors)
                open(full_current_renderpath, 'a').close()
    
            #Jump to animation frame (frame is a float)        
            scene.frame_set(int(anim_frame), anim_frame % 1)
        
            scene.render.filepath = current_renderpath
            print("Rendering true frame:", anim_frame)
            #Render frame
            bpy.ops.render.render(write_still=True)
            print("Frames completed: " + str(count+1) + "/" +
                    str(total_num_fr) + "\n\n")
            count += 1

            #Clean up after the keyframing of immune objects (if there are any)
            for iobj in immuneObjects:
                delete_locrot_keyframes(iobj, anim_frame)
            
            #Check if CTL+C was pressed by user
            if self.abort_render:
                print("\nAborting Animation")
                #reset the SIGINT handler back to default
                signal.signal(signal.SIGINT, signal.default_int_handler)
                break
        #End loop that renders frames
            
        #reset the filepath in case user wants to play movie afterwards
        scene.render.filepath = orig_render_path
        
        print("\n\nDone")
        
        return {'FINISHED'}
    #end of execute(.)
#end of class OBJECT_OT_render_TR


class OBJECT_OT_playback_TR(bpy.types.Operator):
    bl_idname = 'render.playback_timeremapper'
    bl_label = "Playback time remapped frames"
    bl_description = "Plays back frames, defining the start and end" \
                        " based on the time remapping"
    bl_register = True

    def execute(self, context):
        
        scene = context.scene
        
        print("Preparing playback")
        #get number of frames that we need to play back
        num_frames = len(get_TR_frames(context))
        
        old_frame_end = scene.frame_end
        
        scene.frame_end = scene.frame_start + num_frames - 1
        
        bpy.ops.render.play_rendered_anim()

        #restore the old end frame
        scene.frame_end = old_frame_end
        
        return {'FINISHED'}

#end of class OBJECT_OT_playback_TR

    
def draw(self, context):
    layout = self.layout

    scene = context.scene

    layout.label("Time Remapper:")
    
    row = layout.row(align=True)
    row.alignment = 'LEFT'
    row.prop(scene, 'timeremap_method')
    if scene.timeremap_method == 'SF':
        row.prop(scene, 'timeremap_speedfactor')
    elif scene.timeremap_method == 'TTC':
        row.prop(scene, 'timeremap_TTC')
    
    row = layout.row(align=True)
    rowsub = row.row(align=True)
    rowsub.operator('render.render_timeremapper',
                    text="TR Animation",
                    icon="RENDER_ANIMATION")
    rowsub.operator('render.playback_timeremapper',
                    text="TR Playback",
                    icon='PLAY')
    
    row = layout.row(align=True)
    row.alignment = 'LEFT'
    rowsub = row.row(align=True)
    rowsub.label("Immune objects:")
    rowsub.prop_search(scene, "timeremap_immuneObject1", scene, "objects",
                       text="")
    rowsub.prop_search(scene, "timeremap_immuneObject2", scene, "objects",
                       text="")
    rowsub.prop_search(scene, "timeremap_immuneObject3", scene, "objects",
                       text="")
    
    
def find_fcurve(scene_or_obj, data_path, index=0):
    '''Find a particular F-Curve.'''
    anim_data = scene_or_obj.animation_data
    for fcurve in anim_data.action.fcurves:
        if fcurve.data_path == data_path and fcurve.array_index == index:
            return fcurve
    
     
def is_keyframed(scene_or_obj, data_path, index=0):
    '''Check if the scene or object property is already keyframed
    Ideas from @CoDEmanX on Blender SE for this.'''

    anim = scene_or_obj.animation_data
    
    if anim is not None and anim.action is not None:
        for fcurve in anim.action.fcurves:
            if fcurve.data_path == data_path and fcurve.array_index == index:
                return True
    return False


def using_immune_objects(context):
    '''Check if the user has a valid immune object set, i.e. an object
    that will be immune to time remapping.'''
    scene = context.scene
    
    for iobj_name in [scene.timeremap_immuneObject1,
                      scene.timeremap_immuneObject2,
                      scene.timeremap_immuneObject3]:
        if iobj_name != '':
            if iobj_name not in scene.objects.keys():
                print('WARNING: One of your selected immune objects ("' +
                      iobj_name + '") no longer corresponds to an object. '
                      'Did you change the name of that object?')
                continue
            else:
                return True
    
    return False
    
    
def keyframe_locrot_by_target_frame(obj, target_fr, frame):
    '''Set the location and rotation of the object at frame to be same as
    values at target keyframe
    
    Return: if the object already had a keyframe there, then return a list of
    3-tuples, one 3-tuple for each keyframed property
    '''
    
    for data_path, tot_indices in [('location', 3), ('rotation_euler', 3),
                      ('rotation_axis_angle', 4), ('rotation_quaternion', 4)]:
        #loop through index
        #(we loop 4 times for properties like Quaternion Rot.)
        for ind in range(tot_indices):
            if is_keyframed(obj, data_path=data_path, index=ind):
                fcurve = find_fcurve(obj, data_path, index=ind)
            else:
                continue

            #update the property to have value that it has at target frame
            props_to_update = getattr(obj, data_path)
            props_to_update[ind] = fcurve.evaluate(target_fr)
            setattr(obj, data_path, props_to_update)
            
            obj.keyframe_insert(data_path=data_path, index=ind, frame=frame)
     
    return


def delete_locrot_keyframes(obj, frame):
    '''Delete all the location and rotation keyframes for object at given
    frame.'''
    
    for data_path, tot_indices in [('location', 3), ('rotation_euler', 3),
                      ('rotation_axis_angle', 4), ('rotation_quaternion', 4)]:
        #loop through index
        #(we loop 4 times for properties like Quaternion Rot.)
        for ind in range(tot_indices):
            if is_keyframed(obj, data_path=data_path, index=ind) is False:
                continue
            obj.keyframe_delete(data_path, ind, frame)
    
    return


def get_TR_frames(context):
    '''Gets a list of time-remapped frames to be rendered'''

    scene = context.scene
    
    if scene.timeremap_method == 'SF':
        TR_frames = get_TR_frames_from_SF(context)
    elif scene.timeremap_method == 'TTC':
        TR_frames = get_TR_frames_from_TTC(context)
    else:
        assert False
        
    return TR_frames
    

def get_TR_frames_from_SF(context):
    '''Gets a list of time-remapped frames to be rendered by
    looking at the Speed Factor parameter.'''

    scene = context.scene
    
    #Time-remapped frames to render
    TR_frames = []
    
    #current time-remapped frame
    current_TR_frame = scene.frame_start

    #for unkeyframed, we can't use the F-Curve, so we treat it separately
    if is_keyframed(scene, 'timeremap_speedfactor') is False:
        
        #avoid infinite loop by checing that speed factor's positive
        if scene.timeremap_speedfactor <= 0:
            raise RuntimeError(
                    "\n\nYou're speed factor must always be positive"
                    " to avoid getting stuck in an infinite loop!")
        
        #loop through all frames until the end
        while current_TR_frame <= scene.frame_end:
            TR_frames.append(current_TR_frame)
            current_TR_frame += scene.timeremap_speedfactor
        
        return TR_frames
    #end of if block
    
    #speed factor's F-Curve
    SF_fcurve = find_fcurve(scene, 'timeremap_speedfactor')
    assert SF_fcurve is not None
    
    #we loop through however many (time-remapped) frames it takes
    #to get to the end frame
    while current_TR_frame <= scene.frame_end:
        
        #add current frame to our list
        TR_frames.append(current_TR_frame)

        #get current speed factor
        current_SF = SF_fcurve.evaluate(current_TR_frame)
        
        #avoid infinite loop by checing that speed factor's positive
        if current_SF <= 0:
            raise RuntimeError(
                    "\n\nYou're speed factor must always be positive"
                    " to avoid getting stuck in an infinite loop!")
        
        #move to next frame based on the current value of the speed factor
        current_TR_frame += current_SF
    #end while loop
    
    return TR_frames
#end of get_TR_frames_from_SF(.)


def get_TR_frames_from_TTC(context):
    '''Gets a list of time-remapped frames to be rendered by
    looking at the Time Time Curve parameter.'''
    
    scene = context.scene
    
    if is_keyframed(scene, 'timeremap_TTC') is False:
        raise RuntimeError('the property timeremap_TTC must be keyframed'
                            '\nIt cannot be a constant value.')
    
    #Time-remapped frames to render
    TR_frames = []
    #jump to non-time-remapped start frame
    nonTR_frame = scene.frame_start
    scene.frame_set(nonTR_frame)

    #to avoid getting stuck in an infinite loop (ex: TT curve never reaches the
    #end frame), we break when we exceed max_frames.
    count = 0
    max_frames = 100000

    #TTC's F-Curve
    TTC_fcurve = find_fcurve(scene, 'timeremap_TTC')
    assert TTC_fcurve is not None

    current_TTC_value = TTC_fcurve.evaluate(nonTR_frame)

    #we loop through however many (time-remapped) frames
    #it takes to get to the end frame
    while current_TTC_value <= scene.frame_end:
        
        TR_frames.append(current_TTC_value)
        
        nonTR_frame += 1
        current_TTC_value = TTC_fcurve.evaluate(nonTR_frame)
        
        count += 1
        if count >= max_frames:
            raise RuntimeError("\n\nHaven't reached end after counting 100 000"
                                "frames!\nMake sure the TT Curve value reaches"
                                " the end frame at some point.")
    #end of while loop
    
    return TR_frames
#end of get_TR_frames_from_TTC(.)
        
    
def update_TR_method(self, context):
    '''Check if user switched to using a TT curve.  If so, and it is not
    keyframed, then keyframe it to produce a 45 degree angle curve (which
    corresponds to a one-to-one time mapping)
    
    Ideas from @pinkvertex on Blender SE.'''

    scene = context.scene
    
    print('Inside update method')
    
    #if not switching to TT curve, or if it's already keyframed, return
    if scene.timeremap_method != 'TTC' or is_keyframed(scene, 'timeremap_TTC'):
        print('OK no need')
        return
    
    if not scene.animation_data:
        scene.animation_data_create()
    if not scene.animation_data.action:
        scene.animation_data.action = (bpy.data.actions
                                                .new('timeremap_TTC_action'))
    
    #find the correct f-curve in case there's multiple
    fcurve = scene.animation_data.action.fcurves.new('timeremap_TTC')
    #keyframe it to make a 45 degree straight line
    fcurve.extrapolation = 'LINEAR'
    fcurve.keyframe_points.insert(frame=0.0, value=0.0)
    fcurve.keyframe_points.insert(frame=1.0, value=1.0)
          

def register():
    bpy.utils.register_module(__name__)
    
    bpy.types.Scene.timeremap_speedfactor = bpy.props.FloatProperty(
                    name="Speed factor",
                    options={'ANIMATABLE'},
                    default=1.0)
    bpy.types.Scene.timeremap_TTC = bpy.props.FloatProperty(
                    name="TT Curve",
                    options={'ANIMATABLE'},
                    default=0.0)
    bpy.types.Scene.timeremap_method = bpy.props.EnumProperty(
                    name="",
                    description="Method for defining the time remapping",
                    items=[
                            ('SF', 'Speed Factor', 'Use a speed factor'
                                              '(where 0.5 means 2x slow-mo)'),
                           ('TTC', 'Time-Time Curve',
                           'Use a curve which shows how rendered frame maps'
                                              'to true-time frame')
                           ],
                    default='SF', update=update_TR_method)

    #We allow for 3 immune objects (of course, this could be increased)
    #I couldn't figure out how to get these into a collection and still use
    #the prop_search funciton while drawing panel.
    bpy.types.Scene.timeremap_immuneObject1 = bpy.props.StringProperty(
                    name="Immune Object 1",
                    description="Make object immune to time remapping effects")
    bpy.types.Scene.timeremap_immuneObject2 = bpy.props.StringProperty(
                    name="Immune Object 2",
                    description="Make object immune to time remapping effects")
    bpy.types.Scene.timeremap_immuneObject3 = bpy.props.StringProperty(
                    name="Immune Object 3",
                    description="Make object immune to time remapping effects")

    #Draw panel under the header "Render" in Render tab of Properties window
    bpy.types.RENDER_PT_render.append(draw)


def unregister():
    
    del bpy.types.Scene.timeremap_speedfactor
    del bpy.types.Scene.timeremap_TTC
    del bpy.types.Scene.timeremap_method
    del bpy.types.Scene.timeremap_immuneObject1
    del bpy.types.Scene.timeremap_immuneObject2
    del bpy.types.Scene.timeremap_immuneObject3
    
    #remove the panel from the UI
    bpy.types.RENDER_PT_render.remove(draw)
    
    bpy.utils.unregister_module(__name__)


if __name__ == "__main__":
    register()
