#!/usr/bin/env python3

# main script for the visualiser
# this is literally just an interface between an sACNreceiver and Blender
# and the coding is really bad
# and all the comments sound really depressed
#
# also i've left a load of debug lines just commented out instead of removed


print('someone do be loading main.py doe')

import bpy
import numpy
import time
import sqlite3
import os
import sacn
import atexit
#from colormath import color_objects, color_conversions



# a Fixture
class Fixture():
    def __init__(self, data):
        # data keys we understand
        allowed_keys={'name': str, 'blender_names': dict, 'intensity': bool, 'maxwatts': int, 'pantilt': bool, 'colour': bool, 'colour_mode': str, 'zoom': bool, 'addr': int, 'intensity_chan': int, 'colour_startchan': int, 'colour_endchan': int, 'zoom_chan': int, 'pan_chan': int, 'tilt_chan': int}
        self.data = {}
        # check all the keys we've been given, see if they're allowed
        # and of the right type
        for key in data:
            if (key in list(allowed_keys.keys())) and (type(data[key]) == allowed_keys[key]):
                self.data[key] = data[key]
            else:
                if not key in list(allowed_keys.keys()):
                    raise ValueError(str(key)+' is not supported.')
                elif not type(data[key]) == allowed_keys[key]:
                    raise TypeError(str(key)+' was passed as '+str(type(data[key]))+', should be '+str(allowed_keys[key]))

        # if we know of any keys we haven't been given, add them as NoneType
        for key in allowed_keys:
            if not key in list(self.data.keys()):
                self.data[key] = None

        # make sure colour comes with colour mixing - work in progress
        self.known_colour_modes = ['rgb','cmy']
        if self.data['colour']:
            if self.data['colour_mode'] is None:
                print("Warning - you enabled colour but didn't assign a colour mode.")
                self.data['colour_mode'] = 'rgb'
            self.data['colour_mode'] = self.data['colour_mode'].lower()
            if not self.data['colour_mode'] in self.known_colour_modes:
                raise ValueError(str(self.data['colour_mode'])+' is not supported.')

        # if everything gets controlled by the colour channels,
        # set intensity to max by default
        if not self.data['intensity']:
            self.set_intensity(255)

    # get a part of the light by key
    def get_blender_obj(self, key):
        return bpy.data.objects[self.data['blender_names'][key]]


    # get an absolute dmx address
    # dmx addresses start from 1 but lists
    # start from ZERO, remember to subtract one from
    # this or things will shit
    def get_absolute_addr(self, relative_addr):
        return self.data['addr']-1+relative_addr


    # generate addressing data
    def get_addr_data(self, key):
        enabled = False
        addressing = []
        misc = {}
        if key == 'pantilt':
            if self.data['pantilt']:
                enabled = True
                addressing = [self.data['pan_chan'], self.data['tilt_chan']]

            else:
                addressing = None

        elif key == 'colour':
            if self.data['colour']:
                enabled = True
                for i in range(self.data['colour_endchan']-self.data['colour_startchan']+1):
                    addressing.append(self.data['colour_startchan']+i-1)

                misc['mode'] = self.data['colour_mode']

            else:
                addressing = None

        elif key == 'intensity':
            if self.data['intensity']:
                enabled = True
                addressing = [self.data['intensity_chan']]

            else:
                addressing = None

        elif key == 'zoom':
            if self.data['zoom']:
                enabled = True
                addressing = [self.data['zoom_chan']]

            else:
                addressing = None

        else:
            raise ValueError('get_addr_data doesn\'t recognize key '+str(key))

        # convert our relative address into an absolute one
        if addressing is not None:
            absolute_addressing = []
            for addr in addressing:
                absolute_addressing.append(self.get_absolute_addr(addr))
        else:
            absolute_addressing = addressing

        return {'parameter': key, 'enabled': enabled, 'addressing': absolute_addressing, 'misc': misc}

    def get_addressing(self):
        pantilt = self.get_addr_data('pantilt')
        colour = self.get_addr_data('colour')
        intensity = self.get_addr_data('intensity')
        zoom = self.get_addr_data('zoom')

        return {'pantilt': pantilt, 'colour': colour, 'intensity': intensity, 'zoom': zoom}


    # parse an sacn.DataPacket object
    def parse_dmx(self, dmx):
        dmx_data = dmx.dmxData

        addressing = self.get_addressing()

        if addressing['pantilt']['enabled']:
            pan_data = dmx_data[addressing['pantilt']['addressing'][0]-1]
            tilt_data = dmx_data[addressing['pantilt']['addressing'][1]-1]
            self.set_pantilt([pan_data, tilt_data])

        if addressing['colour']['enabled']:
            colour_data = []
            for addr in addressing['colour']['addressing']:
                colour_data.append(dmx_data[addr])

            self.set_colour(colour_data)

        if addressing['intensity']['enabled']:
            intensity_data = dmx_data[addressing['intensity']['addressing'][0]-1]
            self.set_intensity(intensity_data)

        if addressing['zoom']['enabled']:
            zoom_data = dmx_data[addressing['zoom']['addressing'][0]-1]
            self.set_zoom(zoom_data)




    # set intensity out of 255
    def set_intensity(self, intensity):
        if not self.data['intensity']:
            print("This fixture doesn't have an intensity parameter!")
            return False

        lamp = self.get_blender_obj('lamp').data
        new_intensity = (intensity/255)*self.data['maxwatts']
        lamp.energy = new_intensity
        return new_intensity

    # get intensity
    def get_intensity(self):
        if not self.data['intensity']:
            print("This fixture doesn't have an intensity parameter!")
            return False

        watts = self.get_blender_obj('lamp').data.energy
        # return a PERCENTAGE
        return 100*(watts/self.data['maxwatts'])


    # set pan, tilt in DEGREES
    # currently works between 0-255.
    # something spicy happens and it basically translates it
    # into a val between -180 and 180
    # (if you're lucky)

    # update: this works between 0-180 degrees. I don't know why.
    # no way am i changing it on a fixture-by-fixture basis either

    # pass in [pan, tilt]
    def set_pantilt(self, pantilt):
        if not self.data['pantilt']:
            print("This fixture doesn't have pan and tilt enabled!")
            return False

        self.get_blender_obj('arms').rotation_euler[2] = numpy.radians(((pantilt[0]-127)/255)*360)
        self.get_blender_obj('head').rotation_euler[0] = numpy.radians(((pantilt[1]-127)/255)*360)
        return pantilt

    # get pan and tilt
    # same as above, returns [pan, tilt]
    def get_pantilt(self):
        if not self.data['pantilt']:
            print("This fixture doesn't have pan and tilt enabled!")
            return False
        pan = numpy.degrees(self.get_blender_obj('arms').rotation_euler[2])
        tilt = numpy.degrees(self.get_blender_obj('head').rotation_euler[0])
        return [pan,tilt]

    # set pan
    def set_pan(self, pan):
        return self.set_pantilt([pan, self.get_pantilt()[1]])

    # set tilt
    def set_tilt(self, tilt):
        return self.set_pantilt([self.get_pantilt()[0], tilt])

    # set colour
    # different mix modes are work in progress, currently
    # we only support rgb
    # blender automatically uses rgb 0-255 anyway! :))))

    # update: cmy is hella easy to calculate. well i never
    def set_colour(self, new_col):
        if not self.data['colour']:
            print("This fixture doesn't have colour enabled!")
            return False

        # if we accept, for example, 3 colours but we have 6 colour channels, it's most likely 16-bit colour
        if len(self.data['colour_mode'])*2 == (self.data['colour_endchan']-self.data['colour_startchan'])+1:
            #raise Exception('16-bit colour detected, please fuck yourself.')
            # no we're big boys now we can handle this

            # i haven't even tested if i need to copy this or not but i aint risking it
            old_col = new_col.copy()
            new_col = []
            # set new_col to every other value in old_col
            for i in range(len(self.data['colour_mode'])):
                new_col[i] = old_col[i*2]

        # DISCLAIMER: 16-bit colour support is UNTESTED and PROBABLY DOESN'T WORK.
        # please, just use a different mode, or change the profile, or something


        if self.data['colour_mode'] == 'rgb':
            self.get_blender_obj('lamp').data.color = new_col
            return new_col

        elif self.data['colour_mode'] == 'cmy':
            # the old method is shit
            '''
            cmy_object = color_objects.CMYColor(new_col[0],new_col[1],new_col[2])
            rgb_object = color_conversions.convert_color(cmy_object, color_objects.sRGBColor)

            rgb_list = list(rgb_object.get_upscaled_value_tuple())
            self.get_blender_obj('lamp').data.color = rgb_list
            return rgb_object
            '''
            self.get_blender_obj('lamp').data.color = [255-new_col[0], 255-new_col[1], 255-new_col[2]]

        else:
            # you wouldn't think people are this dumb but they are
            raise ValueError('Looks like support for '+self.data['colour_mode']+' mixing is a work in progress!')

    # get colour
    def get_colour(self):
        if not self.data['colour']:
            print("This fixture doesn't have colour enabled!")
            return False

        if self.data['colour_mode'] in ['rgb','cmy']:
            return self.get_blender_obj['lamp'].data.color

        else:
            raise ValueError('Looks like support for '+self.data['colour_mode']+' mixing is a work in progress!')


    # Pass in a zoom angle between 0 and 255, change it to between 0 and 180, then do unspeakable things
    # to it so that it's formatted for Blender's strange spot_size logic
    def set_zoom(self, zoom):
        if not self.data['zoom']:
            print("This fixture doesn't have zoom enabled!")
            return False

        if zoom > 255 or zoom < 0:
            raise ValueError('Zoom must be in [0, 255]')

        zoom = 180*(zoom/255)

        lamp = self.get_blender_obj('lamp').data
        lamp.spot_size = ((zoom/180)*(3.14159-0.0174533))+0.0174533
        return zoom

    # get the zoom angle
    def get_zoom(self):
        if not self.data['zoom']:
            print("This fixture doesn't have zoom enabled!")
            return False

        blender_zoom = self.get_blender_obj('lamp').data.spot_size
        normal_zoom = ((blender_zoom-0.0174533)/(3.14159-0.0174533))*180
        return normal_zoom


