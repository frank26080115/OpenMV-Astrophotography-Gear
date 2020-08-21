import micropython
micropython.opt_level(2)

import pyb, uos, utime, math
import pole_movement

SIDEREAL_DAY_SECONDS = micropython.const(86164.09054)

class TimeLocationManager(object):
    def __init__(self):
        # scan all files to get an estimated date
        files = uos.listdir()
        maxsec = 0
        for f in files:
            stats = uos.stat(f)
            j = 7
            while j <= 9:
                t = stats[j]
                if t > maxsec:
                    maxsec = t
                j += 1

        self.start_time = utime.localtime(maxsec)
        self.start_sec = maxsec - (pyb.millis() // 1000)

        # default location is my local star gazing spot
        self.set_location(-122.246086, 37.364107)

        # at Greenwich (longitude = 0), the solar time that matches sidereal time = 00:00
        self.sidereal_sync_time = utc_to_epoch(2020, 8, 10, 20, 40, 46)

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
        return jdn(t[0], t[1], t[2])

    def get_sec(self):
        t = self.start_sec + (self.latest_millis // 1000)
        return t

    def get_time(self):
        return utime.localtime(int(round(self.get_sec())))

    def set_utc_time(self, utc_yr, utc_month, utc_day, utc_hr, utc_min, utc_sec):
        s = utc_to_epoch(utc_yr, utc_month, utc_day, utc_hr, utc_min, utc_sec)
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
        while x > SIDEREAL_DAY_SECONDS:
            x -= SIDEREAL_DAY_SECONDS
        x *= 360.0
        x /= SIDEREAL_DAY_SECONDS
        return x

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

def utc_to_epoch(utc_yr, utc_month, utc_day, utc_hr, utc_min, utc_sec):
    s = utime.mktime((utc_yr, utc_month, utc_day, utc_hr, utc_min, utc_sec, 0, 0))
    return s

def jdn(y, m, d):
    # http://www.cs.utsa.edu/~cs1063/projects/Spring2011/Project1/jdn-explanation.html
    return d + (((153 * m) + 2) // 5) + (356 * y) + (y // 4) - (y // 100) + (y // 400) - 32045

"""
def test():
    mgr = TimeLocationManager()
    print("Start Time From File: " + str(mgr.start_time))
    print("File Time Stamp %u" % mgr.start_sec)
    i = 0
    ms = pyb.millis()
    while i < 5:
        mgr.tick()
        print("tick " + str(mgr.get_time()))
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
        mgr.set_utc_time(2021 + (pyb.rng() % 2), 1 + (pyb.rng() % 12), 1 + (pyb.rng() % 27), pyb.rng() % 24, pyb.rng() % 60, pyb.rng() % 60)
        print("%d, %s, %0.4f" % (longitude, str(mgr.get_time()), mgr.get_angle()))
        i += 1
    print("=============")

if __name__ == "__main__":
    test()
"""
