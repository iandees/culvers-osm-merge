from xml.dom.minidom import Document
import xml.etree.ElementTree as ET
from pyosm.shapeify import get_shapes
from pyosm.model import Node, Way
import requests
from math import radians, cos, sin, asin, sqrt
from datetime import datetime

def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    m = 6372800 * c
    return m

def build_tag_elem(doc, key, value):
    elem = doc.createElement('tag')
    elem.setAttribute('k', key)
    elem.setAttribute('v', value)
    return elem

def build_elem(osm_data, doc, action=None):
    elem = doc.createElement(osm_data['type'])

    elem.setAttribute('id', str(osm_data['id']))
    elem.setAttribute('visible', 'true')

    if osm_data.get('version'):
        elem.setAttribute('version', str(osm_data['version']))
    if osm_data.get('timestamp'):
        elem.setAttribute('timestamp', osm_data['timestamp'].isoformat())
    if osm_data.get('uid'):
        elem.setAttribute('uid', str(osm_data['uid']))
    if osm_data.get('user'):
        elem.setAttribute('user', osm_data['user'])
    if osm_data.get('changeset'):
        elem.setAttribute('changeset', str(osm_data['changeset']))
    if action:
        elem.setAttribute('action', action)

    for (key, value) in osm_data['tags'].items():
        elem.appendChild(build_tag_elem(doc, key, value))

    if osm_data['type'] == 'node':
        elem.setAttribute('lat', str(round(osm_data['lat'], 7)))
        elem.setAttribute('lon', str(round(osm_data['lon'], 7)))
    elif osm_data['type'] == 'way':
        for nd in osm_data['nds']:
            nd_elem = doc.createElement('nd')
            nd_elem.setAttribute('ref', str(nd))
            elem.appendChild(nd_elem)

    return elem

def get_opening_hours(crackerbarrel_poi):
    day_groups = []
    this_day_group = None
    for day in ('sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'):
        open_time = datetime.strftime(datetime.strptime(crackerbarrel_poi.find(day + '_open').text, '%I:%M %p'), '%H:%M')
        close_time = datetime.strftime(datetime.strptime(crackerbarrel_poi.find(day + '_close').text, '%I:%M %p'), '%H:%M')
        hours = open_time + "-" + close_time
        day_short = day.title()[:2]

        if not this_day_group:
            this_day_group = dict(from_day=day_short, to_day=day_short, hours=hours)
        elif this_day_group['hours'] == hours:
            this_day_group['to_day'] = day_short
        elif this_day_group['hours'] != hours:
            day_groups.append(this_day_group)
            this_day_group = dict(from_day=day_short, to_day=day_short, hours=hours)
    day_groups.append(this_day_group)

    if len(day_groups) == 1:
        opening_hours = day_groups[0]['hours']
        if opening_hours == '07:00-07:00':
            opening_hours = '24/7'
    else:
        opening_hours = ''
        for day_group in day_groups:
            if day_group['from_day'] == day_group['to_day']:
                opening_hours += '{from_day} {hours}; '.format(**day_group)
            else:
                opening_hours += '{from_day}-{to_day} {hours}; '.format(**day_group)
        opening_hours = opening_hours[:-2]

    return opening_hours

def transform_osm_data(osm_poi):
    if type(osm_poi[0]) == Node:
        kind = 'node'
    elif type(osm_poi[0]) == Way:
        kind = 'way'

    ret = {
        "lat": osm_poi[1].centroid.y,
        "lon": osm_poi[1].centroid.x,
        "type": kind,
        "id": osm_poi[0].id,
        "version": osm_poi[0].version,
        "timestamp": osm_poi[0].timestamp,
        "user": osm_poi[0].user,
        "uid": osm_poi[0].uid,
        "changeset": osm_poi[0].changeset,
        "tags": dict([(t.key, t.value) for t in osm_poi[0].tags])
    }

    if kind == 'way':
        ret['nds'] = osm_poi[0].nds

    return ret

def get_crackerbarrel_osm(fetch_from_overpass=True):
    if fetch_from_overpass:
        payload = { "data":
            """
            [out:xml][timeout:300];
            (
              node["name"~".*cracker barrel.*",i]["amenity"](14.43468021529728,-127.79296875,58.12431960569377,-63.017578125);
              way["name"~".*cracker barrel.*",i]["amenity"](14.43468021529728,-127.79296875,58.12431960569377,-63.017578125);
            );
            out meta;
            >;
            out meta qt;
            """
        }
        resp = requests.post('https://overpass-api.de/api/interpreter', data=payload)
        resp.raise_for_status()
        with open('crackerbarrel.osm', 'w') as f:
            f.write(resp.content)

    with open('crackerbarrel.osm') as data:
        return [transform_osm_data(t) for t in get_shapes(data)]

