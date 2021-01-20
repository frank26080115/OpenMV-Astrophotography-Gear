import micropython
micropython.opt_level(2)

import pyb, uos
import image, sensor
import array
import math
import gc
import blobstar
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

def find_stars(img, hist = None, stats = None, thresh = 0, max_dia = 100, region = None, force_solve = False, exponent = 1, advanced = 0):

    # histogram and statistics might be computationally costly, use cached results if available
    if hist is None:
        hist = img.get_histogram()
    if stats is None:
        stats = hist.get_statistics()

    if force_solve == False:
        # force_solve is to test performance
        # check the quality
        # this prevents the later steps from running out of memory due to false blobs
        if stats.mean() > 60:
            return [], EXPO_TOO_HIGH
        if stats.stdev() >= 7:
            return [], EXPO_TOO_NOISY
        if stats.max() < (64 * 3):
            return [], EXPO_TOO_LOW

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
        blobs = img.find_blobs([(thresh, 255)], merge = False, x_stride = 2, y_stride = 2, roi = region, area_threshold = -area, pixel_threshold = -maxpix, width_threshold = -max_star_width, height_threshold = -max_star_width)
    except MemoryError as exc:
        print("MEMORY ERROR from find_blobs")
        exclogger.log_exception(exc, to_file = False)
        #micropython.mem_info(True)
        return [], EXPO_MEMORY_ERR
    stars = []
    #too_long = 0
    #too_big  = 0
    for b in blobs:
        bb = blob_to_star(b, img, thresh, expo = exponent, adv = advanced)
        if bb is not None:
            stars.append(bb)
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

def blob_to_star(b, img, thresh, expo = 1, adv = 0):
    # this function iterates over the blob's region of interest
    # performs summations and calculates a weighted centoid
    # and gathers brightness data
    w = b.w()
    h = b.h()
    # weight center using histogram
    xbucket = array.array('I',(0 for i in range(0, w)))
    ybucket = array.array('I',(0 for i in range(0, h)))
    xstart = b.x()
    ystart = b.y()
    x = xstart
    xlim = x + w
    brightness = 0
    maxbrite = 0
    areacnt = 0
    satcnt = 0
    # iterate the ROI
    while x < xlim:
        y = ystart
        ylim = y + h
        while y < ylim:
            br = img.get_pixel(x, y)
            p = br
            if expo > 1.0:
                p = int(math.round(math.pow(br, expo)))
            if p > thresh: # is in blob ROI
                areacnt += 1
                # sum the brightness
                xbucket[x - xstart] += p
                ybucket[y - ystart] += p
                brightness += br
                if br > maxbrite:
                    maxbrite = br
                if br >= 254:
                    satcnt += 1
            y += 1
        x += 1
    # calculate weighted center for each axis
    x = 0
    sumn = 0
    sumd = 0
    while x < w:
        buc = xbucket[x]
        sumn += x * buc
        sumd += buc
        x += 1
    if sumd > 0:
        cx = sumn / sumd
    else:
        cx = 0
    cx += xstart
    # calculate weighted center for each axis
    y = 0
    sumn = 0
    sumd = 0
    while y < h:
        buc = ybucket[y]
        sumn += y * buc
        sumd += buc
        y += 1
    if sumd > 0:
        cy = sumn / sumd
    else:
        cy = 0
    cy += ystart
    # approximate radius (should be dividing by 4 but it doesn't really matter)
    r = (w + h) / 3.0
    # if the star has a saturated pixel, it could be a hot-pixel
    # make the brightness even or odd to signal as such
    if maxbrite >= 254:
        if (brightness % 2) == 0:
            brightness += 1
    else:
        if (brightness % 2) != 0:
            brightness += 1
    if adv == 0:
        return blobstar.BlobStar(cx, cy, r, brightness)
    else:
        sums, pointiness = guide_star_analyze(img, cx, cy, r, mode = 2 if adv == 1 else 0)
        guidestar = blobstar.GuideStar(cx, cy, r, brightness, maxbrite, satcnt, areacnt, pointiness)
        guidestar.profile = sums
        return guidestar

