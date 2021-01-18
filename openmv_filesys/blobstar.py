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

class GuideStar(object):

    def __init__(self, cx, cy, r, brightness, maxbrite, saturated, area, pointiness):
        self.cx = cx
        self.cy = cy
        self.r  = r
        self.brightness = brightness
        self.maxbrite = maxbrite
        self.saturated = saturated
        self.area = area
        self.saturation = saturated * 100.0 / area
        self.pointiness = pointiness
        self.rating = self._eval()
        self.profile = []

    def _eval(self):
        # we want the star to be not too close to the edge
        if self.cx < SENSOR_WIDTH / 3:
            return 0
        if self.cx > (SENSOR_WIDTH * 2) / 3:
            return 0
        if self.cy < SENSOR_HEIGHT / 3:
            return 0
        if self.cy > (SENSOR_HEIGHT * 2) / 3:
            return 0

        # we want the star to be bright enough
        # but saturating is bad
        score_maxbrite = 0
        best_maxbrite = 256 - 16
        if self.maxbrite == best_maxbrite:
            score_maxbrite = 100
        elif self.maxbrite < best_maxbrite:
            score_maxbrite = comutils.map_val(self.maxbrite, 64, best_maxbrite, 0, 100)
        elif self.maxbrite > best_maxbrite:
            score_maxbrite = 100 - comutils.map_val(self.maxbrite, best_maxbrite, 255, 0, 25)

        # fully saturated stars are bad for tracking because it's harder to find the center
        score_saturation = 100 - self.saturation

        # closer to center of screen is better
        center_x = SENSOR_WIDTH / 2
        center_y = SENSOR_HEIGHT / 2
        mag = comutils.vector_between([center_x, center_y], [self.cx, self.cy], mag_only = True)
        score_centerdist = 100 - comutils.map_val(mag, 0, SENSOR_HEIGHT / 6, 0, 100)

        score_pointiness = self.pointiness

        # place weights on each item
        return (score_pointiness * 0.9) + (score_maxbrite * 0.7) + (score_saturation * 0.7) + (score_centerdist * 0.5)

    def to_jsonobj(self):
        obj = {}
        obj.update({"cx": round_num(self.cx)})
        obj.update({"cy": round_num(self.cy)})
        #obj.update({"r" : round_num(self.r)})
        #obj.update({"brightness": round_num(self.brightness)})
        #obj.update({"saturation": round_num(self.saturation)})
        obj.update({"rating": self.rating})
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

def sort_rating_func(star):
    return star.rating

def sort_brightness(star_list):
    res_list = sorted(star_list, key = sort_brightness_func, reverse = True)
    return res_list

def sort_dist(star_list):
    res_list = sorted(star_list, key = sort_dist_func)
    return res_list

def sort_rating(star_list):
    res_list = sorted(star_list, key = sort_rating_func)
    return res_list
