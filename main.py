import webbrowser
import json
import pandas as pd
from urllib.parse import quote
import requests
import random
import tkinter as tk
from tkinter import *
import overpy
from haversine import haversine, inverse_haversine, Direction, Unit
import sys
import os


api_key = 'Air2eVsMuWPALfj-EVx62avI4ZjcTD86eOQAKFC7IfJpVzw9WCii7ycjX-0qN6ra'
slo_coords = [35.2853287, -120.6589948]
start_coords_ints = {}  # dict of starting coordinates sets with associated intersection lists


# from user max at https://stackoverflow.com/questions/7674790/bundling-data-files-with-pyinstaller-onefile/13790741
# #13790741
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


# get intersections from geojson file
def get_ints_file(filename):
    f = open(filename, 'r')
    ints_json = json.load(f)
    df_ints = pd.json_normalize(ints_json['features'])

    # extract latitude and longitude as separate columns in dataframe
    for i in df_ints.index:
        df_ints.at[i, 'lon'] = df_ints.loc[i]['geometry.coordinates'][0]
        df_ints.at[i, 'lat'] = df_ints.loc[i]['geometry.coordinates'][1]

    df_ints = df_ints[['lon', 'lat']]   # remove unnecessary columns

    return df_ints


# check previously used starting coordinates to see if a suitable intersection set exists
def check_prev_starts(start_coords):
    # print('checking previous start coordinates')

    for prev_coords in start_coords_ints.keys():
        # convert string coordinates back to list form
        prev_coords_dec = [float(prev_coords[1:prev_coords.find(',')]), float(prev_coords[prev_coords.find(',') + 1:-1])]

        # if start location is within 1 mile of previously used start, use existing intersections set
        if haversine(prev_coords_dec, start_coords) < 1.0:
            # print('found previously used start coordinates')
            return start_coords_ints[prev_coords]

    # print('didn\'t find previously used start coordinates')

    return pd.DataFrame()   # return empty dataframe to indicate no usable set of intersections found


# get intersections from overpass api call centered at starting location
def get_ints_coords(start_coords):
    # print(start_coords_ints)

    df_ints = check_prev_starts(start_coords)

    if df_ints.empty is False:
        # print('using previously generated intersections set')
        return df_ints

    dist = 1.0

    # get bounds for area to find intersections
    s = inverse_haversine(start_coords, dist, Direction.SOUTH, unit=Unit.MILES)[0]
    w = inverse_haversine(start_coords, dist, Direction.WEST, unit=Unit.MILES)[1]
    n = inverse_haversine(start_coords, dist, Direction.NORTH, unit=Unit.MILES)[0]
    e = inverse_haversine(start_coords, dist, Direction.EAST, unit=Unit.MILES)[1]

    # print(s)
    # print(w)
    # print(n)
    # print(e)

    api = overpy.Overpass()

    # query from user tyr at https://stackoverflow.com/questions/12965090/get-list-of-all-intersections-in-a-city
    query = '''<!-- Only select the type of ways you are interested in -->
    <query type="way" into="relevant_ways">
      <has-kv k="highway"/>
      <has-kv k="highway" modv="not" regv="path|footway|motorway|cycleway|service|track"/>
      <bbox-query s="%s" w="%s" n="%s" e="%s"/>
    </query>

    <!-- Now find all intersection nodes for each way independently -->
    <foreach from="relevant_ways" into="this_way">

      <!-- Get all ways which are linked to this way -->
      <recurse from="this_way" type="way-node" into="this_ways_nodes"/>
      <recurse from="this_ways_nodes" type="node-way" into="linked_ways"/>
      <!-- Again, only select the ways you are interested in, see beginning -->
      <query type="way" into="linked_ways">
        <item set="linked_ways"/>
        <has-kv k="highway"/>
        <has-kv k="highway" modv="not" regv="path|footway|motorway|cycleway|service|track"/>
      </query>

      <!-- Get all linked ways without the current way -->
      <difference into="linked_ways_only">
        <item set="linked_ways"/>
        <item set="this_way"/>
      </difference>
      <recurse from="linked_ways_only" type="way-node" into="linked_ways_only_nodes"/>

      <!-- Return all intersection nodes -->
      <query type="node">
        <item set="linked_ways_only_nodes"/>
        <item set="this_ways_nodes"/>
      </query>
      <print/>
    </foreach>''' % (str(s), str(w), str(n), str(e))

    result = api.query(query)
    ints = {'lat': [], 'lon': []}

    for node in result.nodes:
        ints['lat'].append(node.lat)
        ints['lon'].append(node.lon)

    df_ints_new = pd.DataFrame(ints).astype(float)[:625]
    start_coords_ints[str(start_coords)] = df_ints_new

    return df_ints_new


