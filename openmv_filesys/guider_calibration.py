import micropython
micropython.opt_level(2)

import math
import ujson
import comutils
import exclogger

RECOMMENDED_POINTS       = micropython.const(10)
MINIMUM_REQUIRED_POINTS  = micropython.const(5)

class GuiderCalibration(object):
    def __init__(self, x, y, pulse_width):
        self.points = [[x, y]]
        self.pulse_width = pulse_width
        self.has_cal = False
        self.time = 0

        self.accepted_points = []
        self.farthest = 0
        self.angle = 0
        self.pix_per_ms = 0
        self.ms_per_pix = 0

        self.success = "init"

    def set_origin(self, x, y):
        self.points = [[x, y]]

    def append(self, x, y):
        self.append_pt([x, y])
        #self.points.append([x, y])

    def append_pt(self, pt):
        self.success = "wait"
        self.points.append(pt)

    def append_all(self, pts):
        for i in pts:
            self.append_pt(i)
        #self.points.extend(pts)

    def reset_pts(self):
        self.points = [self.points[0]]

    def get_span(self):
        p0 = self.points[0]

    def get_span_between(self, p0, point_list = None):
        if point_list is None:
            point_list = self.points
        max_mag = 0
        i = 0
        while i < len(point_list):
            p = point_list[i]
            mag = comutils.vector_between(p, p0, mag_only = True)
            if mag > max_mag:
                max_mag = mag
            i += 1
        return max_mag

    def get_span_all(self, point_list = None):
        if point_list is None:
            point_list = self.points
        i = 0
        max_mag = 0
        while i < len(point_list):
            x = get_span_between(point_list[i], point_list = point_list)
            if x > max_mag:
                max_mag = x
            i += 1
        return max_mag

    def analyze(self):
        i = 0
        min_mag = 10000
        max_mag = 0
        mag_sum = 0
        all_mags = []
        # this first loop simply figures out the farthest distance between any two consecutive points
        while i < len(self.points) - 1:
            p1 = self.points[i]
            p2 = self.points[i + 1]
            mag = comutils.vector_between(p1, p2, mag_only = True)
            if mag > max_mag:
                max_mag = mag
            if mag < min_mag:
                min_mag = mag
            all_mags.append(mag)
            i += 1
        # now we figure out which moves were inhibited by backlash
        d_mag = max_mag - min_mag
        mag_limit = min_mag + (d_mag / 4)
        mag_sum = 0
        mag_sum_cnt = 0
        for i in all_mags:
            # only count the ones that are not affected by backlash
            if i >= mag_limit:
                mag_sum += i
                mag_sum_cnt += 1
        # we can figure out the pixels per millisec, and millisec per pixel
        self.avg_step_mag = mag_sum / mag_sum_cnt
        self.pix_per_ms = self.avg_step_mag / self.pulse_width
        self.ms_per_pix = self.pulse_width / self.avg_step_mag
        i = 1
        self.accepted_points = []
        farthest_point = None
        farthest = 0
        pstart = self.points[0]
        # now we go through the points again, find the ones not affected by backlash
        # these "good" points will be used to calculate a line-of-best-fit
        while i < len(self.points) - 1:
            p0 = self.points[i - 1]
            p1 = self.points[i]
            p2 = self.points[i + 1]
            mag1 = comutils.vector_between(p0, p1, mag_only = True)
            mag2 = comutils.vector_between(p1, p2, mag_only = True)
            mag_start = comutils.vector_between(pstart, p2, mag_only = True)
            if mag1 >= mag_limit and mag2 >= mag_limit: # "good" point
                self.accepted_points.append(p1)
            if i == 0 and mag1 >= mag_limit: # "good" point
                self.accepted_points.append(p0)
            if i == len(self.points) - 2 and mag2 >= mag_limit: # "good" point
                self.accepted_points.append(p2)
            if mag_start > farthest:
                farthest = mag_start
                farthest_point = p2
            i += 1
        self.line_est_center, self.angle = line_est(self.accepted_points)
        # we have a line-of-best-fit but there are two possible directions
        # use the start point and the farthest point to see if the direction needs to be flipped
        mag, ang = comutils.vector_between(pstart, farthest_point)
        dang = comutils.angle_diff(ang, self.angle)
        if abs(dang) > 90: # direction needs flipping
            self.angle += 180.0
        self.angle = comutils.ang_normalize(self.angle)
        self.farthest = farthest

        if len(self.accepted_points) < MINIMUM_REQUIRED_POINTS:
            self.success = "failed"
            return False
        else:
            self.has_cal = True
            self.success = "done"
            return True

    def summary(self):
        return len(self.accepted_points), self.farthest, self.angle, self.line_est_center, self.points[0]

    def get_json_obj(self):
        obj = {}
        obj.update({"success"      : self.success})
        obj.update({"pulse_width"  : self.pulse_width})
        obj.update({"points"       : self.accepted_points})
        obj.update({"points_cnt"   : len(self.accepted_points)})
        obj.update({"start_x"      : self.points[0][0]})
        obj.update({"start_y"      : self.points[0][1]})
        obj.update({"pix_per_ms"   : self.pix_per_ms})
        obj.update({"ms_per_pix"   : self.ms_per_pix})
        obj.update({"farthest"     : self.farthest})
        obj.update({"angle"        : self.angle})
        obj.update({"time"         : self.timestamp})
        return obj

    def load_json_obj(self, obj):
        if "str" in str(type(obj)):
            obj = ujson.loads(obj)
        self.has_cal = True
        self.pulse_width = comutils.try_parse_setting(obj["pulse_width"])
        self.accepted_points = []
        self.points = [[comutils.try_parse_setting(obj["start_x"]),  comutils.try_parse_setting(obj["start_y"])]]
        pix_per_ms = comutils.try_parse_setting(obj["pix_per_ms"])
        ms_per_pix = comutils.try_parse_setting(obj["ms_per_pix"])
        if pix_per_ms != 0 and ms_per_pix != 0:
            self.pix_per_ms = pix_per_ms
            self.ms_per_pix = ms_per_pix
        elif pix_per_ms != 0:
            self.pix_per_ms = pix_per_ms
            self.ms_per_pix = 1.0 / pix_per_ms
        elif ms_per_pix != 0:
            self.ms_per_pix = ms_per_pix
            self.pix_per_ms = 1.0 / ms_per_pix
        else:
            self.has_cal = False
        self.angle = comutils.ang_normalize(comutils.try_parse_setting(obj["angle"]))
        self.farthest = comutils.try_parse_setting(obj["farthest"])
        self.timestamp = comutils.try_parse_setting(obj["time"])

