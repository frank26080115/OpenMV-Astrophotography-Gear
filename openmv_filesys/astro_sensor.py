import sensor, image, pyb, time

class AstroCam(object):

    def __init__(self, pixfmt = sensor.GRAYSCALE):
        self.pixfmt = pixfmt
        self.has_init = False
        self.gain = -2
        self.shutter = 0
        self.framesize = sensor.QQCIF
        self.flip = False
        self.fileseq = 1
        self.img = None

    def init(self, gain_db = 0, shutter_us = 500000, framesize = sensor.WQXGA2, force_reset = True, flip = False):
        if force_reset or self.gain != gain_db or self.shutter != shutter_us or self.framesize != framesize or self.flip != flip or self.has_init == False:
            sensor.reset()
            sensor.set_pixformat(self.pixfmt)
            sensor.set_framesize(framesize)
            if flip: # upside down camera
                sensor.set_vflip(True)
                sensor.set_hmirror(True)
            self.flip = flip
            self.framesize = framesize
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
            sensor.set_auto_gain(False, gain_db)
            self.gain = gain_db
            sensor.skip_frames(time = 2000)
        self.has_init = True

    def snapshot(self, filename = None):
        if self.has_init == False:
            self.init()
        self.img = sensor.snapshot()
        if filename == "auto":
            filename = "%u_%u_%u.jpg" % (self.fileseq, round(self.gain), self.shutter)
        self.fileseq += 1
        if filename is not None:
            self.img.save(filename, quality = 100)
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
        self.init(gain_db = 100, shutter_us = 1400000, framesize = sensor.WQXGA2, force_reset = True, flip = True)
        clock = time.clock()
        while True:
            clock.tick()
            self.snapshot()
            print("%u - %0.2f" % (self.fileseq, clock.fps()))

if __name__ == "__main__":
    cam = AstroCam()
    cam.test_view()
    #cam.test_gather()