def transform_vendor_data(vendor_poi):
    return {
        "lat": float(vendor_poi.find('latitude').text),
        "lon": float(vendor_poi.find('longitude').text),
        "type": "node",
        "tags": {
            "amenity": "restaurant",
            "cuisine": "regional",
            "name": "Cracker Barrel",
            "opening_hours": get_opening_hours(vendor_poi),
            "phone": vendor_poi.find('phone').text,
            "addr:city": vendor_poi.find('city').text,
            "addr:full": vendor_poi.find('address1').text,
            "ref": vendor_poi.find('clientkey').text,
        }
    }

def get_crackerbarrel_data(fetch_from_web=True):
    if fetch_from_web:
        resp = requests.get('https://hosted.where2getit.com/crackerbarrel/ajax?lang=en_US&xml_request=<request><appkey>3C44AEBA-B85D-11E5-B8DC-C8188E89CD5A<%2Fappkey><formdata+id%3D"locatorsearch"><dataview>store_default<%2Fdataview><geolocs><geoloc><addressline>24450<%2Faddressline><%2Fgeoloc><%2Fgeolocs><searchradius>2400<%2Fsearchradius><%2Fformdata><%2Frequest>')
        resp.raise_for_status()

        with open('crackerbarrel.xml', 'w') as f:
            f.write(resp.content)

    with open('crackerbarrel.xml', 'r') as f:
        root = ET.parse(f).getroot()
        return [transform_vendor_data(row) for row in root.findall('collection/poi')]

print "Getting Cracker Barrel data."
crackerbarrel_data = get_crackerbarrel_data(False)
print "Getting OSM Cracker Barrel data"
osm_data = get_crackerbarrel_osm(False)
matches_array = []
referenced_nodes = set()

print "There are %s OSM objects and %s Cracker Barrel stations." % (len(osm_data), len(crackerbarrel_data))

# Check the area around the rest of the Divvy-sourced stations for OSM data and
# merge it together.
def match_by_distance(barrel_row):
    best_distance = 10000
    best_osm_candidate = None
    for candidate in osm_data:
        dist_m = haversine(
            barrel_row['lon'], barrel_row['lat'],
            candidate['lon'], candidate['lat']
        )

        if dist_m < best_distance:
            best_osm_candidate = candidate
            best_distance = dist_m

    if best_distance < 1000:
        matches_array.append((best_osm_candidate, barrel_row))

        # print "OSM %s %s is %0.1f meters away from Cracker Barrel %s, so matching them." % (best_osm_candidate['type'], best_osm_candidate['id'], best_distance, barrel_row['tags']['addr:full'])
        osm_data.remove(best_osm_candidate)
        return False

    return True

crackerbarrel_data = filter(match_by_distance, crackerbarrel_data)
print "After matching by distance, there are %s OSM nodes and %s unmatched Cracker Barrel restaurants." % (len(osm_data), len(crackerbarrel_data))

# Lastly, add brand new nodes based on externally-sourced data that wasn't merged in the two steps above.
new_node_id = -1
while True:
    barrel_row = crackerbarrel_data.pop()
    matches_array.append((None, barrel_row))
    if not crackerbarrel_data:
        break
print "After adding new OSM nodes, there are %s OSM nodes and %s unmatched Cracker Barrel restaurants." % (len(osm_data), len(crackerbarrel_data))


data_actions = []
for (osm_data, crackerbarrel_data) in matches_array:
    action = None
    merged_data = {}

    if osm_data:
        if crackerbarrel_data:
            # OSM data and external data both exist, need to merge
            action = 'modify'
            merged_data = osm_data

            address = crackerbarrel_data['tags']['addr:full']
            (housenumber, street) = address.split(' ', 1)
            crackerbarrel_data['tags']['addr:housenumber'] = housenumber
            crackerbarrel_data['tags']['addr:street'] = street

            merged_data['tags'].update(crackerbarrel_data['tags'])

        else:
            # OSM data that doesn't exist in external dataset
            # TODO Consider deleting the OSM data?
            continue
    else:
        if crackerbarrel_data:
            # New data not in OSM
            action = 'create'
            merged_data = crackerbarrel_data
            merged_data['id'] = new_node_id

            new_node_id -= 1

    if action:
        data_actions.append((action, merged_data))

doc = Document()
root = doc.createElement('osm')
root.setAttribute('version', '0.6')
doc.appendChild(root)
for action, osm_data in data_actions:
    root.appendChild(build_elem(osm_data, doc, action))

with open('crackerbarrel_modified.osm', 'w') as f:
    f.write(doc.toprettyxml(indent='  ', encoding='utf8'))
