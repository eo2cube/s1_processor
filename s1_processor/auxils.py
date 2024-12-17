import os
import shutil
import geopandas as gpd
from shapely.geometry import Polygon
from zipfile import ZipFile
import re
import xml.etree.ElementTree as ET
import pandas as pd
from pyroSAR import identify_many
##function to clean up temporary elements


def remove(path):
    """param <path> could either be relative or absolute."""
    if os.path.isfile(path) or os.path.islink(path):
        os.remove(path)  # remove the file
    elif os.path.isdir(path):
        shutil.rmtree(path)  # remove dir and all contains


## group files in nested lists based on common parameter
def group_by_info(infiles, group=None):
    ##sort files by characteristic of S-1 data (e.g. orbit number, platform, ...)
    info = identify_many(infiles, sortkey=group)
    ##extract file paths of sorted files
    fps_lst = [fp.scene for fp in info]

    ##extract and identify unique keys
    groups = []
    for o in info:
        orb = eval("o." + group)
        groups.append(orb)

    query_group = groups.count(groups[0]) == len(groups)
    unique_groups = list(set(groups))

    out_files = []
    if query_group is True:
        out_files = infiles
    else:
        group_idx = []
        # index files of key
        for a in unique_groups:
            tmp_groups = []
            for idx, elem in enumerate(groups):
                if a == elem:
                    tmp_groups.append(idx)

            group_idx.append(tmp_groups)
        ###group by same keyword
        for i in range(0, len(group_idx)):
            fpsN = list(map(fps_lst.__getitem__, group_idx[i]))
            out_files.append(fpsN)

    return out_files


## get metadata from zip file for specific polarization and subswaths
def load_metadata(zip_path, subswath, polarization):
    # print(subswath)
    # print(polarization)
    archive = ZipFile(zip_path)
    archive_files = archive.namelist()
    # print(f'archive_files: {archive_files}')
    regex_filter = r"s1(?:a|b)-iw\d-slc-(?:vv|vh|hh|hv)-.*\.xml"
    metadata_file_list = []
    for item in archive_files:
        if "calibration" in item:
            continue
        match = re.search(regex_filter, item)
        if match:
            metadata_file_list.append(item)
    target_file = None
    # print(f'archive_files: {archive_files}')
    for item in metadata_file_list:
        if subswath.lower() in item and polarization.lower() in item:
            target_file = item
    return target_file
    # if subswath.lower() in item and polarization.lower() in item:
    #    target_file = item
    #    print(target_file)
    # if not target_file:
    # raise Exception(f'Found no matching XML file with target subswath "{subswath}" and target polarization "{target_polarization}". \
    #                Possible matches: {metadata_file_list}')
    # return archive.open(target_file)


## get total number of bursts and their coordinates from metadata
def parse_location_grid(metadata):
    tree = ET.parse(metadata)
    root = tree.getroot()
    lines = []
    coord_list = []
    for grid_list in root.iter("geolocationGrid"):
        for point in grid_list:
            for item in point:
                lat = item.find("latitude").text
                lon = item.find("longitude").text
                line = item.find("line").text
                lines.append(line)
                coord_list.append((float(lat), float(lon)))
    total_num_bursts = len(set(lines)) - 1

    return total_num_bursts, coord_list


## get subswath geometry from each burst
def parse_subswath_geometry(coord_list, total_num_bursts):
    def get_coords(index, coord_list):
        coord = coord_list[index]
        assert isinstance(coord[1], float)
        assert isinstance(coord[0], float)
        return coord[1], coord[0]

    bursts_dict = {}
    top_right_idx = 0
    top_left_idx = 20
    bottom_left_idx = 41
    bottom_right_idx = 21

    for burst_num in range(1, total_num_bursts + 1):
        burst_polygon = Polygon(
            [
                [
                    get_coords(top_right_idx, coord_list)[0],
                    get_coords(top_right_idx, coord_list)[1],
                ],  # Top right
                [
                    get_coords(top_left_idx, coord_list)[0],
                    get_coords(top_left_idx, coord_list)[1],
                ],  # Top left
                [
                    get_coords(bottom_left_idx, coord_list)[0],
                    get_coords(bottom_left_idx, coord_list)[1],
                ],  # Bottom left
                [
                    get_coords(bottom_right_idx, coord_list)[0],
                    get_coords(bottom_right_idx, coord_list)[1],
                ],  # Bottom right
            ]
        )

        top_right_idx += 21
        top_left_idx += 21
        bottom_left_idx += 21
        bottom_right_idx += 21

        bursts_dict[burst_num] = burst_polygon

    return bursts_dict


## get geometry of individual bursts
def get_burst_geometry(path, target_subswaths, polarization):
    df_all = gpd.GeoDataFrame(
        columns=["subswath", "burst", "geometry"], crs="EPSG:4326"
    )
    for subswath in target_subswaths:
        archive = ZipFile(path)
        fmeta = load_metadata(
            zip_path=path, subswath=subswath, polarization=polarization
        )
        meta = archive.open(fmeta)
        total_num_bursts, coord_list = parse_location_grid(meta)
        subswath_geom = parse_subswath_geometry(coord_list, total_num_bursts)
        df = gpd.GeoDataFrame(
            {
                "subswath": [subswath.upper()] * len(subswath_geom),
                "burst": [x for x in subswath_geom.keys()],
                "geometry": [x for x in subswath_geom.values()],
            },
            crs="EPSG:4326",
        )
        df_all = gpd.GeoDataFrame(pd.concat([df_all, df]), crs="EPSG:4326")
    return df_all
