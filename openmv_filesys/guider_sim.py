import micropython
micropython.opt_level(2)

import autoguider
import exclogger
import comutils
import blobstar

import math, pyb

class GuiderSimulator(object):

    def __init__(self):
        self.base_stars     = None
        self.guider         = None
        self.new_stars      = None
        self.prev_state     = 0
        self.rand_angle_ra  = None
        self.rand_angle_dec = None
        self.rand_scale_ra  = 0
        self.rand_scale_dec = 0
        self.messy          = False

    def get_stars(self, guider, stars):
        self.guider = guider
        if self.base_stars is None:
            self.base_stars = stars
            print("simulator loaded base stars %u" % len(self.base_stars))
        if self.base_stars is None:
            return None
        star_cnt = len(self.base_stars)
        if self.new_stars is None:
            self.new_stars = [None] * star_cnt
            i = 0
            while i < star_cnt:
                self._remake_star(i)
                i += 1
        if self.messy:
            i = 0
            while i < star_cnt:
                self._remake_star(i)
                self.new_stars[i].cx = pyb.rng() % comutils.SENSOR_WIDTH
                self.new_stars[i].cy = pyb.rng() % comutils.SENSOR_HEIGHT
                i += 1
        elif self.guider.guide_state == autoguider.GUIDESTATE_GUIDING or self.guider.guide_state == autoguider.GUIDESTATE_IDLE or self.guider.guide_state == autoguider.GUIDESTATE_PANIC or self.guider.guide_state == autoguider.GUIDESTATE_DITHER:
            dx = 0
            dy = 0
            if self.guider.target_coord is not None and self.guider.selected_star is not None:
                dx = self.guider.target_coord[0] - self.guider.selected_star.cx
                dy = self.guider.target_coord[1] - self.guider.selected_star.cy
            i = 0
            while i < star_cnt:
                old_star = self.base_stars[i]
                self._remake_star(i)
                self.new_stars[i].cx = old_star.cx + dx + get_rand_move(8, 10)
                self.new_stars[i].cy = old_star.cy + dy + get_rand_move(8, 10)
                i += 1
        elif self.guider.guide_state == autoguider.GUIDESTATE_CALIBRATING_RA or self.guider.guide_state == autoguider.GUIDESTATE_CALIBRATING_DEC:
            if self.prev_state != self.guider.guide_state:
                if self.guider.guide_state == autoguider.GUIDESTATE_CALIBRATING_RA:
                    self.rand_angle_ra = get_rand_move(360, 10)
                    self.rand_scale_ra = (pyb.rng() % 20) + 5
                elif self.guider.guide_state == autoguider.GUIDESTATE_CALIBRATING_DEC:
                    self.rand_angle_dec = get_rand_move(360, 10)
                    self.rand_scale_dec = (pyb.rng() % 20) + 5
                dx = self.guider.target_coord[0] - self.guider.selected_star.cx
                dy = self.guider.target_coord[1] - self.guider.selected_star.cy
                i = 0
                while i < star_cnt:
                    cx = self.base_stars[i].cx
                    cy = self.base_stars[i].cy
                    self._remake_star(i)
                    self.new_stars[i].cx = cx + dx + get_rand_move(8, 10)
                    self.new_stars[i].cy = cy + dy + get_rand_move(8, 10)
                    i += 1
            else:
                if self.guider.guide_state == autoguider.GUIDESTATE_CALIBRATING_RA:
                    mag = self.rand_scale_ra + get_rand_move(4, 10)
                    ang = self.rand_angle_ra + get_rand_move(2, 10)
                elif self.guider.guide_state == autoguider.GUIDESTATE_CALIBRATING_DEC:
                    mag = self.rand_scale_dec + get_rand_move(4, 10)
                    ang = self.rand_angle_dec + get_rand_move(2, 10)
                ang_rad = math.radians(ang)
                dx = mag * math.cos(ang_rad)
                dy = mag * math.sin(ang_rad)
                i = 0
                while i < star_cnt:
                    cx = self.new_stars[i].cx
                    cy = self.new_stars[i].cy
                    self._remake_star(i)
                    self.new_stars[i].cx = cx + dx
                    self.new_stars[i].cy = cx + dy
                    i += 1
        self.prev_state = self.guider.guide_state
        return self.new_stars

    def _remake_star(self, i):
        old_star = self.base_stars[i]
        new_star = blobstar.GuideStar(old_star.cx, old_star.cy, old_star.r, old_star.brightness, old_star.maxbrite, old_star.saturated, old_star.area, old_star.pointiness)
        new_star.rating = old_star.rating
        new_star.profile = old_star.profile
        self.new_stars[i] = new_star

def get_rand_move(lim, mul):
    limi = int(round(lim * mul))
    limh = lim * mul / 2
    return ((pyb.rng() % limi) - limh) / mul

if __name__ == "__main__":
    x = autoguider.AutoGuider(debug = True, simulate_file = "rand_stars.bmp")
    #x = AutoGuider(debug = True)
    while True:
        try:
            x.task()
        except KeyboardInterrupt:
            raise
        except MemoryError as exc:
            exclogger.log_exception(exc, to_file = False)
            micropython.mem_info(True)
        except Exception as exc:
            exclogger.log_exception(exc)
