SHUTTER_DURATION_SHORT   = micropython.const(1000)
SHUTTER_DURATION_LONG    = micropython.const(1400)

PANICTHRESH_EXPOERR      = micropython.const(10)
PANICTHRESH_MOVESCORE    = micropython.const(100)

    def decide(self):
        decided_pulse = 0
        if self.stream_sock is not None or self.img_is_compressed:
            self.guide_state    = GUIDESTATE_IDLE
            return decided_pulse
        if self.img is not None:
            panic = False
            self.histogram = self.img.get_histogram()
            self.img_stats = self.histogram.get_statistics()
            stars, code = star_finder.find_stars(self.img, hist = self.histogram, stats = self.img_stats, thresh = self.settings["thresh"], force_solve = self.settings["force_solve"], advanced = True)
            if self.simulation is not None:
                stars, code = self.simulation.get_stars(self.guide_state)
            stars = blobstar.sort_rating(stars)
            if code != star_finder.EXPO_JUST_RIGHT or len(stars) <= 0:
                self.expo_err += 1
                if self.debug:
                    print("exposure error %u %u" % (code, len(stars)))
                if self.expo_err > self.settings["panicthresh_expoerr"]:
                    if self.debug:
                        print("exposure error exceeded threshold")
                    self.panic()
                self.update_web_img()
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

                self.update_web_img()

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
                        
                    return decided_pulse
                elif self.guide_state == GUIDESTATE_CALIBRATING_RA or self.guide_state == GUIDESTATE_CALIBRATING_DEC:
                    self.backlash_ra.neutralize()
                    self.backlash_dec.neutralize()
                    if self.selected_star is None:
                        # hmm...
                        self.guide_state = GUIDESTATE_IDLE:
                        return
                    if self.virtual_star is None:
                        self.virtual_star = [self.selected_star.cx, self.selected_star.cy]
                    if self.guide_state == GUIDESTATE_CALIBRATING_RA:
                        i = CALIIDX_RA
                    else:
                        i = CALIIDX_DEC
                    if self.calibration[i] is None:
                    self.calibration[i] = guider_calibration.GuiderCalibration(virtual_star[0], virtual_star[1], self.settings["calibration_pulse"])
                    else:
                        self.calibration[i].append_pt(self.virtual_star)
                    if len(self.calibration[i].points) >= self.settings["calib_points_cnt"]:
                        self.guide_state = GUIDESTATE_IDLE
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
        if self.calibration[0] is None or self.calibration[1] is None:
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
        ang_dec = comutils.ang_normalize(ang - self.calibration[CALIIDX_DEC])
        nx = mag * math.cos(math.radians(ang_ra ))
        ny = mag * math.cos(math.radians(ang_dec))
        pulse_ra_ori  = nx * self.calibration[CALIIDX_RA ].ms_per_pix
        pulse_dec_ori = ny * self.calibration[CALIIDX_DEC].ms_per_pix
        pulse_ra_abs  = abs(pulse_ra_ori)
        pulse_dec_abs = abs(pulse_dec_ori)
        self.pulse_sum += pulse_ra_abs + pulse_dec_abs
        ret = max(pulse_ra_abs, pulse_dec_abs)
        if ret > 0 && ret <= 1:
            ret = 1
        pulse_ra_fin  = self.backlash_ra.filter(pulse_ra_ori)
        pulse_dec_fin = self.backlash_dec.filter(pulse_dec_ori)
        self.pulser.move(pulse_ra_fin, pulse_dec_fin, self.settings["move_grace"])
        return ret

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