# update the viewport
# you're really not meant to do this i only used it
# for testing early on
def update():
    print('updating')
    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=20)

# testing stuff
def sleep():
    print('sleeping')
    time.sleep(2)

# i am the god of testing
def updateAndSleep():
    update()
    sleep()

# testing infrastructure 100
def test(test_light):

    print('intensity 0')
    test_light.set_intensity(0)
    updateAndSleep()

    print('intensity 100')
    test_light.set_intensity(100)
    updateAndSleep()

    print('tilt down')
    test_light.set_tilt(95)
    updateAndSleep()

    print('tilt up')
    test_light.set_tilt(0)
    updateAndSleep()

    print('Pan left')
    test_light.set_pan(90)
    updateAndSleep()

    print('Pan right')
    test_light.set_pan(-90)
    updateAndSleep()

    print('Pan center')
    test_light.set_pan(0)
    updateAndSleep()

    print('r')
    test_light.set_colour([255,0,0])
    updateAndSleep()

    print('g')
    test_light.set_colour([0,255,0])
    updateAndSleep()

    print('b')
    test_light.set_colour([0,0,255])
    updateAndSleep()

    print('w')
    test_light.set_colour([255,255,255])
    updateAndSleep()

    print('zoom big')
    test_light.set_zoom(90)
    updateAndSleep()

    print('zoom small')
    test_light.set_zoom(15)
    updateAndSleep()

    print('zoom normal')
    test_light.set_zoom(30)
    updateAndSleep()

    print('done')

