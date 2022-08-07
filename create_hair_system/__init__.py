#====================== BEGIN GPL LICENSE BLOCK ======================
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
#======================= END GPL LICENSE BLOCK ========================

from mathutils import *
from bpy.props import *
import bpy
import bmesh
import os

# Version history
# 1.0.0 - 2021-12-28: Original version.
# 1.0.1 - 2022-01-09: Made better defaults for eyelashes. Lots of little tweaks as well.
# 1.0.2 - 2022-01-10: Yet more tweaks for eyelashes.
# 1.0.3 - 2022-01-11: More eyelash tweaks.
# 1.0.4 - 2022-01-16: Made Render -> Path -> B-Spline checked by default. Set Render -> Path -> Steps to hair_segments and changed the UI accordingly. Added some saner eyebrow defaults.
# 1.0.5 - 2022-01-17: More sane eyebrow defaults. Removed where I was using "Use Modifier Stack" -- which makes the particle appear in weird places when truly rendering. (It looks fine when you're in Render mode, for some reason.)
# 1.0.6 - 2022-01-18: Fixed an eyebrow default -- Children -> Simple -> Radius should be 0.001 as a starting point; it's too bushy otherwise.
# 1.0.7 - 2022-01-20: Changed hair defaults -- it should use Simple child elements, not Interpolated. We can now set parent and/or child particles to 0.
# 1.0.8 - 2022-01-22: Changed more hair defaults.
# 1.0.9 - 2022-01-23: Changed even more hair defaults.
# 1.0.10 - 2022-01-24: If you use a vertex group, hair sprouts of vertices, not faces.
# 1.0.11 - 2022-01-25: Yesterday's tweak was wrong; I'm keeping it set to faces. Otherwise, you cannot manually add new particles. (Also, I've decided to take a slightly different approach to the helicopter hair concept since yesterday.)
# 1.0.12 - 2022-01-30: Setting up hair parameters that worked well for Isobelle.
# 1.0.13 - 2022-02-06: Added option for hair to be created on vertex or face because -- yes, it DOES make sense to have hair sprouting from vertices.
# 1.0.14 - 2022-02-07: Changed the lengths of hair to be more reasonable.
# 1.0.15 - 2022-02-07: Realized that when you create hair you should NOT set the length by vertex group, so I fixed that. Also removed the "Emit From" feature because of the bug with combing particles that were emitted from vertices. (The bug is, the hair will show up in the INVERSE direction on the Z axis when you render the image...but it'll look fine in Render mode.)
# 1.0.16 - 2022-06-13: Added male body hair options: arm hair, back hair, chest hair, leg hair, stubble.
# 1.0.17 - 2022-06-14: Removed Segments/Render Path Steps for eyelashes and eyebrows and am now using the defaults of 5 and 3, respectively.
# 1.0.18 - 2022-08-07: Misc formatting cleanup before uploading to GitHub.

###############################################################################
SCRIPT_NAME = 'create_hair_system'

# This add-on creates a hair/fur/eyelash/eyebrow particle system with sane
# default values.
###############################################################################

bl_info = {
    "name": "Create Hair System",
    "author": "Jeff Boller",
    "version": (1, 0, 18),
    "blender": (2, 93, 0),
    "location": "View3D > Properties > Hair",
    "description": 'Creates a hair/fur/eyelash/eyebrow/body hair particle system with sane defaults.',
    "wiki_url": "https://github.com/sundriftproductions/blenderaddon-create-hair-system/wiki",
    "tracker_url": "https://github.com/sundriftproductions/blenderaddon-create-hair-system",
    "category": "3D View"}

def select_name( name = "", extend = True ):
    if extend == False:
        bpy.ops.object.select_all(action='DESELECT')
    ob = bpy.data.objects.get(name)
    ob.select_set(state=True)
    bpy.context.view_layer.objects.active = ob

def does_cache_name_exist_in_object(proposed_name):
    obj = bpy.context.active_object
    for particle_system in obj.particle_systems:
        for cache in particle_system.point_cache.point_caches:
            if cache.name == proposed_name:
                return True
    return False

