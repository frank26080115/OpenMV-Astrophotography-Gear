import pyb, uos, utime, math

SIDEREAL_DAY_SECONDS = 86164.09054

# table pre-generated using data from https://britastro.org/node/17066
# [0]   is the upper bound of the latitude, lower bound found in next entry
# [1:3] are quadratic coefficients for that latitude
REFRACTION_TABLE = [
[90.0, 0.0000000000,  0.0000000000, 0.0000000000],
[89.0, 0.0000000000, -0.0183333333, 1.6500000000],
[75.0, 0.0001666667, -0.0433333333, 2.5833333333],
[65.0, 0.0002500000, -0.0541666667, 2.9333333333],
[55.0, 0.0004166667, -0.0725000000, 3.4333333333],
[45.0, 0.0010000000, -0.1250000000, 4.6000000000],
[35.0, 0.0022500000, -0.2125000000, 6.1000000000],
[25.0, 0.0080000000, -0.5000000000, 9.5500000000],
[17.5, 0.0093333333, -0.5466666667, 9.9500000000],
[12.5, 0.0536666667, -1.6550000000, 16.6000000000],
[7.5,  0.1965277778, -3.7979166667, 23.7430555556],
[3.5,  0.5986111111, -6.6125000000, 27.7638888889],
[1.5,  1.1222222222, -8.1833333333, 28.8111111111],
[0.75, 1.4666666667, -8.7000000000, 28.9833333333],
[0.25, 1.4333333333, -8.6833333333, 28.9833333333]]

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

    def set_location(self, longitude, latitude):
        if longitude is not None:
            self.longitude = longitude
        if latitude is not None:
            self.latitude  = latitude
            i = 0
            tbl_len = len(REFRACTION_TABLE)
            etr = None
            # find the best entry in the table
            while i < tbl_len:
                if latitude <= REFRACTION_TABLE[i][0]:
                    if i < tbl_len - 1:
                        if latitude > REFRACTION_TABLE[i + 1][0]:
                            etr = REFRACTION_TABLE[i]
                            break
                    else:
                        etr = REFRACTION_TABLE[i]
                        break
                i += 1
            # quadratic coeff
            x_2 = etr[1] * (latitude ** 2)
            x_1 = etr[2] * latitude
            x_0 = etr[3]
            self.refraction = x_2 + x_1 + x_0
            self.refraction /= 60.0 # calculation was for minutes

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

    def get_refraction(self):
        return self.refraction

def utc_to_epoch(utc_yr, utc_month, utc_day, utc_hr, utc_min, utc_sec):
    s = utime.mktime((utc_yr, utc_month, utc_day, utc_hr, utc_min, utc_sec, 0, 0))
    return s

def jdn(y, m, d):
    # http://www.cs.utsa.edu/~cs1063/projects/Spring2011/Project1/jdn-explanation.html
    return d + (((153 * m) + 2) // 5) + (356 * y) + (y // 4) - (y // 100) + (y // 400) - 32045

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
    print("Refraction Test")
    lat = 90
    lat_step = 10
    while lat >= -1:
        mgr.set_location(mgr.longitude, lat)
        print("%0.2f = %0.8f" % (lat, mgr.get_refraction()))
        lat -= lat_step
        if lat <= 20:
            lat_step = 5
        if lat <= 5:
            lat_step = 1
        if lat <= 2:
            lat_step = 0.5
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