#test()

# get a db table
def get_db(path, table):
    conn = sqlite3.connect(path)
    curs = conn.cursor()
    curs.execute('SELECT * FROM '+table)
    data = curs.fetchall()
    curs.close()
    conn.close()
    return data


# get object children
# this is inefficient as fuck but it's the only way
def getChildren(myObject):
    children = []
    for ob in bpy.data.objects:
        if ob.parent == myObject:
            children.append(ob)
    return children


# find child object whose name starts with something
def get_target_object(parent, starts_with):
    children = getChildren(parent)
    potential_targets = []
    for child in children:
        if child.name.startswith(starts_with):
            potential_targets.append(child)

    if len(potential_targets) > 1:
        print('Multiple children could be the target, try renaming some.')
        return False

    final_target = potential_targets[0]
    return final_target


# given the name of the base object, get blender names for the arms, head and lamp
# cOnVeNtIoNs mUsT bE fOlLoWeD:
#   - arms must start with "Arms"
#   - head must start with "Head"
#   - lamp must start with "Lamp" and be of type SpotLight (or whatever the fuck
#     they rename it to in the next version of Blender)
#
#   - Arms must be a direct child of the base
#   - Head must be a direct child of the arms
#   - Lamp must be a direct child of the head
#
# shit is pretty self explanatory though tbh

