import micropython
micropython.opt_level(2)

import pyb, uos
import image, sensor
import array
import gc
import blobstar
import exclogger

EXPO_TOO_LOW      = micropython.const(-1)
EXPO_JUST_RIGHT   = micropython.const(0)
EXPO_TOO_HIGH     = micropython.const(1)
EXPO_TOO_NOISY    = micropython.const(2)
EXPO_MOVEMENT     = micropython.const(3)
EXPO_TOO_BIG      = micropython.const(4)
EXPO_TOO_MANY     = micropython.const(5)
EXPO_MEMORY_ERR   = micropython.const(6)

def find_stars(img, hist = None, stats = None, thresh = 0, region = None, force_solve = False):

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
        region = (0, 0, img.width(), img.height())

    # custom firmware supports negative area for inverted area threshold
    max_star_width = int(35)
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
    too_long = 0
    too_big  = 0
    for b in blobs:
        accept = True
        #if b.roundness() < 0.2 and b.area() > (5 * 5):
        #    too_long += 1
        #    accept = False
        ## the reduced lightweight firmware cannot calculate roundness
        if b.area() > (25 * 25):
            too_big += 1
            accept = False
        if accept:
            stars.append(blob_to_star(b, img, thresh))
    if force_solve == False:
        if too_big > len(stars):
            return stars, EXPO_TOO_BIG
        if too_long > len(stars):
            return stars, EXPO_MOVEMENT
        if len(stars) > 125:
            # we have a database of around 20 stars
            # only 4 are needed for a solution
            # if you see 30, that's a really really good exposure but unlikely in all conditions
            # above 150 you are likely to run into memory limits if it increases
            # return this as a warning
            return stars, EXPO_TOO_MANY
    return stars, EXPO_JUST_RIGHT

def blob_to_star(b, img, thresh):
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
    # iterate the ROI
    while x < xlim:
        y = ystart
        ylim = y + h
        while y < ylim:
            p = img.get_pixel(x, y)
            if p > thresh: # is in blob ROI
                # sum the brightness
                xbucket[x - xstart] += p
                ybucket[y - ystart] += p
                brightness += p
                if p > maxbrite:
                    maxbrite = p
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
    return blobstar.BlobStar(cx, cy, r, brightness)

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
