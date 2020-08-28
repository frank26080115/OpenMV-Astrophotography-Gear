#!/usr/bin/env python

import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SENSOR_WIDTH  = 2592
SENSOR_HEIGHT = 1944
SENSOR_DIAGONAL = np.sqrt((SENSOR_WIDTH ** 2) + (SENSOR_HEIGHT ** 2))
PIXELS_PER_DEGREE = 875.677409 / 2.9063 # calculated using "OV Cep"
LIMIT_DEC = 90 - (SENSOR_DIAGONAL / PIXELS_PER_DEGREE)
font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 80)

DRAW_AEP_IMAGE = True
DRAW_STAR_CENTERED_IMAGE = True

DRAW_ME = ["* tet Dra", "* eta Dra", "* iot Dra", "* eps UMa", "* alf UMa"]

class Star(object):
    def __init__(self, name, coord_str, bmag):
        # coord_str is formatted by SIMBAD
        self.name = name.strip()
        self.coord_str = coord_str.strip()
        self.bmag = bmag

        coordsplit = self.coord_str.split(' ')
        self.ra_hour = np.float64(int(coordsplit[0]))
        self.ra_min = np.float64(int(coordsplit[1]))
        self.ra_sec = np.float64(float(coordsplit[2]))
        self.dec_deg = np.float64(int(coordsplit[3]))
        self.dec_min = np.float64(int(coordsplit[4]))
        self.dec_sec = np.float64(float(coordsplit[5]))
        self.get_celestial_coord_float()
        self.get_aep_coord_xy()

    def get_celestial_coord_float(self):
        # converts the input DDMMSS into floats
        # warning: RA is still in 24H units, not degrees
        self.ra_float  = self.ra_hour + (self.ra_min  / 60.0) + (self.ra_sec  / (60.0 * 60.0))
        self.dec_float = self.dec_deg + (self.dec_min / 60.0) + (self.dec_sec / (60.0 * 60.0))
        return self.ra_float, self.dec_float

    def get_aep_coord_xy(self):
        # azimuthal equidistant projection absolute cartesian coordinates
        ra, dec = self.get_celestial_coord_float()
        rho = (90 - dec) * PIXELS_PER_DEGREE
        phi = np.radians(hours_to_degrees(ra))
        x = rho * np.cos(phi)
        y = rho * np.sin(phi)
        self.x = x
        self.y = y
        return x, y

    def calc_aep_dxdy(self, star):
        # azimuthal equidistant projection relative cartesian coordinates
        self.get_aep_coord_xy()
        x, y = star.get_aep_coord_xy()
        return (x - self.x), (y - self.y)

    def calc_aep_vector(self, star):
        # azimuthal equidistant projection vector
        dx, dy = self.calc_aep_dxdy(star)
        #dist = np.sqrt((dx ** 2) + (dy ** 2))
        dist = self.calc_arc_dist(star)
        ang  = np.degrees(np.arctan2(dy, dx))
        return dist, ang

    def calc_gnomonic_dxdy(self, star):
        delta_ra = np.radians(hours_to_degrees(self.ra_float) - hours_to_degrees(star.ra_float))
        dec_0 = np.radians(star.dec_float)
        dec   = np.radians(self.dec_float)
        x_numerator   = np.cos(dec) * np.sin(delta_ra)
        x_denominator = (np.cos(dec_0) * np.cos(dec) * np.cos(delta_ra)) + (np.sin(dec_0) * np.sin(dec))
        y_numerator = (np.sin(star.dec_float) * np.cos(dec) * np.cos(delta_ra)) - (np.cos(dec_0) * np.sin(dec))
        y_denominator = (np.cos(dec_0) * np.cos(dec) * np.cos(delta_ra)) - (np.sin(dec) * np.sin(dec_0))
        x = x_numerator / x_denominator
        y = y_numerator / y_denominator
        mag = np.sqrt((x ** 2) + (y ** 2))
        arcdist = self.calc_arc_dist(star)
        mult = arcdist / mag
        x *= mult
        y *= mult
        return x, y

    def calc_gnomonic_vector(self, star):
        dx, dy = self.calc_gnomonic_dxdy(star)
        dist = self.calc_arc_dist(star)
        ang  = np.degrees(np.arctan2(dy, dx))
        return dist, ang

    def calc_arc_dist(self, star):
        # https://en.wikipedia.org/wiki/Great-circle_distance
        # https://www.gyes.eu/calculator/calculator_page1.htm
        ra1, dec1 = self.get_celestial_coord_float()
        ra2, dec2 = star.get_celestial_coord_float()
        ra1 = hours_to_degrees(ra1)
        ra2 = hours_to_degrees(ra2)
        ra1 = np.radians(ra1)
        ra2 = np.radians(ra2)
        dec1 = np.radians(dec1)
        dec2 = np.radians(dec2)
        cosa = (np.sin(dec1) * np.sin(dec2)) + (np.cos(dec1) * np.cos(dec2) * np.cos(ra1 - ra2))
        if cosa > 1.0 or cosa < -1.0:
            return 0
        arcdist = np.arccos(cosa)
        return np.degrees(arcdist)

    def calc_arc_vector(self, star):
        arcdist = self.calc_arc_dist(star)

        # https://en.wikipedia.org/wiki/Solution_of_triangles
        # point C is the NCP, point A is the current reference star, point B is the input star
        # all units are radians right now
        arc_a = (np.pi / 2.0) - dec2
        arc_b = (np.pi / 2.0) - dec1
        arc_c = np.radians(arcdist)
        numerator = np.cos(arc_a) - (np.cos(arc_b) * np.cos(arc_c))
        denominator = np.sin(arc_b) * np.sin(arc_c)
        if denominator == 0.0:
            return 0, 0
        x = numerator / denominator
        if x > 1.0 or x < -1.0:
            return 0, 0
        alpha = np.arccos(x)

        # if the star is more east, then we want alpha to be positive
        # otherwise, alpha should be negative
        # lower RA is more East, so if ra1 - ra2 is greater than zero, ra2 is more east
        delta_ra = angle_norm(np.degrees(ra1 - ra2))
        if delta_ra < 0:
            alpha *= -1.0

        return arcdist, np.degrees(alpha)

    def calc_visual_vector(self, star):
        # the azimuthal equidistant projection still works great near the pole, do not re-calculate for stars here
        if star.dec_float >= LIMIT_DEC:
            dist, ang = self.calc_aep_vector(star)
            return dist * PIXELS_PER_DEGREE, ang

        dist, ang = self.calc_gnomonic_vector(star)
        return dist * PIXELS_PER_DEGREE, ang

    def printme(self):
        ra, dec = self.get_celestial_coord_float()
        print("[%s]: %f  |  %f    |    %f" % (self.name, ra, dec, self.bmag))

