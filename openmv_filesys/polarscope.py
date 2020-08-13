import micropython
micropython.opt_level(2)

import blobstar, astro_sensor, time_location, captive_portal, pole_finder, star_finder, pole_movement
import exclogger, fakestream
import pyb, uos, uio, gc, sys, time, math, ujson
import network
import sensor, image

class PolarScope(object):

    def __init__(self, debug = False):
        self.highspeed = False
        self.daymode = False
        self.simulate = False
        self.cam = astro_sensor.AstroCam()
        self.cam.init(gain_db = 48, shutter_us = 1500000)
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

        self.settings = {}
        self.settings.update({"name":        "PolarScope-?"})
        self.settings.update({"longitude":   self.time_mgr.longitude})
        self.settings.update({"latitude":    self.time_mgr.latitude})
        self.settings.update({"time":        self.time_mgr.get_sec()})
        self.settings.update({"center_x":    sensor.width() / 2})
        self.settings.update({"center_y":    sensor.height() / 2})
        self.settings.update({"gain":        sensor.get_gain_db()})
        self.settings.update({"shutter":     sensor.get_exposure_us()})
        self.settings.update({"gain_hs":     48})
        self.settings.update({"shutter_hs":  500000})
        self.settings.update({"force_solve": False})
        self.load_settings()
        self.time_mgr.readiness = False

        try:
            if debug == False:
                self.portal = captive_portal.CaptivePortal(ssid = self.settings["name"])
            else:
                self.portal = captive_portal.CaptivePortal("moomoomilk", "1234567890", winc_mode = network.WINC.MODE_STA, winc_security = network.WINC.WPA_PSK, debug = True)
        except OSError:
            print("shield not connected")
            self.portal = None

        self.img = None
        self.expo_code = 0
        self.histogram = None
        self.img_stats = None
        self.stars = []
        self.solution = None
        self.solutions = [None, None]
        self.locked_solution = None
        if self.portal is not None:
            self.register_http_handlers()
        self.cam.snapshot_start()

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
                    self.settings[i] = v
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
        state = {}
        state.update({"time": self.time_mgr.get_sec()})
        state.update({"highspeed": self.highspeed})
        state.update({"daymode": self.daymode})
        if self.img is not None:
            state.update({"expo_code": self.expo_code})
        stable_solution = self.stable_solution()
        if stable_solution is not None:
            state.update({"solution": ujson.dumps(stable_solution.to_jsonobj())})
            state.update({"star_x": self.locked_solution[0]})
            state.update({"star_y": self.locked_solution[1]})
            state.update({"pole_x": self.locked_solution[2]})
            state.update({"pole_y": self.locked_solution[3]})
            state.update({"rotation": self.locked_solution[4]})
        else:
            state.update({"solution": False})
        if self.stars is not None:
            state.update({"stars": blobstar.to_jsonobj(self.stars)})

        # diagnostic info
        state.update({"diag_cnt":        self.diag_cnt})
        state.update({"diag_frm_cnt":    self.frm_cnt})
        state.update({"diag_dur_all":    self.dur_all})
        state.update({"diag_dur_ls":     self.dur_ls})
        state.update({"diag_dur_hs":     self.dur_hs})
        state.update({"diag_dur_ls_sol": self.solu_dur_ls})
        state.update({"diag_dur_hs_sol": self.solu_dur_hs})
        if self.img_stats is not None:
            state.update({"diag_img_mean":  self.img_stats.mean()})
            state.update({"diag_img_stdev": self.img_stats.stdev()})
            state.update({"diag_img_max":   self.img_stats.max()})
            state.update({"diag_img_min":   self.img_stats.min()})

        json_str = ujson.dumps(state)
        client_stream.write(captive_portal.default_reply_header(content_type = "application/json", content_length = len(json_str)) + json_str)
        client_stream.close()

    def handle_getsettings(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_getsettings")
        json_str = ujson.dumps(self.settings)
        client_stream.write(captive_portal.default_reply_header(content_type = "application/json", content_length = len(json_str)) + json_str)
        client_stream.close()

    def handle_highspeed(self, client_stream, req, headers, content):
        if self.stable_solution() is not None:
            self.highspeed = True
            if self.debug:
                print("go high speed")
            self.reply_ok(client_stream)
        else:
            if self.debug:
                print("can't go high speed")
            self.reply_ok(client_stream, sts=False, err="no solution")

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

    def handle_simulate(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_simulate")
        self.start_simulation()
        self.reply_ok(client_stream)

    def handle_endsim(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_endsim")
        self.end_simulation()
        self.reply_ok(client_stream)

    def handle_updatesetting(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_updatesetting", end="")
        try:
            request_page, request_urlparams = captive_portal.split_get_request(req)
            if self.debug:
                print(" keys %u" % len(request_urlparams))
            for i in request_urlparams.keys():
                v = request_urlparams[i]
                if i in self.settings:
                    v = v.lstrip().rstrip()
                    try: # micropython doesn't have "is_numeric"
                        if v.lower() == "false":
                            v = False
                        elif v.lower() == "true":
                            v = True
                        elif "." in v:
                            v = float(v)
                        else:
                            v = int(v)
                    except:
                        pass
                    self.settings[i] = v
                    if self.debug:
                        print("setting \"%s\" value \"%s\"" % (i, str(v)))
                    if i == "time":
                        self.time_mgr.set_utc_time_epoch(v)
                    elif i == "longitude":
                        self.time_mgr.set_location(v, None)
                        self.settings[i] = self.time_mgr.longitude # normalized
                    elif i == "latitude":
                        self.time_mgr.set_location(None, v)
                        self.settings[i] = self.time_mgr.latitude # normalized
                else:
                    print("unknown setting \"%s\": \"%s\"" % (i, str(v)))
            self.save_settings()
            self.reply_ok(client_stream)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            s = exclogger.log_exception(exc)
            self.reply_ok(client_stream, sts=False, err=s)

    def handle_getimg(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_getimg", end="")
        try:
            if self.img is None:
                client_stream.write(captive_portal.default_reply_header(content_type = "image/jpeg", content_length = 0))
                client_stream.close()
                if self.debug:
                    print(" no image")
                return
            cimage = self.img.compressed(quality=50)
            client_stream.write(captive_portal.default_reply_header(content_type = "image/jpeg", content_length = cimage.size()))
            client_stream.write(cimage)
            client_stream.close()
            if self.debug:
                print(" sent %u" % cimage.size())
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

    def register_http_handlers(self):
        if self.portal is None:
            return
        self.portal.install_handler("/getimg",         self.handle_getimg)
        self.portal.install_handler("/updatesetting",  self.handle_updatesetting)
        self.portal.install_handler("/highspeed",      self.handle_highspeed)
        self.portal.install_handler("/daymode",        self.handle_daymode)
        self.portal.install_handler("/nightmode",      self.handle_nightmode)
        self.portal.install_handler("/getsettings",    self.handle_getsettings)
        self.portal.install_handler("/getstate",       self.handle_getstate)
        self.portal.install_handler("/simulate",       self.handle_simulate)
        self.portal.install_handler("/endsim",         self.handle_endsim)
        self.portal.install_handler("/memory",         self.handle_memory)

    def stable_solution(self):
        if self.solutions[0] is not None and self.solutions[1] is not None and self.solution is not None:
            if self.solutions[0].solved and self.solutions[1].solved and self.solution.solved:
                return self.solution
        return None

    def invalidate_solutions(self):
        self.solution     = None
        self.solutions[0] = None
        self.solutions[1] = None
        self.locked_solution = None
        self.highspeed       = False

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
                self.solu_dur_ls = pyb.elapsed_millis(t) # debug solution speed
                accept = True
                if self.solutions[0] is not None:
                    if self.solutions[0].compare(self.solution) == False:
                        accept = False
                if self.solutions[1] is not None:
                    if self.solutions[1].compare(self.solution) == False:
                        accept = False
                if accept:
                    # pop off [1] and insert new solution into buffer
                    self.solutions[1] = self.solutions[0]
                    self.solutions[0] = self.solution
                    self.solution.get_pole_coords() # this caches x and y
                    if self.stable_solution() is not None:
                        self.locked_solution = [self.solution.Polaris.cx, self.solution.Polaris.cy, self.solution.x, self.solution.y, self.solution.get_rotation()]
                        if debug and prev_sol is None:
                            print("new solution! matched %u" % self.solution.stars_matched)
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
        if self.expo_code == star_finder.EXPO_JUST_RIGHT and len(self.stars) > 0 and self.locked_solution is not None and destroy == False:
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
            self.solu_dur_hs = pyb.elapsed_millis(t) # debug solution speed
        else:
            destroy = True # lost the star for other reasons

        # get out of this mode
        if destroy:
            self.invalidate_solutions()
            return False
        return True

    def solve(self):
        self.histogram = self.img.get_histogram()
        self.img_stats = self.histogram.get_statistics()
        stars, code = star_finder.find_stars(self.img, hist = self.histogram, stats = self.img_stats, force_solve = self.settings["force_solve"])
        self.expo_code = code
        self.stars = stars
        if self.highspeed == False:
            return self.solve_full()
        else: # highspeed = True
            return self.solve_fast()

    def start_simulation(self):
        if self.simulate == False:
            self.img = None
        self.simulate = True

    def end_simulation(self):
        if self.simulate and self.img is not None:
            sensor.dealloc_extra_fb()
        self.simulate = False

    def task(self):
        gc.collect()
        self.diag_cnt += 1
        t = pyb.millis()
        self.time_mgr.tick(latest_millis = t)
        self.tick_all, self.dur_all = self.diag_tick(t, self.tick_all, self.dur_all) # debug loop speed
        if self.portal is not None:
            self.portal.task()
        if self.cam.snapshot_check():
            # camera has finished an exposure
            img = self.cam.snapshot_finish()
            self.frm_cnt += 1

            if self.simulate:
                # make the camera go fast in simulation mode
                self.cam.init(gain_db = -1, shutter_us = -1, force_reset = False)
                if self.img is None:
                    gc.collect()
                    print("about to load simulation file, checking memory")
                    micropython.mem_info(True)
                    print("loading simulation file ...", end="")
                    self.img = image.Image("simulate.bmp", copy_to_fb = True)
                    print(" done, alloc and converting ...", end="")
                    self.img = sensor.alloc_extra_fb(self.img.width(), self.img.height(), sensor.RGB565).replace(self.img).to_grayscale()
                    print(" done!")
                    pass
            # day mode is just auto exposure for testing
            elif self.daymode:
                self.cam.init(gain_db = -1, shutter_us = -1, force_reset = False)
                self.img = img
                self.histogram = self.img.get_histogram()
                self.img_stats = self.histogram.get_statistics()
                self.cam.snapshot_start()
                return # this will skip solving
            else: # not day mode or simulate
                self.img = img
                # take the next frame with settings according to mode
                if self.highspeed == False:
                    self.tick_ls, self.dur_ls = self.diag_tick(t, self.tick_ls, self.dur_ls) # debug loop speed
                    self.tick_hs = t
                    self.dur_hs = -1
                    self.cam.init(gain_db = self.settings["gain"], shutter_us = self.settings["shutter"], force_reset = False)
                else:
                    self.tick_hs, self.dur_hs = self.diag_tick(t, self.tick_hs, self.dur_hs) # debug loop speed
                    self.tick_ls = t
                    self.dur_ls = -1
                    self.cam.init(gain_db = self.settings["gain_hs"], shutter_us = self.settings["shutter_hs"], force_reset = False)
            self.cam.snapshot_start()
            self.solve()

def main():
    polarscope = PolarScope(debug = True)
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
