import micropython
micropython.opt_level(2)

import comutils
import blobstar, astro_sensor, time_location, captive_portal, pole_finder, star_finder, pole_movement
import exclogger
import pyb, uos, uio, gc, sys
import time, math, ujson, ubinascii
import network
import sensor, image

red_led   = pyb.LED(1)
green_led = pyb.LED(2)
blue_led  = pyb.LED(3)
ir_leds   = pyb.LED(4)

class AutoguiderScope(object):

    def __init__(self, debug = False, simulate_file = None, use_leds = True):
        exclogger.init()
        self.simulate = False
        self.cam = astro_sensor.AstroCam(simulate = simulate_file)
        self.cam.init(gain_db = -1, shutter_us = 250000)
        self.time_mgr = time_location.TimeLocationManager()
        self.has_time = False

        self.debug = debug
        self.use_leds = use_leds
        self.sleeping = False
        self.cam_err = False

        t = pyb.millis()
        self.diag_cnt    = 0
        self.frm_cnt     = 0
        self.tick_all    = t
        self.dur_all     = -1
        self.snap_millis = 0

        self.settings = {}
        self.settings.update({"time":        self.time_mgr.get_sec()})
        self.settings.update({"center_x":    self.cam.width / 2})
        self.settings.update({"center_y":    self.cam.height / 2})
        self.settings.update({"gain":        self.cam.gain})
        self.settings.update({"shutter":     self.cam.shutter})
        self.settings.update({"thresh":      (0)})
        self.settings.update({"max_stars":   0})
        self.settings.update({"force_solve": False})
        self.load_settings()
        self.time_mgr.readiness = False
        exclogger.log_exception("Time Guessed (%u)" % pyb.millis(), time_str=comutils.fmt_time(self.time_mgr.get_time()))

        self.portal = captive_portal.CaptivePortal(debug = self.debug)

        self.img = None
        self.img_compressed = None
        self.extra_fb = None
        self.expo_code = 0
        self.histogram = None
        self.img_stats = None
        self.stars = []
        self.hot_pixels = []
        self.max_stars = 0
        self.packjpeg = False
        self.zoom = 1
        self.prevzoom = 1
        self.mem_errs = 0
        self.accel_sec = 0
        if self.portal is not None:
            self.register_http_handlers()
        while self.cam.check_init() == False:
            self.cam.check_init()
        self.cam.snapshot_start()
        self.snap_millis = pyb.millis()

        self.stream_sock = None
        self.stream_sock_err = 0

    def try_parse_setting(self, v):
        try: # micropython doesn't have "is_numeric"
            v = v.lstrip().rstrip()
            if v.lower() == "false":
                v = False
            elif v.lower() == "true":
                v = True
            elif "." in v:
                v = float(v)
            else:
                v = int(v)
        except Exception as exc:
            exclogger.log_exception(exc, to_print = False, to_file = False)
        return v

    def save_settings(self, filename = "config.json"):
        if self.debug:
            print("save_settings")
        with open(filename, mode="wb") as f:
            ujson.dump(self.settings, f)

    def load_settings(self, filename = "config.json"):
        obj = None
        try:
            with open(filename, mode="rb") as f:
                obj = ujson.load(f)
            for i in obj.keys():
                v = obj[i]
                if i in self.settings:
                    self.settings[i] = self.try_parse_setting(v)
                else:
                    print("extra JSON setting \"%s\": \"%s\"" % (i, str(v)))
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            exclogger.log_exception(exc)
        self.apply_settings()

    def apply_settings(self):
        self.time_mgr.set_utc_time_epoch(self.settings["time"])
        if self.debug:
            print("apply_settings")

    def reply_ok(self, stream, sts = True, err = None):
        x = {}
        x.update({"time": self.time_mgr.get_sec()})
        x.update({"status": sts})
        x.update({"err": err})
        json_str = ujson.dumps(x)
        stream.write(captive_portal.default_reply_header(content_type = "application/json", content_length = len(json_str)) + json_str)
        stream.close()

    def handle_getstate(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_getstate")
        self.handle_query(client_stream, req, reply = False, save = False)
        state = {}
        state.update({"time": self.time_mgr.get_sec()})
        if self.img is not None and self.cam_err == False:
            state.update({"expo_code": self.expo_code})
        elif self.img is None:
            state.update({"expo_code": star_finder.EXPO_NO_IMG})
        elif self.cam_err:
            state.update({"expo_code": star_finder.EXPO_CAMERA_ERR})
        if self.stars is not None:
            state.update({"stars": blobstar.to_jsonobj(self.stars)})

        state.update({"max_stars": self.max_stars})

        # diagnostic info
        state.update({"frm_cnt":         self.frm_cnt})
        if self.debug:
            state.update({"diag_cnt":        self.diag_cnt})
            state.update({"diag_dur_all":    self.dur_all})
            state.update({"diag_mem_alloc":  gc.mem_alloc()})
            state.update({"diag_mem_free":   gc.mem_free()})
        if self.img_stats is not None:
            state.update({"img_mean":  self.img_stats.mean()})
            state.update({"img_stdev": self.img_stats.stdev()})
            state.update({"img_max":   self.img_stats.max()})
            state.update({"img_min":   self.img_stats.min()})

        json_str = ujson.dumps(state)
        client_stream.write(captive_portal.default_reply_header(content_type = "application/json", content_length = len(json_str)) + json_str)
        client_stream.close()
        if self.use_leds:
            red_led.on()

    def handle_getsettings(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_getsettings")
        self.kill_streamer()
        json_str = ujson.dumps(self.settings)
        client_stream.write(captive_portal.default_reply_header(content_type = "application/json", content_length = len(json_str)) + json_str)
        client_stream.close()

    def handle_updatesetting(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_updatesetting", end="")
        self.handle_query(client_stream, req, reply = True)

    def handle_query(self, client_stream, req, reply = True, save = True):
        need_save = False
        try:
            request_page, request_urlparams = captive_portal.split_get_request(req)
            if self.debug and reply:
                print(" keys %u" % len(request_urlparams))
            for i in request_urlparams.keys():
                v = request_urlparams[i]
                v = self.try_parse_setting(v)
                if i in self.settings:
                    need_save = True
                    self.settings[i] = v
                    if self.debug and (reply or save):
                        print("setting \"%s\" value \"%s\"" % (i, str(v)))
                    if i == "time":
                        if self.has_time == False:
                            self.time_mgr.set_utc_time_epoch(v)
                            exclogger.log_exception("Time Obtained (%u)" % pyb.millis(), time_str=time_location.fmt_time(self.time_mgr.get_time()))
                        self.has_time = True
                    elif i == "max_stars":
                        self.max_stars = v
                elif i == "hotpixels":
                    self.hot_pixels = star_finder.decode_hotpixels(v)
                elif i == "use_debug":
                    self.debug = v
                elif i == "use_leds":
                    self.use_leds = v
                    if v == False:
                        red_led.off()
                        green_led.off()
                        blue_led.off()
                elif i == "sleep":
                    self.sleeping = v
                    if v == False:
                        self.use_leds = False
                        red_led.off()
                        green_led.off()
                        blue_led.off()
                elif i == "save":
                    save = (v == True)
                    need_save = True
                else:
                    print("unknown setting \"%s\": \"%s\"" % (i, str(v)))
            if need_save and save:
                self.save_settings()
            if reply:
                self.reply_ok(client_stream)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            s = exclogger.log_exception(exc)
            if reply:
                self.reply_ok(client_stream, sts=False, err=s)

    def handle_getimg(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_getimg", end="")
        try:
            if self.img_compressed is None:
                client_stream.write(captive_portal.default_reply_header(content_type = "image/jpeg", content_length = 0))
                client_stream.close()
                if self.debug:
                    print(" no image")
                return
            sz = self.img_compressed.size()
            client_stream.write(captive_portal.default_reply_header(content_type = "image/jpeg", content_length = sz))
            sent = client_stream.write(self.img_compressed)
            client_stream.close()
            if self.debug:
                print(" sent %u" % sent)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            s = exclogger.log_exception(exc)
            self.reply_ok(client_stream, sts=False, err=s)

    def handle_memory(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_memory")
        micropython.mem_info(True)
        self.reply_ok(client_stream)

    def handle_sleep(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_sleep")
        self.sleeping = True
        self.use_leds = False
        red_led.off()
        green_led.off()
        blue_led.off()
        self.reply_ok(client_stream)

    def handle_stream(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_stream")
        self.kill_streamer()
        self.handle_query(client_stream, req, reply = False, save = False)
        self.stream_sock = client_stream
        self.stream_sock.settimeout(5.0)
        self.stream_sock.send("HTTP/1.1 200 OK\r\n" \
                    "Server: OpenMV\r\n" \
                    "Content-Type: multipart/x-mixed-replace;boundary=openmv\r\n" \
                    "Cache-Control: no-cache\r\n" \
                    "Pragma: no-cache\r\n\r\n")
        self.stream_sock_err = 0

    def handle_index(self, client_stream, req, headers, content):
        self.sleeping = False
        self.kill_streamer()
        captive_portal.gen_page(client_stream, "autoguider.htm", add_files = ["web/jquery-ui-1.12.1-darkness.css", "web/jquery-3.5.1.min.js", "web/jquery-ui-1.12.1.min.js"], debug = self.debug)
        return True

    def update_stream(self):
        if self.stream_sock is None:
            return
        try:
            self.portal.update_stream(self.stream_sock, self.img_compressed)
            self.stream_sock_err = 0
        except Exception as exc:
            self.stream_sock_err += 1
            if self.stream_sock_err > 5:
                if self.debug:
                    print("img stream too many errors")
                exclogger.log_exception(exc, to_file=False)
                self.kill_streamer()
            pass

    def kill_streamer(self):
        if self.stream_sock is not None:
            try:
                self.stream_sock.close()
            except:
                pass
            try:
                del self.stream_sock
            except:
                pass
        self.stream_sock = None

    def compress_img(self):
        if self.img is None:
            self.img_compressed = None
            return
        try:
            if self.extra_fb is None:
                self.extra_fb = sensor.alloc_extra_fb(self.cam.width // 2, self.cam.height // 2, sensor.GRAYSCALE)
            if self.debug:
                print("compressing (%u %u) ..." % (self.img.height(), self.img.size()), end="")
            gc.collect()
            if self.zoom <= 1:
                self.img_compressed = self.img.scale(x_scale = 0.5, y_scale = 0.5, copy_to_fb = self.extra_fb).compress(quality=50)
            else:
                iw = int(math.floor(self.cam.width / self.zoom))
                ih = int(math.floor(self.cam.height / self.zoom))
                iwh = int(round(iw / 2.0))
                ihh = int(round(ih / 2.0))
                roi = (int(math.floor(self.settings["center_x"] - iwh)), int(math.floor(self.settings["center_y"] - ihh)), iw, ih)
                while roi[0] < 0:
                    roi[0] += 1
                while roi[1] < 0:
                    roi[1] += 1
                while roi[0] + roi[2] > self.cam.width:
                    roi[0] -= 1
                while roi[1] + roi[3] > self.cam.height:
                    roi[1] -= 1
                self.img_compressed = self.img.crop(roi, copy_to_fb = self.extra_fb).compress(quality=50)
            self.prevzoom = self.zoom
            if self.debug:
                print("done (%u %u)" % (self.img_compressed.height(), self.img_compressed.size()))
        except MemoryError as exc:
            exclogger.log_exception(exc, to_file = False)
            pass
        except Exception as exc:
            exclogger.log_exception(exc)
            pass

    def register_http_handlers(self):
        if self.portal is None:
            return
        self.portal.install_handler("/",               self.handle_index)
        self.portal.install_handler("/index.htm",      self.handle_index)
        self.portal.install_handler("/index.html",     self.handle_index)
        self.portal.install_handler("/getimg",         self.handle_getimg)
        self.portal.install_handler("/getimg.jpg",     self.handle_getimg)
        self.portal.install_handler("/getimg.jpeg",    self.handle_getimg)
        self.portal.install_handler("/stream",         self.handle_stream)
        self.portal.install_handler("/updatesetting",  self.handle_updatesetting)
        self.portal.install_handler("/getsettings",    self.handle_getsettings)
        self.portal.install_handler("/getstate",       self.handle_getstate)
        self.portal.install_handler("/memory",         self.handle_memory)
        self.portal.install_handler("/sleep",          self.handle_sleep)

    def diag_tick(self, now, before, dur):
        dt = now - before
        if dur < 0:
            dur = dt
        else:
            dur = (dur * 0.9) + (dt * 0.1)
        return now, dur

    def solve(self):
        if self.img is None:
            return False
        self.histogram = self.img.get_histogram()
        self.img_stats = self.histogram.get_statistics()
        gc.collect()
        stars, code = star_finder.find_stars(self.img, hist = self.histogram, stats = self.img_stats, thresh = self.settings["thresh"], force_solve = self.settings["force_solve"])
        self.expo_code = code
        self.stars = stars
        if self.expo_code == star_finder.EXPO_MEMORY_ERR:
            self.mem_errs += 1
        if len(self.stars) > self.max_stars:
            self.max_stars = len(self.stars)
            if self.debug:
                print("max stars %u" % self.max_stars)
        pass # TODO

    def task_network(self):
        if self.portal is not None:
            ret = self.portal.task()
            if ret == captive_portal.STS_KICKED:
                red_led.off()
            if self.portal.hw_retries > 5:
                print("ERROR: WiFi hardware failure")
                green_led.off()
                while True:
                    red_led.toggle()
                    pyb.delay(150)

    def task(self):
        gc.collect()
        self.diag_cnt += 1
        self.t = pyb.millis()
        self.time_mgr.tick(latest_millis = self.t)
        self.tick_all, self.dur_all = self.diag_tick(self.t, self.tick_all, self.dur_all) # debug loop speed

        if self.debug:
            if (self.diag_cnt % 20) == 0:
                print("tick %u %u" % (self.diag_cnt, self.frm_cnt))

        self.task_network()

        if self.cam.check_init() == False:
            return

        if self.cam.snapshot_check():
            # camera has finished an exposure
            self.img = self.cam.snapshot_finish()
            if self.img is not None:
                self.frm_cnt += 1
            else:
                self.cam_err = True

            if self.sleeping:
                red_led.off()
                green_led.off()
                blue_led.off()
                return

            self.cam.init(gain_db = self.settings["gain"], shutter_us = self.settings["shutter"], force_reset = self.cam_err)

            already_done = False
            if self.cam.check_init() == False:
                already_done = True
                if self.stream_sock is None:
                    self.solve()
                if self.packjpeg or self.stream_sock is not None:
                    self.compress_img()
                    if self.stream_sock is not None:
                        self.update_stream()
                while self.cam.check_init() == False:
                    self.task_network()

            if self.packjpeg == False and self.stream_sock is None:
                self.cam.snapshot_start()
                self.snap_millis = pyb.millis()
            if self.use_leds:
                green_led.toggle()
            if self.stream_sock is None and already_done == False:
                self.solve()
            if self.packjpeg or self.stream_sock is not None:
                if already_done == False:
                    self.compress_img()
                    if self.stream_sock is not None:
                        self.update_stream()
                self.cam.snapshot_start()
                self.snap_millis = pyb.millis()
            self.cam_err = self.cam.has_error
        else:
            if pyb.elapsed_millis(self.snap_millis) > 5000:
                self.cam_err = True
                if self.debug:
                    print("warning: camera timeout")
                self.cam.init(gain_db = self.settings["gain"], shutter_us = self.settings["shutter"], force_reset = True)
                while self.cam.check_init() == False:
                    self.task_network()
                self.cam.snapshot_start()
                self.snap_millis = pyb.millis()

def main(debug = False):
    guidescope = AutoguiderScope(debug = True)
    while True:
        try:
            guidescope.task()
        except KeyboardInterrupt:
            raise
        except MemoryError as exc:
            exclogger.log_exception(exc, to_file = False)
            micropython.mem_info(True)
        except Exception as exc:
            exclogger.log_exception(exc)

if __name__ == "__main__":
    main(debug = True)
