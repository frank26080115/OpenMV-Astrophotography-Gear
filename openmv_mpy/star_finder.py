import micropython
micropython.opt_level(2)

import pyb, uos
import image, sensor
import array
import math
import gc
import blobstar
import guidestar
import comutils
import exclogger

EXPO_NO_IMG       = micropython.const(-2)
EXPO_TOO_LOW      = micropython.const(-1)
EXPO_JUST_RIGHT   = micropython.const(0)
EXPO_TOO_HIGH     = micropython.const(1)
EXPO_TOO_NOISY    = micropython.const(2)
EXPO_MOVEMENT     = micropython.const(3)
EXPO_TOO_BIG      = micropython.const(4)
EXPO_TOO_MANY     = micropython.const(5)
EXPO_MEMORY_ERR   = micropython.const(6)
EXPO_CAMERA_ERR   = micropython.const(7)
EXPO_NOT_READY    = micropython.const(8)

def find_stars(img, hist = None, stats = None, thresh = 0, max_dia = 100, region = None, force_solve = False, guider = False):

    # histogram and statistics might be computationally costly, use cached results if available
    if hist is None:
        hist = img.get_histogram()
    if stats is None:
        stats = hist.get_statistics()

    if force_solve == False:
        # force_solve is to test performance
        # check the quality
        # this prevents the later steps from running out of memory due to false blobs
        if stats.mean() >= 20:
            return [], EXPO_TOO_HIGH
        if stats.stdev() >= 7:
            return [], EXPO_TOO_NOISY
        #if stats.max() < (64 * 3):
        #    return [], EXPO_TOO_LOW
        if stats.mean() >= thresh * 0.75 and thresh != 0:
            return [], EXPO_TOO_MANY

    # this threshold was tested in a photo editor first
    thresh_a = stats.mean() * 3
    if thresh < thresh_a:
        thresh = thresh_a

    if region is None:
        region = (0, 0, img.width() - 150, img.height())

    # custom firmware supports negative area for inverted area threshold
    max_star_width = int(round(max_dia))
    area = int(max_star_width * max_star_width)
    maxpix = int(round(((float(max_star_width) / 2.0) ** 2) * 3.14159))

    gc.collect()
    try:
        blobs = img.find_blobs([(thresh, 255)], merge = False, x_stride = 2, y_stride = 2, roi = region, area_threshold = -area, pixel_threshold = -maxpix, width_threshold = -max_star_width, height_threshold = -max_star_width, guidestarmode = guider)
    except MemoryError as exc:
        print("MEMORY ERROR from find_blobs")
        exclogger.log_exception(exc, to_file = False)
        #micropython.mem_info(True)
        return [], EXPO_MEMORY_ERR
    if guider: # use new faster technique for autoguider
        try:
            guidestars = guidestar.blobs2guidestars(blobs)
            return guidestars, EXPO_JUST_RIGHT
        except MemoryError as exc:
            print("MEMORY ERROR from blobs2guidestars")
            exclogger.log_exception(exc, to_file = False)
            #micropython.mem_info(True)
            return [], EXPO_MEMORY_ERR

    # use old technique for polarscope
    blobs_cnt = len(blobs)
    stars = []
    while blobs_cnt > 0:
        try:
            stars = [None] * blobs_cnt
            break
        except MemoryError:
            blobs_cnt - 10
            print("memerr allocating new list")
    #too_long = 0
    #too_big  = 0
    try:
        i = 0
        for b in blobs:
            r = (b.w() + b.h()) / 3
            bb = blobstar.BlobStar(b.cxf(), b.cyf(), r, b.brightness_sum())
            if i < blobs_cnt:
                stars[i] = bb
            i += 1
    except MemoryError as exc:
        print("MEMORY ERROR adding blob star to list")
        exclogger.log_exception(exc, to_file = False)
        return [], EXPO_MEMORY_ERR
    if force_solve == False:
        #if too_big > len(stars):
        #    return stars, EXPO_TOO_BIG
        #if too_long > len(stars):
        #    return stars, EXPO_MOVEMENT
        if len(stars) > 125:
            # we have a database of around 20 stars
            # only 4 are needed for a solution
            # if you see 30, that's a really really good exposure but unlikely in all conditions
            # above 150 you are likely to run into memory limits if it increases
            # return this as a warning
            return stars, EXPO_TOO_MANY
    return stars, EXPO_JUST_RIGHT

def simple_list(list):
    cnt = len(list)
    res = [[1.5, 1.5]] * cnt
    i = 0
    while i < cnt:
        res[i][0] = list[i].cx
        res[i][1] = list[i].cy
        i += 1
    return res

def decode_hotpixels(str):
    res = []
    split = str.split(";")
    for i in split:
        try:
            istr = i.lstrip().rstrip()
            isplit = i.split(",")
            if len(isplit) != 2:
                continue
            # isnumeric doesn't exist so no checks available
            # if it can't be parsed, it will throw an exception
            x = int(round(float(isplit[0])))
            y = int(round(float(isplit[1])))
            # note: custom firmware expects integers, cannot handle floats
            # note: custom firmware expects a tuple, not a list, use tuple notation
            res.append((x, y))
        except Exception as exc:
            exclogger.log_exception(exc, to_file = False)
    return res

def encode_hotpixels(star_list, r = 8):
    str = ""
    for i in star_list:
        if i.r() <= r:
            str += "%u,%u;" % (int(round(i.cxf())), int(round(i.cyf())))
    return str
