SHUTTER_DURATION_SHORT   = micropython.const(1000)
SHUTTER_DURATION_LONG    = micropython.const(1400)

PANICTHRESH_EXPOERR      = micropython.const(10)
PANICTHRESH_MOVESCORE    = micropython.const(100)

    def get_state_obj(self):
        state = {}
        state.update({"packet_type", "state"})
        state.update({"time": self.time_mgr.get_sec()})
        if self.websock_randid != 0:
            state.update({"rand_id": self.websock_randid})
        state.update({"guider_state": self.guide_state})
        state.update({"intervalometer_state": self.intervalometer_state})
        if self.img is not None and self.cam_err == False:
            state.update({"expo_code": self.expo_code})
        elif self.img is None:
            state.update({"expo_code": star_finder.EXPO_NO_IMG})
        elif self.cam_err > 0:
            state.update({"expo_code": star_finder.EXPO_CAMERA_ERR})
        if self.img_stats is not None:
            state.update({"img_mean":  self.img_stats.mean()})
            state.update({"img_stdev": self.img_stats.stdev()})
            state.update({"img_max":   self.img_stats.max()})
            state.update({"img_min":   self.img_stats.min()})
        if self.stars is not None:
            star_list = self.stars
            if len(star_list) > 50:
                star_list = star_list[0:50]
            state.update({"stars": blobstar.to_jsonobj(star_list)})
        if self.selected_star is not None:
            state.update({"selected_star", [self.selected_star.cx, self.selected_star.cy]})
            state.update({"selected_star_profile", self.selected_star.profile})
        if self.target_coord is not None:
            state.update({"target_coord", self.target_coord})
        if self.origin_coord is not None:
            state.update({"origin_coord", self.origin_coord})
        if self.calibration[CALIIDX_RA] is not None:
            state.update({"calib_ra", self.calibration[CALIIDX_RA].get_json_obj()})
        else:
            state.update({"calib_ra", False})
        if self.calibration[CALIIDX_DEC] is not None:
            state.update({"calib_dec", self.calibration[CALIIDX_DEC].get_json_obj()})
        else:
            state.update({"calib_dec", False})
        return state

    def decide(self):
        decided_pulse = 0
        if self.stream_sock is not None or self.img_is_compressed:
            self.guide_state = GUIDESTATE_IDLE
            return decided_pulse
        if self.img is not None:
            self.histogram = self.img.get_histogram()
            self.img_stats = self.histogram.get_statistics()
            stars, code = star_finder.find_stars(self.img, hist = self.histogram, stats = self.img_stats, thresh = self.settings["thresh"], force_solve = self.settings["force_solve"], advanced = True)
            if self.simulation is not None:
                stars, code = self.simulation.get_stars(self.guide_state)
            stars = blobstar.sort_rating(stars)
            self.expo_code = code
            if code != star_finder.EXPO_JUST_RIGHT or len(stars) <= 0:
                self.expo_err += 1
                if self.debug:
                    print("exposure error %u %u" % (code, len(stars)))
                if self.expo_err > self.settings["panicthresh_expoerr"]:
                    if self.debug:
                        print("exposure error exceeded threshold")
                    self.panic()
                self.dither_calm = 0
                return decided_pulse
            else:
                # exposure is just right
                self.expo_err = 0
                self.prev_stars = self.stars
                self.stars = stars

                # motion can be detected if previous data is available
                # if previous data is unavailable, then just populate it for no motion
                if self.prev_stars is None:
                    self.prev_stars = stars

                real_star, virtual_star, move_data, score, avg_cnt = star_motion.get_all_star_movement(self.prev_stars, self.stars, selected_star = self.selected_star)
                # TODO: settings
                self.selected_star = real_star
                self.virtual_star  = virtual_star
                if score > self.settings["panicthresh_movescore"]:
                    if self.debug:
                        print("movement analysis score too low %f" % score)
                    self.panic()

                if self.guide_state == GUIDESTATE_GUIDING:
                    if self.selected_star is None:
                        if self.debug:
                            print("warning: no selected star while guiding")
                        self.guide_state = GUIDESTATE_IDLE:
                        return
                    if self.target_coord is None:
                        self.target_coord = [self.selected_star.cx, self.selected_star.cy]
                        if self.debug:
                            print("target coord auto-selected: (%0.1f , %0.2f)" % (self.target_coord[0], self.target_coord[1]))
                    if self.origin_coord is None:
                        self.origin_coord = self.target_coord
                        if self.debug:
                            print("origin coord auto-selected: (%0.1f , %0.2f)" % (self.origin_coord[0], self.origin_coord[1]))
                    if self.intervalometer_state == INTERVALSTATE_ACTIVE_DITHER and self.pulser.is_shutter_open() == False:
                        amt = int(round(self.settings["dither_amount"] * 10.0))
                        nx = ((pyb.rng() % (amt * 2)) - amt) / 10.0
                        ny = ((pyb.rng() % (amt * 2)) - amt) / 10.0
                        self.target_coord = [self.origin_coord[0] + nx, self.origin_coord[1] + ny]
                        if self.debug:
                            print("dithering coord: (%0.1f , %0.2f)" % (self.target_coord[0], self.target_coord[1]))
                        self.guide_state = GUIDESTATE_DITHER
                        self.dither_calm = 0
                        self.dither_frames = 0
                        self.backlash_ra.neutralize()
                        self.backlash_dec.neutralize()
                    decided_pulse = self.pulse_to_target()
                    return decided_pulse
                elif self.guide_state == GUIDESTATE_DITHER:
                    self.dither_frames += 1
                    self.backlash_ra.neutralize()
                    self.backlash_dec.neutralize()
                    decided_pulse = self.pulse_to_target()
                    if decided_pulse <= self.settings["dither_calmness"]:
                        self.dither_calm += 1
                    else:
                        self.dither_calm = 0
                        if self.debug:
                            print("dithering too much error " % (self.target_coord[0], self.target_coord[1]))
                    done_dither = False
                    if self.dither_calm >= self.settings["dither_calm_cnt"]:
                        done_dither = True
                        if self.debug:
                            print("dither finished due to calm")
                    elif self.dither_frames >= self.settings["dither_frames_cnt"]:
                        done_dither = True
                        if self.debug:
                            print("dither finished due to timeout")
                    if done_dither:
                        self.guide_state = GUIDESTATE_GUIDING
                        self.pulser.shutter(self.settings["intervalometer_bulb_time"])
                        self.intervalometer_timestamp = 0
                    return decided_pulse
                elif self.guide_state == GUIDESTATE_CALIBRATING_RA or self.guide_state == GUIDESTATE_CALIBRATING_DEC:
                    self.backlash_ra.neutralize()
                    self.backlash_dec.neutralize()
                    if self.selected_star is None:
                        if self.debug:
                            print("warning: calibration without selected star")
                        self.guide_state = GUIDESTATE_IDLE:
                        return
                    if self.virtual_star is None:
                        self.virtual_star = [self.selected_star.cx, self.selected_star.cy]
                    if self.guide_state == GUIDESTATE_CALIBRATING_RA:
                        i = CALIIDX_RA
                    else:
                        i = CALIIDX_DEC
                    if self.calibration[i] is None:
                        pulse_width = self.settings["calibration_pulse"]
                        if pulse_width <= 0:
                            # use automatic mode
                            pulse_width = int(round(self.settings["shutter"] * 0.9))
                        self.calibration[i] = guider_calibration.GuiderCalibration(virtual_star[0], virtual_star[1], pulse_width)
                    else:
                        self.calibration[i].append_pt(self.virtual_star)
                    if len(self.calibration[i].points) >= self.settings["calib_points_cnt"]:
                        self.guide_state = GUIDESTATE_IDLE
                        success = self.calibration[i].analyze()
                        if success:
                            if self.debug:
                                print("calibration done, angle = %0.1f , dist = %0.1f" % (self.calibration[i].angle, self.calibration[i].farthest))
                        else:
                            if self.debug:
                                print("calibration failed")
                            self.calibration[i] = None
                    else:
                        decided_pulse = self.calibration[i].pulse_width
                        if self.guide_state == GUIDESTATE_CALIBRATING_RA:
                            self.pulser.move(decided_pulse, 0, self.settings["move_grace"])
                        else:
                            self.pulser.move(0, decided_pulse, self.settings["move_grace"])
                    return decided_pulse
                elif self.guide_state == GUIDESTATE_IDLE:
                    self.backlash_ra.neutralize()
                    self.backlash_dec.neutralize()
                    if self.selected_star is None:
                        return decided_pulse
                    if self.target_coord is None:
                        self.target_coord = [self.selected_star.cx, self.selected_star.cy]
                    if self.origin_coord is None:
                        self.origin_coord = self.target_coord
                return decided_pulse
        else:
            # self.img is None
            return decided_pulse

    def pulse_to_target(self):
        if self.calibration[CALIIDX_RA] is None:
            return 0
        if self.target_coord is None or self.selected_star is None:
            return 0
        if self.virtual_star is None:
            self.virtual_star = self.selected_star
        dx = self.target_coord[0] - self.virtual_star[0]
        dy = self.target_coord[1] - self.virtual_star[1]
        mag = math.sqrt((dx * dx) + (dy * dy))
        ang = math.degrees(math.atan2(dy, dx))
        ang_ra  = comutils.ang_normalize(ang - self.calibration[CALIIDX_RA ])
        nx = mag * math.cos(math.radians(ang_ra))
        pulse_ra_ori  = nx * self.calibration[CALIIDX_RA ].ms_per_pix
        if self.calibration[CALIIDX_DEC] is not None:
            ang_dec = comutils.ang_normalize(ang - self.calibration[CALIIDX_DEC])
            ny = mag * math.cos(math.radians(ang_dec))
        else:
            # declination not calibrated
            pulse_dec_ori = 0
            ny = mag * math.sin(math.radians(ang_ra))
            pulse_dec_ori = ny * self.calibration[CALIIDX_RA].ms_per_pix
        pulse_ra_abs  = abs(pulse_ra_ori)
        pulse_dec_abs = abs(pulse_dec_ori)
        self.pulse_sum += pulse_ra_abs + pulse_dec_abs
        min_pulse_wid = self.settings["min_pulse_wid"]
        max_pulse_wid = self.settings["max_pulse_wid"]
        if min_pulse_wid < 5:
            min_pulse_wid = 5
        if max_pulse_wid < 5:
            max_pulse_wid = int(round(self.settings["shutter"] * 0.9))
        if pulse_ra_abs < min_pulse_wid * 0.75:
            pulse_ra_abs = 0
            pulse_ra_ori = 0
        elif pulse_ra_abs < min_pulse_wid:
            pulse_ra_abs = min_pulse_wid
            if pulse_ra_ori > 0:
                pulse_ra_ori = min_pulse_wid
            else:
                pulse_ra_ori = -min_pulse_wid
        if pulse_dec_abs < min_pulse_wid * 0.75:
            pulse_dec_abs = 0
            pulse_dec_ori = 0
        elif pulse_dec_abs < min_pulse_wid:
            pulse_dec_abs = min_pulse_wid
            if pulse_dec_ori > 0:
                pulse_dec_ori = min_pulse_wid
            else:
                pulse_dec_ori = -min_pulse_wid
        if pulse_ra_abs > max_pulse_wid:
            pulse_ra_abs = max_pulse_wid
            if pulse_ra_ori > 0:
                pulse_ra_ori = max_pulse_wid
            else:
                pulse_ra_ori = -max_pulse_wid
        if pulse_dec_abs > max_pulse_wid:
            pulse_dec_abs = max_pulse_wid
            if pulse_dec_ori > 0:
                pulse_dec_ori = max_pulse_wid
            else:
                pulse_dec_ori = -max_pulse_wid
        ret = max(pulse_ra_abs, pulse_dec_abs)
        if ret > 0 && ret <= 1:
            ret = 1
        pulse_ra_fin  = self.backlash_ra.filter(pulse_ra_ori)
        if self.calibration[CALIIDX_DEC] is None:
            pulse_dec_ori = 0
        pulse_dec_fin = self.backlash_dec.filter(pulse_dec_ori)
        if pulse_ra_fin != 0 or pulse_dec_fin != 0:
            self.pulser.move(pulse_ra_fin, pulse_dec_fin, self.settings["move_grace"])
            return ret
        return 0

    def reset_guiding(self):
        self.backlash_ra.neutralize()
        self.backlash_dec.neutralize()
        self.selected_star   = None
        self.prev_stars      = None
        self.target_origin   = None
        self.target_final    = None

    def panic(self):
        if self.guiding_state != GUIDESTATE_IDLE:
            self.guiding_state = GUIDESTATE_PANIC
            self.pulser.panic(True)
        self.reset_guiding()

    def snap_start(self):
        try:
            self.cam.init(gain_db = self.settings["gain"], shutter_us = self.settings["shutter"] * 1000, force_reset = self.cam_err)
            while self.cam.check_init() == False:
                self.task_network()
                self.pulser.task()
            self.cam.snapshot_start()
            self.snap_millis = pyb.millis()
            self.cam_err = 0
            if self.cam_initing > 0:
                self.cam_initing -= 1
            self.img_is_compressed = False
            return True
        except Exception as exc:
            self.cam_err += 1
            exclogger.log_exception(exc, time_str=comutils.fmt_time(self.time_mgr.get_time()))
            self.task_network()
            self.pulser.task()
            return False

    def snap_wait(self):
        self.task_network()
        self.pulser.task()
        while True:
            if pyb.elapsed_millis(self.snap_millis) <= (self.move - self.settings["net_quiet_time"]) or self.move == 0 or self.pulser.is_moving() == False:
                self.task_network()
            self.pulser.task()
            if self.pulser.is_moving():
                if self.cam.snapshot_check():
                    # moving more than a frame duration
                    # take the frame but toss it out, start a new one (which will be tossed later anyways)
                    garbage = self.cam.snapshot_finish()
                    self.snap_start()
            else:
                if self.stop_time <= 0:
                    self.stop_time = self.pulser.get_stop_time()
                if self.cam.snapshot_check():
                    return True
                elif pyb.elapsed_millis(self.snap_millis) > (self.cam.get_timespan() + 500):
                    self.cam_err += 1
                    print("warning: camera timeout")
                    exclogger.log_exception("warning: camera timeout", time_str=comutils.fmt_time(self.time_mgr.get_time()))
                    return False

    def task(self):
        success = self.snap_start()
        gc.collect()
        if success == False:
            return
        self.move = self.decide()
        self.update_web_img()
        if self.snap_wait():
            img = self.cam.snapshot_finish()
            img_time = img.timestamp()
            if img_time > self.stop_time and (img_time - (self.cam.get_timespan() + 100)) > self.stop_time:
                # this image was taken while staying still
                self.img = img
                if self.move == 0 and self.stream_sock is not None and self.img_is_compressed == False:
                    self.compress_img()
                    self.img_is_compressed = True
            else:
                # did not stay still, do another one while staying still
                if self.snap_start():
                    if self.snap_wait():
                        self.img = self.cam.snapshot_finish()

    def task_pulser(self):
        self.pulser.task()
        gap_time = self.settings["intervalometer_gap_time"]
        if gap_time <= 1000:
            gap_time = 1000
        if self.pulser.is_shutter_open() == False:
            self.pulse_sum = 0
            if self.intervalometer_timestamp <= 0:
                self.intervalometer_timestamp = pyb.millis()
                if self.intervalometer_state == INTERVALSTATE_ACTIVE_DITHER:
                    if self.debug:
                        print("shutter closed while in dither mode")
            if self.intervalometer_state == INTERVALSTATE_ACTIVE:
                self.intervalometer_state = INTERVALSTATE_ACTIVE_GAP
                if self.debug:
                    print("shutter closed for brief gap")
            elif self.intervalometer_state == INTERVALSTATE_ACTIVE_GAP:
                if pyb.elapsed_millis(self.intervalometer_timestamp) >= gap_time:
                    self.intervalometer_state = INTERVALSTATE_ACTIVE
                    self.pulser.shutter(self.settings["intervalometer_bulb_time"])
                    self.intervalometer_timestamp = 0
                    if self.debug:
                        print("shutter opened")
            elif self.intervalometer_state == INTERVALSTATE_ACTIVE_ENDING:
                self.intervalometer_state = INTERVALSTATE_IDLE
                if self.debug:
                    print("intervalometer finished")
            elif self.intervalometer_state == INTERVALSTATE_ACTIVE_DITHER and self.guide_state != GUIDESTATE_GUIDING and self.guide_state != GUIDESTATE_DITHER:
                self.intervalometer_state = INTERVALSTATE_IDLE
                if self.debug:
                    print("intervalometer dithering mode interrupted")

    def intervalometer_cmd(self, cmd):
        if cmd == INTERVALSTATE_ACTIVE or cmd == INTERVALSTATE_ACTIVE_DITHER:
            self.intervalometer_state = cmd
            self.shutter(self.settings["intervalometer_bulb_time"])
            self.intervalometer_timestamp = 0
            self.pulse_sum = 0
            if self.debug:
                print("intervalometer activated")
        elif cmd == INTERVALSTATE_BULB_TEST:
            self.pulser.shutter(self.settings["intervalometer_bulb_time"])
            self.intervalometer_timestamp = 0
            self.pulse_sum = 0
            if self.debug:
                print("shutter bulb test")
            self.intervalometer_state = INTERVALSTATE_ACTIVE_ENDING
        elif cmd == INTERVALSTATE_ACTIVE_ENDING:
            self.intervalometer_state = cmd
            if self.debug:
                print("intervalometer ending on next shutter close")
        elif cmd == INTERVALSTATE_ACTIVE_HALT:
            self.pulser.shutter_halt()
            self.intervalometer_state = INTERVALSTATE_IDLE
            if self.debug:
                print("intervalometer ending on next shutter close")

    def task_network(self):
        if self.portal is not None:
            ret = self.portal.task()
            if ret == captive_portal.STS_KICKED:
                red_led.off()
            if self.portal.hw_retries > 5:
                print("ERROR: WiFi hardware failure")
                green_led.off()
                if (self.t % 300) < 150:
                    red_led.on()
                else:
                    red_led.off()

    def register_http_handlers(self):
        if self.portal is None:
            return
        self.portal.install_handler("/",               self.handle_index)
        self.portal.install_handler("/index.htm",      self.handle_index)
        self.portal.install_handler("/index.html",     self.handle_index)
        self.portal.install_handler("/stream",         self.handle_imgstream)
        self.portal.install_handler("/updatesetting",  self.handle_updatesetting)
        self.portal.install_handler("/getsettings",    self.handle_getsettings)
        self.portal.install_handler("/getstate",       self.handle_getstate)
        self.portal.install_handler("/websocket",      self.handle_websocket)
        self.portal.install_handler("/memory",         self.handle_memory)