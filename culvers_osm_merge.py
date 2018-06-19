from xml.dom.minidom import Document, parse
from pyosm.shapeify import get_shapes
from pyosm.model import Node, Way
import requests
import csv
import shutil
from math import radians, cos, sin, asin, sqrt

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
    if type(osm_data) == Node:
        elem = doc.createElement('node')
    elif type(osm_data) == Way:
        elem = doc.createElement('way')

    elem.setAttribute('id', str(osm_data.id))
    elem.setAttribute('visible', 'true')

    if osm_data.version:
        elem.setAttribute('version', str(osm_data.version))
    if action:
        elem.setAttribute('action', action)
    for tag in osm_data.tags:
        elem.appendChild(build_tag_elem(doc, tag.key, tag.value))

    if type(osm_data) == Node:
        elem.setAttribute('lat', str(round(osm_data.lat, 7)))
        elem.setAttribute('lon', str(round(osm_data.lon, 7)))
    elif type(osm_data) == Way:
        for nd in osm_data.nds:
            nd_elem = doc.createElement('nd')
            nd_elem.setAttribute('ref', str(nd))
            elem.appendChild(nd_elem)

    return elem

def get_culvers_osm(fetch_from_overpass=False):
    if fetch_from_overpass:
        body = """[out:xml][timeout:90];
            (
              node["name"~"^Culver'?s$"];
              way["name"~"^Culver'?s$"];
              relation["name"~"^Culver'?s$"];
            );
            out body;
            >;
            out id meta;"""
        resp = requests.post('http://overpass-api.de/api/interpreter', data=body)
        resp.raise_for_status()
        with open('culvers.osm', 'w') as f:
            f.write(resp.text)

    with open('culvers.osm', 'rb') as f:
        return [t for t in get_shapes(f)]

def get_culvers_data(fetch_from_web=False):
    if fetch_from_web:
        params = {
            "xml_request": '<request><appkey>1099682E-D719-11E6-A0C4-347BDEB8F1E5</appkey><formdata id="locatorsearch"><dataview>store_default</dataview><order></order><limit>250</limit><geolocs><geoloc><longitude></longitude><latitude></latitude><country>US</country></geoloc></geolocs><searchradius>250</searchradius></formdata></request>',
        }
        resp = requests.get('https://hosted.where2getit.com/culvers/2015/ajax', params=params, stream=True)
        resp.raise_for_status()
        with open('culvers.xml', 'w') as f:
            f.write(resp.text)

    def convert_hours(bho):
        return None

    def get(poi_elem, node_name):
        e = poi_elem.getElementsByTagName(node_name)

        if not e or len(e) != 1:
            return None

        e = e[0].firstChild

        if not e:
            return None

        return e.data

    def convert(poi_elem):
        return {
            'name': "Culver's",
            'lat': float(get(poi_elem, 'latitude')),
            'lon': float(get(poi_elem, 'longitude')),
            'phone': get(poi_elem, 'phone'),
            'website': get(poi_elem, 'url'),
            'ref': get(poi_elem, 'clientkey'),
            'opening_hours': convert_hours(get(poi_elem, 'bho')),
            'addr:full': get(poi_elem, 'address1'),
        }

    with open('culvers.xml', 'r') as f:
        return [convert(row) for row in parse(f).getElementsByTagName('poi')]

print("Getting Culver's data.")
culvers_data = get_culvers_data(False)
print("Getting OSM Culver's data")
osm_data = get_culvers_osm(False)
matches_array = []

print("There are %s OSM objects and %s Culver's locations." % (len(osm_data), len(culvers_data)))

def match_by_distance(culvers_row):
    best_distance = 1000
    best_candidate = None
    for candidate in osm_data:
        osm_centroid = candidate[1].centroid
        dist_m = haversine(culvers_row['lon'], culvers_row['lat'], osm_centroid.x, osm_centroid.y)

        if dist_m < best_distance:
            best_candidate = candidate
            best_distance = dist_m

    if best_distance < 100:
        matches_array.append((best_candidate, culvers_row))

        print("OSM %s %s is %0.1f meters away from Culver's %s, so matching them." % (
            type(best_candidate[0]), best_candidate[0].id, best_distance, culvers_row['ref']
        ))
        osm_data.remove(best_candidate)
        return False

    return True

culvers_data = list(filter(match_by_distance, culvers_data))
print("After matching by distance, there are %s OSM nodes and %s unmatched Culver's restaurants." % (len(osm_data), len(culvers_data)))

# Lastly, add brand new nodes based on Divvy-sourced data that wasn't merged in the two
# steps above.
new_node_id = -1
while True:
    culvers_row = culvers_data.pop()
    matches_array.append((None, culvers_row))
    if not culvers_data:
        break
print("After adding new OSM nodes, there are %s OSM nodes and %s unmatched Culver's restaurants." % (len(osm_data), len(culvers_data)))

doc = Document()
root = doc.createElement('osm')
root.setAttribute('version', '0.6')
doc.appendChild(root)

for (osm_data, culvers_data) in matches_array:
    if osm_data:
        #elem = build_elem(osm_data, doc, 'modify')
        if culvers_data:
            # OSM data and external data both exist, need to merge
        else:
            # OSM data that doesn't exist in external dataset
            continue
    else:
        if culvers_data:
            # New data not in OSM
            elem = doc.createElement('node')
            elem.setAttribute('id', str(new_node_id))
            elem.setAttribute('visible', 'true')
            elem.setAttribute('lat', str(culvers_data['lat']))
            elem.setAttribute('lon', str(culvers_data['lon']))
            elem.setAttribute('action', 'create')
            elem.appendChild(build_tag_elem(doc, 'amenity', 'fast_food'))
            elem.appendChild(build_tag_elem(doc, 'name', "Culver's"))
            elem.appendChild(build_tag_elem(doc, 'cuisine', 'burger'))
            elem.appendChild(build_tag_elem(doc, 'addr:full', culvers_data['addr:full']))

            new_node_id -= 1

    root.appendChild(elem)

with open('culvers_modified.osm', 'w') as f:
    f.write(doc.toprettyxml(indent='  '))
