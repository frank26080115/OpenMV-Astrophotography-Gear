import micropython
micropython.opt_level(2)

import autoguider
import exclogger
import comutils
import blobstar
import guidestar

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
                cx = pyb.rng() % comutils.SENSOR_WIDTH
                cy = pyb.rng() % comutils.SENSOR_HEIGHT
                self.new_stars[i].move_coord(cx, cy)
                i += 1
        elif self.guider.guide_state == autoguider.GUIDESTATE_GUIDING or self.guider.guide_state == autoguider.GUIDESTATE_IDLE or self.guider.guide_state == autoguider.GUIDESTATE_PANIC or self.guider.guide_state == autoguider.GUIDESTATE_DITHER:
            dx = 0
            dy = 0
            if self.guider.target_coord is not None and self.guider.selected_star is not None:
                dx = self.guider.target_coord[0] - self.guider.selected_star.cxf()
                dy = self.guider.target_coord[1] - self.guider.selected_star.cyf()
            i = 0
            while i < star_cnt:
                old_star = self.base_stars[i]
                self._remake_star(i)
                cx = old_star.cxf() + dx + get_rand_move(4, 10)
                cy = old_star.cyf() + dy + get_rand_move(4, 10)
                self.new_stars[i].move_coord(cx, cy)
                i += 1
        elif self.guider.guide_state == autoguider.GUIDESTATE_CALIBRATING_RA or self.guider.guide_state == autoguider.GUIDESTATE_CALIBRATING_DEC:
            if self.prev_state != self.guider.guide_state:
                if self.guider.guide_state == autoguider.GUIDESTATE_CALIBRATING_RA:
                    if self.rand_angle_dec is None:
                        self.rand_angle_ra = get_rand_move(360, 10)
                    else:
                        self.rand_angle_ra = self.rand_angle_dec + 90 + get_rand_move(4, 10)
                    self.rand_scale_ra = (pyb.rng() % 20) + 5
                    print("sim calib RA ang %0.1f scale %0.1f" % (self.rand_angle_ra, self.rand_scale_ra))
                elif self.guider.guide_state == autoguider.GUIDESTATE_CALIBRATING_DEC:
                    if self.rand_angle_ra is None:
                        self.rand_angle_dec = get_rand_move(360, 10)
                    else:
                        self.rand_angle_dec = self.rand_angle_ra + 90 + get_rand_move(4, 10)
                    self.rand_scale_dec = (pyb.rng() % 20) + 5
                    print("sim calib DEC ang %0.1f scale %0.1f" % (self.rand_angle_dec, self.rand_scale_dec))
                dx = self.guider.target_coord[0] - self.guider.selected_star.cxf()
                dy = self.guider.target_coord[1] - self.guider.selected_star.cyf()
                i = 0
                while i < star_cnt:
                    ocx = self.base_stars[i].cxf()
                    ocy = self.base_stars[i].cyf()
                    self._remake_star(i)
                    cx = ocx + dx + get_rand_move(4, 10)
                    cy = ocy + dy + get_rand_move(4, 10)
                    self.new_stars[i].move_coord(cx, cy)
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
                print("sim cali move %0.1f %0.1f" % (dx, dy))
                i = 0
                while i < star_cnt:
                    ocx = self.new_stars[i].cxf()
                    ocy = self.new_stars[i].cyf()
                    self._remake_star(i)
                    cx = ocx + dx
                    cy = ocy + dy
                    self.new_stars[i].move_coord(cx, cy)
                    i += 1
        self.prev_state = self.guider.guide_state
        return self.new_stars

    def _remake_star(self, i):
        self.new_stars[i] = self.base_stars[i].clone()

def get_rand_move(lim, mul):
    limi = int(round(lim * mul))
    limh = lim * mul / 2
    return ((pyb.rng() % limi) - limh) / mul

if __name__ == "__main__":
    import gc
    print("memory at boot %u" % gc.mem_free())
    x = autoguider.AutoGuider(debug = True, simulate_file = "snap-20210206-040632.bmp")
    #x = autoguider.AutoGuider(debug = True, simulate_file = "simulate.bmp")
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