# this calculates what each degree in RA is in terms of pixels
# since this value changes according to declination
# at zero declination, the equator, cos() = 1
def pix_per_ra(dec):
    return PIXELS_PER_DEGREE * np.cos(np.degrees(dec))

def angle_norm(x):
    while x > 180.0:
        x -= 360.0
    while x < -180.0:
        x += 360.0
    return x

def hours_to_degrees(x):
    return x * 360.0 / 24.0

def draw_stars(stars):
    # this function draws all the stars onto an azimuthal equidistant projection
    # first, figure out how big the image needs to be
    minx = 0
    maxx = 0
    miny = 0
    maxy = 0
    for i in stars:
        x = i.x
        y = i.y
        if x > maxx:
            maxx = x
        if x < minx:
            minx = x
        if y > maxy:
            maxy = y
        if y < miny:
            miny = y
    width = maxx - minx + 100
    height = maxx - minx + 100
    im = Image.new("RGB", (int(round(width)), int(round(height))), (0, 0, 0))
    draw = ImageDraw.Draw(im)

    # draw NCP crosshair
    draw.line([(0, height / 2), (width, height / 2)], fill=(128, 128, 0))
    draw.line([(width / 2, 0), (width / 2, height)], fill=(128, 128, 0))
    # draw each star with azimuthal equidistant projection
    for star in stars:
        radius = 40.0 / star.bmag
        x, y = star.get_aep_coord_xy()
        x += (width / 2)
        y += (height / 2)
        draw.ellipse([(x - radius, y - radius), (x + radius, y + radius)], fill=(255, 255, 255))

    im.save("stars_aep_full.png")
    im1 = im.crop(((width / 2) - (SENSOR_WIDTH / 2), (height / 2) - (SENSOR_HEIGHT / 2), (width / 2) + (SENSOR_WIDTH / 2), (height / 2) + (SENSOR_HEIGHT / 2)))
    draw = ImageDraw.Draw(im1)
    i = 1
    while i < 90:
        radius = i * PIXELS_PER_DEGREE
        draw.ellipse([((SENSOR_WIDTH / 2) - radius, (SENSOR_HEIGHT / 2) - radius), ((SENSOR_WIDTH / 2) + radius, (SENSOR_HEIGHT / 2) + radius)], fill=None, outline=(255, 255, 0))
        i += 1
    im1.save("stars_aep_cropped.png")

