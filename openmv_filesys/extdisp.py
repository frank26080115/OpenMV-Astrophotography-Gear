import micropython
micropython.opt_level(2)
import math, utime
import pyb
import framebuf
import comutils, exclogger

OLED_DEFAULT_I2C_ADDR    = micropython.const(0x3C)
GPS_DEFAULT_I2C_ADDR     = micropython.const(0x42) # "The receiver's DDC address is set to 0x42 by default. This address can be changed by setting the mode field in CFG-PRT for DDC accordingly."
I2C_DEFAULT_CHANNEL      = micropython.const(2)
I2C_DEFAULT_BAUDRATE     = micropython.const(100000)

OLED_SET_CONTRAST        = micropython.const(0x81)
OLED_SET_ENTIRE_ON       = micropython.const(0xA4)
OLED_SET_NORM_INV        = micropython.const(0xA6)
OLED_SET_DISP            = micropython.const(0xAE)
OLED_SET_MEM_ADDR        = micropython.const(0x20)
OLED_SET_COL_ADDR        = micropython.const(0x21)
OLED_SET_PAGE_ADDR       = micropython.const(0x22)
OLED_SET_DISP_START_LINE = micropython.const(0x40)
OLED_SET_SEG_REMAP       = micropython.const(0xA0)
OLED_SET_MUX_RATIO       = micropython.const(0xA8)
OLED_SET_COM_OUT_DIR     = micropython.const(0xC0)
OLED_SET_DISP_OFFSET     = micropython.const(0xD3)
OLED_SET_COM_PIN_CFG     = micropython.const(0xDA)
OLED_SET_DISP_CLK_DIV    = micropython.const(0xD5)
OLED_SET_PRECHARGE       = micropython.const(0xD9)
OLED_SET_VCOM_DESEL      = micropython.const(0xDB)
OLED_SET_CHARGE_PUMP     = micropython.const(0x8D)
OLED_SCROLL_DEACTIVATE   = micropython.const(0x2E)

class SSD1306_I2C(object):

    def __init__(self, width = 128, height = 64, i2c = None, addr = OLED_DEFAULT_I2C_ADDR):
        if i2c is None:
            i2c = pyb.I2C(I2C_DEFAULT_CHANNEL, pyb.I2C.MASTER, baudrate = I2C_DEFAULT_BAUDRATE)
        self.i2c          = i2c
        self.addr         = addr
        self.width        = width
        self.height       = height
        self.pages        = self.height // 8
        self.external_vcc = False

    def test_connect(self):
        return self.i2c.is_ready(self.addr)

    def init_display(self):
        for cmd in (
                OLED_SET_DISP            | 0x00,  # off
                OLED_SET_DISP_CLK_DIV    , 0x80,
                OLED_SET_MUX_RATIO       , self.height - 1,
                OLED_SET_DISP_OFFSET     , 0x00,
                OLED_SET_DISP_START_LINE | 0x00,
                OLED_SET_CHARGE_PUMP     , 0x10 if self.external_vcc else 0x14,
                OLED_SET_MEM_ADDR        , 0x00,  # horizontal
                OLED_SET_SEG_REMAP       | 0x01,  # column addr 127 mapped to SEG0
                OLED_SET_COM_OUT_DIR     | 0x08,  # scan from COM[N] to COM0
                OLED_SET_COM_PIN_CFG     , 0x02 if self.height == 32 else 0x12,
                OLED_SET_CONTRAST        , 0xCF,
                OLED_SET_PRECHARGE       , 0x22 if self.external_vcc else 0xF1,
                OLED_SET_VCOM_DESEL      , 0x40,  # Vcom = 0.83 * Vcc
                OLED_SET_ENTIRE_ON       | 0x00,  # output follows RAM contents
                OLED_SET_NORM_INV        | 0x00,  # not inverted
                OLED_SCROLL_DEACTIVATE   ,
                OLED_SET_DISP            | 0x01): # turn on display
            self.write_cmd(cmd)

    def poweroff(self):
        self.write_cmd(OLED_SET_DISP | 0x00)

    def contrast(self, contrast):
        self.write_cmd(OLED_SET_CONTRAST)
        self.write_cmd(contrast)

    def write_cmd(self, cmd):
        temp    = bytearray(2)
        temp[0] = 0x80 # Co=1, D/!C=0
        temp[1] = cmd
        self.i2c.send(temp, addr=self.addr)

    def write_data(self, buf):
        temp = bytearray(1 + len(buf))
        temp[0] = 0x40 # Co=0, D/!C=1
        i = 1
        while i < len(temp):
            temp[i] = buf[i - 1]
            i += 1
        self.i2c.send(temp, addr=self.addr)

