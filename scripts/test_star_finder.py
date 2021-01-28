import micropython
import pyb
import math
import star_finder, astro_sensor, guidestar

cam = astro_sensor.AstroCam()
#cam = astro_sensor.AstroCam(simulate = "polaris.bmp")

print("cam init...", end="")
cam.init(gain_db = 32, shutter_us = 1500 * 1000)

while cam.check_init() == False:
    print(".", end="")
print(" done")

print("capturing...")
img = cam.snapshot()
print("done")
hist = img.get_histogram()
stats = hist.get_statistics()

stars, code = star_finder.find_stars(img, hist = hist, stats = stats, thresh = (16 * 3), guider = True)

print("stars: %u , mean: %u" % (len(stars), stats.mean()))

guidestar.process_list(stars, 100, [], 2)
sel_star = guidestar.select_first(stars)

bar_len = 10

for i in stars:
    r = i.r() * 2
    cx = i.cxf()
    cy = i.cyf()
    cx_i = int(round(cx))
    cy_i = int(round(cy))
    cx_floor = int(math.floor(cx))
    cy_floor = int(math.floor(cy))
    cx_ceil  = int( math.ceil(cx))
    cy_ceil  = int( math.ceil(cy))
    shade_left   = (cx_ceil - cx) * 255
    shade_right  = 255 - shade_left
    shade_top    = (cy_ceil - cy) * 255
    shade_bottom = 255 - shade_top
    shade_left   = int(round(shade_left))
    shade_right  = int(round(shade_right))
    shade_top    = int(round(shade_top))
    shade_bottom = int(round(shade_bottom))
    if cx_floor == cx_ceil:
        shade_left   = 255
        shade_right  = 255
    if cy_floor == cy_ceil:
        shade_top    = 255
        shade_bottom = 255
    img.draw_line(cx_i - r - bar_len, cy_floor, cx_i - r, cy_floor, shade_top)
    img.draw_line(cx_i + r + bar_len, cy_floor, cx_i + r, cy_floor, shade_top)
    img.draw_line(cx_i - r - bar_len, cy_ceil , cx_i - r, cy_ceil , shade_bottom)
    img.draw_line(cx_i + r + bar_len, cy_ceil , cx_i + r, cy_ceil , shade_bottom)
    img.draw_line(cx_floor, cy_i - r - bar_len, cx_floor, cy_i - r, shade_left)
    img.draw_line(cx_floor, cy_i + r + bar_len, cx_floor, cy_i + r, shade_left)
    img.draw_line(cx_ceil , cy_i - r - bar_len, cx_ceil , cy_i - r, shade_right)
    img.draw_line(cx_ceil , cy_i + r + bar_len, cx_ceil , cy_i + r, shade_right)
    text_x = 0
    text_y = 0
    #profile = i.star_profile()
    #if len(profile) > 5:
    #    profile = profile[0:5]
    #profile_text = ""
    #for j in profile:
    #    profile_text += "%u," % j
    text = "%u" % (i.star_rating())
    if cx_i >= img.width() // 2:
        text_x = cx_i - r - bar_len - (len(text) * 9) - 1
    else:
        text_x = cx_i + r + bar_len + 1
    if cy_i < img.height() // 2:
        text_y = cy_i + r + 2
    else:
        text_y = cy_i - r
    img.draw_string(text_x, text_y, text, 255)

img.draw_ellipse(int(round(sel_star.cxf())), int(round(sel_star.cyf())), int(round(sel_star.r() + 5)), int(round(sel_star.r() + 5)), 0, 255)

fname = "test.jpg"
print("saving: " + fname)
img.save(fname, quality = 100)