def draw_single_star(star, bucket):
    fname = star.name.replace("*", "star").replace(" ", "_") + ".png"
    print("drawing for " + fname)

    im = Image.new("RGB", (int(round(SENSOR_DIAGONAL * 2)), int(round(SENSOR_DIAGONAL * 2))), (0, 0, 0))
    draw = ImageDraw.Draw(im)
    radius = 80.0 / star.bmag
    draw.ellipse([(SENSOR_DIAGONAL - radius, SENSOR_DIAGONAL - radius), (SENSOR_DIAGONAL + radius, SENSOR_DIAGONAL + radius)], fill=(255, 255, 255))
    draw.text((SENSOR_DIAGONAL + radius + 2, SENSOR_DIAGONAL), star.name, font = font, align = "left")
    for s in bucket:
        radius = 80.0 / s.bmag
        dx = s.rel_dist * np.cos(np.radians(s.rel_ang))
        dy = s.rel_dist * np.sin(np.radians(s.rel_ang))
        dx += SENSOR_DIAGONAL
        dy += SENSOR_DIAGONAL
        draw.ellipse([(dx - radius, dy - radius), (dx + radius, dy + radius)], fill=(255, 255, 255))
        draw.text((dx + radius + 2, dy), s.name, font = font, align = "left")

    ra10 = np.round(star.ra_float)
    dec10 = np.round(star.dec_float)
    ra_list = []
    dec_list = []
    i = -300
    while i <= 300:
        ra_list.append(ra10 + i)
        dec_list.append(dec10 + i)
        i += 0.1

    for ri in ra_list:
        if ri < 0 or ri > 24:
            continue
        line_list = []
        for di in dec_list:
            if di > 90 or di < 0:
                continue
            ns = Star("", "%u 0 0 %u 0 0" % (ri, di), 0)
            dist, ang = ns.calc_visual_vector(star)
            ns.rel_dist = dist
            ns.rel_ang = ang
            line_list.append(ns)
        i = 0
        while i < len(line_list) - 1:
            ns1 = line_list[i]
            ns2 = line_list[i + 1]
            x1 = ns1.rel_dist * np.cos(np.radians(ns1.rel_ang))
            y1 = ns1.rel_dist * np.sin(np.radians(ns1.rel_ang))
            x2 = ns2.rel_dist * np.cos(np.radians(ns2.rel_ang))
            y2 = ns2.rel_dist * np.sin(np.radians(ns2.rel_ang))
            x1 += SENSOR_DIAGONAL
            y1 += SENSOR_DIAGONAL
            x2 += SENSOR_DIAGONAL
            y2 += SENSOR_DIAGONAL
            draw.line((x1, y1, x2, y2), fill=(255, 255, 0), width = 2)
            i += 1
    for di in dec_list:
        if di > 90 or di < 0:
            continue
        line_list = []
        for ri in ra_list:
            if ri < 0 or ri > 24:
                continue
            ns = Star("", "%u 0 0 %u 0 0" % (ri, di), 0)
            dist, ang = ns.calc_visual_vector(star)
            ns.rel_dist = dist
            ns.rel_ang = ang
            line_list.append(ns)
        i = 0
        while i < len(line_list) - 1:
            ns1 = line_list[i]
            ns2 = line_list[i + 1]
            x1 = ns1.rel_dist * np.cos(np.radians(ns1.rel_ang))
            y1 = ns1.rel_dist * np.sin(np.radians(ns1.rel_ang))
            x2 = ns2.rel_dist * np.cos(np.radians(ns2.rel_ang))
            y2 = ns2.rel_dist * np.sin(np.radians(ns2.rel_ang))
            x1 += SENSOR_DIAGONAL
            y1 += SENSOR_DIAGONAL
            x2 += SENSOR_DIAGONAL
            y2 += SENSOR_DIAGONAL
            draw.line((x1, y1, x2, y2), fill=(255, 255, 0), width = 2)
            i += 1

    im.save(fname)

