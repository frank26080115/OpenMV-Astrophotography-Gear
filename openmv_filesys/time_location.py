import micropython
micropython.opt_level(2)

import pyb, uos, utime, math
import pole_movement

import comutils
from comutils import SIDEREAL_DAY_SECONDS

USE_FIXED_POINT = micropython.const(False)

class TimeLocationManager(object):
    def __init__(self):
        # scan all files to get an estimated date
        files = uos.listdir()
        maxsec = 0
        for f in files:
            try:
                stats = uos.stat(f)
                j = 7
                while j <= 9:
                    t = stats[j]
                    if t > maxsec:
                        maxsec = t
                    j += 1
            except:
                pass

        self.start_time = utime.localtime(maxsec)
        self.start_sec = maxsec - (pyb.millis() // 1000)

        # default location is my local star gazing spot
        self.set_location(-122.246086, 37.364107)

        # at Greenwich (longitude = 0), the solar time that matches sidereal time = 00:00
        self.sidereal_sync_time = comutils.utc_to_epoch(2020, 8, 10, 20, 40, 53)
        # in Jan 1 2040 at 11:17:05 is another such epoch

        self.pole_move = pole_movement.PoleMovement()

        self.tick()

        self.readiness = False

    # call this function before getting or setting the time
    # this allows for the time to be kept still for various tests
    def tick(self, latest_millis = None):
        if latest_millis is None:
            latest_millis = pyb.millis()
        self.latest_millis = latest_millis
        pass

    def get_jdn(self):
        t = self.get_time()
        return comutils.jdn(t[0], t[1], t[2])

    def get_sec(self):
        t = self.start_sec + (self.latest_millis // 1000)
        return t

    def get_time(self):
        return utime.localtime(int(round(self.get_sec())))

    def set_utc_time(self, utc_yr, utc_month, utc_day, utc_hr, utc_min, utc_sec):
        s = comutils.utc_to_epoch(utc_yr, utc_month, utc_day, utc_hr, utc_min, utc_sec)
        self.set_utc_time_epoch(s)

    def set_utc_time_epoch(self, s):
        self.start_sec = s - (self.latest_millis // 1000)
        self.readiness = True

    def set_location(self, longitude, latitude):
        if longitude is not None:
            self.longitude = longitude
            while self.longitude > 180.0:
                self.longitude -= 360.0
            while self.longitude < -180.0:
                self.longitude += 360.0
        if latitude is not None:
            self.latitude  = latitude
            while self.latitude > 90.0:
                self.latitude -= 90.0
            while self.latitude < -90.0:
                self.latitude += 90.0

    def is_ready(self):
        return self.readiness

    def get_sidereal_angle(self):
        x = self.get_sec()
        x -= self.sidereal_sync_time

        if USE_FIXED_POINT:
            x = [int(round(x)), 0]
            y = micropython.const([int(86164), int(9054)])
            div, rem = fixed_point_divide(x, y, 100000)
        else:
            rem = math.fmod(x, SIDEREAL_DAY_SECONDS)
        rem *= 360.0
        rem /= SIDEREAL_DAY_SECONDS
        return rem

    def get_longitude_angle(self):
        x = self.longitude
        # negative longitude means west
        while x < 0:
            x += 360.0
        return x

    def get_angle(self):
        # NOTE: the angle here will rotate counterclockwise
        x = self.get_sidereal_angle() + self.get_longitude_angle()
        while x < 0:
            x += 360.0
        while x > 360.0:
            x -= 360.0
        return x

    def get_polaris(self):
        return self.pole_move.calc_for_jdn(self.get_jdn())

def fixed_point_divide(x, y, dec):
    cnt = 0
    if x[1] < dec:
        x[1] += dec
    while x[0] / y[0] >= 1100:
        x[0] -= 1000 * y[0]
        x[1] -= 1000 * y[1]
        cnt += 1000
        while x[1] < dec:
            x[1] += dec
            x[0] -= 1
    while x[0] / y[0] >= 110:
        x[0] -= 100 * y[0]
        x[1] -= 100 * y[1]
        cnt += 100
        while x[1] < dec:
            x[1] += dec
            x[0] -= 1
    while x[0] / y[0] >= 11:
        x[0] -= 10 * y[0]
        x[1] -= 10 * y[1]
        cnt += 10
        while x[1] < dec:
            x[1] += dec
            x[0] -= 1
    while True:
        z = [x[0] - y[0], x[1] - y[1]]
        if z[0] < 0:
            break
        if z[0] == 0 and z[1] < dec:
            break
        if z[1] < dec:
            z[0] -= 1
            z[1] += dec
        x = z
        cnt += 1
    x[1] -= dec
    r = x[1] / dec
    r += x[0]
    return cnt, r

def test():
    mgr = TimeLocationManager()
    print("Start Time From File: " + str(mgr.start_time))
    print("File Time Stamp %u" % mgr.start_sec)
    i = 0
    ms = pyb.millis()
    while i < 5:
        mgr.tick()
        print("tick " + comutils.fmt_time(mgr.get_time()))
        pyb.delay(1001)
        i += 1
    print("=============")
    print("Time Test")
    i = 0
    while i < 3:
        utc_yr = 2020 + (pyb.rng() % 2)
        utc_month = 1 + (pyb.rng() % 12)
        utc_day = 1 + (pyb.rng() % 27)
        utc_hr = (pyb.rng() % 24)
        utc_min = (pyb.rng() % 60)
        utc_sec = (pyb.rng() % 60)
        mgr.set_utc_time(utc_yr, utc_month, utc_day, utc_hr, utc_min, utc_sec)
        print("%s = %s" % (str((utc_yr, utc_month, utc_day, utc_hr, utc_min, utc_sec)), str(mgr.get_time())))
        i += 1
    print("=============")
    print("Rotation Test")
    i = 0
    while i < 10:
        longitude = pyb.rng() % 360
        if longitude > 180:
            longitude -= 360
        mgr.set_location(longitude, None)
        mgr.set_utc_time(2021 + (pyb.rng() % 20), 1 + (pyb.rng() % 12), 1 + (pyb.rng() % 27), pyb.rng() % 24, pyb.rng() % 60, pyb.rng() % 60)
        ang = mgr.get_angle()
        if ang < 1 or ang > 359:
            print("%d, %s, %0.4f" % (longitude, comutils.fmt_time(mgr.get_time()), ang))
            i += 1
    print("=============")

if __name__ == "__main__":
    test()