class Ublox6M(object):

    def __init__(self, i2c = None, addr = GPS_DEFAULT_I2C_ADDR, debug = False):
        if i2c is None:
            i2c = pyb.I2C(I2C_DEFAULT_CHANNEL, pyb.I2C.MASTER, baudrate = I2C_DEFAULT_BAUDRATE)
        self.i2c      = i2c
        self.addr     = addr
        self.debug    = debug
        self.has_fix  = False
        self.has_date = False
        self.has_nmea = False
        self.message  = ""

    def test_connect(self):
        return self.i2c.is_ready(self.addr)

    def has_data(self):
        try:
            data = self.i2c.mem_read(2, self.addr, micropython.const(0xFD)) # "at addresses 0xFD and 0xFE, the currently available number of bytes in the message stream can be read"
            cnt = data[1]
            cnt <<= 8
            cnt += data[0]
            return cnt
        except:
            return 0

    def task(self):
        did = False
        data_avail = 256
        #data_avail = self.has_data()
        #if data_avail < 16:
        #    return did
        #if data_avail > 256:
        #    data_avail = 256
        # note: data_avail is observed to be useless
        # data will contain 0xFF which will cause conversion functions to throw exceptions
        data = self.i2c.mem_read(data_avail, self.addr, micropython.const(0xFF))
        fidx = 0
        i = 0
        # find first location of invalid ASCII
        while i < len(data):
            if data[i] >= 0x80:
                fidx = i
                break
            i += 1
        # parse only the correct binary chunk that can be correctly converted
        if fidx > 0:
            self.message += data[0:fidx].decode("utf-8")
        while True:
            # process all the data until there's no start indicator or end indicator
            if "$" not in self.message:
                return did
            # everything before $ is useless
            self.message = self.message[self.message.index('$'):]
            # look for the end indicator
            if "*" not in self.message:
                return did
            # extract one NMEA message
            i = self.message.index('*')
            chunk = self.message[0:i]
            self.message = self.message[i:]
            self.parse_nmea(chunk)

    def parse_nmea(self, chunk):
        if self.debug:
            print("NEMA parse: %s" % chunk)
        parts = chunk.split(',')
        self.has_nmea = True
        # parse the message according to the header
        if parts[0] == "$GPGGA":
            self.parse_time(parts[1])
            self.parse_latitude(parts[2], parts[3])
            self.parse_longitude(parts[4], parts[5])
            self.has_fix = (parts[6] != "0")
            did = True
        elif parts[0] == "$GPGLL":
            self.parse_latitude(parts[1], parts[2])
            self.parse_longitude(parts[3], parts[4])
            if len(parts) > 5:
                self.parse_time(parts[5])
                if parts[6] == "A":
                    self.has_fix = True
            did = True
        elif parts[0] == "$GPRMC":
            if self.has_fix:
                self.parse_time(parts[1])
                self.parse_latitude(parts[3], parts[4])
                self.parse_longitude(parts[5], parts[6])
                self.parse_date_rmc(parts[9])
            did = True
        elif parts[0] == "$GPZDA":
            # this message does not come by default
            if self.has_fix:
                self.parse_time(parts[1])
                self.parse_date_zda(parts[2], parts[3], parts[4])
            did = True
        elif parts[0] == "$GPGSA" or parts[0] == "$GPVTG":
            did = True # these messages come by default but are useless to us

        if self.has_fix == False:
            self.has_date = False

    def parse_time(self, strin):
        if len(strin) < 6:
            return
        self.time_hour   = int(strin[0:2]) % 24
        self.time_minute = int(strin[2:4])
        self.time_second = int(round(float(strin[4:])))

    def parse_date_zda(self, s1, s2, s3):
        if len(s1) <= 0 or len(s2) <= 0 or len(s3) <= 0:
            return
        self.date_day   = int(s1)
        self.date_month = int(s2)
        self.date_year  = int(s3)
        if self.date_year < 2000:
            self.date_year += 2000
        if self.has_fix:
            self.has_date = True

    def parse_date_rmc(self, strin):
        if len(strin) < 6:
            return
        self.date_day   = int(strin[0:2])
        self.date_month = int(strin[2:4])
        self.date_year  = int(strin[4:6])
        if self.date_year < 2000:
            self.date_year += 2000
        if self.has_fix:
            self.has_date = True

    def parse_coord(self, strin, hemi):
        offset = 0
        mul    = 0
        if hemi == "N":
            offset = 2
            mul = 1
        elif hemi == "S":
            offset = 2
            mul = -1
        elif hemi == "E":
            offset = 3
            mul = 1
        elif hemi == "W":
            offset = 3
            mul = -1
        if len(strin) <= offset or offset == 0 or mul == 0:
            return
        degs = float(strin[0:offset])
        mins = float(strin[offset: ])
        return (degs + (mins / 60.0)) * mul

    def parse_latitude(self, strin, hemi):
        x = self.parse_coord(strin, hemi)
        self.latitude = x
        return x

    def parse_longitude(self, strin, hemi):
        x = self.parse_coord(strin, hemi)
        self.longitude = x
        return x

    def get_utc_epoch(self):
        return comutils.utc_to_epoch(self.date_year, self.date_month, self.date_day, self.time_hour, self.time_minute, self.time_second)

