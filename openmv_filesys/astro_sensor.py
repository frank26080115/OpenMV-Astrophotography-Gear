import micropython
micropython.opt_level(2)

import sensor, image, pyb, time, gc
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
            self.shutter = shutter_us
            self.gain = gain_db
            self.snap_started = False
            return
        if force_reset or self.gain != gain_db or self.shutter != shutter_us or self.framesize != framesize or self.flip != flip:
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
                    if shutter_us > 1000000:
                        sensor.__write_reg(0x3037, 0x18)   # slow down PLL
                        if shutter_us > 1500000:
                            sensor.__write_reg(0x3036, 80) # slow down PLL
                            # warning: doesn't work well, might crash
                    else:
                        sensor.__write_reg(0x3037, 0x08)   # slow down PLL
                    pyb.delay(200)
                sensor.set_auto_exposure(False, shutter_us)
            self.shutter = shutter_us
            if gain_db < 0:
                sensor.set_auto_gain(True)
            else:
                sensor.set_auto_gain(False, gain_db)
            self.gain = gain_db
            try:
                sensor.skip_frames(time = 2000)
                self.width = sensor.width()
                self.height = sensor.height()
            except RuntimeError as exc:
                exclogger.log_exception(exc)
                self.gain = -2
                self.shutter = -2
            self.snap_started = False

    def snapshot(self, filename = None):
        if self.simulate:
            pyb.delay(self.shutter // 1000)
            self.snap_started = False
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

    def snapshot_check(self):
        if self.snap_started == False:
            return False
        if self.simulate:
            dt = pyb.elapsed_millis(self.sim_t)
            if dt > (self.shutter // 1000):
                return True
            else:
                return False
        return sensor.snapshot_check()

    def snapshot_finish(self):
        if self.snap_started == False:
            return None
        if self.snap_started == False:
            return False
        if self.simulate:
            while self.snapshot_check() == False:
                gc.collect()
            self.snap_started = False
            return self.img
        try:
            self.img = sensor.snapshot_finish()
        except RuntimeError as exc:
            exclogger.log_exception(exc)
            self.img = None
        self.snap_started = False
        return self.img

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
        self.init(gain_db = -1, shutter_us = -1, framesize = sensor.WQXGA2, force_reset = True, flip = True)
        clock = time.clock()
        while True:
            clock.tick()
            self.snapshot()
            print("%u - %0.2f" % (self.fileseq, clock.fps()))

if __name__ == "__main__":
    cam = AstroCam()
    cam.test_view()
    #cam.test_gather()
