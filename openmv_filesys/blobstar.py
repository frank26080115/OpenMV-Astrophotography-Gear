import micropython
micropython.opt_level(2)
import comutils
from comutils import SENSOR_WIDTH, SENSOR_HEIGHT
import math
import ujson

class BlobStar(object):

    def __init__(self, cx, cy, r, brightness):
        self.cx = cx
        self.cy = cy
        self.r  = r
        self.brightness = brightness
        self.score = 0
        self.penalty = 0

    def set_ref_star(self, ref_star):
        self.ref_star = ref_star
        mag, ang = comutils.vector_between([self.cx, self.cy], [ref_star.cx, ref_star.cy])
        self.ref_star_dist = mag
        self.ref_star_angle = ang

    def reset_score(self):
        self.score = 0

    def to_jsonobj(self):
        obj = {}
        obj.update({"cx": self.cx})
        obj.update({"cy": self.cy})
        obj.update({"r": self.r})
        obj.update({"brightness": self.brightness})
        return obj

def round_num(x):
    return round(x * 10.0)/10.0

def to_jsonobj(star_list):
    x = []
    for i in star_list:
        x.append(i.to_jsonobj())
    return x

def sort_brightness_func(star):
    if star.brightness > 0:
        return star.brightness
    return star.r

def sort_dist_func(star):
    return star.ref_star_dist

def sort_brightness(star_list):
    res_list = sorted(star_list, key = sort_brightness_func, reverse = True)
    return res_list

def sort_dist(star_list):
    res_list = sorted(star_list, key = sort_dist_func)
    return res_list