class CREATEHAIRSYSTEM_PT_CreateHairSystem(bpy.types.Operator):
    bl_idname = "chs.create_hair_system"
    bl_label = ""

    def execute(self, context):
        # Create the hair system.

        self.report({'INFO'}, '**********************************')
        self.report({'INFO'}, SCRIPT_NAME + ' - START')

        if (len(bpy.path.basename(bpy.context.blend_data.filepath)) == 0):
            self.report({'ERROR'},
                        '  ERROR: The project file must be saved before adding the particle system. Save this project and run the script again.')
            return {'CANCELLED'}

        self.report({'INFO'}, 'Creating this kind of system: ' + bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system)
        SYSTEM_NAME = bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system  # The particle system name

        if bpy.context.preferences.addons['create_hair_system'].preferences.vertex_group_name != '':
            SYSTEM_NAME += ' (' + bpy.context.preferences.addons['create_hair_system'].preferences.vertex_group_name + ')' # Append the vertex group to be more specific (if applicable).

        ###############################################################################
        # Part 1: Remove Physics -> Collision (and storing parameter values) if present
        ###############################################################################
        self.report({'INFO'}, "Removing Physics -> Collision (and storing parameter values) if present...")

        # Make sure we don't have Physics -> Collision turned on before we turn on Hair Dynamics.
        # For whatever reason, Blender 2.91 locks up if you turn on Hair Dynamics and Collision for that object is already turned on.
        # If we already have Physics -> Collision turned on, then we save all the values that we'll need to restore, then turn it off (i.e. remove the modifier).
        mode = bpy.context.active_object.mode
        bpy.ops.object.mode_set(mode='OBJECT')

        obj = bpy.context.active_object  # Just use our current active object as the one we want to affect.

        # Default values for Physics -> Collision
        collision_absorption = 0  # Field Absorption
        collision_permeability = 0.1  # Particle -> Permeability
        collision_stickiness = 0.1  # Particle -> Stickiness
        collision_use_particle_kill = False  # Particle -> Kill Particles
        collision_damping_factor = 0  # Particle -> Damping
        collision_damping_random = 0  # Particle -> (Damping) Randomize
        collision_friction_factor = 0  # Particle -> Friction
        collision_friction_random = 0  # Particle -> (Friction) Randomize
        collision_damping = 0.1  # Softbody And Cloth -> Damping
        collision_cloth_friction = 5  # Softbody And Cloth -> Friction
        collision_use_culling = True  # Softbody And Cloth -> Single Sided
        collision_use_normal = False  # Softbody And Cloth -> Override Normals
        collision_thickness_inner = 0.2  # Softbody And Cloth -> Thickness Inner

        collisionModifierName = None
        for modifier in obj.modifiers:
            if modifier.name.upper() == 'COLLISION':  # Need to use upper() here because it could be 'COLLISION' or 'Collision' depending on how it was added.
                collisionModifierName = modifier.name
                break

        if collisionModifierName != None:
            # Store all of our the values that we will carry over when we re-instantiate Physics -> Collusion.
            collision_absorption = bpy.context.object.collision.absorption
            collision_permeability = bpy.context.object.collision.permeability
            collision_stickiness = bpy.context.object.collision.stickiness
            collision_use_particle_kill = bpy.context.object.collision.use_particle_kill
            collision_damping_factor = bpy.context.object.collision.damping_factor
            collision_damping_random = bpy.context.object.collision.damping_random
            collision_friction_factor = bpy.context.object.collision.friction_factor
            collision_friction_random = bpy.context.object.collision.friction_random
            collision_damping = bpy.context.object.collision.damping
            collision_cloth_friction = bpy.context.object.collision.cloth_friction
            collision_use_culling = bpy.context.object.collision.use_culling
            collision_use_normal = bpy.context.object.collision.use_normal
            collision_thickness_inner = bpy.context.object.collision.thickness_inner

            self.report({'INFO'}, "Temporarily removing Physics -> Collision (will restore it at the end)...")
            bpy.ops.object.modifier_remove(modifier=collisionModifierName)

        # Go back to whatever mode we were in.
        bpy.ops.object.mode_set(mode=mode)

        ###############################################################################
        # Part 2: Add particle system
        ###############################################################################
        self.report({'INFO'}, "Adding particle system...")

        mode = bpy.context.active_object.mode
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        select_name(bpy.context.preferences.addons['create_hair_system'].preferences.object_name)
        obj = bpy.context.active_object  # Now that we've selected the object that needs a hair system, set it as the one we want to affect.

        # Create the particle system.
        bpy.ops.object.particle_system_add()
        particles = obj.particle_systems[-1]
        psettings = particles.settings

        particles.name = SYSTEM_NAME  # Assign the main particle system name (the name in the top listbox in the Particles properties tab)
        psettings.name = SYSTEM_NAME  # Assign the particle name (the name UNDERNEATH the top listbox in the Particles properties tab)
        psettings.type = 'HAIR'  # We want Hair, not the default (Emitter)

        if bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'hair':
            ###########################################################################
            ## HAIR
            ###########################################################################
            parent_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemhair_parent_particle_amount
            child_display_render_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemhair_child_display_render_particle_amount
            hair_segments = int(bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemhair_hair_segments)
            strand_shape = -0.75   # Human hair-like shape, where you have a constant thickness until the very tip of the hair.
            hair_dynamics = bpy.context.preferences.addons['create_hair_system'].preferences.systemhair_hair_dynamics
            material = bpy.context.preferences.addons['create_hair_system'].preferences.systemhair_material
            clump = 0.900
            clump_shape = 0
            use_emit_random = True
            userjit = 0
            use_even_distribution = False
            jitter_factor = 1.0
            use_length_vertex_group = False
            child_type = 'SIMPLE'
            child_radius = 0.02 # This is a good radius for hair.

            if bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemhair_hair_length == 'xs':
                hair_length = 0.075
                child_length = 1
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemhair_hair_length == 's':
                hair_length = 0.2
                child_length = 1
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemhair_hair_length == 'm':
                hair_length = 0.3375
                child_length = 1
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemhair_hair_length == 'l':
                hair_length = 0.475
                child_length = 1
            else: # xl
                hair_length = 0.75
                child_length = 1

            if bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemhair_hair_thickness == 'xs':
                hair_thickness = 0.01
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemhair_hair_thickness == 's':
                hair_thickness = 0.03
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemhair_hair_thickness == 'm':
                hair_thickness = 0.04
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemhair_hair_thickness == 'l':
                hair_thickness = 0.05
            else: # xl
                hair_thickness = 0.06

            hair_tip = 0
            kink_type = 'NO'

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'fur':
            ###########################################################################
            ## FUR
            ###########################################################################
            parent_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemfur_parent_particle_amount
            child_display_render_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemfur_child_display_render_particle_amount
            hair_segments = int(bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemfur_hair_segments)
            strand_shape = -0.5  # Fur-like shape, where the fur strand starts tapering off at the 3/4 point.
            hair_length = 0.025 # Since fur is usually shorter than hair, we use this same hair_length for everything for fur.
            hair_dynamics = bpy.context.preferences.addons['create_hair_system'].preferences.systemfur_hair_dynamics
            material = bpy.context.preferences.addons['create_hair_system'].preferences.systemfur_material
            clump = 0
            clump_shape = 0
            use_emit_random = True
            userjit = 0
            use_even_distribution = False
            jitter_factor = 1.0
            use_length_vertex_group = True
            child_type = 'INTERPOLATED'
            child_radius = 0.001 # Not actually used for fur since it's interpolated.

            if bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemfur_hair_length == 'xs':
                child_length = 0.125
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemfur_hair_length == 's':
                child_length = 0.25
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemfur_hair_length == 'm':
                child_length = 0.5
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemfur_hair_length == 'l':
                child_length = 0.75
            else: # xl
                child_length = 1

            if bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemfur_hair_thickness == 'xs':
                hair_thickness = 0.025
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemfur_hair_thickness == 's':
                hair_thickness = 0.06875
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemfur_hair_thickness == 'm':
                hair_thickness = 0.1125
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemfur_hair_thickness == 'l':
                hair_thickness = 0.15625
            else: # xl
                hair_thickness = 0.2

            hair_tip = 0
            kink_type = 'NO'

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'eyelashes':
            ###########################################################################
            ## EYELASHES
            ###########################################################################
            parent_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemeyelashes_parent_particle_amount
            child_display_render_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemeyelashes_child_display_render_particle_amount
            hair_segments = 5
            strand_shape = -0.25  # Eyelash-like shape
            hair_length = 0.025
            hair_dynamics = bpy.context.preferences.addons['create_hair_system'].preferences.systemeyelashes_hair_dynamics
            material = bpy.context.preferences.addons['create_hair_system'].preferences.systemeyelashes_material
            clump = 1 # We want the strongest clumping possible.
            clump_shape = 0.999 # This clump shape makes the ends of the hair clump together.
            use_emit_random = False
            userjit = 1
            use_even_distribution = True
            jitter_factor = 0.0
            use_length_vertex_group = True
            child_type = 'INTERPOLATED'
            child_radius = 0.001  # Not actually used for eyelashes since it's interpolated.

            if bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyelashes_hair_length == 'xs':
                child_length = 0.2
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyelashes_hair_length == 's':
                child_length = 0.3
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyelashes_hair_length == 'm':
                child_length = 0.4
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyelashes_hair_length == 'l':
                child_length = 0.5
            else: # xl
                child_length = 1.0

            if bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyelashes_hair_thickness == 'xs':
                hair_thickness = 0.009375
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyelashes_hair_thickness == 's':
                hair_thickness = 0.01875
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyelashes_hair_thickness == 'm':
                hair_thickness = 0.0375
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyelashes_hair_thickness == 'l':
                hair_thickness = 0.075
            else: # xl
                hair_thickness = 0.10

            hair_tip = 0
            kink_type = 'NO'

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'eyebrows':
            ###########################################################################
            ## EYEBROWS
            ###########################################################################
            parent_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemeyebrows_parent_particle_amount
            child_display_render_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemeyebrows_child_display_render_particle_amount
            hair_segments = 3
            strand_shape = -0.750
            hair_length = 0.06
            hair_dynamics = bpy.context.preferences.addons['create_hair_system'].preferences.systemeyebrows_hair_dynamics
            material = bpy.context.preferences.addons['create_hair_system'].preferences.systemeyebrows_material
            clump = 0.933
            clump_shape = 0
            use_emit_random = True
            userjit = 0
            use_even_distribution = False
            jitter_factor = 1.0
            use_length_vertex_group = False # Eyebrows are different -- we do NOT want to determine the length from the weight-painted vertex group.
            child_type = 'SIMPLE'
            child_radius = 0.001  # This is a sane setting for eyebrows. Larger numbers make the particles fly EVERYWHERE.

            if bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyebrows_hair_length == 'xs':
                child_length = 0.25
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyebrows_hair_length == 's':
                child_length = 0.5
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyebrows_hair_length == 'm':
                child_length = 1.0
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyebrows_hair_length == 'l':
                child_length = 1.5
            else: # xl
                child_length = 2.0

            if bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyebrows_hair_thickness == 'xs':
                hair_thickness = 0.05
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyebrows_hair_thickness == 's':
                hair_thickness = 0.01
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyebrows_hair_thickness == 'm':
                hair_thickness = 0.02
            elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_systemeyebrows_hair_thickness == 'l':
                hair_thickness = 0.04
            else: # xl
                hair_thickness = 0.08

            hair_tip = 0
            kink_type = 'NO'

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'arm_hair':
            ###########################################################################
            ## ARM HAIR
            ###########################################################################
            parent_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemarmhair_parent_particle_amount
            child_display_render_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemarmhair_child_display_render_particle_amount
            hair_segments = 3
            strand_shape = -0.750
            hair_length = 0.060
            hair_dynamics = bpy.context.preferences.addons['create_hair_system'].preferences.systemarmhair_hair_dynamics
            material = bpy.context.preferences.addons['create_hair_system'].preferences.systemarmhair_material
            clump = 0.933
            clump_shape = 0
            use_emit_random = True
            userjit = 0
            use_even_distribution = False
            jitter_factor = 1.0
            use_length_vertex_group = False
            child_type = 'SIMPLE'
            child_radius = 0.025
            child_length = 0.500
            hair_thickness = 0.01
            hair_tip = 0
            kink_type = 'CURL'
            kink_amplitude = 0.00125
            kink_clump = 0.1
            kink_flatness = 0
            kink_frequency = 2.0
            kink_shape = 0

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'back_hair':
            ###########################################################################
            ## BACK HAIR
            ###########################################################################
            parent_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systembackhair_parent_particle_amount
            child_display_render_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systembackhair_child_display_render_particle_amount
            hair_segments = 3
            strand_shape = -0.750
            hair_length = 0.060
            hair_dynamics = bpy.context.preferences.addons['create_hair_system'].preferences.systembackhair_hair_dynamics
            material = bpy.context.preferences.addons['create_hair_system'].preferences.systembackhair_material
            clump = 0.933
            clump_shape = 0
            use_emit_random = True
            userjit = 0
            use_even_distribution = False
            jitter_factor = 1.0
            use_length_vertex_group = False
            child_type = 'SIMPLE'
            child_radius = 0.040
            child_length = 0.200
            hair_thickness = 0.04
            hair_tip = 0.02
            kink_type = 'CURL'
            kink_amplitude = 0.005
            kink_clump = 0
            kink_flatness = 0
            kink_frequency = 3.0
            kink_shape = 0

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'chest_hair':
            ###########################################################################
            ## CHEST HAIR
            ###########################################################################
            parent_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemchesthair_parent_particle_amount
            child_display_render_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemchesthair_child_display_render_particle_amount
            hair_segments = 3
            strand_shape = -0.800
            hair_length = 0.060
            hair_dynamics = bpy.context.preferences.addons['create_hair_system'].preferences.systemchesthair_hair_dynamics
            material = bpy.context.preferences.addons['create_hair_system'].preferences.systemchesthair_material
            clump = 0.933
            clump_shape = 0
            use_emit_random = True
            userjit = 0
            use_even_distribution = False
            jitter_factor = 1.0
            use_length_vertex_group = False
            child_type = 'SIMPLE'
            child_radius = 0.040
            child_length = 0.600
            hair_thickness = 0.04
            hair_tip = 0.02
            kink_type = 'CURL'
            kink_amplitude = 0.0025
            kink_clump = 0.100
            kink_flatness = 0
            kink_frequency = 4.0
            kink_shape = 0

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'leg_hair':
            ###########################################################################
            ## LEG HAIR
            ###########################################################################
            parent_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemleghair_parent_particle_amount
            child_display_render_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemleghair_child_display_render_particle_amount
            hair_segments = 3
            strand_shape = -0.750
            hair_length = 0.060
            hair_dynamics = bpy.context.preferences.addons['create_hair_system'].preferences.systemleghair_hair_dynamics
            material = bpy.context.preferences.addons['create_hair_system'].preferences.systemleghair_material
            clump = 0.933
            clump_shape = 0
            use_emit_random = True
            userjit = 0
            use_even_distribution = False
            jitter_factor = 1.0
            use_length_vertex_group = False
            child_type = 'SIMPLE'
            child_radius = 0.040
            child_length = 0.400
            hair_thickness = 0.04
            hair_tip = 0.01
            kink_type = 'CURL'
            kink_amplitude = 0.0025
            kink_clump = 0.100
            kink_flatness = 0
            kink_frequency = 4.0
            kink_shape = 0

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'stubble':
            ###########################################################################
            ## STUBBLE
            ###########################################################################
            parent_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemstubble_parent_particle_amount
            child_display_render_particle_amount = bpy.context.preferences.addons['create_hair_system'].preferences.systemstubble_child_display_render_particle_amount
            hair_segments = 3
            strand_shape = -0.800
            hair_length = 0.060
            hair_dynamics = bpy.context.preferences.addons['create_hair_system'].preferences.systemstubble_hair_dynamics
            material = bpy.context.preferences.addons['create_hair_system'].preferences.systemstubble_material
            clump = 0.933
            clump_shape = 0
            use_emit_random = True
            userjit = 0
            use_even_distribution = False
            jitter_factor = 1.0
            use_length_vertex_group = False
            child_type = 'SIMPLE'
            child_radius = 0.005
            child_length = 0.750
            hair_thickness = 0.02
            hair_tip = 0.10
            kink_type = 'NO'

        if bpy.context.preferences.addons['create_hair_system'].preferences.vertex_group_name != '':
            particles.vertex_group_density = obj.vertex_groups[bpy.context.preferences.addons['create_hair_system'].preferences.vertex_group_name].name  # Put hair on just the selected vertex group.
            if use_length_vertex_group == True:
                particles.vertex_group_length = obj.vertex_groups[bpy.context.preferences.addons['create_hair_system'].preferences.vertex_group_name].name  # ...and consider how long the hair should be based on the vertex group vertices' weight.

        psettings.use_advanced_hair = True  # Advanced checkbox
        psettings.count = parent_particle_amount  # Emission -> Number
        psettings.hair_length = hair_length  # Emission -> Hair Length
        psettings.hair_step = hair_segments  # Emission -> Segments
        psettings.use_emit_random = use_emit_random # Emission -> Source -> Random Order
        psettings.use_even_distribution = use_even_distribution # Emission -> Source -> Even Distribution
        psettings.userjit = userjit # Emission -> Source -> Particles/Face
        psettings.jitter_factor = jitter_factor # Emission -> Source -> Jittering Amount

        psettings.child_type = child_type  # Children -> Simple/Interpolated

        # Children -> Simple and Children -> Interpolated shared settings
        psettings.child_nbr = child_display_render_particle_amount  # Children -> Display Amount
        psettings.rendered_child_count = child_display_render_particle_amount  # Children -> Render Amount
        psettings.child_length = child_length  # Children -> Length -- This is how you control the lengths of ALL hairs (when Children -> Threshold is set to 0)...I don't totally understand how it works.
        psettings.child_length_threshold = 0  # Children -> Threshold -- This is how you can control the hair's REAL length. By not allowing any hairs to be longer than Children -> Length, it cuts off the length of all hairs.
        psettings.clump_factor = clump # Children -> Clumping -> Clump
        psettings.clump_shape = clump_shape # Children -> Clumping -> Shape

        # Children -> Simple-only settings
        psettings.child_radius = child_radius # Children -> Radius

        psettings.display_step = hair_segments  # Viewport Display -> Strand Steps

        try:
            if material != '':
                psettings.material_slot = material # Render -> Material
        except:
            pass

        psettings.use_hair_bspline = True  # Render -> Path -> B-Spline
        psettings.render_step = hair_segments  # Render -> Path -> Steps
        psettings.shape = strand_shape  # Hair Shape -> Strand Shape
        psettings.root_radius = hair_thickness  # Hair Shape -> Diameter Root
        psettings.tip_radius = hair_tip # Hair Shape -> Tip
        
        if kink_type != 'NO':
            psettings.kink = kink_type  # Kink -> Kink Type
            psettings.kink_amplitude = kink_amplitude # Kink -> Amplitude
            psettings.kink_amplitude_clump = kink_clump # Kink -> Clump
            psettings.kink_flat = kink_flatness # Kink -> Flatness
            psettings.kink_frequency = kink_frequency # Kink -> Frequency
            psettings.kink_shape = kink_shape # Kink -> Shape

        # We'll first turn on Hair Dynamics so we can set the Hair Dynamics-related settings.
        # If it turns out that we don't have Hair Dynamics checked in the add-on, then we'll turn it off in the Physics properties.
        # That way, if we change our mind and decide that we want hair dynamics, at least we have decent default settings as a starting point.
        particles.use_hair_dynamics = True  # Hair Dynamics checkbox

        particles.settings.factor_random = 0.01  # Velocity -> Randomize
        bpy.data.particles[SYSTEM_NAME].factor_random = 0.01

        if particles.cloth != None:
            particles.cloth.settings.mass = 0.001  # Hair Dynamics -> Structure -> Vertex Mass
            particles.cloth.settings.bending_stiffness = 1.0  # Hair Dynamics -> Structure -> Stiffness
            particles.cloth.settings.bending_damping = 0  # Hair Dynamics -> Structure -> Damping
            particles.cloth.collision_settings.distance_min = 0.001  # Hair Dynamics -> Collisions -> Distance

        # Give the cache a name...otherwise it'll be blank.
        cache_name = obj.name  # Call it the name of the object...
        if bpy.context.preferences.addons['create_hair_system'].preferences.vertex_group_name != '':
            cache_name += ' ' + bpy.context.preferences.addons['create_hair_system'].preferences.vertex_group_name  # ...but append the vertex group to be more specific (if applicable).

        # But also make sure we have a unique cache name for this object.
        # If you have the same cache name in another particle system on this object, you will not be able to create a name and Blender will not
        # automatically append a number to the name. Since you won't be able to create a name, you will run into serious problems when you
        # create the physics simulation to disk -- the multiple caches will overwrite themselves.
        # Anyway, we are compensating for Blender here by appending ".00X" to the cache if it already exists somewhere in this object.
        original_cache_name = cache_name
        index_append = 0
        while (does_cache_name_exist_in_object(cache_name)):
            index_append += 1
            cache_name = original_cache_name + '.' + '{0:03d}'.format(index_append)

        particles.point_cache.point_caches[
            -1].name = cache_name  # Cache -> Listbox with caches, first one in the list (name).

        particles.point_cache.point_caches[-1].frame_start = bpy.context.scene.frame_start  # Cache -> Simulation Start
        particles.point_cache.point_caches[-1].frame_end = bpy.context.scene.frame_end  # Cache -> (Simulation) End

        particles.point_cache.point_caches[
            -1].use_disk_cache = True  # Cache -> Disk Cache. This only works if you've already saved the file. If you haven't, no error is thrown, but the param is not set.
        particles.point_cache.point_caches[-1].compression = 'HEAVY'

        if not hair_dynamics:
            particles.use_hair_dynamics = False  # Uncheck the Hair Dynamics checkbox.

        # Go back to whatever mode we were in.
        bpy.ops.object.mode_set(mode=mode)

        ###############################################################################
        # Part 3: Add Physics -> Collection
        ###############################################################################
        self.report({'INFO'}, "Adding Physics -> Collection...")

        # Now add back in Collision on the Physics Properties tab.
        mode = bpy.context.active_object.mode
        bpy.ops.object.mode_set(mode='OBJECT')

        bpy.ops.object.modifier_add(
            type='COLLISION')  # Yes, we have to add the name as uppercase if doing it programmatically; adding it via the UI makes the name "Collision".

        # Restore all of the Collision parameters (assuming we had to delete it before adding the particle system)...
        bpy.context.object.collision.absorption = collision_absorption
        bpy.context.object.collision.permeability = collision_permeability
        bpy.context.object.collision.stickiness = collision_stickiness
        bpy.context.object.collision.use_particle_kill = collision_use_particle_kill
        bpy.context.object.collision.damping_factor = collision_damping_factor
        bpy.context.object.collision.damping_random = collision_damping_random
        bpy.context.object.collision.friction_factor = collision_friction_factor
        bpy.context.object.collision.friction_random = collision_friction_random
        bpy.context.object.collision.damping = collision_damping
        bpy.context.object.collision.cloth_friction = collision_cloth_friction
        bpy.context.object.collision.use_culling = collision_use_culling
        bpy.context.object.collision.use_normal = collision_use_normal
        bpy.context.object.collision.thickness_inner = collision_thickness_inner

        # ...and set the custom parameters we care about.
        bpy.context.object.collision.thickness_outer = 0.015  # Softbody And Cloth -> Thickness Outer

        # Go back to whatever mode we were in.
        bpy.ops.object.mode_set(mode=mode)

        self.report({'INFO'}, SCRIPT_NAME + ' - END')
        self.report({'INFO'}, '**********************************')
        self.report({'INFO'}, 'Done running script ' + SCRIPT_NAME)

        return {'FINISHED'}

