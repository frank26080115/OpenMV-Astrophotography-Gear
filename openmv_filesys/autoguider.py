import micropython
micropython.opt_level(2)

import comutils
import blobstar, astro_sensor, time_location, captive_portal, star_finder, guider_calibration, backlash_mgr, guide_filter
import guidepulser
import guidestar
import exclogger
import pyb, uos, uio, gc, sys, machine
import time, math, ujson, ubinascii
import network
import sensor, image

red_led   = pyb.LED(1)
green_led = pyb.LED(2)
blue_led  = pyb.LED(3)
ir_leds   = pyb.LED(4)

LOG_BUFF_LEN        = micropython.const(3)
STAR_CNT_JSON_LIMIT = micropython.const(100)
WIFI_HW_RETRIES     = micropython.const(5)

GUIDESTATE_IDLE              = micropython.const(0)
GUIDESTATE_GUIDING           = micropython.const(1)
GUIDESTATE_DITHER            = micropython.const(2)
GUIDESTATE_PANIC             = micropython.const(3)
GUIDESTATE_CALIBRATING_RA    = micropython.const(4)
GUIDESTATE_CALIBRATING_DEC   = micropython.const(5)

INTERVALSTATE_IDLE           = micropython.const(0)
INTERVALSTATE_ACTIVE         = micropython.const(1)
INTERVALSTATE_ACTIVE_GAP     = micropython.const(2)
INTERVALSTATE_BULB_TEST      = micropython.const(3)
INTERVALSTATE_HALT           = micropython.const(4)
INTERVALSTATE_ENDING         = micropython.const(5)
INTERVALSTATE_SINGLE_ENDING  = micropython.const(6)

CALIIDX_RA  = micropython.const(0)
CALIIDX_DEC = micropython.const(1)

