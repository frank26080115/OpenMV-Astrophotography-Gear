import micropython
micropython.opt_level(2)

import blobstar, astro_sensor, time_location, captive_portal, pole_finder, star_finder, pole_movement
import exclogger, fakestream
import pyb, uos, uio, gc, sys
import time, math, ujson, ubinascii
import network
import sensor, image

red_led   = pyb.LED(1)
green_led = pyb.LED(2)
blue_led  = pyb.LED(3)
ir_leds   = pyb.LED(4)

class PolarScope(object):

    def __init__(self, debug = False, simulate_file = None):
        self.highspeed = False
        self.daymode = False
        self.simulate = False
        self.cam = astro_sensor.AstroCam(simulate = simulate_file)
        self.cam.init(gain_db = -1, shutter_us = 250000)
        self.time_mgr = time_location.TimeLocationManager()

        self.debug = debug
        self.fakestream = fakestream.FakeStream()

        t = pyb.millis()
        self.diag_cnt    = 0
        self.frm_cnt     = 0
        self.tick_all    = t
        self.tick_ls     = t
        self.tick_hs     = t
        self.dur_all     = -1
        self.dur_ls      = -1
        self.dur_hs      = -1
        self.solu_dur_ls = -1
        self.solu_dur_hs = -1
        self.snap_millis = 0

        self.settings = {}
        self.settings.update({"longitude":   self.time_mgr.longitude})
        self.settings.update({"latitude":    self.time_mgr.latitude})
        self.settings.update({"time":        self.time_mgr.get_sec()})
        self.settings.update({"center_x":    self.cam.width / 2})
        self.settings.update({"center_y":    self.cam.height / 2})
        self.settings.update({"gain":        self.cam.gain})
        self.settings.update({"shutter":     self.cam.shutter})
        self.settings.update({"thresh":      (0)})
        self.settings.update({"gain_hs":     48})
        self.settings.update({"shutter_hs":  500000})
        self.settings.update({"thresh_hs":   (0)})
        self.settings.update({"use_refraction": False})
        self.settings.update({"force_solve": False})
        self.settings.update({"max_stars":   0})
        self.load_settings()
        self.time_mgr.readiness = False

        self.portal = captive_portal.CaptivePortal()

        self.img = None
        self.img_compressed = None
        self.extra_fb = None
        self.expo_code = 0
        self.histogram = None
        self.img_stats = None
        self.stars = []
        self.max_stars = 0
        self.packjpeg = False
        self.zoom = 1
        self.prevzoom = 1
        self.mem_errs = 0
        self.solution = None
        #self.solutions = [None, None]
        self.locked_solution = None
        if self.portal is not None:
            self.register_http_handlers()
        self.cam.snapshot_start()
        self.snap_millis = pyb.millis()

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

    def save_settings(self, filename = "settings.json"):
        if self.debug:
            print("save_settings")
        with open(filename, mode="wb") as f:
            ujson.dump(self.settings, f)

    def load_settings(self, filename = "settings.json"):
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
        self.time_mgr.set_location(self.settings["longitude"], self.settings["latitude"])
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
        state.update({"highspeed": self.highspeed})
        state.update({"packjpeg": self.packjpeg})
        state.update({"daymode": self.daymode})
        if self.img is not None:
            state.update({"expo_code": self.expo_code})
        stable_solution = self.stable_solution()
        if stable_solution is not None:
            state.update({"solution": stable_solution.to_jsonobj()})
            state.update({"star_x": self.locked_solution[0]})
            state.update({"star_y": self.locked_solution[1]})
            state.update({"pole_x": self.locked_solution[2]})
            state.update({"pole_y": self.locked_solution[3]})
            state.update({"rotation": self.locked_solution[4]})
            state.update({"pix_per_deg": stable_solution.pix_per_deg})
        else:
            state.update({"solution": False})
        if self.stars is not None:
            state.update({"stars": blobstar.to_jsonobj(self.stars)})
        state.update({"polar_clock": self.time_mgr.get_angle()})

        state.update({"max_stars": self.max_stars})

        # diagnostic info
        state.update({"frm_cnt":         self.frm_cnt})
        state.update({"diag_cnt":        self.diag_cnt})
        state.update({"diag_dur_all":    self.dur_all})
        state.update({"diag_dur_ls":     self.dur_ls})
        state.update({"diag_dur_hs":     self.dur_hs})
        state.update({"diag_dur_ls_sol": self.solu_dur_ls})
        state.update({"diag_dur_hs_sol": self.solu_dur_hs})
        if self.img_stats is not None:
            state.update({"img_mean":  self.img_stats.mean()})
            state.update({"img_stdev": self.img_stats.stdev()})
            state.update({"img_max":   self.img_stats.max()})
            state.update({"img_min":   self.img_stats.min()})

        json_str = ujson.dumps(state)
        client_stream.write(captive_portal.default_reply_header(content_type = "application/json", content_length = len(json_str)) + json_str)
        client_stream.close()
        red_led.on()

    def handle_getsettings(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_getsettings")
        json_str = ujson.dumps(self.settings)
        client_stream.write(captive_portal.default_reply_header(content_type = "application/json", content_length = len(json_str)) + json_str)
        client_stream.close()

    def handle_highspeed(self, client_stream, req, headers, content):
        self.highspeed = True
        if self.debug:
            print("go high speed")
        self.reply_ok(client_stream)

    def handle_lowspeed(self, client_stream, req, headers, content):
        self.highspeed = False
        if self.debug:
            print("go low speed")
        self.reply_ok(client_stream)

    def handle_daymode(self, client_stream, req, headers, content):
        self.daymode = True
        if self.debug:
            print("go day mode")
        self.reply_ok(client_stream)

    def handle_nightmode(self, client_stream, req, headers, content):
        self.daymode = False
        if self.debug:
            print("go night mode")
        self.reply_ok(client_stream)

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
                        self.time_mgr.set_utc_time_epoch(v)
                    elif i == "longitude":
                        self.time_mgr.set_location(v, None)
                        self.settings[i] = self.time_mgr.longitude # normalized
                    elif i == "latitude":
                        self.time_mgr.set_location(None, v)
                        self.settings[i] = self.time_mgr.latitude # normalized
                    elif i == "max_stars":
                        self.max_stars = v
                elif i == "highspeed":
                    self.highspeed = (v == True)
                elif i == "packjpeg":
                    self.packjpeg = (v == True)
                    if self.zoom != self.prevzoom and self.packjpeg:
                        self.compress_img()
                elif i == "zoom":
                    self.zoom = v
                    if self.zoom != self.prevzoom and self.packjpeg:
                        self.compress_img()
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

    def handle_index(self, client_stream, req, headers, content):
        captive_portal.gen_page(client_stream, "index.htm", add_files = ["web/jquery-ui-1.12.1-darkness.css", "web/jquery-3.5.1.min.js", "web/jquery-ui-1.12.1.min.js", "web/magellan.js"], add_dir = "web", debug = self.debug)

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
        self.portal.install_handler("/updatesetting",  self.handle_updatesetting)
        self.portal.install_handler("/highspeed",      self.handle_highspeed)
        self.portal.install_handler("/lowspeed",       self.handle_lowspeed)
        self.portal.install_handler("/daymode",        self.handle_daymode)
        self.portal.install_handler("/nightmode",      self.handle_nightmode)
        self.portal.install_handler("/getsettings",    self.handle_getsettings)
        self.portal.install_handler("/getstate",       self.handle_getstate)
        self.portal.install_handler("/memory",         self.handle_memory)

    def stable_solution(self):
        #if self.solutions[0] is not None and self.solutions[1] is not None and self.solution is not None:
        #    if self.solutions[0].solved and self.solutions[1].solved and self.solution.solved:
        #        return self.solution
        if self.solution is not None:
            if self.solution.solved:
                return self.solution
        return None

    def invalidate_solutions(self):
        self.solution     = None
        #self.solutions[0] = None
        #self.solutions[1] = None
        self.locked_solution = None
        #self.highspeed       = False

    def diag_tick(self, now, before, dur):
        dt = now - before
        if dur < 0:
            dur = dt
        else:
            dur = (dur * 0.9) + (dt * 0.1)
        return now, dur

    def solve_full(self):
        prev_sol = self.stable_solution()
        if self.expo_code == star_finder.EXPO_JUST_RIGHT:
            self.solution = pole_finder.PoleSolution(self.stars)
            if self.solution.solve(self.time_mgr.get_polaris()):
                self.solu_dur_ls = pyb.elapsed_millis(self.t) # debug solution speed
                accept = True
                """
                if self.solutions[0] is not None:
                    if self.solutions[0].compare(self.solution) == False:
                        accept = False
                if self.solutions[1] is not None:
                    if self.solutions[1].compare(self.solution) == False:
                        accept = False
                """
                if accept:
                    # pop off [1] and insert new solution into buffer
                    #self.solutions[1] = self.solutions[0]
                    #self.solutions[0] = self.solution
                    self.solution.get_pole_coords() # this caches x and y
                    if self.stable_solution() is not None:
                        self.locked_solution = [self.solution.Polaris.cx, self.solution.Polaris.cy, self.solution.x, self.solution.y, self.solution.get_rotation()]
                        if self.debug and prev_sol is None:
                            print("new solution! matched %u" % len(self.solution.stars_matched))
                    return True
                else:
                    # too much movement, invalidate all solutions
                    self.invalidate_solutions()
                    return False
            else:
                # no solution means invalidate all solutions
                self.invalidate_solutions()
                return False
        else:
            # camera image not good, invalidate all solutions
            self.invalidate_solutions()
            return False

    def solve_fast(self):
        destroy = False
        if self.expo_code == star_finder.EXPO_JUST_RIGHT and len(self.stars) > 0 and self.locked_solution is not None and self.solution is not None and destroy == False:
            if self.solution.solved != False:
                # find the brightest star and assume it's Polaris
                brite_sorted = blobstar.sort_brightness(self.stars)
                bright_star = brite_sorted[0]

                # how much did it move?
                dx = bright_star.cx - self.locked_solution[0]
                dy = bright_star.cy - self.locked_solution[1]

                # check if there's too much movement for one frame
                lim = sensor.width() / 5
                if abs(dx) > lim or abs(dy) > lim:
                    destroy = True

                # update state for next frame comparison
                self.locked_solution[0] += dx
                self.locked_solution[1] += dy
                x, y, r = self.solution.get_pole_coords_for(bright_star)
                self.locked_solution[2] = x
                self.locked_solution[3] = y
                self.locked_solution[4] = r
                self.solu_dur_hs = pyb.elapsed_millis(self.t) # debug solution speed
            else:
                destroy = True # lost the star for other reasons
        else:
            destroy = True # lost the star for other reasons

        # get out of this mode
        if destroy:
            self.invalidate_solutions()
            return False
        return True

    def solve(self):
        if self.img is None:
            return False
        self.histogram = self.img.get_histogram()
        self.img_stats = self.histogram.get_statistics()
        gc.collect()
        thresh_idx = "thresh"
        if self.highspeed:
            thresh_idx = "thresh_hs"
        stars, code = star_finder.find_stars(self.img, hist = self.histogram, stats = self.img_stats, thresh = self.settings[thresh_idx], force_solve = self.settings["force_solve"])
        self.expo_code = code
        self.stars = stars
        if self.expo_code == star_finder.EXPO_MEMORY_ERR:
            self.mem_errs += 1
        if len(self.stars) > self.max_stars:
            self.max_stars = len(self.stars)
            #self.save_settings()
            if self.debug:
                print("max stars %u" % self.max_stars)
        if self.highspeed == False:
            return self.solve_full()
        else: # highspeed = True
            return self.solve_fast()

    def task(self):
        gc.collect()
        self.diag_cnt += 1
        self.t = pyb.millis()
        self.time_mgr.tick(latest_millis = self.t)
        self.tick_all, self.dur_all = self.diag_tick(self.t, self.tick_all, self.dur_all) # debug loop speed

        if self.debug:
            if (self.diag_cnt % 20) == 0:
                print("tick %u %u" % (self.diag_cnt, self.frm_cnt))

        if self.portal is not None:
            ret = self.portal.task()
            if ret == captive_portal.STS_KICKED:
                red_led.off()

        if self.cam.snapshot_check():
            # camera has finished an exposure
            self.img = self.cam.snapshot_finish()
            self.frm_cnt += 1

            # day mode is just auto exposure for testing
            if self.daymode:
                self.cam.init(gain_db = -1, shutter_us = -1, force_reset = False)
                self.snap_millis = pyb.millis()
                if self.img is not None:
                    self.histogram = self.img.get_histogram()
                    self.img_stats = self.histogram.get_statistics()
                    if self.packjpeg:
                        self.compress_img()
                self.cam.snapshot_start()
                green_led.toggle()
                return # this will skip solving
            # take the next frame with settings according to mode
            if self.highspeed == False:
                self.tick_ls, self.dur_ls = self.diag_tick(self.t, self.tick_ls, self.dur_ls) # debug loop speed
                self.tick_hs = self.t
                self.dur_hs = -1
                self.cam.init(gain_db = self.settings["gain"], shutter_us = self.settings["shutter"], force_reset = False)
            else:
                self.tick_hs, self.dur_hs = self.diag_tick(self.t, self.tick_hs, self.dur_hs) # debug loop speed
                self.tick_ls = self.t
                self.dur_ls = -1
                self.cam.init(gain_db = self.settings["gain_hs"], shutter_us = self.settings["shutter_hs"], force_reset = False)
            if self.packjpeg == False:
                self.cam.snapshot_start()
                self.snap_millis = pyb.millis()
            green_led.toggle()
            self.solve()
            if self.packjpeg:
                self.compress_img()
                self.cam.snapshot_start()
                self.snap_millis = pyb.millis()
        else:
            if pyb.elapsed_millis(self.snap_millis) > 5000:
                if self.debug:
                    print("warning: camera timeout")
                if self.daymode:
                    self.cam.init(gain_db = -1, shutter_us = -1, force_reset = True)
                elif self.highspeed == False:
                    self.cam.init(gain_db = self.settings["gain"], shutter_us = self.settings["shutter"], force_reset = True)
                else:
                    self.cam.init(gain_db = self.settings["gain_hs"], shutter_us = self.settings["shutter_hs"], force_reset = True)
                self.cam.snapshot_start()
                self.snap_millis = pyb.millis()

def main():
    polarscope = PolarScope(debug = True, simulate_file = "simulate.bmp")
    #polarscope = PolarScope(debug = True)
    while True:
        try:
            polarscope.task()
        except KeyboardInterrupt:
            raise
        except MemoryError as exc:
            exclogger.log_exception(exc, to_file = False)
            micropython.mem_info(True)
        except Exception as exc:
            exclogger.log_exception(exc)

if __name__ == "__main__":
    main()
