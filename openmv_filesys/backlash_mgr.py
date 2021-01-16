class BacklashManager(object):

    def __init__(self):
        self.hysteresis = 0
        self.max_limit  = 0
        self.value      = 0
        self.state      = 0
        self.reduction  = 0
        self.hard_lock  = False

    def neutralize(self):
        self.value = 0
        self.state = 0

    def filter(self, x):
        x = self._filter(x)
        return int(round(x))

    def _filter(self, x):
        if self.max_limit < 0:
            self.max_limit *= -1
        if self.hysteresis < 0:
            self.hysteresis *= -1
        max_limit = self.max_limit
        if max_limit is None:
            max_limit = 0
        if max_limit == 0:
            max_limit = self.hysteresis
        if self.hysteresis == 0 and self.max_limit == 0:
            self.state = 0
            self.value = 0
            return x
        #elif self.hysteresis == 0:
        #    if (self.value > 0 or self.state >= 0) and x > 0:
        #        self._value_add(x, max_limit)
        #        self.state = 1
        #        return x
        #    elif (self.value < 0 or self.state <= 0) and x < 0:
        #        self._value_add(x, max_limit)
        #        self.state = -1
        #        return x
        #    else:
        #        self._value_add(x, max_limit)
        #        if self.value > 0:
        #            self.state = 1
        #        elif self.value < 0:
        #            self.state = -1
        #        return x * self.reduction
        #elif self.hysteresis != 0:
        else:
            x = int(round(x))
            if self.state == 0:
                self._value_add(x, max_limit)
                if self.hysteresis != 0:
                    if self.value >= self.hysteresis:
                        self.state = 1
                    elif self.value <= -self.hysteresis:
                        self.state = -1
                else:
                    if self.value > self.hysteresis:
                        self.state = 1
                    elif self.value < -self.hysteresis:
                        self.state = -1
                return x
            elif self.state > 0:
                if self.hard_lock == False or x > 0:
                    self._value_add(x, max_limit)
                if x > 0:
                    return x
                elif x < 0 and self.value <= -self.hysteresis:
                    self.state = -1
                    return x
                else:
                    return x * self.reduction
            elif self.state < 0:
                if self.hard_lock == False or x < 0:
                    self._value_add(x, max_limit)
                if x < 0:
                    return x
                elif x > 0 and self.value >= self.hysteresis:
                    self.state = 1
                    return x
                else:
                    return x * self.reduction

    def _value_add(self, x, max_limit):
        self.value += x
        self._limit_value(max_limit)

    def _limit_value(self, max_limit):
        if self.value >=  max_limit:
            self.value =  max_limit
        if self.value <= -max_limit:
            self.value = -max_limit

def report_state(mgr):
    return "%u %u %d %d %s" % (mgr.hysteresis, mgr.max_limit, mgr.value, mgr.state, "locked" if mgr.hard_lock else " ")

if __name__ == "__main__":
    import pyb
    print("Test Backlash Manager")
    mgr = BacklashManager()
    #mgr.hard_lock = True

    print("MGR: %s" % report_state(mgr))
    i = 0
    while i < 10:
        x = (pyb.rng() % 20) - 10
        y = mgr.filter(x)
        print("[%u] %d => %d : %s" % (i, x, y, report_state(mgr)))
        i += 1

    mgr.hysteresis = 0
    mgr.max_limit  = 100
    mgr.neutralize()
    print("MGR: %s" % report_state(mgr))
    i = 0
    while i < 50:
        x = (pyb.rng() % 50) - 25
        y = mgr.filter(x)
        print("[%u] %d => %d : %s" % (i, x, y, report_state(mgr)))
        i += 1

    mgr.hysteresis = 100
    mgr.max_limit  = 0
    mgr.neutralize()
    print("MGR: %s" % report_state(mgr))
    i = 0
    while i < 50:
        x = (pyb.rng() % 400) - 200
        y = mgr.filter(x)
        print("[%u] %d => %d : %s" % (i, x, y, report_state(mgr)))
        i += 1

    mgr.hysteresis = 100
    mgr.max_limit  = 200
    mgr.neutralize()
    print("MGR: %s" % report_state(mgr))
    i = 0
    while i < 50:
        x = (pyb.rng() % 400) - 200
        y = mgr.filter(x)
        print("[%u] %d => %d : %s" % (i, x, y, report_state(mgr)))
        i += 1