def get_blender_names(base):
    base_obj = bpy.data.objects[base]
    arms_obj = get_target_object(base_obj, 'Arms')
    head_obj = get_target_object(arms_obj, 'Head')
    lamp_obj = get_target_object(head_obj, 'Lamp')

    return {'arms': arms_obj.name, 'lamp': lamp_obj.name, 'head': head_obj.name}


# if the boolkey in the source is true, set the target's
# copykey to the source's copykey
def set_conditional(boolkey, copykey, source, target):
    if source[boolkey]:
        target[copykey] = source[copykey]


# generate a Fixture from our (basic) fixture library
def generate_fixture(name, addr, blender_base):
    # modify this if you've made a huge or tiny scene and you want
    # everything brighter/dimmer
    INTENSITY_COEFFICIENT = 10

    cwd = os.getcwd()
    db_path = '/fixtures.db'

    fixtures_data = list(get_db(cwd+db_path, 'fixture_names'))
    # that gives us a list of 1-tuples, let's convert them to a list
    fixtures = []
    for item in fixtures_data:
        fixtures.append(item[0])


    if not name in fixtures:
        print("This fixture isn't in our library!")
        return False

    fixtures_db = get_db(cwd+db_path,'Fixtures')
    fixture_info = list(fixtures_db[fixtures.index(name)])
    fixture_info_clean = []

    #print(fixture_info)

    # me and the boys implementing static typing
    NoneType = type(None)

    columns = ['has_intensity','has_pantilt','has_zoom','name','maxwatts','has_colour','colour_mode','addresses','manufacturer','model','intensity_chan','pan_chan','tilt_chan','colour_startchan','colour_endchan','zoom_chan']
    column_types = [[bool],[bool],[bool],[str],[int],[bool],[str, NoneType],[int],[str, NoneType],[str, NoneType],[int, NoneType],[int, NoneType],[int, NoneType],[int, NoneType],[int, NoneType],[int, NoneType]]

    for index, val in enumerate(fixture_info):
        this_val = val
        if not (type(this_val) in column_types[index]):
            this_val = column_types[index][0](this_val)


        fixture_info_clean.insert(index, this_val)

    fixture_info_dict = {}
    for i, column in enumerate(columns):
        fixture_info_dict[column] = fixture_info_clean[i]

    blender_names = get_blender_names(blender_base)
    fixture_info_formatted = {'name': name,
    'blender_names': blender_names,
    'intensity': fixture_info_dict['has_intensity'],
    'maxwatts': fixture_info_dict['maxwatts'],
    'pantilt': fixture_info_dict['has_pantilt'],
    'colour': fixture_info_dict['has_colour'],
    'zoom': fixture_info_dict['has_zoom'],
    'addr': addr
    }

    set_conditional('has_colour', 'colour_mode',  fixture_info_dict, fixture_info_formatted)
    set_conditional('has_colour', 'colour_startchan',  fixture_info_dict, fixture_info_formatted)
    set_conditional('has_colour', 'colour_endchan',  fixture_info_dict, fixture_info_formatted)

    set_conditional('has_intensity', 'intensity_chan',  fixture_info_dict, fixture_info_formatted)

    set_conditional('has_pantilt', 'pan_chan',  fixture_info_dict, fixture_info_formatted)
    set_conditional('has_pantilt', 'tilt_chan',  fixture_info_dict, fixture_info_formatted)

    set_conditional('has_zoom', 'zoom_chan',  fixture_info_dict, fixture_info_formatted)

    fixture_info_formatted['maxwatts'] = fixture_info_formatted['maxwatts']*INTENSITY_COEFFICIENT


        #fixture_info_formatted['colour_mode'] = 'rgb'bpy.context.active_object.animation_data_clear()

    print(fixture_info_formatted)

    fixture = Fixture(fixture_info_formatted)

    return fixture



fixtures = {}

# we create the receiver and then we're like
# "fUcK make it safe before my code crashes"

receiver = sacn.sACNreceiver()
def quit():
    print('quitting')
    receiver.stop()
atexit.register(quit)

# phew

# this, this right here, is the cause of every single threading issue
# in the visualiser
receiver.start()
# bitch


# TODO FOR RECORDING:
#   - Current keyframe always calculated to be 0
#   - Keyframes aren't being recorded.