def line_est(points):
    cnt = len(points)
    sum_x   = 0
    sum_y   = 0
    sum_xx = 0
    sum_xy  = 0
    for p in points:
        sum_x  += p[0]
        sum_y  += p[1]
        sum_xx += p[0] * p[0]
        sum_xy += p[0] * p[1]
    avg_x = sum_x / cnt
    avg_y = sum_y / cnt
    dy = (sum_xy / cnt) - (avg_x * avg_y)
    dx = (sum_xx / cnt) - (avg_x * avg_x)
    #print("%u %f %f %f %f %f %f %f %f" % (cnt, sum_x, sum_y, sum_xx, sum_xy, avg_x, avg_y, dy, dx))
    if dy == 0 and dx == 0:
        return [avg_x, avg_y], 90
    return [avg_x, avg_y], math.degrees(math.atan2(dy, dx))

if __name__ == "__main__":
    tests = []
    tests.append([[0,   1], [0,   2], [0,   3], [0,   4], [0,   5]])
    tests.append([[0,  -1], [0,  -2], [0,  -3], [0,  -4], [0,  -5]])
    tests.append([[1,   0], [2,   0], [3,   0], [4,   0], [5,   0]])
    tests.append([[-1,  0], [-2,  0], [-3,  0], [-4,  0], [-5,  0]])
    tests.append([[1,   1], [2,   2], [3,   3], [4,   4], [5,   5]])
    tests.append([[1,  -1], [2,  -2], [3,  -3], [4,  -4], [5,  -5]])
    tests.append([[-1, -1], [-2, -2], [-3, -3], [-4, -4], [-5, -5]])
    tests.append([[-1,  1], [-2,  2], [-3,  3], [-4,  4], [-5,  5]])
    tests.append([[0,   1], [0,  20], [0,  30], [0,  40], [0,  50], [0, 60], [0, 70], [0, 80]])
    tests.append([[0,  10], [0,  20], [0,  30], [0,  40], [0,  50], [0, 60], [0, 70], [0, 80]])
    tests.append([[0,   1], [0,  20], [0,  30], [0,  40], [0,  50], [0, 60], [0, 70], [0, 71]])

    print("Guider Calibration Test")
    i = 0
    while i < len(tests):
        cali = GuiderCalibration(0, 0, 750)
        cali.append_all(tests[i])
        cali.analyze()
        cnt, farthest, angle, line_center, start_pt = cali.summary()
        print("test [%u]: %u , %f , %f , ( %f , %f ) , ( %f , %f ), %f , %f" % (i, cnt, farthest, angle, line_center[0], line_center[1], start_pt[0], start_pt[1], cali.pix_per_ms, cali.ms_per_pix))
        i += 1

