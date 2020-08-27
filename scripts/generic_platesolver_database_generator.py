#!/usr/bin/env python

import sys
import numpy as np
from PIL import Image, ImageDraw

SENSOR_WIDTH  = 2592
SENSOR_HEIGHT = 1944
SENSOR_DIAGONAL = np.sqrt((SENSOR_WIDTH ** 2) + (SENSOR_HEIGHT ** 2))
PIXELS_PER_DEGREE = 875.677409 / 2.9063 # calculated using "OV Cep"

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
        self.ra_float  = self.ra_hour  + (self.ra_min  / 60.0) + (self.ra_sec  / (60.0 * 60.0))
        self.dec_float = self.dec_deg + (self.dec_min / 60.0) + (self.dec_sec / (60.0 * 60.0))
        return self.ra_float, self.dec_float

    def get_aep_coord_xy(self):
        # azimuthal equidistant projection absolute cartesian coordinates
        ra, dec = self.get_celestial_coord_float()
        rho = (90 - dec) * PIXELS_PER_DEGREE
        phi = np.radians(360.0 * ra / 24.0)
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
        dist = np.sqrt((dx ** 2) + (dy ** 2))
        ang  = np.degrees(np.arctan2(dy, dx))
        return dist, ang

    def calc_arc_vector(self, star):
        # https://en.wikipedia.org/wiki/Great-circle_distance
        # https://www.gyes.eu/calculator/calculator_page1.htm
        ra1, dec1 = self.get_celestial_coord_float()
        ra2, dec2 = star.get_celestial_coord_float()
        ra1 = ra1 * 360.0 / 24.0
        ra2 = ra2 * 360.0 / 24.0
        ra1 = np.radians(ra1)
        ra2 = np.radians(ra2)
        dec1 = np.radians(dec1)
        dec2 = np.radians(dec2)
        cosa = (np.sin(dec1) * np.sin(dec2)) + (np.cos(dec1) * np.cos(dec2) * np.cos(ra1 - ra2))
        if cosa > 1.0 or cosa < -1.0:
            return 0, 0
        arcdist = np.arccos(cosa)

        # https://en.wikipedia.org/wiki/Solution_of_triangles
        # point C is the NCP, point A is the current reference star, point B is the input star
        # all units are radians right now
        arc_a = (np.pi / 2.0) - dec2
        arc_b = (np.pi / 2.0) - dec1
        arc_c = arcdist
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

        return np.degrees(arcdist), np.degrees(alpha)

    def calc_visual_vector(self, star):
        ra, dec = self.get_celestial_coord_float()
        dist1, ang1 = self.calc_aep_vector(star)
        dist2, ang2 = self.calc_arc_vector(star)
        if dist2 == 0: # calc_arc_vector encountered invalid data
            return 0, 0

        # only use dist2, as it is an arc distance, it is accurate no matter what projection we use
        dist = dist2 * PIXELS_PER_DEGREE

        # the azimuthal equidistant projection still works great near the pole, do not re-calculate for stars here
        if dec >= SENSOR_DIAGONAL / PIXELS_PER_DEGREE:
            return dist, ang1

        # RA still in hours, convert to degrees
        ra = ra * 360.0 / 24.0
        ra2, dec2 = star.get_celestial_coord_float()
        ra2 = ra2 * 360.0 / 24.0
        delta_ra = angle_norm(ra - ra2) # east is positive, just like X is positive
        # SOHCAHTOA, cos(theta) = A/H, where A is delta_ra converted to pixels, and H is dist
        theta = np.arccos(delta_ra * pix_per_ra(dec2) / dist)
        # theta is positive if target star has lower dec than reference star
        if dec2 > dec:
            theta *= -1.0

        return dist, np.degrees(theta)

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
    return im, draw

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

    print("drawing stars")
    im, draw = draw_stars(stars)
    im.save("stars_aep.png")
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
            if j.rel_dist > 0 and j.rel_dist < maxdist and j.bmag <= 7:
                bucket.append(j)
        if len(bucket) < 4: # need a minimum number of matches
            continue
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