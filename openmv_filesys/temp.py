    def send_settings(self):
        obj = {}
        obj.update({"packet_type", "settings"})
        for k in self.settings.keys():
            obj.update({k, self.settings[k]})
        self.send_websocket(obj)

    def get_state_obj(self):
        state = {}
        state.update({"packet_type", "state"})
        state.update({"time": self.time_mgr.get_sec()})
        if self.websock_randid != 0:
            state.update({"rand_id": self.websock_randid})
        state.update({"guider_state": self.guide_state})
        state.update({"intervalometer_state": self.intervalometer_state})
        if self.img is not None and self.cam_err <= 0:
            state.update({"expo_code": self.expo_code})
        elif self.img is None:
            state.update({"expo_code": star_finder.EXPO_NO_IMG})
        elif self.cam_err > 0:
            state.update({"expo_code": star_finder.EXPO_CAMERA_ERR})
        else:
            state.update({"expo_code": self.expo_code})
        if self.img_stats is not None:
            state.update({"img_mean":  self.img_stats.mean()})
            state.update({"img_stdev": self.img_stats.stdev()})
            state.update({"img_max":   self.img_stats.max()})
            state.update({"img_min":   self.img_stats.min()})
        if self.stars is not None:
            star_list = self.stars
            star_cnt_limit = 50
            if len(star_list) > star_cnt_limit:
                star_list = star_list[0:star_cnt_limit]
            state.update({"stars": blobstar.to_jsonobj(star_list)})
        else:
            state.update({"stars": []})
        if self.selected_star is not None:
            state.update({"selected_star", [self.selected_star.cx, self.selected_star.cy]})
            state.update({"selected_star_profile", self.selected_star.profile})
        else:
            state.update({"selected_star", False})
        if self.target_coord is not None:
            state.update({"target_coord", self.target_coord})
        else:
            state.update({"target_coord", False})
        if self.origin_coord is not None:
            state.update({"origin_coord", self.origin_coord})
        else:
            state.update({"origin_coord", False})
        if self.calibration[CALIIDX_RA] is not None:
            state.update({"calib_ra", self.calibration[CALIIDX_RA].get_json_obj()})
        else:
            state.update({"calib_ra", False})
        if self.calibration[CALIIDX_DEC] is not None:
            state.update({"calib_dec", self.calibration[CALIIDX_DEC].get_json_obj()})
        else:
            state.update({"calib_dec", False})
        state.update({"logs": self.get_logs_obj()})
        return state

    def get_logs_obj(self):
        obj = {}
        i = 0
        while i < LOG_BUFF_LEN:
            msglog   = self.msglog_buff[i]
            pulselog = self.pulselog_buff[i]
            obj.update({("msg_tick_%u" % i)   : msglog[0]})
            obj.update({("msg_time_%u" % i)   : msglog[1]})
            obj.update({("msg_str_%u"  % i)   : msglog[2]})
            obj.update({("pulse_time_%u" % i) : pulselog[0]})
            obj.update({("pulse_ra_%u"   % i) : pulselog[1]})
            obj.update({("pulse_dec_%u"  % i) : pulselog[2]})
            obj.update({("pulse_sum_%u"  % i) : pulselog[3]})
            i += 1
        return obj

    def send_state(self):
        obj = self.get_state_obj()
        self.send_websocket(obj)

    def send_logs(self):
        obj = self.get_logs_obj()
        obj.update({"packet_type": "logs"})
        self.send_websocket(obj)

    def send_websocket(self, obj):
        if self.websock is None:
            return
        json_str = ujson.dumps(obj)
        self.websock.settimeout(10)
        try:
            self.portal.websocket_send(self.websock, json_str)
            self.stream_sock_err = 0
            self.websock_millis = pyb.millis()
        except Exception as exc:
            self.stream_sock_err += 1
            if self.stream_sock_err > 5:
                if self.debug:
                    print("websock too many errors")
                exclogger.log_exception(exc, to_file=False)
                self.kill_websocket()
            pass

    def check_websocket(self):
        if self.websock is None:
            return
        try:
            rep = captive_portal.websocket_readmsg(self.websock)
            self.websock.settimeout(0.1)
            if rep is None:
                return False
            if len(rep) <= 0:
                return False
        except:
            return False
        self.stream_sock_err = 0
        self.websock_millis = pyb.millis()
        try:
            self.parse_websocket(rep)
        except Exception as exc:
            exclogger.log_exception(exc, to_file=False)
        return True

    def parse_websocket(self, x):
        obj = ujson.loads(x)
        pkt_type = obj["packet_type"]
        if pkt_type == "guide_cmd":
            v = comutils.try_parse_setting(obj["cmd"])
            self.guide_cmd(v)
        elif pkt_type == "intervalometer_cmd":
            v = comutils.try_parse_setting(obj["cmd"])
            self.intervalometer_cmd(v)
        elif pkt_type == "misc_cmd":
            self.misc_cmd(obj["cmd"])
        elif pkt_type == "settings":
            child = obj["settings"]
            need_save = False
            for k in child.keys():
                v = child[k]
                vv = comutils.try_parse_setting(v)
                if k in self.settings:
                    need_save = True
                    self.settings[k] = vv
                    if self.debug:
                        print("setting \"%s\" => value \"%s\"" % (k, str(vv)))
                if k == "time":
                    self.time_mgr.set_utc_time_epoch(vv)
                    if self.has_time == False:
                        exclogger.log_exception("Time Obtained (%u)" % pyb.millis(), time_str=comutils.fmt_time(self.time_mgr.get_time()))
                    self.has_time = True
                elif k == "use_debug":
                    self.debug = vv
                elif k == "rand_id":
                    self.websock_randid = vv
            self.apply_settings()
            if need_save:
                self.save_settings()

    def apply_settings(self):
        self.backlash_ra.hysteresis  = v = self.settings["backlash_hyster"]
        self.backlash_dec.hysteresis = v
        self.backlash_ra.max_limit   = v = self.settings["backlash_limit"]
        self.backlash_dec.max_limit  = v
        self.backlash_ra.reduction   = v = self.settings["backlash_reduc"]
        self.backlash_dec.reduction  = v
        self.backlash_ra.hard_lock   = v = self.settings["backlash_lock"]
        self.backlash_dec.hard_lock  = v

    def save_settings(self, filename = "settings.json"):
        if self.debug:
            print("save_settings")
        with open(filename, mode="wb") as f:
            ujson.dump(self.settings, f)

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
            if self.hotpixels is not None and self.use_hotpixels:
                stars = star_finder.filter_hotpixels(stars, self.hotpixels)
            stars = blobstar.sort_rating(stars)
            self.expo_code = code
            if code != star_finder.EXPO_JUST_RIGHT or len(stars) <= 0:
                self.expo_err += 1
                if self.debug:
                    print("exposure error %u %u" % (code, len(stars)))
                if self.expo_err > self.settings["panicthresh_expoerr"]:
                    self.panic(msg = "too many exposure errors")
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
                    self.panic(msg = "movement analysis score too low %f" % score)

                if self.guide_state == GUIDESTATE_GUIDING:
                    if self.selected_star is None:
                        self.log_msg("WARN: guidance requested without selected star")
                        self.guide_state = GUIDESTATE_IDLE:
                        return
                    if self.calibration[CALIIDX_RA] is None:
                        self.log_msg("WARN: guidance requested without RA calibration")
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
                            print("dithering too much error")
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
                        if self.digital_intervalometer:
                            print("!SHUTTER!")
                    return decided_pulse
                elif self.guide_state == GUIDESTATE_CALIBRATING_RA or self.guide_state == GUIDESTATE_CALIBRATING_DEC:
                    self.backlash_ra.neutralize()
                    self.backlash_dec.neutralize()
                    if self.selected_star is None:
                        self.log_msg("WARN: calibration requested without selected star")
                        self.guide_state = GUIDESTATE_IDLE:
                        return
                    if self.virtual_star is None:
                        self.virtual_star = [self.selected_star.cx, self.selected_star.cy]
                    if self.guide_state == GUIDESTATE_CALIBRATING_RA:
                        i = CALIIDX_RA
                        dir = "RA"
                    else:
                        i = CALIIDX_DEC
                        dir = "DEC"
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
                            self.calibration[i].timestamp = self.time_mgr.get_sec()
                            msg = "calibration of %s done, angle = %0.1f , dist = %0.1f" % (dir, self.calibration[i].angle, self.calibration[i].farthest)
                            self.log_msg("SUCCESS: " + msg)
                        else:
                            msg = "calibration of %s failed" % (dir)
                            self.log_msg("FAILED: " + msg)
                            self.calibration[i] = None
                    else:
                        decided_pulse = self.calibration[i].pulse_width
                        if self.guide_state == GUIDESTATE_CALIBRATING_RA:
                            self.pulser.move(decided_pulse, 0, self.settings["move_grace"])
                        else:
                            self.pulser.move(0, decided_pulse, self.settings["move_grace"])
                        self.stop_time = self.pulser.get_stop_time()
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
        self.log_pulse(nx, ny)
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
            self.stop_time = self.pulser.get_stop_time()
            return ret
        return 0

    def log_pulse(self, nx, ny):
        timestamp = self.img.timestamp()
        self.pulselog_buff[self.pulselog_buff_idx][0] = timestamp
        self.pulselog_buff[self.pulselog_buff_idx][1] = nx
        self.pulselog_buff[self.pulselog_buff_idx][2] = ny
        self.pulselog_buff[self.pulselog_buff_idx][3] = self.pulse_sum
        if self.pulser.is_shutter_open() == False or self.queue_shutter_closed:
            self.pulselog_buff[self.pulselog_buff_idx][4] = 0
            self.queue_shutter_closed = False
            # queue_shutter_closed is used to guarantee at least a small gap in the graph
        else:
            self.pulselog_buff[self.pulselog_buff_idx][4] = 1
        self.pulselog_buff_idx += 1
        self.pulselog_buff_idx %= LOG_BUFF_LEN

    def log_msg(self, msg, to_print=True):
        self.time_mgr.tick()
        timestamp = self.time_mgr.latest_millis
        self.msglog_buff[self.msglog_buff_idx][0] = timestamp
        self.msglog_buff[self.msglog_buff_idx][1] = self.time_mgr.get_sec()
        self.msglog_buff[self.msglog_buff_idx][2] = msg
        self.msglog_buff_idx += 1
        self.msglog_buff_idx %= LOG_BUFF_LEN
        if to_print:
            if self.has_time:
                tstr = comutils.fmt_time(self.time_mgr.get_time())
            else:
                tstr = str(timestamp)
            print("msg[%s]: %s" % (tstr, msg))

    def reset_guiding(self):
        self.backlash_ra.neutralize()
        self.backlash_dec.neutralize()
        self.selected_star   = None
        self.prev_stars      = None
        self.target_origin   = None
        self.target_final    = None

    def panic(self, msg = None):
        if msg is not None:
            self.log_msg("PANIC: " + msg)
        if self.guiding_state != GUIDESTATE_IDLE:
            self.guiding_state = GUIDESTATE_PANIC
            self.pulser.panic(True)
        self.reset_guiding()

    def user_select_star(self, x, y, tol = 100):
        if x < 0 or y < 0:
            self.guide_state = GUIDESTATE_IDLE
            self.pulser.panic(False)
            self.selected_star = None
            self.target_coord = None
            self.origin_coord = None
            self.log_msg("MSG: deselected star")
        if self.stars is None:
            self.log_msg("ERR: no star list for selection")
            return False
        if len(self.stars) <= 0:
            self.log_msg("ERR: no stars in the list for selection")
            return False
        nearest = None
        nearest_dist = 9999
        for i in self.stars:
            mag = comutils.vector_between([x, y], [i.cx, i.cy], mag_only=True)
            if mag < nearest_dist:
                nearest_dist = mag
                nearest = i
        if nearest_dist <= tol:
            self.selected_star = nearest
            self.log_msg("SUCCESS: selected star at [%u , %u]" % (self.selected_star.cx, self.selected_star.cy))
            self.target_coord = [self.selected_star.cx, self.selected_star.cy]
            self.origin_coord = self.target_coord
            return True
        else:
            self.log_msg("FAILED: cannot select star at [%u , %u]" % (x, y))
            return False

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
            self.log_msg("ERR: guidecam init failed")
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
                if self.cam.snapshot_check():
                    return True
                elif pyb.elapsed_millis(self.snap_millis) > (self.cam.get_timespan() + 500):
                    self.cam_err += 1
                    self.log_msg("WARN: camera timeout")
                    exclogger.log_exception("warning: camera timeout", time_str=comutils.fmt_time(self.time_mgr.get_time()))
                    return False

    def task(self):
        self.time_mgr.tick()
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
                    else:
                        self.log_msg("ERR: guidecam failed to read image during wait")
        else:
            self.log_msg("ERR: guidecam failed to read image")

    def task_pulser(self):
        self.pulser.task()
        gap_time = self.settings["intervalometer_gap_time"]
        if gap_time <= 1000:
            gap_time = 1000
        if self.pulser.is_shutter_open() == False:
            self.pulse_sum = 0
            self.queue_shutter_closed = True
            # queue_shutter_closed is used to guarantee at least a small gap in the graph
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
                    if self.digital_intervalometer:
                        print("!SHUTTER!")
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

    def guide_cmd(self, cmd):
        if cmd == GUIDESTATE_GUIDING:
            if self.guide_state != GUIDESTATE_IDLE and self.guide_state != GUIDESTATE_PANIC:
                self.log_msg("ERR: invalid moment to start autoguiding")
                return
            self.pulser.panic(False)
            if self.selected_star is None:
                self.log_msg("ERR: no selected star to start autoguiding")
                return
            self.guide_state = GUIDESTATE_GUIDING
            self.log_msg("CMD: auto-guidance starting")
        elif cmd == GUIDESTATE_CALIBRATING_RA or cmd == GUIDESTATE_CALIBRATING_DEC:
            if self.guide_state != GUIDESTATE_IDLE and self.guide_state != GUIDESTATE_PANIC:
                self.log_msg("ERR: invalid moment to start calibration")
                return
            self.pulser.panic(False)
            if self.selected_star is None:
                self.log_msg("ERR: no selected star to start calibration")
                return
            if cmd == GUIDESTATE_CALIBRATING_RA:
                cstr = "RA"
                self.calibration[CALIIDX_RA] = None
            elif cmd == GUIDESTATE_CALIBRATING_DEC:
                cstr = "DEC"
                self.calibration[CALIIDX_DEC] = None
            self.guide_state = cmd
            self.log_msg("CMD: starting calibration of " + cstr)
        elif cmd == GUIDESTATE_IDLE:
            self.pulser.panic(False)
            self.guide_state = cmd
            self.log_msg("CMD: autoguider is now idle")

    def intervalometer_cmd(self, cmd):
        if cmd == INTERVALSTATE_ACTIVE or cmd == INTERVALSTATE_ACTIVE_DITHER:
            self.intervalometer_state = cmd
            self.shutter(self.settings["intervalometer_bulb_time"])
            self.intervalometer_timestamp = 0
            self.pulse_sum = 0
            self.log_msg("CMD: intervalometer activated")
        elif cmd == INTERVALSTATE_BULB_TEST:
            self.pulser.shutter(self.settings["intervalometer_bulb_time"])
            self.intervalometer_timestamp = 0
            self.pulse_sum = 0
            self.log_msg("CMD: bulb test")
            self.intervalometer_state = INTERVALSTATE_ACTIVE_ENDING
        elif cmd == INTERVALSTATE_ACTIVE_ENDING:
            self.intervalometer_state = cmd
            self.log_msg("CMD: intervalometer ending on next shutter close")
        elif cmd == INTERVALSTATE_ACTIVE_HALT:
            self.pulser.shutter_halt()
            self.intervalometer_state = INTERVALSTATE_IDLE
            self.log_msg("CMD: intervalometer halting")

    def misc_cmd(self, cmd):
        if cmd == "echo":
            self.log_msg("CMD: echo")
        elif cmd == "getstate":
            self.send_state()
        elif cmd == "getsettings":
            self.send_settings()
        elif cmd == "calib_reset":
            self.calibration[0] = None
            self.calibration[1] = None
            self.pulser.panic(False)
            self.guide_state = cmd
            self.log_msg("CMD: all calibration reset")
        elif cmd == "calib_load":
            try:
                with open("calib_ra.json", mode="rb") as f:
                    obj = ujson.load(f)
                    if self.calibration[CALIIDX_RA] is None:
                        self.calibration[CALIIDX_RA] = guider_calibration.GuiderCalibration(0, 0, 0)
                    self.calibration[CALIIDX_RA].load_json_obj(obj)
                    self.log_msg("SUCCESS: loaded RA calibration from file")
            except Exception as exc:
                self.log_msg("FAILED: cannot load RA calibration from file")
                exclogger.log_exception(exc)
            try:
                with open("calib_dec.json", mode="rb") as f:
                    obj = ujson.load(f)
                    if self.calibration[CALIIDX_DEC] is None:
                        self.calibration[CALIIDX_DEC] = guider_calibration.GuiderCalibration(0, 0, 0)
                    self.calibration[CALIIDX_RA].load_json_obj(obj)
                    self.log_msg("SUCCESS: loaded DEC calibration from file")
            except Exception as exc:
                self.log_msg("FAILED: cannot load DEC calibration from file")
                exclogger.log_exception(exc)
        elif cmd == "calib_save":
            if self.calibration[CALIIDX_RA] is None:
                self.log_msg("ERR: RA calibration not available for saving")
            else:
                try:
                    with open("calib_ra.json", mode="wb") as f:
                        ujson.dump(self.calibration[CALIIDX_RA].get_json_obj(), f)
                    self.log_msg("SUCCESS: saved RA calibration to file")
                except Exception as exc:
                    self.log_msg("FAILED: cannot save RA calibration to file")
                    exclogger.log_exception(exc)
            if self.calibration[CALIIDX_DEC] is None:
                self.log_msg("ERR: DEC calibration not available for saving")
            else:
                try:
                    with open("calib_dec.json", mode="wb") as f:
                        ujson.dump(self.calibration[CALIIDX_DEC].get_json_obj(), f)
                    self.log_msg("SUCCESS: saved DEC calibration to file")
                except Exception as exc:
                    self.log_msg("FAILED: cannot save DEC calibration to file")
                    exclogger.log_exception(exc)
        elif cmd == "hotpixels_save":
            if self.hotpixels is not None:
                if len(self.hotpixels) > 0 and self.use_hotpixels:
                    self.log_msg("ERR: cannot overwrite current hot-pixels, please clear or disable the hot-pixel list first")
                    return
            if self.stars is None:
                self.log_msg("ERR: cannot save current hot-pixels, the star list does not exist")
                return
            encoded = star_finder.encode_hotpixels(self.stars)
            self.hotpixels = star_finder.decode_hotpixels(encoded)
            try:
                with open("hotpixels.txt", mode="w") as f:
                    f.write(encoded)
                self.log_msg("SUCCESS: saved hot-pixels to file")
            except Exception as exc:
                self.log_msg("FAILED: cannot save hot-pixels to file")
                exclogger.log_exception(exc)
        elif cmd == "hotpixels_load":
            try:
                with open("hotpixels.txt", mode="rt") as f:
                    encoded = f.read()
                    self.hotpixels = star_finder.decode_hotpixels(encoded)
                    self.use_hotpixels = True
                    self.log_msg("SUCCESS: loaded hot-pixels from file")
            except Exception as exc:
                self.log_msg("FAILED: cannot load hot-pixels from file")
                exclogger.log_exception(exc)
        elif cmd == "hotpixels_use":
            if self.hotpixels is None:
                self.log_msg("ERR: cannot use hot-pixels, the hot-pixel list does not exist")
                return
            self.use_hotpixels = True
            self.log_msg("SUCCESS: hot-pixels are being used")
        elif cmd == "hotpixels_disable":
            if self.use_hotpixels == False:
                self.log_msg("ERR: hot-pixel usage already disabled")
                return
            self.use_hotpixels = False
            self.log_msg("SUCCESS: hot-pixels are disabled")
        elif cmd == "hotpixels_clear":
            if self.hotpixels is None:
                self.log_msg("ERR: cannot clear hot-pixels, the hot-pixel list already does not exist")
                return
            self.hotpixels = None
            self.log_msg("SUCCESS: hot-pixels list deleted")

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
        self.portal.install_handler("/websocket",      self.handle_websocket)
        self.portal.install_handler("/memory",         self.handle_memory)