class CreateHairSystemPreferencesPanel(bpy.types.AddonPreferences):
    bl_idname = __module__
    object_name: bpy.props.StringProperty(name = 'Object', default = '', description = 'The name of the object that needs hair')
    vertex_group_name: bpy.props.StringProperty(name='Vertex Group', default='', description='The vertex group on the object that needs hair')

    enum_hair_system: bpy.props.EnumProperty(
        name="",
        description="The type of hair system to create",
        items=[
            ('hair', 'Hair', 'Hair'),
            ('fur', 'Fur', 'Fur'),
            ('eyelashes', 'Eyelashes', 'Eyelashes'),
            ('eyebrows', 'Eyebrows', 'Eyebrows'),
            ('arm_hair', 'Male Arm Hair', 'Male Arm Hair'),
            ('back_hair', 'Male Back Hair', 'Male Back Hair'),
            ('chest_hair', 'Male Chest Hair', 'Male Chest Hair'),
            ('leg_hair', 'Male Leg Hair', 'Male Leg Hair'),
            ('stubble', 'Male Stubble', 'Male Stubble')
        ], default='hair')

    systemhair_material: StringProperty(name='Material', default="", description="Material for hair")
    systemfur_material: StringProperty(name='Material', default="", description="Material for fur")
    systemeyelashes_material: StringProperty(name='Material', default="", description="Material for eyelashes")
    systemeyebrows_material: StringProperty(name='Material', default="", description="Material for eyebrows")
    systemarmhair_material: StringProperty(name='Material', default="", description="Material for arm hair")
    systembackhair_material: StringProperty(name='Material', default="", description="Material for back hair")
    systemchesthair_material: StringProperty(name='Material', default="", description="Material for chest hair")
    systemleghair_material: StringProperty(name='Material', default="", description="Material for leg hair")
    systemstubble_material: StringProperty(name='Material', default="", description="Material for stubble")

    enum_systemhair_hair_length: bpy.props.EnumProperty(
        name="enum_systemhair_hair_length",
        description="How long the hair should be",
        items=[
            ('xs', 'XS', 'XS'),
            ('s', 'S', 'S'),
            ('m', 'M', 'M'),
            ('l', 'L', 'L'),
            ('xl', 'XL', 'XL')
        ], default='m')

    enum_systemfur_hair_length: bpy.props.EnumProperty(
        name="enum_systemfur_hair_length",
        description="How long the fur should be",
        items=[
            ('xs', 'XS', 'XS'),
            ('s', 'S', 'S'),
            ('m', 'M', 'M'),
            ('l', 'L', 'L'),
            ('xl', 'XL', 'XL')
        ], default='m')

    enum_systemeyelashes_hair_length: bpy.props.EnumProperty(
        name="enum_systemeyelashes_hair_length",
        description="How long the eyelashes should be",
        items=[
            ('xs', 'XS', 'XS'),
            ('s', 'S', 'S'),
            ('m', 'M', 'M'),
            ('l', 'L', 'L'),
            ('xl', 'XL', 'XL')
        ], default='m')

    enum_systemeyebrows_hair_length: bpy.props.EnumProperty(
        name="enum_systemeyebrows_hair_length",
        description="How long the eyebrows should be",
        items=[
            ('xs', 'XS', 'XS'),
            ('s', 'S', 'S'),
            ('m', 'M', 'M'),
            ('l', 'L', 'L'),
            ('xl', 'XL', 'XL')
        ], default='m')

    enum_systemhair_hair_thickness: bpy.props.EnumProperty(
        name="enum_systemhair_hair_thickness",
        description="How thick the hair should be",
        items=[
            ('xs', 'XS', 'XS'),
            ('s', 'S', 'S'),
            ('m', 'M', 'M'),
            ('l', 'L', 'L'),
            ('xl', 'XL', 'XL')
        ], default='m')

    enum_systemfur_hair_thickness: bpy.props.EnumProperty(
        name="enum_systemfur_hair_thickness",
        description="How thick the fur should be",
        items=[
            ('xs', 'XS', 'XS'),
            ('s', 'S', 'S'),
            ('m', 'M', 'M'),
            ('l', 'L', 'L'),
            ('xl', 'XL', 'XL')
        ], default='m')

    enum_systemeyelashes_hair_thickness: bpy.props.EnumProperty(
        name="enum_systemeyelashes_hair_thickness",
        description="How thick the eyelashes should be",
        items=[
            ('xs', 'XS', 'XS'),
            ('s', 'S', 'S'),
            ('m', 'M', 'M'),
            ('l', 'L', 'L'),
            ('xl', 'XL', 'XL')
        ], default='m')

    enum_systemeyebrows_hair_thickness: bpy.props.EnumProperty(
        name="enum_systemeyebrows_hair_thickness",
        description="How thick the eyebrows should be",
        items=[
            ('xs', 'XS', 'XS'),
            ('s', 'S', 'S'),
            ('m', 'M', 'M'),
            ('l', 'L', 'L'),
            ('xl', 'XL', 'XL')
        ], default='m')

    enum_systemhair_hair_segments: bpy.props.EnumProperty(
        name="enum_systemhair_hair_segments",
        description="How many segments the hair should have",
        items=[
            ('2', '2', 'For Hair Helicopter'),
            ('3', '3', 'Very stiff'),
            ('5', '5', 'Blender default amount'),
            ('7', '7', 'Reasonable amount for animated fur'),
            ('10', '10', 'Reasonable amount for animated hair'),
            ('15', '15', 'Reasonable amount for animated hair'),
        ], default='7')

    enum_systemfur_hair_segments: bpy.props.EnumProperty(
        name="enum_systemfur_hair_segments",
        description="How many segments the fur should have",
        items=[
            ('3', '3', 'Very stiff'),
            ('5', '5', 'Blender default amount'),
            ('7', '7', 'Reasonable amount for animated fur'),
            ('10', '10', 'Reasonable amount for animated hair'),
            ('15', '15', 'Reasonable amount for animated hair'),
            ('25', '25', 'Reasonable amount for long female hair')
        ], default='7')

    systemhair_parent_particle_amount: bpy.props.IntProperty(name="Parent Particle Amount", min = 0, default=100, description='The number of parent particles')
    systemhair_child_display_render_particle_amount: bpy.props.IntProperty(name="Child Display/Render Particle Amount", min = 0, default=3000, description='Starting point for the number of child particles for both Display and Render modes')
    systemfur_parent_particle_amount: bpy.props.IntProperty(name="Parent Particle Amount", min = 0, default=100, description='The number of parent particles')
    systemfur_child_display_render_particle_amount: bpy.props.IntProperty(name="Child Display/Render Particle Amount", min = 0, default=3000, description='Starting point for the number of child particles for both Display and Render modes')
    systemeyelashes_parent_particle_amount: bpy.props.IntProperty(name="Parent Particle Amount", min = 0, default=100, description='The number of parent particles')
    systemeyelashes_child_display_render_particle_amount: bpy.props.IntProperty(name="Child Display/Render Particle Amount", min = 0, default=3000, description='Starting point for the number of child particles for both Display and Render modes')
    systemeyebrows_parent_particle_amount: bpy.props.IntProperty(name="Parent Particle Amount", min = 0, default=100, description='The number of parent particles')
    systemeyebrows_child_display_render_particle_amount: bpy.props.IntProperty(name="Child Display/Render Particle Amount", min = 0, default=3000, description='Starting point for the number of child particles for both Display and Render modes')
    systemarmhair_parent_particle_amount: bpy.props.IntProperty(name="Parent Particle Amount", min = 0, default=0, description='The number of parent particles')
    systemarmhair_child_display_render_particle_amount: bpy.props.IntProperty(name="Child Display/Render Particle Amount", min = 0, default=0, description='Starting point for the number of child particles for both Display and Render modes')
    systembackhair_parent_particle_amount: bpy.props.IntProperty(name="Parent Particle Amount", min = 0, default=0, description='The number of parent particles')
    systembackhair_child_display_render_particle_amount: bpy.props.IntProperty(name="Child Display/Render Particle Amount", min = 0, default=0, description='Starting point for the number of child particles for both Display and Render modes')
    systemchesthair_parent_particle_amount: bpy.props.IntProperty(name="Parent Particle Amount", min = 0, default=0, description='The number of parent particles')
    systemchesthair_child_display_render_particle_amount: bpy.props.IntProperty(name="Child Display/Render Particle Amount", min = 0, default=0, description='Starting point for the number of child particles for both Display and Render modes')
    systemleghair_parent_particle_amount: bpy.props.IntProperty(name="Parent Particle Amount", min = 0, default=0, description='The number of parent particles')
    systemleghair_child_display_render_particle_amount: bpy.props.IntProperty(name="Child Display/Render Particle Amount", min = 0, default=0, description='Starting point for the number of child particles for both Display and Render modes')
    systemstubble_parent_particle_amount: bpy.props.IntProperty(name="Parent Particle Amount", min = 0, default=0, description='The number of parent particles')
    systemstubble_child_display_render_particle_amount: bpy.props.IntProperty(name="Child Display/Render Particle Amount", min = 0, default=0, description='Starting point for the number of child particles for both Display and Render modes')
    systemhair_hair_dynamics: bpy.props.BoolProperty(name="Hair Dynamics", description="Use physics to animate the hair", default=True)
    systemfur_hair_dynamics: bpy.props.BoolProperty(name="Hair Dynamics", description="Use physics to animate the fur", default=True)
    systemeyelashes_hair_dynamics: bpy.props.BoolProperty(name="Hair Dynamics", description="Use physics to animate the eyelashes", default=False)
    systemeyebrows_hair_dynamics: bpy.props.BoolProperty(name="Hair Dynamics", description="Use physics to animate the eyebrows", default=False)
    systemarmhair_hair_dynamics: bpy.props.BoolProperty(name="Hair Dynamics", description="Use physics to animate the arm hair", default=False)
    systembackhair_hair_dynamics: bpy.props.BoolProperty(name="Hair Dynamics", description="Use physics to animate the arm hair", default=False)
    systemchesthair_hair_dynamics: bpy.props.BoolProperty(name="Hair Dynamics", description="Use physics to animate the chest hair", default=False)
    systemleghair_hair_dynamics: bpy.props.BoolProperty(name="Hair Dynamics", description="Use physics to animate the leg hair", default=False)
    systemstubble_hair_dynamics: bpy.props.BoolProperty(name="Hair Dynamics", description="Use physics to animate the stubble", default=False)

    def draw(self, context):
        self.layout.label(text="Current values")

