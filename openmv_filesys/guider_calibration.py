import micropython
micropython.opt_level(2)

import comutils

class GuiderCalibration(object):
    def __init__(self, x, y, pulse_width):
        self.points = [[x, y]]
        self.pulse_width
        self.has_cal = False

    def append(self, x, y):
        self.points.append([x, y])

    def get_span(self):
        p0 = self.points[0]

    def get_span_between(self, p0, point_list = self.points):
        max_mag = 0
        i = 0
        while i < len(point_list):
            p = point_list[i]
            mag = comutils.vector_between(p, p0, mag_only = True)
            if mag > max_mag:
                max_mag = mag
            i += 1
        return max_mag

    def get_span_all(self, point_list = self.points):
        i = 0
        max_mag = 0
        while i < len(point_list):
            x = get_span_between(point_list[i], point_list = point_list)
            if x > max_mag:
                max_mag = x
            i += 1

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
        accepted_points = []
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
                accepted_points.append(p1)
            if i == 0 and mag1 >= mag_limit: # "good" point
                accepted_points.append(p0)
            if i == len(self.points) - 2 and mag2 >= mag_limit: # "good" point
                accepted_points.append(p2)
            if mag_start > farthest:
                farthest = mag_start
                farthest_point = p2
        self.line_est_center, self.angle = line_est(accepted_points)
        # we have a line-of-best-fit but there are two possible directions
        # use the start point and the farthest point to see if the direction needs to be flipped
        mag, ang = comutils.vector_between(pstart, farthest_point)
        dang = comutils.angle_diff(ang, self.angle)
        if abs(dang) > 90: # direction needs flipping
            self.angle += 180.0
        self.angle = comutils.angle_normalize(self.angle)
        self.farthest = farthest

        if len(accepted_points) < 10:
            return False
        else:
            self.has_cal = True
            return True

    def summary(self):
        return len(accepted_points), self.farthest, self.angle, self.line_est_center, self.points[0]

def line_est(points):
    cnt = len(points)
    sum_x   = 0
    sum_y   = 0
    sum_xx = 0
    sum_xy  = 0
    for p in points:
        sum_x  += p.cx
        sum_y  += p.cy
        sum_xx += p.cx ** 2
        sum_xy += p.cx * p.cy
    avg_x = sum_x / cnt
    avg_y = sum_y / cnt
    dy = (sum_xy / cnt) - (avg_x * avg_y)
    dx = (sum_xx / cnt) - (avg_x * avg_x)
    return [avg_x, avg_y], math.degrees(math.atan2(dy, dx))
