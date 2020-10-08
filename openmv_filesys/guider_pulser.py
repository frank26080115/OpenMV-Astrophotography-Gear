import micropython
micropython.opt_level(2)

import pyb

addr = micropython.const(0x41)
bm_shutter   = micropython.const(0x10)
bm_ra_east   = micropython.const(0x08)
bm_ra_west   = micropython.const(0x01)
bm_dec_north = micropython.const(0x04)
bm_dec_south = micropython.const(0x02)
bm_led_red   = micropython.const(0x80)
bm_led_green = micropython.const(0x20)
bm_led_blue  = micropython.const(0x40)

class GuiderPulser(object):

    def __init__(self):
        self.i2c = pyb.I2C(2, I2C.MASTER)
        self.cur_data = 0xFF
        self.shutter_flag = False
        self.grace_time = 0
        self.panic_state = 0
        self.panic_time = 0

    def init_hw(self):
        self.i2c.send(bytearray([0x03, 0xFF]), addr)
        self.i2c.send(bytearray([0x01, 0x00]), addr)

    def pulse_move(self, ra, dec):
        self.pulse_time = pyb.millis()
        self.ra_end  = self.pulse_time + abs(ra)
        self.dec_end = self.pulse_time + abs(dec)
        data = self.cur_data
        add_grace = False
        if (data & (bm_ra_east | bm_ra_west | bm_dec_north | bm_dec_south)) != 0x00:
            add_grace = True
        data &= 0xFF ^ (bm_ra_east | bm_ra_west | bm_dec_north | bm_dec_south)
        if ra > 0:
            data |= bm_ra_east
        elif ra < 0:
            data |= bm_ra_west
        if dec > 0:
            data |= bm_dec_north
        elif dec < 0:
            data |= bm_dec_south
        if (data & (bm_ra_east | bm_ra_west | bm_dec_north | bm_dec_south)) != 0x00:
            add_grace = True
        if add_grace:
            data |= bm_led_red
            self.move_end = max(self.ra_end, self.dec_end) + self.grace_time
        else:
            data |= bm_led_green
        if data != self.cur_data:
            self.i2c.send(bytearray([0x03, 0xFF ^ data]), addr)
            self.cur_data = data

    def panic(self, state = 1)
        self.panic_state = state

    def task(self):
        data = self.cur_data
        t = pyb.millis()

        if self.shutter_flag and t > self.shutter_time:
            data &= 0xFF ^ (bm_shutter | bm_led_blue)
            self.shutter_flag = False

        if self.panic_state != 0
            if t > self.panic_time:
                blink = False
                if self.panic_state % 2 == 1:
                    self.panic_state = 2
                    data |= bm_led_red
                elif self.panic_state % 2 == 0:
                    self.panic_state = 1
                    data &= 0xFF ^ bm_led_red
                self.panic_time += 300 # setup next blink
        else:
            if t > self.ra_end:
                data &= 0xFF ^ (bm_ra_east | bm_ra_west)
            if t > self.ra_end:
                data &= 0xFF ^ (bm_dec_north | bm_dec_south)
            if data & (bm_ra_east | bm_ra_west | bm_dec_north | bm_dec_south) == 0x00:
                data &= 0xFF ^ bm_led_red

        if data != self.cur_data:
            self.i2c.send(bytearray([0x03, 0xFF ^ data]), addr)
            self.cur_data = data

    def shutter(self, span):
        t = pyb.millis()
        self.shutter_flag = True
        data = self.cur_data
        data |= bm_shutter
        data |= bm_led_blue
        self.shutter_end = t + (span * 1000)
        if data != self.cur_data:
            self.i2c.send(bytearray([0x03, 0xFF ^ data]), addr)
            self.cur_data = data

    def is_moving(self):
        if pyb.millis() < self.move_end:
            return True

    def is_shutter(self):
        return self.shutter_flag

    def is_panic(self):
        return self.panic_state != 0

    def shutter_halt(self):
        self.shutter_flag = False
        data = self.cur_data
        data &= 0xFF ^ bm_shutter
        data &= 0xFF ^ bm_led_blue
        if data != self.cur_data:
            self.i2c.send(bytearray([0x03, 0xFF ^ data]), addr)
            self.cur_data = data