def guide_star_analyze(img, cx, cy, r, mode = 0):
    cx = int(round(cx))
    cy = int(round(cy))
    r  = int(round(r))
    sums = [0 for i in range(r)]
    cnts = [0 for i in range(r)]
    if mode == 2:
        left   = cx - r
        right  = cx + r
        top    = cy - r
        bottom = cy + r
        x = left
        while x <= right:
            y = top
            while y <= bottom:
                dx = x - cx
                dy = y - cy
                mag = round(math.sqrt((dx * dx) + (dy * dy)))
                if (dx != 0 or dy != 0) and mag == 0:
                    mag = 1
                if mag > r:
                    y += 1
                    continue
                if mag < r:
                    sums[mag] += img.get_pixel(x, y)
                    cnts[mag] += 1
                y += 1
            x += 1
    elif mode == 1:
        i = 1
        sums[0] = img.get_pixel(cx, cy)
        cnts[0] = 1
        while i < r:
            sums[i] += img.get_pixel(cx + i, cy)
            sums[i] += img.get_pixel(cx - i, cy)
            sums[i] += img.get_pixel(cx + i, cy + i)
            sums[i] += img.get_pixel(cx - i, cy + i)
            sums[i] += img.get_pixel(cx + i, cy - i)
            sums[i] += img.get_pixel(cx - i, cy - i)
            sums[i] += img.get_pixel(cx, cy + i)
            sums[i] += img.get_pixel(cx, cy - i)
            cnts[i] += 8
            i += 1
    else:
        i = 1
        sums[0] = img.get_pixel(cx, cy)
        cnts[0] = 1
        while i < r:
            sums[i] += img.get_pixel(cx + i, cy)
            sums[i] += img.get_pixel(cx - i, cy)
            sums[i] += img.get_pixel(cx, cy + i)
            sums[i] += img.get_pixel(cx, cy - i)
            cnts[i] += 4
            i += 1
    i = 0
    j = r
    pointiness = 0
    px = -1
    while i < len(sums):
        x = sums[i] / cnts[i]
        sums[i] = x
        if i != 0 and j > 0:
            dx = px - x
            dx *= j
            dx /= px
            if dx < 0:
                dx *= 2
            pointiness += dx
            j -= 1
        px = x
        i += 1
    pointiness = comutils.map_val(pointiness, 0, r, 0, 100)
    return sums, pointiness

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
            x = float(isplit[0])
            y = float(isplit[1])
            res.append([x, y])
        except Exception as exc:
            exclogger.log_exception(exc, to_file = False)
    return res

def encode_hotpixels(star_list, r = 5):
    str = ""
    for i in star_list:
        if i.r <= r:
            str += "%u,%u;" % (int(round(i.cx)), int(round(i.cy)))
    return str

def filter_hotpixels(star_list, hotpixels, lim = 3):
    res = []
    for i in star_list:
        nearest = 9999
        for p in hotpixels:
            mag = comutils.vector_between([i.cx, i.cy], p, mag_only=True)
            if mag < nearest:
                nearest = mag
                if nearest <= lim:
                    break
        if nearest > lim:
            res.append(i)
    return res

"""
def demo_image(filepath, find_polaris = False):
    print("opening %s" % filepath, end = "")
    img = image.Image(filepath, copy_to_fb = True)
    print(" done")
    print("copying to grayscale ...", end = "")
    img = sensor.alloc_extra_fb(img.width(), img.height(), sensor.RGB565).replace(img).to_grayscale()
    print(" done")
    stars, retcode = find_stars(img)
    if retcode == EXPO_JUST_RIGHT:
        print("found %u stars" % len(stars))
        for i in stars:
            cx = i[0]
            cy = i[1]
            r = i[2]
            b = i[3]
            img.draw_circle(int(round(cx)), int(round(cy)), int(round(r)), 255, 1, False)
            print("[%0.8f, %0.8f, %0.8f, %0.8f, ]," % (cx, cy, r, b))
    else:
        print("not a good image, %d" % retcode)
        return
    new_file = filepath + ".out.jpg"
    print("saving %s" % new_file)
    img.save(new_file)

def demo_dir(dirpath = uos.getcwd(), find_polaris = False):
    list = uos.listdir(dirpath)
    for f in list:
        if f.lower().endswith(".bmp"):
            fn = dirpath + "/" + f
            demo_image(f, find_polaris)

if __name__ == "__main__":
    demo_dir()
"""
