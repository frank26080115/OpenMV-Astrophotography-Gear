import gc
import pyb, uos
import image, sensor
import array


EXPO_TOO_LOW      = -1
EXPO_JUST_RIGHT   = 0
EXPO_TOO_HIGH     = 1
EXPO_TOO_NOISY    = 2
EXPO_MOVEMENT     = 3
EXPO_TOO_BIG      = 4

def find_stars(img, hist = None, stats = None):
    gc.collect()

    # histogram and statistics might be computationally costly, use cached results if available
    if hist is None:
        hist = img.get_histogram()
    if stats is None:
        stats = hist.get_statistics()

    # check the quality
    if stats.mean() > 60:
        return [], EXPO_TOO_HIGH
    if stats.stdev() >= 7:
        return [], EXPO_TOO_NOISY
    if stats.max() < (64 * 3):
        return [], EXPO_TOO_LOW

    # this threshold was tested in a photo editor first
    thresh = stats.mean() * 3
    blobs = img.find_blobs([(thresh, 255)], merge = True)
    stars = []
    too_long = 0
    too_big  = 0
    for b in blobs:
        accept = True
        if b.roundness() < 0.2 and b.area() > (5 * 5):
            too_long += 1
            accept = False
        if b.area() > (25 * 25):
            too_big += 1
            accept = False
        if accept:
            stars.append(blob_to_star(b, img, thresh))
    if too_big > len(stars):
        return stars, EXPO_TOO_BIG
    if too_long > len(stars):
        return stars, EXPO_MOVEMENT
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
    cx = sumn / sumd
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
    cy = sumn / sumd
    cy += ystart
    # approximate radius (should be dividing by 4 but it doesn't really matter)
    r = (w + h) / 3.0
    return (cx, cy, r, brightness)

def demo_image(filepath, find_polaris = False):
    gc.collect()
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
