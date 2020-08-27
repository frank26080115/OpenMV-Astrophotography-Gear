#!/usr/bin/env python

import sys
import numpy as np
from PIL import Image, ImageDraw

SENSOR_WIDTH  = 2592
SENSOR_HEIGHT = 1944
LENS_V_FOV    = 6.8
SCALE_TABLE   = [(454.393361, 476.91), (830.678717, 874.01), (620.699249, 653.95), (839.364112, 883.53), (93.786663, 99.7)] # pairs of data, predicted pixel distances vs measured pixel distances, later averaged for calibrating true pixel distances

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

    def get_coord_float(self):
        # converts the input DDMMSS into floats
        # warning: RA is still in 24H units, not degrees
        self.ra_float  = self.ra_hour  + (self.ra_min  / 60.0) + (self.ra_sec  / (60.0 * 60.0))
        self.dec_float = self.dec_deg + (self.dec_min / 60.0) + (self.dec_sec / (60.0 * 60.0))
        return self.ra_float, self.dec_float

    def get_coord_xy(self, flip_y = False, cx = (SENSOR_WIDTH / 2), cy = (SENSOR_HEIGHT / 2)):
        # azimuthal equidistant projection absolute cartesian coordinates
        ra, dec = self.get_coord_float()
        dist = (SENSOR_HEIGHT / 2) / np.tan(np.radians(LENS_V_FOV / 2.0))
        rho = np.tan(np.radians(90 - dec)) * dist
        phi = np.radians(360.0 * ra / 24.0)
        x = rho * np.cos(phi)
        y = rho * np.sin(phi)
        x += cx
        if flip_y:
            y = cy - y
        else:
            y += cy
        self.x = x
        self.y = y
        return x, y

    def calc_rel_xy(self, star):
        self.get_coord_xy()
        x, y = star.get_coord_xy()
        return (x - self.x), (y - self.y)

    def calc_rel_polar(self, star):
        dx, dy = self.calc_rel_xy(star)
        dist = np.sqrt((dx ** 2) + (dy ** 2))
        ang  = np.degrees(np.arctan2(dy, dx))
        return dist, ang

    def printme(self):
        ra, dec = self.get_coord_float()
        print("[%s]: %f  |  %f    |    %f" % (self.name, ra, dec, self.bmag))

def draw_stars(stars):
    im = Image.new("RGB", (SENSOR_WIDTH, SENSOR_HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(im)
    # draw center crosshair at NCP
    draw.line([(0, SENSOR_HEIGHT / 2), (SENSOR_WIDTH, SENSOR_HEIGHT / 2)], fill=(128, 128, 0))
    draw.line([(SENSOR_WIDTH / 2, 0), (SENSOR_WIDTH / 2, SENSOR_HEIGHT)], fill=(128, 128, 0))
    # draw each star with azimuthal equidistant projection
    for star in stars:
        radius = 20.0 / star.bmag
        x, y = star.get_coord_xy()
        draw.ellipse([(x - radius, y - radius), (x + radius, y + radius)], fill=(255, 255, 255))
    return im, draw

def get_polaris(stars):
    # find Polaris by maximum brightness
    maxmag = sys.float_info.max
    res = None
    for star in stars:
        if star.bmag < maxmag:
            res = star
            maxmag = star.bmag
    return res

def sort_polaris_dist(x):
    return x.polaris_dist

def main():
    stars = []
    f = open("stars_around_polaris.txt", "r")
    lines = f.readlines()
    started = False
    for line in lines:
        split = line.split('|')
        if len(split) == 12:
            if split[0].lstrip().rstrip().isnumeric():
                started = True
        elif started:
            started = False
            break
        if started and split[0].isnumeric:
            star = Star(split[1], split[3], float(split[5]))
            star.printme()
            stars.append(star)

    im, draw = draw_stars(stars)

    polaris = get_polaris(stars)
    px, py = polaris.get_coord_xy()

    for star in stars:
        dist, ang = polaris.calc_rel_polar(star)
        star.polaris_dist = dist
        star.polaris_ang  = ang
        #draw.ellipse([(px - dist, py - dist), (px + dist, py + dist)], outline=(0, 0, 255))

    stars.sort(key = sort_polaris_dist)
    for star in stars:
        print("[%s]:  %f  ,  %f" % (star.name, star.polaris_dist, star.polaris_ang))

    im.show()
    im.save("ncp_stars_projected.png")

    sum = 0
    cnt = 0
    # calculate best calibration using measured pixel distances
    for pair in SCALE_TABLE:
        r = pair[0] / pair[1]
        sum += r
        cnt += 1
    avg = sum / cnt

    print("camera calibrated results:")
    for star in stars:
        print("[\"%s\", %f, %f]," % (star.name, star.polaris_dist / avg, star.polaris_ang))
    # the output here is copied into the MicroPython code

    return 0

if __name__ == "__main__":
    main()