class ExtDisp(object):

    def __init__(self, i2c = None, oled = None, gps = None, debug = False):
        if i2c is None:
            i2c = pyb.I2C(I2C_DEFAULT_CHANNEL, pyb.I2C.MASTER, baudrate = I2C_DEFAULT_BAUDRATE)
        self.i2c = i2c

        if oled is None:
            oled = SSD1306_I2C(i2c = i2c)
        self.oled        = oled
        self.oled_ok     = False
        self.frame       = None
        self.framebuffer = None

        if gps is None:
            gps = Ublox6M(i2c = i2c, debug = debug)
        self.gps    = gps
        self.gps_ok = False

        self.ip     = None
        self.error  = None

    def task(self):
        if self.gps_ok == False:
            self.gps_ok = self.gps.test_connect()
        if self.gps_ok == False:
            return False
        try:
            self.gps.task()
            return True
        except Exception as exc:
            self.gps_ok = False
            exclogger.log_exception(exc)
        return False

    def has_gps_fix(self):
        return self.gps.has_fix

    def get_date(self):
        if self.gps.has_fix and self.gps.has_date:
            return self.gps.get_utc_epoch()
        return 0

    def get_coords(self):
        return self.gps.latitude, self.gps.longitude

    def get_latitude(self):
        return self.gps.latitude

    def get_longitude(self):
        return self.gps.longitude

    def set_ip(self, ip):
        self.ip = ip

    def set_error(self, err):
        self.error = err

    def show_ip(self):
        if self.make_framebuff() == False:
            return
        if self.ip is not None:
            if len(self.ip) > 0:
                self.frame.fill_rect(0, 0, self.oled.width, 1 + 8 + 1, 0)
                x = 1
                if len(self.ip) >= 128 // 8:
                    x = 0
                self.frame.text(self.ip, x, 1, 1)

    def show_error(self):
        if self.make_framebuff() == False:
            return
        if self.error is not None:
            if len(self.error) > 0:
                self.frame.fill_rect(0, self.oled.height - 2 - 8, self.oled.width, 10, 0)
                x = 1
                if len(self.error) >= 128 // 8:
                    x = 0
                self.frame.text(self.error, x, self.oled.height - 1 - 8, 1)

    def make_framebuff(self):
        if self.oled_ok == False:
            self.show() # this will force a check of I2C
        if self.oled_ok == False:
            return False # no point in wasting memory and time

        if self.frame is None:
            self.framebuffer = bytearray((self.oled.height // 8) * self.oled.width)
            self.frame = framebuf.FrameBuffer(self.framebuffer, self.oled.width, self.oled.height, framebuf.MONO_VLSB)
        return True

    def prep(self, pole_coords, center_coords, rotation):
        if self.make_framebuff() == False:
            return

        self.frame.fill(0)
        mid_x = int(self.oled.width  // 2)
        mid_y = int(self.oled.height // 2)
        self.frame.hline(0, mid_y, self.oled.width,  1)
        self.frame.vline(mid_x, 0, self.oled.height, 1)
        if pole_coords is not None:
            dx = pole_coords[0] - center_coords[0]
            dy = pole_coords[1] - center_coords[1]
            adx = abs(dx)
            ady = abs(dy)
            # if out of screen
            if adx > mid_x - 5 or ady > mid_y - 5:
                mag = math.sqrt((adx * adx) + (ady * ady))
                ang = math.degrees(math.atan2(dy, dx))
                mag2 = mag - mid_y
                if mag2 < 0:
                    mag2 = 0
                # the size of the spread depends on the distance away from the pole
                spread = (mag2 * 120.0) / (comutils.SENSOR_HEIGHT - mid_y)
                spread /= 2.0
                spread_radius = mid_y - 7
                i = 0
                while i < spread:
                    j = math.radians(ang + i)
                    x = spread_radius * math.cos(j)
                    y = spread_radius * math.sin(j)
                    self.frame.line(mid_x, mid_y, mid_x + int(round(x)), mid_y + int(round(y)), 1)
                    j = math.radians(ang - i)
                    x = spread_radius * math.cos(j)
                    y = spread_radius * math.sin(j)
                    self.frame.line(mid_x, mid_y, mid_x + int(round(x)), mid_y + int(round(y)), 1)
                    i += 0.2 # keep this small to avoid gaps in circle
            else:
                # if in screen, draw the target

                # square box
                #tgtsz = micropython.const(5)
                #self.frame.rect(mid_x + dx - (tgtsz // 2), mid_y + dy - (tgtsz // 2), tgtsz, tgtsz, 1)

                # X shape
                #tgtsz = micropython.const(3)
                #self.frame.line(mid_x + dx - 1, mid_y + dy - 1, mid_x + dx - 1 - tgtsz, mid_y + dy - 1 - tgtsz, 1)
                #self.frame.line(mid_x + dx - 1, mid_y + dy + 1, mid_x + dx - 1 - tgtsz, mid_y + dy + 1 + tgtsz, 1)
                #self.frame.line(mid_x + dx + 1, mid_y + dy - 1, mid_x + dx + 1 + tgtsz, mid_y + dy - 1 - tgtsz, 1)
                #self.frame.line(mid_x + dx + 1, mid_y + dy + 1, mid_x + dx + 1 + tgtsz, mid_y + dy + 1 + tgtsz, 1)

                # iron cross
                tgtsz = micropython.const(3)
                self.frame.line(mid_x + dx - 1, mid_y + dy - 1, mid_x + dx - 1 - tgtsz, mid_y + dy - 1        , 1)
                self.frame.line(mid_x + dx - 1, mid_y + dy - 1, mid_x + dx - 1        , mid_y + dy - 1 - tgtsz, 1)
                self.frame.line(mid_x + dx + 1, mid_y + dy - 1, mid_x + dx + 1 + tgtsz, mid_y + dy - 1        , 1)
                self.frame.line(mid_x + dx + 1, mid_y + dy - 1, mid_x + dx + 1        , mid_y + dy - 1 - tgtsz, 1)
                self.frame.line(mid_x + dx - 1, mid_y + dy + 1, mid_x + dx - 1 - tgtsz, mid_y + dy + 1        , 1)
                self.frame.line(mid_x + dx - 1, mid_y + dy + 1, mid_x + dx - 1        , mid_y + dy + 1 + tgtsz, 1)
                self.frame.line(mid_x + dx + 1, mid_y + dy + 1, mid_x + dx + 1 + tgtsz, mid_y + dy + 1        , 1)
                self.frame.line(mid_x + dx + 1, mid_y + dy + 1, mid_x + dx + 1        , mid_y + dy + 1 + tgtsz, 1)
            if rotation is not None:
                # draw the representation of the ground
                spread = 10
                mag = mid_y - 1
                j = math.radians(rotation + 90 + spread)
                x1 = mag * math.cos(j)
                y1 = mag * math.sin(j)
                j = math.radians(rotation + 90 - spread)
                x2 = mag * math.cos(j)
                y2 = mag * math.sin(j)
                self.frame.line(mid_x + int(round(x1)), mid_y + int(round(y1)), mid_x + int(round(x2)), mid_y + int(round(y2)), 1)
        else:
            # no pole solution, show IP address
            # cover the lens if you want to force the IP to show
            self.show_ip()
        # always show error if available
        self.show_error()

    def show(self):
        if self.oled_ok == False:
            self.oled_ok = self.oled.test_connect()
            try:
                if self.oled_ok:
                    self.oled.init_display()
            except Exception as exc:
                self.oled_ok = False
                exclogger.log_exception(exc)
        if self.oled_ok == False:
            return
        try:
            if self.framebuffer is None:
                return
            self.oled.write_data(self.framebuffer)
        except Exception as exc:
            self.oled_ok = False
            exclogger.log_exception(exc)

def test_gps_parser(disp):
    disp.gps.has_fix = True
    disp.gps.parse_nmea("$GPZDA,172809.456,12,07,2021,00,00")
    print("%s" % (comutils.fmt_time(utime.localtime(disp.get_date()))))
    # 2021/07/12-17:28:09
    disp.gps.parse_nmea("$GPGGA,172814.0,3723.46587704,N,12202.26957864,W,2,6,1.2,18.893,M,-25.669,M,2.0,0031")
    print("%f %f %s" % (disp.get_longitude(), disp.get_latitude(), comutils.fmt_time(utime.localtime(disp.get_date()))))
    # -122.037828 37.391098 2021/07/12-17:28:14
    disp.gps.parse_nmea("$GPGLL,4916.45,N,12311.12,W,225444,A")
    print("%f %f %s" % (disp.get_longitude(), disp.get_latitude(), comutils.fmt_time(utime.localtime(disp.get_date()))))
    # -123.185325 49.274168 2021/07/12-22:54:44
    disp.gps.parse_nmea("$GPRMC,041425.00,A,4916.45,N,12311.12,W,0.068,,070121,,,D")
    print("%f %f %s" % (disp.get_longitude(), disp.get_latitude(), comutils.fmt_time(utime.localtime(disp.get_date()))))
    # -123.185325 49.274168 2021/01/07-04:14:25
    disp.gps.has_fix  = False
    disp.gps.has_date = False

def test_gps(disp):
    now = pyb.millis()
    disp.task()
    if disp.has_gps_fix():
        t = disp.get_date()
        if t == 0:
            timestr = "no time data"
        else:
            timestr = comutils.fmt_time(utime.localtime(t))
        print("GPS[%u]: long= %f , lat= %f , time= %s" % (now, disp.get_longitude(), disp.get_latitude(), timestr))
    elif disp.gps_ok:
        if disp.gps.has_nmea:
            print("GPS[%u] no fix" % (now))
        else:
            print("GPS[%u] no data" % (now))
    else:
        print("GPS[%u] error" % (now))

def test_oled(disp):
    if random.randint(0, 2) == 0:
        pole_coords = None
        rotation = None
    else:
        if random.randint(0, 1) == 0:
            pole_coords = [random.randint(1, comutils.SENSOR_WIDTH - 2), random.randint(1, comutils.SENSOR_HEIGHT - 2)]
        else:
            pole_coords = [random.randint((comutils.SENSOR_WIDTH // 2) - 32, (comutils.SENSOR_WIDTH // 2) + 32), random.randint((comutils.SENSOR_HEIGHT // 2) - 32, (comutils.SENSOR_HEIGHT // 2) + 32)]
        if random.randint(0, 2) == 0:
            rotation = None
        else:
            rotation = random.randint(-360, 360)
    if random.randint(0, 3) == 0:
        disp.set_ip("123.456.789.012")
    if random.randint(0, 3) == 0:
        disp.set_error("ABCD EFGH")
    else:
        disp.set_error(None)
    disp.prep(pole_coords, center_coords, rotation)
    disp.show()
    print("OLED[%u]" % (pyb.millis()), end="")
    if disp.oled_ok == False:
        print(" error")
    else:
        print("")

if __name__ == "__main__":
    import random
    # run the test bench
    disp = ExtDisp(debug = True)
    center_coords = [comutils.SENSOR_WIDTH // 2, comutils.SENSOR_HEIGHT // 2]
    print("Testing ExtDisp")
    test_gps_parser(disp)
    while True:
        test_gps(disp)
        test_oled(disp)
        pyb.delay(1000)