class CREATEHAIRSYSTEM_PT_Main(bpy.types.Panel):
    bl_idname = "CREATEHAIRSYSTEM_PT_Main"
    bl_label = "Create Hair System"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Hair"

    def draw(self, context):
        row = self.layout.row(align=True)
        row.prop_search(bpy.context.preferences.addons['create_hair_system'].preferences, "object_name", bpy.data, "objects", icon='OBJECT_DATA')

        try:
            row = self.layout.row(align=True)
            row.prop_search(bpy.context.preferences.addons['create_hair_system'].preferences, "vertex_group_name", bpy.data.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name], "vertex_groups", icon='GROUP_VERTEX')
        except:
            pass

        row = self.layout.row(align=True)
        row.label(text="Type: ")
        row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "enum_hair_system", expand=False)

        if bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'hair':
            try:
                if bpy.context.preferences.addons['create_hair_system'].preferences.systemhair_material not in bpy.context.scene.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name].material_slots:
                    bpy.context.preferences.addons['create_hair_system'].preferences.systemhair_material = "" # We had some leftover material from selecting another object, so clear this out.

                row = self.layout.row(align=True)
                row.prop_search(bpy.context.preferences.addons['create_hair_system'].preferences, "systemhair_material", bpy.data.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name], "material_slots", icon='MATERIAL_DATA')
            except:
                pass

            row = self.layout.row(align=True)
            row.label(text="Length: ")
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "enum_systemhair_hair_length", expand=True)

            row = self.layout.row(align=True)
            row.label(text="Thickness: ")
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "enum_systemhair_hair_thickness", expand=True)

            row = self.layout.row(align=True)
            row.label(text="Segments/Render Path Steps: ")
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "enum_systemhair_hair_segments", expand=True)

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemhair_parent_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemhair_child_display_render_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemhair_hair_dynamics")

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'fur':
            try:
                if bpy.context.preferences.addons['create_hair_system'].preferences.systemfur_material not in bpy.context.scene.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name].material_slots:
                    bpy.context.preferences.addons['create_hair_system'].preferences.systemfur_material = "" # We had some leftover material from selecting another object, so clear this out.

                row = self.layout.row(align=True)
                row.prop_search(bpy.context.preferences.addons['create_hair_system'].preferences, "systemfur_material", bpy.data.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name], "material_slots", icon='MATERIAL_DATA')
            except:
                pass

            row = self.layout.row(align=True)
            row.label(text="Length: ")
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "enum_systemfur_hair_length", expand=True)

            row = self.layout.row(align=True)
            row.label(text="Thickness: ")
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "enum_systemfur_hair_thickness", expand=True)

            row = self.layout.row(align=True)
            row.label(text="Segments/Render Path Steps: ")
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "enum_systemfur_hair_segments", expand=True)

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemfur_parent_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemfur_child_display_render_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemfur_hair_dynamics")

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'eyelashes':
            try:
                if bpy.context.preferences.addons['create_hair_system'].preferences.systemeyelashes_material not in bpy.context.scene.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name].material_slots:
                    bpy.context.preferences.addons['create_hair_system'].preferences.systemeyelashes_material = "" # We had some leftover material from selecting another object, so clear this out.

                row = self.layout.row(align=True)
                row.prop_search(bpy.context.preferences.addons['create_hair_system'].preferences, "systemeyelashes_material", bpy.data.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name], "material_slots", icon='MATERIAL_DATA')
            except:
                pass

            row = self.layout.row(align=True)
            row.label(text="Length: ")
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "enum_systemeyelashes_hair_length", expand=True)

            row = self.layout.row(align=True)
            row.label(text="Thickness: ")
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "enum_systemeyelashes_hair_thickness", expand=True)

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemeyelashes_parent_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemeyelashes_child_display_render_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemeyelashes_hair_dynamics")

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'eyebrows':
            try:
                if bpy.context.preferences.addons['create_hair_system'].preferences.systemeyebrows_material not in bpy.context.scene.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name].material_slots:
                    bpy.context.preferences.addons['create_hair_system'].preferences.systemeyebrows_material = "" # We had some leftover material from selecting another object, so clear this out.

                row = self.layout.row(align=True)
                row.prop_search(bpy.context.preferences.addons['create_hair_system'].preferences, "systemeyebrows_material", bpy.data.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name], "material_slots", icon='MATERIAL_DATA')
            except:
                pass

            row = self.layout.row(align=True)
            row.label(text="Length: ")
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "enum_systemeyebrows_hair_length", expand=True)

            row = self.layout.row(align=True)
            row.label(text="Thickness: ")
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "enum_systemeyebrows_hair_thickness", expand=True)

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemeyebrows_parent_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemeyebrows_child_display_render_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemeyebrows_hair_dynamics")

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'arm_hair':
            try:
                if bpy.context.preferences.addons['create_hair_system'].preferences.systemarmhair_material not in bpy.context.scene.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name].material_slots:
                    bpy.context.preferences.addons['create_hair_system'].preferences.systemarmhair_material = "" # We had some leftover material from selecting another object, so clear this out.

                row = self.layout.row(align=True)
                row.prop_search(bpy.context.preferences.addons['create_hair_system'].preferences, "systemarmhair_material", bpy.data.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name], "material_slots", icon='MATERIAL_DATA')
            except:
                pass

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemarmhair_parent_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemarmhair_child_display_render_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemarmhair_hair_dynamics")

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'back_hair':
            try:
                if bpy.context.preferences.addons['create_hair_system'].preferences.systembackhair_material not in bpy.context.scene.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name].material_slots:
                    bpy.context.preferences.addons['create_hair_system'].preferences.systembackhair_material = "" # We had some leftover material from selecting another object, so clear this out.

                row = self.layout.row(align=True)
                row.prop_search(bpy.context.preferences.addons['create_hair_system'].preferences, "systembackhair_material", bpy.data.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name], "material_slots", icon='MATERIAL_DATA')
            except:
                pass

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systembackhair_parent_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systembackhair_child_display_render_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systembackhair_hair_dynamics")

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'chest_hair':
            try:
                if bpy.context.preferences.addons['create_hair_system'].preferences.systemchesthair_material not in bpy.context.scene.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name].material_slots:
                    bpy.context.preferences.addons['create_hair_system'].preferences.systemchesthair_material = "" # We had some leftover material from selecting another object, so clear this out.

                row = self.layout.row(align=True)
                row.prop_search(bpy.context.preferences.addons['create_hair_system'].preferences, "systemchesthair_material", bpy.data.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name], "material_slots", icon='MATERIAL_DATA')
            except:
                pass

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemchesthair_parent_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemchesthair_child_display_render_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemchesthair_hair_dynamics")


        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'leg_hair':
            try:
                if bpy.context.preferences.addons['create_hair_system'].preferences.systemleghair_material not in bpy.context.scene.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name].material_slots:
                    bpy.context.preferences.addons['create_hair_system'].preferences.systemleghair_material = "" # We had some leftover material from selecting another object, so clear this out.

                row = self.layout.row(align=True)
                row.prop_search(bpy.context.preferences.addons['create_hair_system'].preferences, "systemleghair_material", bpy.data.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name], "material_slots", icon='MATERIAL_DATA')
            except:
                pass

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemleghair_parent_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemleghair_child_display_render_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemleghair_hair_dynamics")

        elif bpy.context.preferences.addons['create_hair_system'].preferences.enum_hair_system == 'stubble':
            try:
                if bpy.context.preferences.addons['create_hair_system'].preferences.systemstubble_material not in bpy.context.scene.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name].material_slots:
                    bpy.context.preferences.addons['create_hair_system'].preferences.systemstubble_material = "" # We had some leftover material from selecting another object, so clear this out.

                row = self.layout.row(align=True)
                row.prop_search(bpy.context.preferences.addons['create_hair_system'].preferences, "systemstubble_material", bpy.data.objects[bpy.context.preferences.addons['create_hair_system'].preferences.object_name], "material_slots", icon='MATERIAL_DATA')
            except:
                pass

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemstubble_parent_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemstubble_child_display_render_particle_amount")

            row = self.layout.row(align=True)
            row.prop(bpy.context.preferences.addons['create_hair_system'].preferences, "systemstubble_hair_dynamics")

        row = self.layout.row(align=True)
        row = self.layout.row(align=True)
        row.operator("chs.create_hair_system", text='Create Hair System', icon='PARTICLES')
        row.enabled = (bpy.context.preferences.addons['create_hair_system'].preferences.object_name in bpy.context.scene.objects)

def register():
    bpy.utils.register_class(CreateHairSystemPreferencesPanel)
    bpy.utils.register_class(CREATEHAIRSYSTEM_PT_CreateHairSystem)
    bpy.utils.register_class(CREATEHAIRSYSTEM_PT_Main)

def unregister():
    bpy.utils.unregister_class(CreateHairSystemPreferencesPanel)
    bpy.utils.unregister_class(CREATEHAIRSYSTEM_PT_CreateHairSystem)
    bpy.utils.unregister_class(CREATEHAIRSYSTEM_PT_Main)

if __name__ == "__main__":
    register()
