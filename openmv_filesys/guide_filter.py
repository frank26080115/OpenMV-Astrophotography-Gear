import micropython
micropython.opt_level(2)

class GuideFilter(object):

    def __init__(self, axis):
        self.axis = axis.lower()
        self.term_i    = 0
        self.sum_i     = 0
        self.limit_i   = 0
        self.last_val  = None
        self.term_d    = 0
        self.lpf_val   = None
        self.lpf_k     = 0
        self.lpf_mix   = 0
        self.paused    = True
        pass

    def pause(self, x):
        self.paused = x
        if x:
            self.neutralize()

    def load_settings(self, settings):
        n = "advfilt_" + self.axis + "_"
        self.term_i   = settings[n + "term_i" ]
        self.limit_i  = settings[n + "limit_i"]
        self.term_d   = settings[n + "term_d" ]
        self.lpf_k    = settings[n + "lpf_k"  ]
        self.lpf_mix  = settings[n + "lpf_mix"]

    def neutralize(self):
        self.sum_i    = 0
        self.last_val = None
        self.lpf_val  = None

    def filter(self, x):
        if self.paused:
            return x
        total = x
        self.sum_i += x
        self.limit_i = abs(self.limit_i)
        if self.sum_i > self.limit_i:
            self.sum_i = self.limit_i
        elif self.sum_i < -self.limit_i
            self.sum_i = -self.limit_i
        i = self.sum_i * self.term_i
        i /= 100
        if self.last_val is None:
            self.last_val = x
        d = x - self.last_val
        d *= self.term_d
        d /= 100
        self.last_val = x
        total = i + d
        if self.lpf_val is None:
            self.lpf_val = x
        lpf_old = self.lpf_val * (100 - self.lpf_k)
        lpf_new = x * self.lpf_k
        lpf_sum = lpf_old + lpf_new
        lpf_sum /= 100
        mix_1 = total * (100 - self.lpf_mix)
        mix_2 = lpf_sum * self.lpf_mix
        final_mix = mix_1 + mix_2
        final_mix /= 100
        return final_mix