def sort_rel_dist(x):
    return x.rel_dist

def sort_declination(x):
    return x.dec_float

def main():
    stars = []
    print("parsing SIMBAD file")
    f = open("extrastars_around_polaris.txt", "r")
    lines = f.readlines()
    started = False
    for line in lines:
        split = line.split('|')
        split0 = split[0].rstrip().lstrip()
        if len(split) == 12:
            if split0.isnumeric():
                started = True
        elif started:
            started = False
            break
        if started and split0.isnumeric():
            star = Star(split[1], split[3], float(split[5]))
            stars.append(star)

    print("finished parsing file")

    if DRAW_AEP_IMAGE:
        print("drawing stars")
        draw_stars(stars)
        print("finished drawing stars")

    dec_sorted = sorted(stars, key = sort_declination, reverse = True) # database must be in order of distance from NCP

    maxdist = SENSOR_DIAGONAL * 0.7 # only include stars within this distance

    longmode = 0 # set to zero for minimal file size output
    # use 1 for minimal JSON object
    # use 2 for maximum JSON object

    print("writing to file")
    fsz = 0
    file = open("generic_platesolver_database.txt", "w") 
    for i in dec_sorted:
        if i.bmag > 6:
            continue
        for j in dec_sorted:
            dist, ang = j.calc_visual_vector(i)
            j.rel_dist = dist
            j.rel_ang = ang
        dist_sorted = sorted(stars, key = sort_rel_dist, reverse = False)
        bucket = []
        for j in dist_sorted:
            if j.rel_dist > 0 and j.rel_dist < maxdist: # and j.bmag <= 7:
                bucket.append(j)
        if len(bucket) < 4: # need a minimum number of matches
            continue
        if i.name in DRAW_ME and DRAW_STAR_CENTERED_IMAGE:
            draw_single_star(i, bucket)
        bucket_str = ""
        pre_val = ""
        for j in bucket:
            if len(bucket_str) > 0 and bucket_str.endswith(",") == False:
                bucket_str += ","
            if longmode >= 1:
                bucket_str += "{"
                if longmode >= 2:
                    bucket_str += "\"name\":\"%s\"," % j.name
                bucket_str += "\"d\":%0.1f,\"a\":%0.1f}" % (j.rel_dist, j.rel_ang)
            else:
                val_str = "%u,%d" % (int(round(j.rel_dist)), int(round(j.rel_ang)))
                if val_str != pre_val:
                    bucket_str += val_str
                    pre_val = val_str
        if longmode >= 1:
            str = "\"%s\":{" % i.name
        else:
            str = "%s:%s" % (i.name, bucket_str)
        if longmode >= 2:
            str += "\"ra\": %0.8f, \"dec\": %0.8f, " % (i.ra_float, i.dec_float)
        if longmode >= 1:
            str += "\"near\":[%s]" % bucket_str
        if longmode >= 2:
            str += ", \"ncnt\": %u" % len(bucket)
        if longmode >= 1:
            str += "}"
        if i.name != dec_sorted[-1].name:
            if longmode >= 1:
                str += ","
            else:
                str += ";"
        file.write(str)
        fsz += len(str)
        if longmode >= 2:
            file.write("\n")
            fsz += 2
        file.flush()
    file.close()
    print("finished writing %u bytes to file" % fsz)

    return 0

if __name__ == "__main__":
    main()