# given a street address, return the address's latitude and longitude
def get_coords(address):
    addr_enc = quote(address)
    # print(addr_enc)
    response = requests.get('http://dev.virtualearth.net/REST/v1/Locations/%s?maxResults=1&key=%s' %
                            (addr_enc, api_key))
    # print(response.text)
    loc_data = json.loads(response.text)
    try:
        coords = loc_data['resourceSets'][0]['resources'][0]['geocodePoints'][0]['coordinates']
        return coords
    except:
        return -1


# build list of destinations for use in json object
def get_dests(df_ints):
    dests = []

    for i in df_ints.index:
        dest = {
            'latitude': df_ints.loc[i]['lat'],
            'longitude': df_ints.loc[i]['lon']
        }

        dests.append(dest)

    return dests


# build json object for use in Bing Maps POST request
def build_json(curr_coords, dests):
    json_obj = {
        'origins': [{
            'latitude': curr_coords[0],
            'longitude': curr_coords[1]
        }],
        'destinations': dests,
        'travelMode': 'walking'
    }

    return json_obj


# get distances from current point to all intersections in area
def get_dists(curr_coords, dests):
    json_obj = build_json(curr_coords, dests)
    # print(json_obj)
    url = 'https://dev.virtualearth.net/REST/v1/Routes/DistanceMatrix?key=%s' % api_key
    response = requests.post(url, json=json_obj)
    # print(response.text)
    data_dists = json.loads(response.text)['resourceSets'][0]['resources'][0]['results']

    df_dists = pd.json_normalize(data_dists)
    df_dists.sort_values('travelDistance', inplace=True)
    df_dists = df_dists[['travelDistance']]
    df_dists['travelDistance'] = df_dists['travelDistance'] * 0.6213712     # convert to miles

    return df_dists


# from the set of intersections, select and return an intersection within a certain distance of the current waypoint
def sel_wypt(curr_coords, dests):
    df_dists = get_dists(curr_coords, dests)
    df_dists = df_dists[df_dists['travelDistance'] > 1]
    df_dists = df_dists[df_dists['travelDistance'] < 1.25]
    # print(df_dists)

    try:
        index = random.choice(df_dists.index)
    except:
        return -1

    wypt = [dests[index]['latitude'], dests[index]['longitude']]
    # print(wypt)

    return wypt


# select waypoints to be used in route
def sel_wypts(df_ints, start_coords, distance):
    wypts = [start_coords]
    dests = get_dests(df_ints)
    # print(dests)

    # for each mile in route, select a waypoint
    for i in range(0, distance - 1):
        wypt = sel_wypt(wypts[-1], dests)

        if wypt == -1:
            return -1

        wypts.append(wypt)

    wypts.append(start_coords)

    return wypts


# send waypoints to google maps in url to be opened on device
def gen_route(waypoints):
    url = 'http://google.com/maps/dir/?api=1'

    wypt = waypoints[0]
    url += '&origin=' + quote(str(wypt[0]) + ',' + str(wypt[1]))

    wypt = waypoints[-1]
    url += '&destination=' + quote(str(wypt[0]) + ',' + str(wypt[1]))

    url += '&travelmode=walking'
    url += '&waypoints='

    for wypt in waypoints[1:-2]:
        url += quote(str(wypt[0]) + ',' + str(wypt[1]) + '|')

    wypt = waypoints[-2]
    url += quote(str(wypt[0]) + ',' + str(wypt[1]))

    # print(url)

    webbrowser.open(url)


def err_start():
    root = Tk()
    text = Text(root)
    text.insert(INSERT, 'ERROR: Invalid starting location')
    text.pack()
    root.mainloop()


def run_program(start, distance):
    filename = resource_path('slo_ints.geojson')
    start_coords = get_coords(start)

    if start_coords == -1:
        err_start()
        return

    # print(start_coords)

    # if starting in SLO, load pre-generated geojson
    if haversine(start_coords, slo_coords) < 3:
        df_ints = get_ints_file(filename)
    else:   # call overpass api to get nearby intersections
        df_ints = get_ints_coords(start_coords)

    # print(type(df_ints.iloc[0]['lat']))
    # print(df_ints)

    waypoints = sel_wypts(df_ints, start_coords, distance)

    if waypoints == -1:
        err_start()
        return

    # print(waypoints)
    gen_route(waypoints)


class Prompt(Frame):
    def __init__(self):
        tk.Frame.__init__(self)
        self.pack()
        self.master.title('LoopRun')

        self.label1 = Label(self, text='Route Length (2-10 miles)')
        self.label1.pack()
        self.spin_box = Spinbox(self, from_=2, to=10)
        self.spin_box.pack()

        self.label2 = Label(self, text='Starting Location')
        self.label2.pack()
        self.entry = Entry(self, bd=5)
        self.entry.pack()

        self.button = Button(self, text='Generate Route', command=lambda: run_program(self.entry.get(),
                                                                                      int(self.spin_box.get())))
        self.button.pack()


def main():
    Prompt().mainloop()


if __name__ == '__main__':
    main()
