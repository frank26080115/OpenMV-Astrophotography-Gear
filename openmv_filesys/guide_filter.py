import micropython
micropython.opt_level(2)

class GuideFilter(object):

    def __init__(self, axis):
        self.axis = axis.lower()
        self.term_i    = 0
        self.sum_i     = 0
        self.limit_i   = 0
        self.decay_i   = 0
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
        self.decay_i  = settings[n + "decay_i"]
        self.term_d   = settings[n + "term_d" ]
        self.lpf_k    = settings[n + "lpf_k"  ]
        self.lpf_mix  = settings[n + "lpf_mix"]
        self.limit_i  = abs(self.limit_i)
        self.decay_i  = abs(self.decay_i)
        self.lpf_k    = abs(self.lpf_k)
        self.lpf_mix  = abs(self.lpf_mix)
        if self.lpf_k > 100:
            self.lpf_k = 100
        if self.lpf_mix > 100:
            self.lpf_mix = 100

    def fill_settings(self, settings):
        n = "advfilt_" + self.axis + "_"
        settings.update({(n + "term_i" ): self.term_i })
        settings.update({(n + "limit_i"): self.limit_i})
        settings.update({(n + "decay_i"): self.decay_i})
        settings.update({(n + "term_d" ): self.term_d })
        settings.update({(n + "lpf_k"  ): self.lpf_k  })
        settings.update({(n + "lpf_mix"): self.lpf_mix})

    def neutralize(self):
        self.sum_i    = 0
        self.last_val = None
        self.lpf_val  = None

    def filter(self, x):
        if self.paused:
            return x
        total = x
        self.sum_i += x
        if self.sum_i > self.limit_i:
            self.sum_i = self.limit_i
        elif self.sum_i < -self.limit_i:
            self.sum_i = -self.limit_i
        i = self.sum_i * self.term_i
        i /= 100
        if self.sum_i > self.decay_i or self.sum_i < -self.decay_i:
            self.sum_i -= self.decay_i
        else:
            self.sum_i = 0
        if self.last_val is None:
            self.last_val = x
        d = x - self.last_val
        d *= self.term_d
        d /= 100
        self.last_val = x
        total = i + d
        if self.lpf_val is None:
            self.lpf_val = x
        if self.lpf_k >= 100:
            lpf_sum = x
        else:
            lpf_old = self.lpf_val * (100 - self.lpf_k)
            lpf_new = x * self.lpf_k
            lpf_sum = lpf_old + lpf_new
            lpf_sum /= 100
        self.lpf_val = x
        if self.lpf_k > 0:
            mix_1 = total * (100 - self.lpf_mix)
            mix_2 = lpf_sum * self.lpf_mix
            final_mix = mix_1 + mix_2
            final_mix /= 100
        else:
            final_mix = total
        return final_mix
