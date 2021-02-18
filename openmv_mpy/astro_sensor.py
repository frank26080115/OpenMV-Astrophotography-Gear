import micropython
micropython.opt_level(2)

import sensor
import image
import pyb
import time
import gc
import exclogger

class AstroCam(object):

    def __init__(self, pixfmt = sensor.GRAYSCALE, simulate = None):
        self.pixfmt = pixfmt
        self.gain = -2
        self.shutter = -2
        self.framesize = sensor.QQCIF
        self.flip = False
        self.fileseq = 1
        self.img = None
        self.has_error = False
        self.wait_init = 0
        self.snap_started = False

        self.simulate = False
        if simulate is not None:
            gc.collect()
            #print("about to load simulation file, checking memory")
            #micropython.mem_info(False)
            print("loading simulation file ...", end="")
            self.img = image.Image(simulate, copy_to_fb = True)
            print(" done, alloc and converting ...", end="")
            self.img = sensor.alloc_extra_fb(self.img.width(), self.img.height(), sensor.RGB565).replace(self.img).to_grayscale()
            print(" done!")
            self.simulate = True
            self.snap_started = False
            self.width = self.img.width()
            self.height = self.img.height()

    def init(self, gain_db = 0, shutter_us = 500000, framesize = sensor.WQXGA2, force_reset = True, flip = False):
        if self.simulate:
            if force_reset or self.has_error or self.gain != gain_db or self.shutter != shutter_us or self.framesize != framesize or self.flip != flip:
                self.wait_init = 2
            self.shutter = shutter_us
            self.gain = gain_db
            self.framesize = framesize
            self.flip = flip
            self.has_error = False
            self.snap_started = False
            return
        if force_reset or self.has_error or self.gain != gain_db or self.shutter != shutter_us or self.framesize != framesize or self.flip != flip:
            sensor.reset()
            sensor.set_pixformat(self.pixfmt)
            sensor.set_framesize(framesize)
            if flip: # upside down camera
                sensor.set_vflip(True)
                sensor.set_hmirror(True)
            self.flip = flip
            self.framesize = framesize
            if shutter_us < 0:
                sensor.set_auto_exposure(True)
            else:
                if shutter_us > 500000:
                    sensor.__write_reg(0x3037, 0x08)   # slow down PLL
                    if shutter_us > 1000000:
                        pyb.delay(100)
                        sensor.__write_reg(0x3037, 0x18)   # slow down PLL
                        if shutter_us > 2750000:
                            pyb.delay(100)
                            sensor.__write_reg(0x3036, 40) # slow down PLL
                        # warning: doesn't work well, might crash
                        elif shutter_us > 1500000:
                            pyb.delay(100)
                            sensor.__write_reg(0x3036, 80) # slow down PLL
                            # warning: doesn't work well, might crash
                    pyb.delay(200)
                sensor.set_auto_exposure(False, shutter_us)
            self.shutter = shutter_us
            if gain_db < 0:
                sensor.set_auto_gain(True)
            else:
                sensor.set_auto_gain(False, gain_db)
            self.gain = gain_db
            self.wait_init = 2
            self.width = sensor.width()
            self.height = sensor.height()

    def check_init(self):
        if self.wait_init > 0:
            if self.snap_started == False:
                self.snapshot_start()
            elif self.snapshot_check():
                self.snapshot_finish()
                self.wait_init -= 1
            return False
        return True

    def snapshot(self, filename = None):
        if self.simulate:
            pyb.delay(self.get_timespan())
            self.snap_started = False
            self.img.set_timestamp(pyb.millis())
            return self.img
        try:
            if self.snap_started == True:
                self.img = self.snapshot_finish()
            else:
                self.img = sensor.snapshot()
            if filename == "auto":
                filename = "%u_%u_%u.jpg" % (self.fileseq, round(self.gain), self.shutter)
            self.fileseq += 1
            if filename is not None:
                self.img.save(filename, quality = 100)
            return self.img
        except RuntimeError as exc:
            exclogger.log_exception(exc)
            self.has_error = True
            return None

    def snapshot_start(self):
        if self.snap_started == True:
            return
        if self.simulate:
            self.sim_t = pyb.millis()
            self.snap_started = True
            return
        try:
            sensor.snapshot_start()
            self.snap_started = True
        except RuntimeError as exc:
            exclogger.log_exception(exc)
            self.has_error = True

    def snapshot_check(self):
        if self.snap_started == False:
            return False
        if self.simulate:
            dt = pyb.elapsed_millis(self.sim_t)
            if dt > self.get_timespan():
                return True
            else:
                return False
        return sensor.snapshot_check()

    def snapshot_finish(self):
        if self.snap_started == False:
            return None
        if self.simulate:
            while self.snapshot_check() == False:
                gc.collect()
            self.snap_started = False
            self.img.set_timestamp(pyb.millis())
            return self.img
        try:
            self.img = sensor.snapshot_finish()
            self.has_error = False
        except RuntimeError as exc:
            exclogger.log_exception(exc)
            self.img = None
            self.has_error = True
        self.snap_started = False
        return self.img

    def get_timespan(self):
        if self.shutter > 500000:
            x = self.shutter * 4 / 3000
        else:
            x = self.shutter / 1000
        return int(round(x))

    def test_gather(self, shots = 2, gain_start = 0, gain_step = 16, gain_limit = 128, shutter_start = 500000, shutter_step = 250000, shutter_limit = 1500000):
        shot = 0
        rnd  = pyb.rng() % 1000
        gain = gain_start
        shutter = shutter_start
        while True:
            self.init(gain_db = gain, shutter_us = shutter, framesize = sensor.WQXGA2, force_reset = False, flip = True)
            fn = "%u_%u_%u_%u_%u.jpg" % (rnd, self.fileseq, shot, round(self.gain), self.shutter)
            print(fn + " ... ", end="")
            self.snapshot(filename = fn)
            print("done")
            shot += 1
            if shot >= shots:
                shot = 0
                gain += gain_step
                if gain > gain_limit:
                    gain = gain_start
                    shutter += shutter_step
                    if shutter > shutter_limit:
                        return

    def test_view(self):
        self.init(gain_db = 50, shutter_us = 1000000, framesize = sensor.WQXGA2, force_reset = True, flip = False)
        clock = time.clock()
        told = pyb.millis()
        while True:
            clock.tick()
            img = self.snapshot()
            tnew = img.timestamp()
            tspan = tnew - told
            print("%u - %0.2f - %u" % (self.fileseq, clock.fps(), tspan))
            told = tnew

    def test_time(self):
        setting = 100
        while setting <= 5000:
            self.init(gain_db = 30, shutter_us = setting * 1000, framesize = sensor.WQXGA2, force_reset = True, flip = False)
            tsum = 0
            i = 0
            j = 0
            told = pyb.millis()
            while i < 10:
                img = self.snapshot()
                tnow = img.timestamp()
                tspan = tnow - told
                told = tnow
                i += 1
                if i > 3:
                    tsum += tspan
                    j += 1
            avg = int(round(tsum / j))
            x = (setting * 4) / 3
            print("%u : %u ? %0.1f" % (setting, avg, x))
            if setting < 500:
                setting += 100
            elif setting < 2000:
                setting += 250
            else:
                setting += 500

if __name__ == "__main__":
    cam = AstroCam()
    #cam.test_time()
    cam.test_view()
    #cam.test_gather()
