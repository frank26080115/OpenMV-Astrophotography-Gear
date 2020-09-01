import micropython
micropython.opt_level(2)
import math
import ujson

"""
class BlobStarUidManager(object):

    def __init__(self):
        self.used = []

    def generate(self):
        x = 0
        while True:
            try:
                import pyd
                x = pyd.rng()
            except:
                pass
            try:
                import random
                x = random.randint(0, 0x7FFFFFFF)
            except:
                pass
            if x != 0:
                if x not in self.used:
                    self.used.append(x)
                    return x
"""

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
        self.ref_star_dist = calc_dist(self, ref_star)
        self.ref_star_angle = calc_angle(self, ref_star)

    def reset_score(self):
        self.score = 0

    def to_jsonobj(self):
        obj = {}
        obj.update({"cx": self.cx})
        obj.update({"cy": self.cy})
        obj.update({"r": self.r})
        obj.update({"brightness": self.brightness})
        return obj

def to_jsonobj(star_list):
    x = []
    for i in star_list:
        x.append(i.to_jsonobj())
    return x

def calc_dist(star1, star2):
    dx = star1.cx - star2.cx
    dy = star1.cy - star2.cy
    return math.sqrt((dx ** 2) + (dy ** 2))

def calc_angle(star1, star2):
    dx = star2.cx - star1.cx
    dy = star2.cy - star1.cy
    return math.degrees(math.atan2(dy, dx))

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
