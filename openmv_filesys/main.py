import micropython
micropython.opt_level(0)
import gc
import pyb

try:
    import exclogger, guidepulser
except:
    red_led = pyb.LED(1)
    while True:
        red_led.on()
        print("ERROR: wrong firmware")
        pyb.delay(200)
        red_led.off()
        pyb.delay(200)

from pyb import I2C

if __name__ == "__main__":
    i2c = I2C(2, I2C.MASTER)
    devs = i2c.scan()
    is_guider = 0x38 in devs
    mem_start = gc.mem_free()
    if is_guider:
        #print("starting autoguider (mem free: %u)" % mem_start)
        import autoguider
        #print("imported module, mem free: %u" % gc.mem_free())
        device = autoguider.AutoGuider(debug = False)
    else:
        #print("starting polarscope (mem free: %u)" % mem_start)
        import polarscope
        #print("imported module, mem free: %u" % gc.mem_free())
        device = polarscope.PolarScope(debug = False)
    mem_loaded = gc.mem_free()
    #print("initialized, mem free: %u , consumed: %u" % (mem_loaded, mem_start - mem_loaded))
    while True:
        try:
            device.task()
        except KeyboardInterrupt:
            raise
        except MemoryError as exc:
            exclogger.log_exception(exc, to_file = False)
            micropython.mem_info(True)
        except Exception as exc:
            exclogger.log_exception(exc)
