import micropython
micropython.opt_level(2)

import guider_pulser
from guider_pulser import GuiderPulser

import pyb

INTVMSTATE_IDLE   = micropython.const(0)
INTVMSTATE_TEST   = micropython.const(1)
INTVMSTATE_CONT   = micropython.const(2)
INTVMSTATE_DELAY  = micropython.const(3)

class Intervalometer(object):

    def __init__(self, pulser):
        self.pulser = pulser
        self.mode = INTVMSTATE_IDLE
        self.cancel = False

    def shoot_test(self, span):
        self.pulser.shutter(span)
        self.mode = INTVMSTATE_TEST

    def shoot_cont(self, span, dly):
        self.pulser.shutter(span)
        self.shutter_length = span
        self.mode = INTVMSTATE_CONT
        self.delay_length = dly

    def cancel_now(self):
        self.pulser.shutter_halt()
        self.mode = INTVMSTATE_IDLE
        self.cancel = False

    def cancel_next(self):
        if self.mode != INTVMSTATE_IDLE:
            self.cancel = True

    def task(self, invoke_task = False):
        if invoke_task:
            self.pulser.task()
        if self.mode == INTVMSTATE_TEST:
            if self.pulser.is_shutter() == False:
                self.mode = INTVMSTATE_IDLE
                self.cancel = False
        if self.mode == INTVMSTATE_CONT
            if self.pulser.is_shutter() == False:
                if self.cancel:
                    self.mode = INTVMSTATE_IDLE
                    self.cancel = False
                else:
                    self.mode = INTVMSTATE_DELAY
                    self.delay_start = pyb.millis()
        if self.mode == INTVMSTATE_DELAY:
            if self.cancel:
                self.mode = INTVMSTATE_IDLE
                self.cancel = False
            elif pyb.millis() >= (self.delay_start + self.delay_length):
                self.shoot_cont(self.shutter_length, self.delay_length)