class AutoGuider(object):

    def __init__(self, debug = False, simulate_file = None, simulate = False):
        #gc.disable()
        exclogger.init()
        guidepulser.init()
        self.cam = astro_sensor.AstroCam(simulate = simulate_file)
        try:
            self.cam.init(gain_db = 48, shutter_us = 1000000)
        except OSError as exc:
            exclogger.log_exception(exc)
            guidepulser.panic(True)
            self.cam = None
            print("ERROR: guidecam cannot initialize, serious HW error, must reboot")

        self.cam_initing = 0
        self.time_mgr = time_location.TimeLocationManager()
        self.has_time = False

        self.debug = debug

        self.guide_state = GUIDESTATE_IDLE
        self.intervalometer_state = INTERVALSTATE_IDLE
        self.intervalometer_timestamp = 0
        self.selected_star = None
        self.target_coord = None
        self.origin_coord = None
        self.passive_guiding = False

        if simulate_file is not None or simulate:
            import guider_sim
            self.simulator = guider_sim.GuiderSimulator()
        else:
            self.simulator = None

        self.pulse_sum = 0
        self.queue_shutter_closed = True
        if guidepulser.get_hw_err() > 0:
            print("ERROR: I2C hardware failure")

        self.calibration    = [None, None]
        self.backlash_ra    = backlash_mgr.BacklashManager()
        self.backlash_dec   = backlash_mgr.BacklashManager()
        self.advfilt_ra     = guide_filter.GuideFilter("ra" , "advfilt")
        self.advfilt_dec    = guide_filter.GuideFilter("dec", "advfilt")
        self.preempfilt_ra  = guide_filter.GuideFilter("ra" , "preempfilt")
        self.preempfilt_dec = guide_filter.GuideFilter("dec", "preempfilt")

        self.cam_err = 0
        self.expo_err = 0
        self.hw_err = 0
        self.prev_panic = ""
        self.panic_move_cnt = 0
        self.last_move_err = 0
        self.snap_millis = 0
        self.stop_time = 0
        self.last_pulse_dur = 0
        self.analysis_dur = [0, 0, 0, 0, 0]
        self.dbg_t1 = 0
        self.dbg_t2 = 0
        self.dbg_t3 = 0
        self.dbg_t4 = 0
        self.hotpixels_eff = 0
        self.queue_imgsave = 0
        self.save_image_name = None
        self.save_image_dir  = None
        self.testpulse_dir = None

        self.settings = {}
        self.default_settings()
        self.load_settings()
        self.load_hotpixels(use_log = False, set_usage = False)

        self.portal = captive_portal.CaptivePortal(debug = self.debug)
        self.portal.allow_hw_kick = False
        if self.portal is not None:
            self.register_http_handlers()

        self.img = None
        self.img_compressed = None
        self.extra_fb = None
        self.expo_code = 0
        self.histogram = None
        self.img_stats = None
        self.stars = None
        self.prev_stars = None
        self.hotpixels = []
        self.multistar_cnt = [0, 0]
        self.zoom = 1
        self.dither_interval = 0

        self.imgstream_sock = None
        self.websock = None
        self.websock_millis = 0
        self.websock_randid = 0
        self.stream_sock_err = 0
        self.session_randid = 0
        self.need_send_stars = False

        self.pulselog_buff = [[0, 0, 0, 0, 0]] * LOG_BUFF_LEN
        self.msglog_buff   = [[0, 0, None]] * LOG_BUFF_LEN
        self.pulselog_buff_idx = 0
        self.msglog_buff_idx   = 0

    def default_settings(self):
        self.settings.update({"guidecam_gain"            : self.cam.gain})
        self.settings.update({"guidecam_shutter"         : self.cam.shutter // 1000})
        self.settings.update({"guidecam_thresh"          : 0})
        self.settings.update({"motionwhilecapture"       : 25})
        self.settings.update({"use_hotpixels"            : False})
        self.settings.update({"panicthresh_expoerr"      : 3})
        self.settings.update({"panicthresh_move_err"     : 50})
        self.settings.update({"panicthresh_move_cnt"     : 2})
        self.settings.update({"starmove_correctrequired" : 50})
        self.settings.update({"dither_amount"            : 0})
        self.settings.update({"dither_amount"            : 0})
        self.settings.update({"dither_interval"          : 1})
        self.settings.update({"dither_calmness"          : 3})
        self.settings.update({"dither_calm_cnt"          : 3})
        self.settings.update({"dither_frames_cnt"        : 5})
        self.settings.update({"intervalometer_bulb_time" : 30})
        self.settings.update({"intervalometer_gap_time"  : 2})
        self.settings.update({"intervalometer_digital"   : False})
        self.settings.update({"calibration_pulse_ra"     : 750})
        self.settings.update({"calibration_pulse_dec"    : 750})
        self.settings.update({"calib_points_cnt"         : 10})
        self.settings.update({"correction_scale_ra"      : 100})
        self.settings.update({"correction_scale_dec"     : 100})
        self.settings.update({"move_grace"               : 50})
        self.settings.update({"flip_ra"                  : 0})
        self.settings.update({"flip_dec"                 : 0})
        self.settings.update({"min_pulse_wid"            : 50})
        self.settings.update({"max_pulse_wid"            : (self.cam.shutter // 1000) - 100})
        self.settings.update({"net_quiet_time"           : 100})
        self.settings.update({"backlash_hyster_ra"       : 0})
        self.settings.update({"backlash_hyster_dec"      : 500})
        self.settings.update({"backlash_limit_ra"        : 0})
        self.settings.update({"backlash_limit_dec"       : 1000})
        self.settings.update({"backlash_reduc_ra"        : 0})
        self.settings.update({"backlash_reduc_dec"       : 0})
        self.settings.update({"backlash_lock_ra"         : False})
        self.settings.update({"backlash_lock_dec"        : False})
        self.settings.update({"multistar_cnt_min"        : 1})
        self.settings.update({"multistar_cnt_max"        : 10})
        self.settings.update({"multistar_ratings_thresh" : 50})
        self.settings.update({"starmove_tolerance"       : 50})
        self.settings.update({"clustering_tolerance"     : 100})
        self.settings.update({"use_led"                  : True})
        self.settings.update({"fast_mode"                : True})
        self.settings.update({"always_guiding"           : False})
        self.advfilt_ra    .fill_settings(self.settings)
        self.advfilt_dec   .fill_settings(self.settings)
        self.preempfilt_ra .fill_settings(self.settings)
        self.preempfilt_dec.fill_settings(self.settings)

    def send_settings(self):
        obj = {}
        obj.update({"pkt_type": "settings"})
        for k in self.settings.keys():
            obj.update({k: self.settings[k]})
        self.send_websocket(obj)

    def get_state_obj(self):
        state = {}
        state.update({"pkt_type"            : "state"})
        state.update({"time"                : self.time_mgr.get_sec()})
        state.update({"session_rand_id"     : self.session_randid})
        state.update({"ws_rand_id"          : self.websock_randid})
        state.update({"guide_state"         : self.guide_state})
        state.update({"interval_state"      : self.intervalometer_state})
        state.update({"blub_remaining"      : guidepulser.shutter_remaining()})
        state.update({"dither_interval"     : self.dither_interval})
        if self.cam.check_init() == False:
            state.update({"expo_code": star_finder.EXPO_NOT_READY})
        elif self.img is not None and self.cam_err <= 0:
            state.update({"expo_code": self.expo_code})
        elif self.img is None:
            state.update({"expo_code": star_finder.EXPO_NO_IMG})
        elif self.cam_err > 0:
            state.update({"expo_code": star_finder.EXPO_CAMERA_ERR})
        else:
            state.update({"expo_code": self.expo_code})
        if self.img_stats is not None:
            state.update({"img"      : True})
            state.update({"img_mean" : self.img_stats.mean()})
            state.update({"img_stdev": self.img_stats.stdev()})
            state.update({"img_max"  : self.img_stats.max()})
            state.update({"img_min"  : self.img_stats.min()})
        else:
            state.update({"img"      : False})

        # star list can be sent here but there's a huge risk of memory allocation error if the list is long
        # problem is solved by sending it separately, in small chunks
        if self.stars is not None:
            if len(self.stars) <= STAR_CNT_JSON_LIMIT:
                x = ""
                for i in self.stars:
                    x += guidestar_to_str(i)
                state.update({"stars": x})
                self.need_send_stars = False
            else:
                state.update({"stars": False})
                self.need_send_stars = True
        else:
            state.update({"stars": None})
            self.need_send_stars = False

        if self.selected_star is not None:
            state.update({"sel_star"        : self.selected_star.coord()})
            state.update({"sel_star_profile": self.selected_star.star_profile()})
        else:
            state.update({"sel_star": None})
        state.update({"tgt_coord": self.target_coord})
        state.update({"ori_coord": self.origin_coord})
        state.update({"last_move_err": self.last_move_err})
        state.update({"multistar_cnt": self.multistar_cnt})
        state.update({"calib_ra" : self.calibration[CALIIDX_RA] .get_json_obj(short = self.guide_state != GUIDESTATE_IDLE) if self.calibration[CALIIDX_RA]  is not None else None})
        state.update({"calib_dec": self.calibration[CALIIDX_DEC].get_json_obj(short = self.guide_state != GUIDESTATE_IDLE) if self.calibration[CALIIDX_DEC] is not None else None})
        if self.hotpixels is not None:
            state.update({"hotpix"     : True})
            state.update({"hotpix_used": self.settings["use_hotpixels"]})
            state.update({"hotpix_cnt" : len(self.hotpixels)})
            state.update({"hotpix_last": self.hotpixels_eff})
        else:
            state.update({"hotpix"     : False})
        state.update({"logs"        : self.get_logs_obj()})
        state.update({"hw_err"      : self.hw_err})
        state.update({"analysis_dur": self.analysis_dur})
        return state

    def get_logs_obj(self):
        obj = {}
        i = 0
        while i < LOG_BUFF_LEN:
            msglog   = self.msglog_buff[i]
            pulselog = self.pulselog_buff[i]
            obj.update({("msg_tick_%u"   % i) : msglog[0]})
            obj.update({("msg_time_%u"   % i) : msglog[1]})
            obj.update({("msg_str_%u"    % i) : msglog[2]})
            obj.update({("pulse_time_%u" % i) : pulselog[0]})
            obj.update({("pulse_ra_%u"   % i) : pulselog[1]})
            obj.update({("pulse_dec_%u"  % i) : pulselog[2]})
            obj.update({("pulse_sum_%u"  % i) : pulselog[3]})
            obj.update({("pulse_shutter_%u" % i) : pulselog[4]})
            i += 1
        return obj

    def send_state(self):
        if self.websock is None:
            return
        obj = self.get_state_obj()
        self.send_websocket(obj)

    def send_stars(self):
        if self.websock is None:
            return
        estimated_len = len(self.stars) if self.stars is not None else 0
        estimated_len *= 26 # worst-case length per star
        headstr = "{\"pkt_type\":\"stars\",\"stars\":\""
        endstr  = "\"}"
        estimated_len += len(headstr) + len(endstr)
        remaining = estimated_len

        # this function sends websocket packet in chunks with an estimated length
        # this avoids potential memory allocation errors inside ujson if the star list is too big

        try:
            self.portal.websocket_send_start(self.websock, remaining, 0x81)
            self.websock.send(headstr)
            remaining -= len(headstr)

            for i in self.stars:
                x = guidestar_to_str(i)
                self.websock.send(x)
                remaining -= len(x)
            self.websock.send(endstr)
            remaining -= len(endstr)
            # pad the remaining with blank space
            x = " " * remaining
            self.websock.send(x)
            self.portal.tickle()
        except Exception as exc:
            self.stream_sock_err += 1
            if self.stream_sock_err > 5:
                if self.debug:
                    print("websock too many errors")
                exclogger.log_exception(exc, to_file=False)
                self.kill_websocket()
            pass

    def send_logs(self):
        if self.websock is None:
            return
        obj = self.get_logs_obj()
        obj.update({"pkt_type": "logs"})
        self.send_websocket(obj)

    def send_websocket(self, obj):
        if self.websock is None:
            return
        json_str = ujson.dumps(obj)
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
            self.websock.settimeout(0.1)
            rep = captive_portal.websocket_readmsg(self.websock)
            if rep is None:
                return False
            if len(rep) <= 0:
                return False
        except Exception as exc:
            #exclogger.log_exception(exc, to_file=False)
            return False
        self.stream_sock_err = 0
        self.websock_millis = pyb.millis()
        try:
            self.parse_websocket(rep)
        except Exception as exc:
            exclogger.log_exception(exc, to_file=False)
        return True

    def parse_websocket(self, x):
        if x == "ping":
            if self.debug:
                print("websock simple ping")
            return
        obj = ujson.loads(x)
        if "time" in obj:
            v = comutils.try_parse_setting(obj["time"])
            self.time_mgr.set_utc_time_epoch(v)
            if self.has_time == False:
                exclogger.log_exception("Time Obtained (%u)" % pyb.millis(), time_str=comutils.fmt_time(self.time_mgr.get_time()))
            self.has_time = True
        pkt_type = "unknown"
        if "pkt_type" in obj:
            pkt_type = obj["pkt_type"]
        if pkt_type == "guide_cmd":
            v = comutils.try_parse_setting(obj["cmd"])
            self.guide_cmd(v)
        elif pkt_type == "intervalometer_cmd":
            v = comutils.try_parse_setting(obj["cmd"])
            self.intervalometer_cmd(v)
        elif pkt_type == "misc_cmd":
            self.misc_cmd(obj["cmd"])
        elif pkt_type == "select_star":
            self.user_select_star(obj["star_x"], obj["star_y"])
        elif pkt_type == "settings":
            need_save = False
            for k in obj.keys():
                if k == "pkt_type":
                    continue
                v = obj[k]
                vv = comutils.try_parse_setting(v)
                if k in self.settings:
                    need_save = True
                    self.settings[k] = vv
                    if self.debug:
                        print("setting \"%s\" => value \"%s\"" % (k, str(vv)))
                elif k == "use_debug":
                    self.debug = vv
                elif k == "rand_id":
                    self.websock_randid = vv
            self.apply_settings()
            if need_save:
                self.save_settings()
        elif pkt_type == "ping":
            if self.debug:
                print("websock json ping")
        else:
            print("unknown websock pkt_type: " + pkt_type)

    def apply_settings(self):
        self.backlash_ra.hysteresis   = self.settings["backlash_hyster_ra"]
        self.backlash_dec.hysteresis  = self.settings["backlash_hyster_dec"]
        self.backlash_ra.max_limit    = self.settings["backlash_limit_ra"]
        self.backlash_dec.max_limit   = self.settings["backlash_limit_dec"]
        self.backlash_ra.reduction    = self.settings["backlash_reduc_ra"]
        self.backlash_dec.reduction   = self.settings["backlash_reduc_dec"]
        self.backlash_ra.hard_lock    = self.settings["backlash_lock_ra"]
        self.backlash_dec.hard_lock   = self.settings["backlash_lock_dec"]
        guidepulser.set_flip_ra (1 if self.settings["flip_ra" ] == 0 else -1)
        guidepulser.set_flip_dec(1 if self.settings["flip_dec"] == 0 else -1)
        self.advfilt_ra    .load_settings(self.settings)
        self.advfilt_dec   .load_settings(self.settings)
        self.preempfilt_ra .load_settings(self.settings)
        self.preempfilt_dec.load_settings(self.settings)
        if self.settings["use_led"]:
            guidepulser.enable_led()
        else:
            guidepulser.disable_led()

    def save_settings(self, filename = "settings_autoguider.json"):
        if self.debug:
            print("save_settings")
        with open(filename, mode="wb") as f:
            ujson.dump(self.settings, f)
            f.flush()
        uos.sync()
        uos.listdir()

    def decide(self):
        decided_pulse = 0
        if self.imgstream_sock is not None or self.img_is_compressed:
            self.guide_state = GUIDESTATE_IDLE
            return decided_pulse
        if self.img is not None:
            self.histogram = self.img.get_histogram()
            self.img_stats = self.histogram.get_statistics()
            latest_stars, code = star_finder.find_stars(self.img, hist = self.histogram, stats = self.img_stats, thresh = self.settings["guidecam_thresh"], force_solve = False, guider = True)
            self.dbg_t1 = pyb.millis()
            if self.simulator is not None:
                latest_stars = self.simulator.get_stars(self, latest_stars)
                pass

            hotpixels = self.hotpixels if self.hotpixels is not None and self.settings["use_hotpixels"] else None
            res = guidestar.process_list(latest_stars, self.settings["clustering_tolerance"], hotpixels, 2, self.settings["multistar_ratings_thresh"])
            self.hotpixels_eff = res[1] - res[2] # internally returned before and after lengths
            #self.prev_good_star_cnt = self.good_star_cnt
            #self.good_star_cnt = res[3]

            self.dbg_t2 = pyb.millis()

            self.expo_code = code
            if code != star_finder.EXPO_JUST_RIGHT or len(latest_stars) <= 0:
                self.expo_err += 1
                if self.debug:
                    print("exposure error %u %u" % (code, len(latest_stars)))
                if self.expo_err > self.settings["panicthresh_expoerr"]:
                    self.stars = []
                    self.panic(msg = "too many exposure errors")
                self.dither_calm = 0
                return decided_pulse
            else:
                # exposure is just right
                self.expo_err = 0
                min_stars_cnt = len(latest_stars)
                if self.prev_stars is not None:
                    prev_stars_cnt = len(self.prev_stars)
                    if prev_stars_cnt < min_stars_cnt:
                        min_stars_cnt = prev_stars_cnt
                    if self.simulator is None:
                        self.prev_stars = None
                        gc.collect()
                self.stars = latest_stars

                # motion can be detected if previous data is available
                # if previous data is unavailable, then just populate it for no motion
                if self.prev_stars is None:
                    self.prev_stars = latest_stars

                if self.selected_star is None and latest_stars is not None:
                    if len(latest_stars) > 0 and self.guide_state == GUIDESTATE_IDLE:
                        self.selected_star = guidestar.select_first(latest_stars)
                        if self.selected_star is not None:
                            self.log_msg("MSG: auto selected star at [%u , %u]" % (int(round(self.selected_star.cxf())), int(round(self.selected_star.cyf()))))

                res = guidestar.get_multi_star_motion(self.prev_stars, latest_stars, self.selected_star, self.settings["starmove_tolerance"], False, self.settings["multistar_ratings_thresh"], self.settings["multistar_cnt_min"], self.settings["multistar_cnt_max"])
                real_star    = res[0]
                virtual_star = [res[1], res[2]]
                move_err     = res[3]
                self.last_move_err = move_err
                self.multistar_cnt = [res[4], res[5]]

                if self.queue_imgsave == 2:
                    self.save_image_meta(res)

                stars_required = int(round((min_stars_cnt * self.settings["starmove_correctrequired"]) / 100))
                has_stars_required = (self.multistar_cnt[0] >= stars_required or stars_required < 8)

                lost = False
                self.dbg_t3 = pyb.millis()
                if self.selected_star is None and real_star is not None:
                    self.log_msg("MSG: auto selected star at [%u , %u]" % (int(round(real_star.cxf())), int(round(real_star.cyf()))))
                elif self.selected_star is not None and real_star is None:
                    if self.guide_state != GUIDESTATE_IDLE:
                        #self.log_msg("MSG: lost track of selected star")
                        pass
                    else:
                        self.log_msg("MSG: lost track of selected star")
                    lost = True
                self.selected_star = real_star
                self.virtual_star  = virtual_star
                # virtual star only matters if multi-star mode is used, it accounts for atmospheric distortion

                if self.debug:
                    print("dbg move err %u nb %u mcnt %u " % (move_err, res[4], res[5]), end="")
                    if real_star is not None:
                        print("rating %u" % real_star.star_rating())
                    else:
                        print("no star")

                if move_err > self.settings["panicthresh_move_err"] or move_err < 0 or has_stars_required == False or lost:
                    self.panic_move_cnt += 1
                    if self.panic_move_cnt >= self.settings["panicthresh_move_cnt"]:
                        if lost:
                            self.panic(msg = "lost track of the star")
                        elif has_stars_required == False:
                            self.panic(msg = "not enough correctly moved stars")
                        else:
                            self.panic(msg = "movement analysis had too much error")
                else:
                    self.panic_move_cnt = 0
                    self.prev_stars     = self.stars

                # passive guiding will cause the mount to autoguide even if not in a autoguiding state
                # this is useful for simulation and headless operation
                passive_guiding = False
                if self.guide_state == GUIDESTATE_IDLE:
                    if self.selected_star is not None and self.target_coord is not None and self.calibration[CALIIDX_RA] is not None:
                        if self.calibration[CALIIDX_RA].has_cal:
                            passive_guiding = self.settings["always_guiding"]
                if self.passive_guiding and passive_guiding == False:
                    self.log_msg("MSG: passive guiding ended")
                elif self.passive_guiding == False and passive_guiding:
                    self.log_msg("MSG: passive guiding started")
                self.passive_guiding = passive_guiding

                if self.testpulse_dir is not None:
                    if self.testpulse_dir == "n":
                        t = self.settings["calibration_pulse_dec"]
                        y = guidepulser.move(0, t, self.settings["move_grace"])
                        decided_pulse = t
                    elif self.testpulse_dir == "s":
                        t = self.settings["calibration_pulse_dec"]
                        y = guidepulser.move(0, -t, self.settings["move_grace"])
                        decided_pulse = t
                    elif self.testpulse_dir == "e":
                        t = self.settings["calibration_pulse_ra"]
                        y = guidepulser.move(t, 0, self.settings["move_grace"])
                        decided_pulse = t
                    elif self.testpulse_dir == "w":
                        t = self.settings["calibration_pulse_ra"]
                        y = guidepulser.move(-t, 0, self.settings["move_grace"])
                        decided_pulse = t
                    self.log_msg("MSG: test pulse \"%s\" %u" % (self.testpulse_dir.upper(), decided_pulse))
                    self.testpulse_dir = None
                    return decided_pulse

                if self.guide_state == GUIDESTATE_GUIDING or self.passive_guiding:
                    if self.selected_star is None:
                        if lost:
                            self.panic(msg = "guidance has lost track of selected star")
                            # note: previous panic should prevent this statement from being reached
                        else:
                            self.log_msg("WARN: guidance requested without selected star")
                            self.guide_state = GUIDESTATE_IDLE
                        return decided_pulse
                    if self.calibration[CALIIDX_RA] is None:
                        if self.calibration[CALIIDX_DEC] is None:
                            self.log_msg("WARN: guidance requested without calibration")
                        else:
                            self.log_msg("WARN: guidance requested without RA calibration")
                        self.guide_state = GUIDESTATE_IDLE
                        return decided_pulse
                    if self.target_coord is None:
                        self.target_coord = self.selected_star.coord()
                        if self.debug:
                            print("target coord auto-selected: (%0.1f , %0.2f)" % (self.target_coord[0], self.target_coord[1]))
                    if self.origin_coord is None:
                        self.origin_coord = self.target_coord
                        if self.debug:
                            print("origin coord auto-selected: (%0.1f , %0.2f)" % (self.origin_coord[0], self.origin_coord[1]))
                    if self.guide_state == GUIDESTATE_GUIDING and self.settings["dither_amount"] > 0 and self.intervalometer_state == INTERVALSTATE_ACTIVE:
                        self.task_pulser() # this will cause the shutter status to update, and the dither_interval counter to go up
                        if self.dither_interval >= self.settings["dither_interval"] and guidepulser.is_shutter_open() == False:
                            self.set_dither_coord()
                            if self.debug:
                                print("dithering coord: (%0.1f , %0.2f)" % (self.target_coord[0], self.target_coord[1]))
                            self.guide_state = GUIDESTATE_DITHER
                            self.dither_interval = 0
                            self.dither_calm = 0
                            self.dither_frames = 0
                            self.advfilt_ra.pause(True)
                            self.advfilt_dec.pause(True)
                            self.preempfilt_ra.pause(True)
                            self.preempfilt_dec.pause(True)
                    if self.guide_state == GUIDESTATE_GUIDING:
                        self.advfilt_ra.pause(False)
                        self.advfilt_dec.pause(False)
                        self.preempfilt_ra.pause(False)
                        self.preempfilt_dec.pause(False)
                    decided_pulse = self.pulse_to_target(force_move = (self.guide_state == GUIDESTATE_DITHER))
                    self.last_pulse_dur = decided_pulse
                    return decided_pulse
                elif self.guide_state == GUIDESTATE_DITHER:
                    if self.selected_star is None:
                        if lost:
                            self.panic(msg = "guidance has lost track of selected star during dithering")
                            # note: previous panic should prevent this statement from being reached
                        else:
                            self.log_msg("WARN: dithering without selected star")
                            self.guide_state = GUIDESTATE_IDLE
                        return decided_pulse
                    self.dither_frames += 1
                    self.advfilt_ra.pause(True)
                    self.advfilt_dec.pause(True)
                    self.preempfilt_ra.pause(True)
                    self.preempfilt_dec.pause(True)
                    decided_pulse = self.pulse_to_target(force_move = True)
                    self.last_pulse_dur = decided_pulse
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
                        self.target_coord = self.selected_star.coord() # retarget to prevent additional moves
                        if self.debug:
                            print("dither finished due to timeout")
                    if done_dither:
                        self.dither_interval = 0
                        self.guide_state = GUIDESTATE_GUIDING
                        self.backlash_ra.neutralize()
                        self.backlash_dec.neutralize()
                        self.advfilt_ra.pause(False)
                        self.advfilt_dec.pause(False)
                        self.preempfilt_ra.pause(False)
                        self.preempfilt_dec.pause(False)
                        guidepulser.shutter(self.settings["intervalometer_bulb_time"])
                        self.intervalometer_timestamp = 0
                        if self.settings["intervalometer_digital"]:
                            print("!SHUTTER!")
                    return decided_pulse
                elif self.guide_state == GUIDESTATE_CALIBRATING_RA or self.guide_state == GUIDESTATE_CALIBRATING_DEC:
                    self.backlash_ra.neutralize()
                    self.backlash_dec.neutralize()
                    self.advfilt_ra.pause(True)
                    self.advfilt_dec.pause(True)
                    self.preempfilt_ra.pause(True)
                    self.preempfilt_dec.pause(True)
                    if self.guide_state == GUIDESTATE_CALIBRATING_RA:
                        i = CALIIDX_RA
                        axis = "RA"
                    else:
                        i = CALIIDX_DEC
                        axis = "DEC"
                    if self.selected_star is None:
                        # note: previous panic should prevent this statement from being reached
                        if lost:
                            self.log_msg("ERR: calibration has lost track of selected star")
                        else:
                            self.log_msg("WARN: calibration without selected star")
                        if self.calibration[i] is not None:
                            self.calibration[i].success = "failed"
                        self.guide_state = GUIDESTATE_IDLE
                        return decided_pulse
                    if self.virtual_star is None:
                        self.virtual_star = self.selected_star.coord()
                    if self.calibration[i] is None:
                        pulse_width = self.settings["calibration_pulse_" + axis.lower()]
                        if pulse_width <= 0:
                            # use automatic mode
                            pulse_width = int(round(self.settings["guidecam_shutter"] * 0.9))
                        self.calibration[i] = guider_calibration.GuiderCalibration(virtual_star[0], virtual_star[1], pulse_width)
                    else:
                        self.calibration[i].append_pt(self.virtual_star)
                    if len(self.calibration[i].points) >= self.settings["calib_points_cnt"]:
                        self.guide_state = GUIDESTATE_IDLE
                        success = self.calibration[i].analyze()
                        if success:
                            self.calibration[i].timestamp = self.time_mgr.get_sec()
                            msg = "calibration of %s done, angle = %0.1f , dist = %0.1f" % (axis, self.calibration[i].angle, self.calibration[i].farthest)
                            self.log_msg("SUCCESS: " + msg)
                        else:
                            msg = "calibration of %s failed" % (axis)
                            self.log_msg("FAILED: " + msg)
                            self.calibration[i] = None
                    else:
                        decided_pulse = self.calibration[i].pulse_width
                        if self.guide_state == GUIDESTATE_CALIBRATING_RA:
                            self.stop_time = guidepulser.move(decided_pulse, 0, self.settings["move_grace"])
                        else:
                            self.stop_time = guidepulser.move(0, decided_pulse, self.settings["move_grace"])
                        self.last_pulse_dur = decided_pulse
                    return decided_pulse
                elif self.guide_state == GUIDESTATE_IDLE:
                    self.backlash_ra.neutralize()
                    self.backlash_dec.neutralize()
                    self.advfilt_ra.neutralize()
                    self.advfilt_dec.neutralize()
                    self.preempfilt_ra.neutralize()
                    self.preempfilt_dec.neutralize()
                    self.dither_interval = 0
                    if self.selected_star is None:
                        return decided_pulse
                    #if self.target_coord is None:
                    self.target_coord = self.selected_star.coord()
                    #if self.origin_coord is None:
                    self.origin_coord = self.target_coord
                return decided_pulse
        else:
            # self.img is None
            return decided_pulse

    def set_dither_coord(self):
        amt = int(round(self.settings["dither_amount"] * 10.0))
        nx = ((pyb.rng() % (amt * 2)) - amt) / 10.0
        ny = ((pyb.rng() % (amt * 2)) - amt) / 10.0
        self.target_coord = (self.origin_coord[0] + nx, self.origin_coord[1] + ny)

    def get_pulse_to_target(self):
        if self.calibration[CALIIDX_RA] is None:
            return None
        if self.target_coord is None or self.selected_star is None:
            return None
        if self.virtual_star is None:
            self.virtual_star = self.selected_star

        dx = self.target_coord[0] - self.virtual_star[0]
        dy = self.target_coord[1] - self.virtual_star[1]
        mag = math.sqrt((dx * dx) + (dy * dy))
        ang = math.degrees(math.atan2(dy, dx))
        ang_ra  = comutils.ang_normalize(ang - self.calibration[CALIIDX_RA ].angle)
        nx = mag * math.cos(math.radians(ang_ra))
        pulse_ra  = nx * self.calibration[CALIIDX_RA ].ms_per_pix
        if self.calibration[CALIIDX_DEC] is not None:
            ang_dec = comutils.ang_normalize(ang - self.calibration[CALIIDX_DEC].angle)
            ny = mag * math.cos(math.radians(ang_dec))
            pulse_dec = ny * self.calibration[CALIIDX_DEC].ms_per_pix
        else:
            # declination not calibrated
            ang_dec = 0
            ny = mag * math.sin(math.radians(ang_ra))
            pulse_dec = ny * self.calibration[CALIIDX_RA].ms_per_pix

        pulse_ra  *= self.settings["correction_scale_ra"]
        pulse_dec *= self.settings["correction_scale_dec"]
        pulse_ra  /= 100
        pulse_dec /= 100
        self.preempfilt_ra.filter(pulse_ra)
        self.preempfilt_dec.filter(pulse_dec)
        pulse_ra  = self.advfilt_ra.filter(pulse_ra)
        pulse_dec = self.advfilt_dec.filter(pulse_dec)
        return [pulse_ra, pulse_dec, nx, ny]

    def clamp_pulse(self, pulse, pul_abs, pul_min, pul_max):
        if pul_abs < pul_min * 0.75:
            pul_abs = 0
            pulse = 0
        elif pul_abs < pul_min:
            pul_abs = pul_min
            if pulse > 0:
                pulse = pul_min
            else:
                pulse = -pul_min
        if pul_abs > pul_max:
            pul_abs = pul_max
            if pulse > 0:
                pulse = pul_max
            else:
                pulse = -pul_max
        return pulse, pul_abs

    def pulse_to_target(self, pulse_data = None, force_move = False):
        if pulse_data is None:
            res = self.get_pulse_to_target()
            if res is None:
                return 0
        else:
            res = pulse_data
        pulse_ra = res[0]
        pulse_dec = res[1]
        if len(res) >= 4:
            nx = res[2]
            ny = res[3]
            print("corrective ", end="")
        else:
            nx = None
            ny = None
            print("preemptive ", end="")

        pulse_ra_abs  = abs(pulse_ra)
        pulse_dec_abs = abs(pulse_dec)
        self.pulse_sum += pulse_ra_abs + pulse_dec_abs
        t = pyb.millis()
        print("pulse %u %u %u %u" % (pyb.elapsed_millis(self.dbg_t4), pulse_ra, pulse_dec, self.pulse_sum))
        self.dbg_t4 = t
        if nx is not None and ny is not None:
            self.log_pulse(nx, ny)
        min_pulse_wid = self.settings["min_pulse_wid"]
        max_pulse_wid = self.settings["max_pulse_wid"]
        if min_pulse_wid < 5:
            min_pulse_wid = 5
        if max_pulse_wid < 5:
            max_pulse_wid = int(round(self.settings["guidecam_shutter"] * 0.9 - 300))
        pulse_ra , pulse_ra_abs  = self.clamp_pulse(pulse_ra , pulse_ra_abs , min_pulse_wid, max_pulse_wid)
        pulse_dec, pulse_dec_abs = self.clamp_pulse(pulse_dec, pulse_dec_abs, min_pulse_wid, max_pulse_wid)
        ret = max(pulse_ra_abs, pulse_dec_abs)
        if ret > 0 and ret <= 1:
            ret = 1
        pulse_ra_fin  = self.backlash_ra.filter(pulse_ra, force_move = force_move)
        if self.calibration[CALIIDX_DEC] is None:
            pulse_dec = 0
        pulse_dec_fin = self.backlash_dec.filter(pulse_dec, force_move = force_move)
        if pulse_ra_fin != 0 or pulse_dec_fin != 0:
            self.stop_time = guidepulser.move(pulse_ra_fin, pulse_dec_fin, self.settings["move_grace"])
            return ret
        return 0

    def preemp_pulse(self):
        if self.guide_state != GUIDESTATE_GUIDING:
            return 0
        if guidepulser.is_moving():
            return 0
        pulse_ra  = self.preempfilt_ra.get_preemp()
        pulse_dec = self.preempfilt_dec.get_preemp()
        x = 0
        if pulse_ra != 0 or pulse_dec != 0:
            x = self.pulse_to_target(pulse_data = [pulse_ra, pulse_dec])
        return x

    def log_pulse(self, nx, ny):
        timestamp = self.img.timestamp()
        self.pulselog_buff[self.pulselog_buff_idx][0] = timestamp
        self.pulselog_buff[self.pulselog_buff_idx][1] = nx
        self.pulselog_buff[self.pulselog_buff_idx][2] = ny
        self.pulselog_buff[self.pulselog_buff_idx][3] = self.pulse_sum
        if guidepulser.is_shutter_open() == False or self.queue_shutter_closed:
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
        for i in self.msglog_buff:
            if i[0] == timestamp:
                timestamp += 1
                break
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
        self.advfilt_ra.neutralize()
        self.advfilt_dec.neutralize()
        self.preempfilt_ra.neutralize()
        self.preempfilt_dec.neutralize()
        self.selected_star   = None
        self.prev_stars      = None
        self.target_origin   = None
        self.target_final    = None

    def panic(self, msg = None):
        if msg is not None:
            if self.prev_panic != msg:
                self.log_msg("PANIC: " + msg)
                self.prev_panic = msg
        if self.guide_state != GUIDESTATE_IDLE:
            self.guide_state = GUIDESTATE_PANIC
            guidepulser.panic(True)
        self.reset_guiding()

    def user_select_star(self, x, y, tol = 100):
        if x < 0 or y < 0:
            self.guide_state = GUIDESTATE_IDLE
            guidepulser.panic(False)
            self.prev_panic = ""
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
            mag = comutils.vector_between([x, y], i.coord(), mag_only=True)
            if mag < nearest_dist:
                nearest_dist = mag
                nearest = i
        if nearest_dist <= tol:
            self.selected_star = nearest
            self.log_msg("SUCCESS: selected star at [%u , %u]" % (self.selected_star.cxf(), self.selected_star.cyf()))
            self.target_coord = self.selected_star.coord()
            self.origin_coord = self.target_coord
            return True
        else:
            self.log_msg("FAILED: cannot select star at [%u , %u]" % (x, y))
            return False

    def snap_start(self):
        try:
            self.cam.init(gain_db = self.settings["guidecam_gain"], shutter_us = self.settings["guidecam_shutter"] * 1000, force_reset = self.cam_err)
            t = pyb.millis()
            while self.cam.check_init() == False:
                if pyb.elapsed_millis(t) > 1000:
                    self.send_state() # this is required to avoid timeout and to update with the camera-not-ready signal
                    t = pyb.millis()
                self.task_network()
                self.task_pulser()
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
            guidepulser.task()
            return False

    def snap_wait(self):
        self.task_network()
        self.task_pulser()
        while True:
            if pyb.elapsed_millis(self.snap_millis) <= (self.move - self.settings["net_quiet_time"]) or self.move == 0 or guidepulser.is_moving() == False:
                self.task_network()
            #guidepulser.task()
            self.task_pulser()
            if guidepulser.is_moving():
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
                    self.log_msg("WARN: guidecam timeout")
                    exclogger.log_exception("warning: guidecam timeout", time_str=comutils.fmt_time(self.time_mgr.get_time()))
                    return False

    def task(self):
        self.time_mgr.tick()

        if self.session_randid == 0:
            self.session_randid = pyb.rng() % 0x10000

        if self.cam is None:
            guidepulser.panic(True)
            self.task_pulser()
            self.task_network()
            if ((pyb.millis() // 500) % 2) == 0:
                self.log_msg("ERROR: guidecam fatal error, must reboot")
            gc.collect()
            return

        success = self.snap_start()
        gc.collect()
        if success == False:
            return
        self.move = self.decide()
        self.analysis_dur[4] = gc.mem_free()
        if self.img is not None:
            img_ts = self.img.timestamp()
            self.analysis_dur[0] = pyb.elapsed_millis(img_ts)
            self.analysis_dur[1] = self.dbg_t1 - img_ts
            self.analysis_dur[2] = self.dbg_t2 - self.dbg_t1
            self.analysis_dur[3] = self.dbg_t3 - self.dbg_t2
            if self.debug:
                print("analysis debug %s" % self.analysis_dur)
        self.send_state()
        if self.need_send_stars:
            self.send_stars()
        if self.snap_wait():
            img = self.cam.snapshot_finish()
            #img_time = img.timestamp()
            tspan = self.cam.get_timespan()
            tspent = self.last_pulse_dur
            dt = ((tspent % tspan) * 100) / tspan
            motionwhilecapture = self.settings["motionwhilecapture"]
            still_enough = (dt <= motionwhilecapture or motionwhilecapture >= 100)
            if still_enough == False:
                preemp = self.preemp_pulse()
                if preemp != 0:
                    still_enough = True
            if still_enough:
                # this image was taken while staying still
                self.img = img
                if self.queue_imgsave > 0:
                    self.save_image()
            else:
                # did not stay still, do another one while staying still
                if self.snap_start():
                    if self.snap_wait():
                        self.preemp_pulse()
                        self.img = self.cam.snapshot_finish()
                    else:
                        self.log_msg("ERR: guidecam failed to read image during wait")
                        self.cam.snapshot_finish()
            if self.imgstream_sock is not None and self.img_is_compressed == False:
                if self.guide_state != GUIDESTATE_IDLE:
                    print("warning: compressing JPG while autoguiding")
                self.compress_img()
                self.img_is_compressed = True
                self.update_imgstream()
        else:
            self.log_msg("ERR: guidecam failed to read image")
            self.cam.snapshot_finish()

    # note: check py_guidepulser.c and qstrdefsomv.h for available function calls
    def task_pulser(self):
        guidepulser.task()

        now_hw_err = guidepulser.get_hw_err()
        #if self.hw_err != now_hw_err and now_hw_err > 0:
        #    self.log_msg("ERR: hardware I2C error!")
        if self.hw_err != now_hw_err and now_hw_err > 1:
            self.panic(msg = "hardware I2C errors detected")
        if now_hw_err == 0 and self.hw_err > 0:
            self.log_msg("MSG: no hardware I2C errors anymore")
            red_led.off()
        self.hw_err = now_hw_err
        self.check_panic_builtin_led()

        gap_time = self.settings["intervalometer_gap_time"] * 1000
        if gap_time <= 1000:
            gap_time = 1000
        if guidepulser.is_shutter_open() == False:
            self.pulse_sum = 0
            self.queue_shutter_closed = True
            dither = (self.settings["dither_amount"] > 0 and (self.dither_interval + 1) >= self.settings["dither_interval"]) or self.guide_state == GUIDESTATE_DITHER
            # queue_shutter_closed is used to guarantee at least a small gap in the graph
            if self.intervalometer_timestamp <= 0:
                self.intervalometer_timestamp = pyb.millis()
                self.dither_interval += 1
                if dither:
                    if self.debug:
                        print("shutter closed while in dither mode")
                else:
                    if self.origin_coord is not None and self.target_coord is not None:
                        if self.intervalometer_state == INTERVALSTATE_IDLE or self.guide_state == GUIDESTATE_IDLE:
                             self.target_coord = self.origin_coord
                        else:
                            d = self.origin_coord[0] - self.target_coord[0]
                            if d > 0.1:
                                self.target_coord = (self.target_coord[0] + 0.1, self.target_coord[1])
                            elif (d <= 0.1 and d >= 0) or (d >= -0.1 and d <= 0):
                                self.target_coord = (self.origin_coord[0], self.target_coord[1])
                            elif d < -0.1:
                                self.target_coord = (self.target_coord[0] - 0.1, self.target_coord[1])
                            d = self.origin_coord[1] - self.target_coord[1]
                            if d > 0.1:
                                self.target_coord = (self.target_coord[0], self.target_coord[1] + 0.1)
                            elif (d <= 0.1 and d >= 0) or (d >= -0.1 and d <= 0):
                                self.target_coord = (self.target_coord[0], self.origin_coord[1])
                            elif d < -0.1:
                                self.target_coord = (self.target_coord[0], self.target_coord[1] - 0.1)
            if self.intervalometer_state == INTERVALSTATE_ACTIVE and dither == False:
                self.intervalometer_state = INTERVALSTATE_ACTIVE_GAP
                if self.debug:
                    print("shutter closed for brief gap")
            elif self.intervalometer_state == INTERVALSTATE_ACTIVE_GAP:
                if pyb.elapsed_millis(self.intervalometer_timestamp) >= gap_time:
                    self.intervalometer_state = INTERVALSTATE_ACTIVE
                    guidepulser.shutter(self.settings["intervalometer_bulb_time"])
                    self.intervalometer_timestamp = 0
                    if self.settings["intervalometer_digital"]:
                        print("!SHUTTER!")
                    elif self.debug:
                        print("shutter opened")
            elif self.intervalometer_state == INTERVALSTATE_ENDING or self.intervalometer_state == INTERVALSTATE_SINGLE_ENDING:
                self.intervalometer_state = INTERVALSTATE_IDLE
                self.log_msg("MSG: intervalometer ended")
            elif dither and self.guide_state != GUIDESTATE_GUIDING and self.guide_state != GUIDESTATE_DITHER and self.intervalometer_state != INTERVALSTATE_IDLE:
                self.intervalometer_state = INTERVALSTATE_IDLE
                self.log_msg("MSG: intervalometer interrupted")

    def clear_panic(self):
        guidepulser.panic(False)
        self.prev_panic = ""
        if self.guide_state == GUIDESTATE_PANIC:
            self.guide_state = GUIDESTATE_IDLE

    def guide_cmd(self, cmd):
        if cmd == GUIDESTATE_GUIDING:
            if self.guide_state != GUIDESTATE_IDLE and self.guide_state != GUIDESTATE_PANIC:
                self.log_msg("ERR: invalid moment to start autoguiding")
                return
            guidepulser.panic(False)
            self.prev_panic = ""
            if self.selected_star is None:
                self.log_msg("ERR: no selected star to start autoguiding")
                return
            if self.calibration[CALIIDX_RA] is None:
                if self.calibration[CALIIDX_DEC] is None:
                    self.log_msg("ERR: auto-guidance can't start without calibration")
                else:
                    self.log_msg("ERR: auto-guidance can't start without RA calibration")
                return
            self.guide_state = GUIDESTATE_GUIDING
            self.log_msg("CMD: auto-guidance starting")
        elif cmd == GUIDESTATE_CALIBRATING_RA or cmd == GUIDESTATE_CALIBRATING_DEC:
            if self.guide_state != GUIDESTATE_IDLE and self.guide_state != GUIDESTATE_PANIC:
                self.log_msg("ERR: invalid moment to start calibration")
                return
            guidepulser.panic(False)
            self.prev_panic = ""
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
            guidepulser.stop()
            guidepulser.panic(False)
            self.prev_panic = ""
            self.guide_state = cmd
            self.log_msg("CMD: autoguider is now idle")

    def intervalometer_cmd(self, cmd):
        if cmd == INTERVALSTATE_ACTIVE:
            self.intervalometer_state = cmd
            guidepulser.shutter(self.settings["intervalometer_bulb_time"])
            self.intervalometer_timestamp = 0
            self.pulse_sum = 0
            self.dither_interval = 0
            self.log_msg("CMD: intervalometer looping")
        elif cmd == INTERVALSTATE_BULB_TEST:
            guidepulser.shutter(self.settings["intervalometer_bulb_time"])
            self.intervalometer_timestamp = 0
            self.pulse_sum = 0
            self.log_msg("CMD: single-shot photo")
            self.intervalometer_state = INTERVALSTATE_SINGLE_ENDING
        elif cmd == INTERVALSTATE_ENDING:
            self.intervalometer_state = cmd
            self.log_msg("CMD: intervalometer ending on next shutter close")
        elif cmd == INTERVALSTATE_HALT:
            guidepulser.halt_shutter()
            self.intervalometer_state = INTERVALSTATE_IDLE
            self.log_msg("CMD: intervalometer halting")

    def misc_cmd(self, cmd):
        if cmd == "echo":
            self.log_msg("CMD: echo")
        elif cmd == "reboot":
            self.log_msg("CMD: reboot")
            t = pyb.millis()
            while pyb.elapsed_millis(t) < 2000:
                self.send_state()
                self.task_network()
            pyb.hard_reset()
        elif cmd == "getstate":
            self.send_state()
        elif cmd == "getsettings":
            self.send_settings()
        elif cmd == "calib_reset":
            self.calibration[0] = None
            self.calibration[1] = None
            self.clear_panic()
            self.log_msg("CMD: all calibration reset")
        elif cmd == "calib_reset_ra":
            self.calibration[CALIIDX_RA] = None
            self.clear_panic()
            self.log_msg("CMD: RA calibration reset")
        elif cmd == "calib_reset_dec":
            self.calibration[CALIIDX_DEC] = None
            self.clear_panic()
            self.log_msg("CMD: DEC calibration reset")
        elif cmd == "calib_load":
            good = 0
            bad  = 0
            try:
                with open("calib_ra.json", mode="rb") as f:
                    obj = ujson.load(f)
                    if self.calibration[CALIIDX_RA] is None:
                        self.calibration[CALIIDX_RA] = guider_calibration.GuiderCalibration(0, 0, 0)
                    self.calibration[CALIIDX_RA].load_json_obj(obj)
                    good += 1
                    #self.log_msg("SUCCESS: loaded RA calibration from file")
            except Exception as exc:
                bad += 1
                #self.log_msg("FAILED: cannot load RA calibration from file")
                exclogger.log_exception(exc)
            try:
                with open("calib_dec.json", mode="rb") as f:
                    obj = ujson.load(f)
                    if self.calibration[CALIIDX_DEC] is None:
                        self.calibration[CALIIDX_DEC] = guider_calibration.GuiderCalibration(0, 0, 0)
                    self.calibration[CALIIDX_DEC].load_json_obj(obj)
                    good += 2
                    #self.log_msg("SUCCESS: loaded DEC calibration from file")
            except Exception as exc:
                bad += 2
                #self.log_msg("FAILED: cannot load DEC calibration from file")
                exclogger.log_exception(exc)
            if good == 3 and bad == 0:
                self.log_msg("SUCCESS: loaded calibration from file")
            elif good == 1:
                self.log_msg("SUCCESS: loaded calibration from file (for RA)")
            elif bad != 0 and good == 0:
                self.log_msg("FAILED: cannot load calibration from file")
            else:
                self.log_msg("FAILED: cannot load some calibration from file")
        elif cmd == "calib_save":
            good = 0
            bad  = 0
            if self.calibration[CALIIDX_RA] is None and self.calibration[CALIIDX_DEC] is None:
                self.log_msg("ERR: calibration data is not available for saving")
                return
            if self.calibration[CALIIDX_RA] is not None:
                try:
                    with open("calib_ra.json", mode="wb") as f:
                        ujson.dump(self.calibration[CALIIDX_RA].get_json_obj(), f)
                        f.flush()
                    uos.sync()
                    uos.listdir()
                    good += 1
                    #self.log_msg("SUCCESS: saved RA calibration to file")
                except Exception as exc:
                    bad += 1
                    #self.log_msg("FAILED: cannot save RA calibration to file")
                    exclogger.log_exception(exc)
            if self.calibration[CALIIDX_DEC] is not None:
                try:
                    with open("calib_dec.json", mode="wb") as f:
                        ujson.dump(self.calibration[CALIIDX_DEC].get_json_obj(), f)
                        f.flush()
                    uos.sync()
                    uos.listdir()
                    good += 2
                    #self.log_msg("SUCCESS: saved DEC calibration to file")
                except Exception as exc:
                    bad += 2
                    #self.log_msg("FAILED: cannot save DEC calibration to file")
                    exclogger.log_exception(exc)
            if good == 3 and bad == 0:
                self.log_msg("SUCCESS: saved all calibration to file")
            elif good == 1:
                self.log_msg("SUCCESS: saved calibration to file (for RA)")
            elif good == 2:
                self.log_msg("SUCCESS: saved calibration to file (for DEC)")
            elif bad != 0 and good == 0:
                self.log_msg("FAILED: cannot save any calibration to file")
            else:
                self.log_msg("FAILED: cannot save some calibration to file")
        elif cmd == "hotpixels_save":
            self.save_hotpixels(use_log = True)
        elif cmd == "hotpixels_load":
            self.load_hotpixels(use_log = True, set_usage = True)
        elif cmd == "hotpixels_use":
            if self.hotpixels is None:
                self.log_msg("ERR: cannot use hot-pixels, the hot-pixel list does not exist")
                return
            self.settings["use_hotpixels"] = True
            self.log_msg("SUCCESS: hot-pixels are being used")
            self.save_settings()
        elif cmd == "hotpixels_disable":
            if self.settings["use_hotpixels"] == False:
                self.log_msg("ERR: hot-pixel usage already disabled")
                return
            self.settings["use_hotpixels"] = False
            self.log_msg("SUCCESS: hot-pixels are disabled")
            self.save_settings()
        elif cmd == "hotpixels_clear":
            if self.hotpixels is None:
                self.log_msg("ERR: cannot clear hot-pixels, the hot-pixel list already does not exist")
                return
            self.hotpixels = None
            self.settings["use_hotpixels"] = False
            self.log_msg("SUCCESS: hot-pixels list cleared")
            self.save_settings()
        elif cmd.startswith("testpulse_"):
            self.testpulse_dir = cmd[10:]
        elif cmd == "disconnect":
            print("forced websocket disconnect")
            self.kill_websocket()
        elif cmd == "snap":
            self.queue_imgsave = 1
        elif cmd == "record":
            if self.queue_imgsave != 2:
                self.log_msg("CMD: recording images")
            else:
                self.log_msg("CMD: already recording images")
            self.queue_imgsave = 2
        elif cmd == "record_stop":
            if self.queue_imgsave != 0:
                self.log_msg("CMD: stopped recording images")
            else:
                self.log_msg("CMD: already stopped recording images")
            self.queue_imgsave = 0
            self.save_image_name = None
            if self.save_image_dir is not None:
                self.log_msg("LIST-DIR[%s]: %s" % (self.save_image_dir, str(uos.listdir(self.save_image_dir))))
            self.save_image_dir = None
        elif cmd == "listdir":
            self.log_msg("LIST-DIR: " + str(uos.listdir()))
        elif cmd == "soft_reset":
            self.log_msg("SUCCESS: soft-reset")
            self.send_logs()
            t = pyb.millis()
            while pyb.elapsed_millis(t) < 2000:
                self.task_network()
            machine.soft_reset()
        elif cmd == "default_settings":
            self.guide_state = GUIDESTATE_IDLE
            self.clear_panic()
            self.default_settings()
            self.save_settings()
            self.log_msg("SUCCESS: default settings")
            self.send_logs()
        elif cmd == "sim_messy":
            if self.simulator is not None:
                self.simulator.messy = True
        elif cmd == "sim_norm":
            if self.simulator is not None:
                self.simulator.messy = False
        elif cmd == "panic":
            self.panic(msg = "cmd triggered panic")
            self.prev_panic = ""

    def task_network(self):
        if self.portal is not None:
            ret = self.portal.task()
            if ret == captive_portal.STS_KICKED:
                red_led.off()
            if self.portal.hw_retries > WIFI_HW_RETRIES:
                print("ERROR: WiFi hardware failure")
                green_led.off()
                self.check_panic_builtin_led()
            self.check_websocket()

    def register_http_handlers(self):
        if self.portal is None:
            return
        self.portal.install_handler("/",               self.handle_index)
        self.portal.install_handler("/index.htm",      self.handle_index)
        self.portal.install_handler("/index.html",     self.handle_index)
        self.portal.install_handler("/stream",         self.handle_imgstream)
        self.portal.install_handler("/websocket",      self.handle_websocket)
        self.portal.install_handler("/memory",         self.handle_memory)

    def handle_memory(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_memory")
        micropython.mem_info(True)
        return True

    def save_image(self, filename = None):
        try:
            tstr = comutils.fmt_time_filename(self.time_mgr.get_time())
            if self.queue_imgsave == 1:
                self.queue_imgsave = 0
            elif self.queue_imgsave == 2 and self.save_image_dir is None:
                self.save_image_dir = "snap-%s" % tstr
                uos.mkdir(self.save_image_dir)
            if filename is None:
                filename = "snap-%s.jpg" % tstr
            fpath = filename
            self.save_image_name = filename
            if self.save_image_dir is not None:
                fpath = self.save_image_dir + "/" + filename
            self.img.save(fpath, quality = 100)
            self.log_msg("SUCCESS: saved image to " + filename)
        except:
            self.log_msg("FAILED: cannot save image")
            self.queue_imgsave = 0
            self.save_image_dir = None

    def save_image_meta(self, res):
        try:
            fpath = self.save_image_name
            if self.save_image_dir is not None:
                fpath = self.save_image_dir + "/" + self.save_image_name
            with open(fpath + ".txt", "w+") as f:
                f.write("img mean: %u\r\n" % (self.img_stats.mean()))
                for i in self.stars:
                    f.write("\t" + guidestar_to_str(i) + "\r\n")
                infostr = "res: %u, cnt: %u, multistar_cnt: %u,\r\n" % (int(round(res[3])), res[4], res[5])
                f.write(infostr)
                if self.selected_star is not None:
                    infostr = "sel [%0.1f , %0.1f],\r\n" % (self.selected_star.cxf(), self.selected_star.cyf())
                    f.write(infostr)
                if res[0] is not None:
                    infostr = "res [%0.1f , %0.1f],\r\n" % (res[0].cxf(), res[0].cyf())
                    f.write(infostr)
                f.flush()
            uos.sync()
            uos.listdir()
        except:
            self.log_msg("ERR: unable to write recording metadata")
            self.queue_imgsave = 0
            self.save_image_dir = None

    def save_settings(self, filename = "settings_autoguider.json"):
        if self.debug:
            print("save_settings")
        with open(filename, mode="wb") as f:
            ujson.dump(self.settings, f)
            f.flush()
        uos.sync()
        uos.listdir()

    def load_settings(self, filename = "settings_autoguider.json"):
        obj = {}
        try:
            uos.stat(filename)
        except OSError:
            print("settings file missing")
            self.apply_settings()
            return
        try:
            with open(filename, mode="rb") as f:
                obj = ujson.load(f)
            for i in obj.keys():
                v = obj[i]
                if i in self.settings:
                    self.settings[i] = comutils.try_parse_setting(v)
                else:
                    print("extra JSON setting \"%s\": \"%s\"" % (i, str(v)))
        except Exception as exc:
            exclogger.log_exception(exc)
        self.apply_settings()

    def delete_settings(self, filename = "settings_autoguider.json"):
        if self.debug:
            print("delete settings")
        try:
            uos.remove(filename)
        except:
            pass

    def load_hotpixels(self, use_log = False, set_usage = False):
        if "hotpixels.txt" not in uos.listdir():
            self.settings["use_hotpixels"] = False
            if set_usage:
                self.save_settings()
            if use_log:
                self.log_msg("FAILED: hot-pixels file is missing")
            return
        try:
            with open("hotpixels.txt", mode="rt") as f:
                encoded = f.read()
                self.hotpixels = star_finder.decode_hotpixels(encoded)
                if set_usage:
                    self.settings["use_hotpixels"] = True
                    self.save_settings()
                if use_log:
                    self.log_msg("SUCCESS: loaded hot-pixels from file")
        except Exception as exc:
            self.log_msg("FAILED: cannot load hot-pixels from file")
            exclogger.log_exception(exc)

    def save_hotpixels(self, use_log = False):
        if self.hotpixels is not None:
            if len(self.hotpixels) > 0 and self.settings["use_hotpixels"]:
                self.log_msg("ERR: cannot overwrite current hot-pixels, please clear or disable the hot-pixel list first")
                return
        if self.stars is None:
            self.log_msg("ERR: cannot save current hot-pixels, the star list does not exist")
            return
        encoded = star_finder.encode_hotpixels(self.stars)
        self.hotpixels = star_finder.decode_hotpixels(encoded)
        self.settings["use_hotpixels"] = True
        self.save_settings()
        try:
            with open("hotpixels.txt", mode="w") as f:
                f.write(encoded)
                f.flush()
            uos.sync()
            uos.listdir()
            if use_log:
                self.log_msg("SUCCESS: saved hot-pixels to file")
        except Exception as exc:
            self.log_msg("FAILED: cannot save hot-pixels to file")
            exclogger.log_exception(exc)

    def handle_imgstream(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_imgstream")
        if "zoom" in req:
            self.zoom = 8
        else:
            self.zoom = 1
        self.kill_imgstreamer()
        self.kill_websocket()
        self.imgstream_sock = client_stream
        self.imgstream_sock.settimeout(5.0)
        self.imgstream_sock.send("HTTP/1.1 200 OK\r\n" \
                    "Server: OpenMV\r\n" \
                    "Content-Type: multipart/x-mixed-replace;boundary=openmv\r\n" \
                    "Cache-Control: no-cache\r\n" \
                    "Pragma: no-cache\r\n\r\n")
        self.stream_sock_err = 0
        return False

    def handle_index(self, client_stream, req, headers, content):
        self.kill_imgstreamer()
        self.kill_websocket()
        captive_portal.gen_page(client_stream, "autoguider.htm", add_files = ["web/autoguider_utils.js", "web/jquery-ui-1.12.1-darkness.css", "web/jquery-3.5.1.min.js", "web/jquery-ui-1.12.1.min.js", "web/chartist.min.js", "web/chartist.min.css", "web/divtable_basic.css", "web/toast.js", "web/websocketutils.js", "web/mathutils.js", "web/draw_guideerror.js", "web/draw_guidescope.js", "web/draw_starprofile.js"], debug = self.debug)
        return True

    def update_imgstream(self):
        if self.imgstream_sock is None or self.img_compressed is None:
            return
        try:
            self.portal.update_imgstream(self.imgstream_sock, self.img_compressed)
            self.stream_sock_err = 0
        except Exception as exc:
            self.stream_sock_err += 1
            if self.stream_sock_err > 5:
                if self.debug:
                    print("img stream too many errors")
                exclogger.log_exception(exc, to_file=False)
                self.kill_imgstreamer()
            pass

    def kill_imgstreamer(self):
        if self.imgstream_sock is not None:
            try:
                self.imgstream_sock.close()
            except:
                pass
            try:
                del self.imgstream_sock
            except:
                pass
        self.imgstream_sock = None

    def kill_websocket(self):
        if self.websock is not None:
            try:
                self.websock.close()
            except:
                pass
            try:
                del self.websock
            except:
                pass
        self.websock = None

    def handle_websocket(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_websocket")
        self.kill_imgstreamer()
        self.kill_websocket()
        # headers and content are empty at this point anyways
        headers, content = captive_portal.get_all_headers(client_stream)
        is_websock = captive_portal.handle_websocket(client_stream, req, headers)
        if is_websock == False:
            print("error handling websocket")
            return True # failed to handle websocket, returning True will kill the socket inside captive_portal
        else:
            print("established websock")
        self.websock = client_stream
        self.websock.settimeout(0.1)
        self.stream_sock_err = 0
        self.websock_millis = pyb.millis()
        return False # won't kill the socket

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
            if self.zoom <= 1 or self.selected_star is None:
                self.img_compressed = self.img.scale(x_scale = 0.5, y_scale = 0.5, copy_to_fb = self.extra_fb).compress(quality=50)
            else:
                iw = int(math.floor(self.cam.width / self.zoom))
                ih = int(math.floor(self.cam.height / self.zoom))
                iwc = int(round(iw / 2.0))
                ihc = int(round(ih / 2.0))
                roi = (int(math.floor(self.selected_star.cxf() - iwc)), int(math.floor(self.selected_star.cyf() - ihc)), iw, ih)
                if roi[0] < 0:
                    roi[0] = 0
                elif (roi[0] + iw) > self.cam.width:
                    roi[0] -= (roi[0] + iw) - self.cam.width
                if roi[1] < 0:
                    roi[1] = 0
                elif (roi[1] + ih) > self.cam.width:
                    roi[1] -= (roi[1] + ih) - self.cam.height
                self.img_compressed = self.img.crop(roi, copy_to_fb = self.extra_fb).compress(quality=50)
            if self.debug:
                print("done (%u %u)" % (self.img_compressed.height(), self.img_compressed.size()))
        except MemoryError as exc:
            exclogger.log_exception(exc, to_file = False)
            pass
        except Exception as exc:
            exclogger.log_exception(exc)
            pass

    def check_panic_builtin_led(self):
        if self.hw_err > 1 or self.portal.hw_retries > WIFI_HW_RETRIES:
            if (pyb.millis() % 300) < 150:
                red_led.on()
            else:
                red_led.off()
        else:
            red_led.off()

def guidestar_to_jsonobj(star):
    obj = {}
    obj.update({"cx": star.cxf()})
    obj.update({"cy": star.cyf()})
    obj.update({"r" : star.r()})
    obj.update({"max_brightness": star.max_brightness()})
    #obj.update({"pointiness": star.star_pointiness()})
    obj.update({"rating": star.star_rating()})
    #obj.update({"profile": })
    return obj

def guidestar_to_str(i):
    return "%0.1f,%0.1f,%u,%u,%u;" % (i.cxf(), i.cyf(), i.r(), i.max_brightness(), i.star_rating())
    # worst-case length is
    # 1234.6,8901.3,567,901,345;
    # 26

if __name__ == "__main__":
    autoguider = AutoGuider(debug = True)
    while True:
        try:
            autoguider.task()
        except KeyboardInterrupt:
            raise
        except MemoryError as exc:
            exclogger.log_exception(exc, to_file = False)
            micropython.mem_info(True)
        except Exception as exc:
            exclogger.log_exception(exc)