# insert locrotscale keyframes for an object
def insert_locrotscale(obj, frame):
    obj.keyframe_insert(data_path="location", frame=frame)
    obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    obj.keyframe_insert(data_path="scale", frame=frame)

# insert color, energy, spot_size keyframes for a SpotLight
def insert_lightdata(light, frame):
    light.keyframe_insert(data_path='color', frame=frame)
    light.keyframe_insert(data_path='energy', frame=frame)
    light.keyframe_insert(data_path='spot_size', frame=frame)

# insert keyframes for all fixtures in a uni
def insert_keyframes(uni, frame_no):
    # iterate over fixtures in the uni
    for fixture in fixtures[uni]:
        insert_locrotscale(bpy.data.objects[fixture.data['blender_names']['arms']], frame_no)
        insert_locrotscale(bpy.data.objects[fixture.data['blender_names']['head']], frame_no)
        insert_lightdata(bpy.data.objects[fixture.data['blender_names']['lamp']].data, frame_no)

# callback for a packet. cause we don't know how many dmx unis
# we might have, we don't get to use decorators so we need
# a function that does all the shit
def packetCallback(packet):
    print('received packet on uni '+str(packet.universe)+'!')
    print(packet.dmxData)
    for fix in fixtures[packet.universe]:
        fix.parse_dmx(packet)

    if recording:
        print('recording packet')
        fps=24
        # check if it's been a whole-ish number of
        # frames since we started.

        current_time = time.time()
        diff = current_time-start_time
        print(diff % (1/fps))
        if diff % (1/fps) < 1:
            frame_no = round(diff / (1/fps))
            print('Inserting new keyframe @ '+str(frame_no))
            insert_keyframes(packet.universe, frame_no)




recording = False

# THIS IS WHERE YOU DO STUFF. PLEASE, DO STUFF NOWHERE ELSE.
# update: we now use patch.db so please do not do stuff here
# double update: you still have to do the universes and the patch here
# triple update: we now store this entire script externally so in fact the universes and the patch are loaded from the caller

def get_fixtures():
    print('reading patch database')
    global fixtures
    global recording

    # these three should come in from the Blender script
    global universe_count
    global patch_path
    global record_mode

    recording = record_mode
    universes = universe_count
    db_path = patch_path

    # if we're recording, delete all keyframes before we even start
    if recording:
        print('resetting keyframe data')
        #for obj in bpy.data.objects:
            #object.animation_data_clear()

    cwd = os.getcwd()
    full_db_path = cwd+'/./'+db_path
    print(full_db_path)
    patch = get_db(full_db_path,'Patch')

    for i in range(universes):
        print('Configuring Universe '+str(i+1))
        fixtures[i+1] = []
        receiver.register_listener('universe', packetCallback, universe=i+1)


    for fixture in patch:
        fixtures[fixture[3]].append(generate_fixture(fixture[0],fixture[1],fixture[2]))

    #print(fixtures)



#test(test_light)

# convert a value out of 255 to a value out of 100
# does he ever actually use this function? we will never know
def dmx_to_percent(out_of_255):
    return 100*(out_of_255/255)

# todo: the Fixture should always accept 0-255 values and process internally
# done

# sacn module is weird, cos they use decorators or some shit
# we have to define callbacks for each uni individually.
# i swear there's a thing for this, working on it.

# it have been fixed

'''
@receiver.listen_on('universe',universe=1)
def callback1(packet):
    print('received packet!')
    print(packet.dmxData)
    for fix in fixtures:
        fix.parse_dmx(packet)
'''

# PLEASE FIGURE OUT THE SHIT WITH ADDRESSING
# done


# ok so normally i'd add an if __name__ == '__main__'
# but cause this gets called from Blender i have no idea
# what __name__ will actually be
# besides, if you don't call the script from blender
# you won't even get this far, you'll get an ImportError for bpy


get_fixtures()
start_time = time.time()
#print(get_db('

# cause of threading and stuff this doesn't get blocked
print('receiver running')


'''
print('test')
test_light.set_colour([255,0,0,])
updateAndSleep()
test_light.set_colour([255,255,255])
update()
'''

'''
test_light.set_pantilt([127,127])
test_light.set_zoom(90)
for i in range(16):
    test_light.set_zoom(test_light.get_zoom()-5)
    update()

for i in range(16):
    test_light.set_zoom(test_light.get_zoom()+5)
    update()
'''
