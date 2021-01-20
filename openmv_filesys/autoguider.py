import micropython
micropython.opt_level(2)

import comutils
import blobstar, astro_sensor, time_location, captive_portal, star_finder, star_motion, guider_calibration, backlash_mgr
import guidepulser
import exclogger
import pyb, uos, uio, gc, sys
import time, math, ujson, ubinascii
import network
import sensor, image

red_led   = pyb.LED(1)
green_led = pyb.LED(2)
blue_led  = pyb.LED(3)
ir_leds   = pyb.LED(4)

LOG_BUFF_LEN = micropython.const(3)

GUIDESTATE_IDLE              = micropython.const(0)
GUIDESTATE_GUIDING           = micropython.const(1)
GUIDESTATE_DITHER            = micropython.const(2)
GUIDESTATE_PANIC             = micropython.const(3)
GUIDESTATE_CALIBRATING_RA    = micropython.const(4)
GUIDESTATE_CALIBRATING_DEC   = micropython.const(5)

INTERVALSTATE_IDLE           = micropython.const(0)
INTERVALSTATE_ACTIVE         = micropython.const(1)
INTERVALSTATE_ACTIVE_GAP     = micropython.const(3)
INTERVALSTATE_BULB_TEST      = micropython.const(4)
INTERVALSTATE_ACTIVE_HALT    = micropython.const(5)
INTERVALSTATE_ACTIVE_ENDING  = micropython.const(6)

CALIIDX_RA  = micropython.const(0)
CALIIDX_DEC = micropython.const(1)

class AutoGuider(object):

    def __init__(self, debug = False, simulate_file = None, simulate = False):
        #gc.disable()
        exclogger.init()
        guidepulser.init()
        self.cam = astro_sensor.AstroCam(simulate = simulate_file)
        try:
            self.cam.init(gain_db = 32, shutter_us = 1000000)
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
        self.selected_star = None
        self.target_coord = None
        self.origin_coord = None

        if simulate_file is not None or simulate:
            import guider_sim
            self.simulator = guider_sim.GuiderSimulator()
        else:
            self.simulator = None

        self.pulse_sum = 0
        self.queue_shutter_closed = True
        if guidepulser.get_hw_err() > 0:
            print("ERROR: I2C hardware failure")

        self.calibration = [None, None]
        self.backlash_ra = backlash_mgr.BacklashManager()
        self.backlash_dec = backlash_mgr.BacklashManager()

        self.cam_err = 0
        self.expo_err = 0
        self.hw_err = 0
        self.prev_panic = ""
        self.snap_millis = 0
        self.stop_time = 0
        self.analysis_dur = [0, 0, 0, 0]
        self.hotpixels_eff = 0

        self.settings = {}
        self.settings.update({"gain"                     : self.cam.gain})
        self.settings.update({"shutter"                  : self.cam.shutter // 1000})
        self.settings.update({"thresh"                   : 0})
        self.settings.update({"use_hotpixels"            : False})
        self.settings.update({"panicthresh_expoerr"      : 5})
        self.settings.update({"panicthresh_movescore"    : 50})
        self.settings.update({"use_dithering"            : False})
        self.settings.update({"dither_amount"            : 3})
        self.settings.update({"dither_calmness"          : 3})
        self.settings.update({"dither_calm_cnt"          : 3})
        self.settings.update({"dither_frames_cnt"        : 5})
        self.settings.update({"intervalometer_bulb_time" : 10})
        self.settings.update({"intervalometer_gap_time"  : 2})
        self.settings.update({"intervalometer_digital"   : False})
        self.settings.update({"calibration_pulse"        : 750})
        self.settings.update({"calib_points_cnt"         : 10})
        self.settings.update({"move_grace"               : 50})
        self.settings.update({"flip_ra"                  : 1})
        self.settings.update({"flip_dec"                 : 1})
        self.settings.update({"min_pulse_wid"            : 50})
        self.settings.update({"max_pulse_wid"            : (self.cam.shutter // 1000) - 100})
        self.settings.update({"net_quiet_time"           : 100})
        self.settings.update({"backlash_hyster"          : 500})
        self.settings.update({"backlash_limit"           : 1000})
        self.settings.update({"backlash_reduc"           : 0})
        self.settings.update({"backlash_lock"            : False})
        self.settings.update({"multistar"                : False})
        self.settings.update({"multistar_cnt_min"        : 1})
        self.settings.update({"multistar_cnt_max"        : 10})
        self.settings.update({"multistar_ratings_thresh" : 10})
        self.settings.update({"starmove_tolerance"       : 50})
        self.settings.update({"use_led"                  : True})
        self.settings.update({"fast_mode"                : True})
        self.settings.update({"slow_profile"             : False})
        self.load_settings()
        self.load_hotpixels(use_log = False, set_usage = False)

        self.portal = captive_portal.CaptivePortal(debug = self.debug)
        if self.portal is not None:
            self.register_http_handlers()

        self.img = None
        self.img_compressed = None
        self.extra_fb = None
        self.expo_code = 0
        self.histogram = None
        self.img_stats = None
        self.stars = None
        self.hotpixels = []
        self.zoom = 1

        self.imgstream_sock = None
        self.websock = None
        self.websock_millis = 0
        self.websock_randid = 0
        self.stream_sock_err = 0

        self.pulselog_buff = [[0, 0, 0, 0]] * LOG_BUFF_LEN
        self.msglog_buff   = [[0, 0, None]] * LOG_BUFF_LEN
        self.pulselog_buff_idx = 0
        self.msglog_buff_idx   = 0

    def send_settings(self):
        obj = {}
        obj.update({"packet_type", "settings"})
        for k in self.settings.keys():
            obj.update({k, self.settings[k]})
        self.send_websocket(obj)

    def get_state_obj(self):
        state = {}
        state.update({"packet_type"         : "state"})
        state.update({"time"                : self.time_mgr.get_sec()})
        state.update({"rand_id"             : self.websock_randid})
        state.update({"guider_state"        : self.guide_state})
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
            state.update({"img_mean" : self.img_stats.mean()})
            state.update({"img_stdev": self.img_stats.stdev()})
            state.update({"img_max"  : self.img_stats.max()})
            state.update({"img_min"  : self.img_stats.min()})
        if self.stars is not None:
            star_list = self.stars
            star_cnt_limit = 50
            if len(star_list) > star_cnt_limit:
                star_list = star_list[0:star_cnt_limit]
            state.update({"stars": blobstar.to_jsonobj(star_list)})
        else:
            state.update({"stars": []})
        if self.selected_star is not None:
            state.update({"selected_star"        : [self.selected_star.cx, self.selected_star.cy]})
            state.update({"selected_star_profile": self.selected_star.profile})
        else:
            state.update({"selected_star": None})
        state.update({"target_coord": self.target_coord})
        state.update({"origin_coord": self.origin_coord})
        state.update({"calib_ra"    : self.calibration[CALIIDX_RA].get_json_obj() if self.calibration[CALIIDX_RA] is not None else None})
        state.update({"calib_dec"   : self.calibration[CALIIDX_DEC].get_json_obj() if self.calibration[CALIIDX_DEC] is not None else None})
        if self.hotpixels is not None:
            state.update({"hotpixels"     : True})
            state.update({"hotpixels_used": self.settings["use_hotpixels"]})
            state.update({"hotpixels_cnt" : len(self.hotpixels)})
            state.update({"hotpixels_last": self.hotpixels_eff})
        else:
            state.update({"hotpixels": False})
        state.update({"logs"  : self.get_logs_obj()})
        state.update({"hw_err": self.hw_err})
        state.update({"analysis_dur": self.analysis_dur})
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
        try:
            self.websock.settimeout(10)
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
            self.websock.settimeout(0.001)
            rep = captive_portal.websocket_readmsg(self.websock)
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
        elif pkt_type == "select_star":
            self.user_select_star(obj["star_x"], obj["star_y"])
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
        guidepulser.set_flip_ra (self.settings["flip_ra" ])
        guidepulser.set_flip_dec(self.settings["flip_dec"])
        if self.settings["use_led"]:
            guidepulser.enable_led()
        else:
            guidepulser.disable_led()

    def save_settings(self, filename = "settings.json"):
        if self.debug:
            print("save_settings")
        with open(filename, mode="wb") as f:
            ujson.dump(self.settings, f)

    def decide(self):
        decided_pulse = 0
        if self.imgstream_sock is not None or self.img_is_compressed:
            self.guide_state = GUIDESTATE_IDLE
            return decided_pulse
        if self.img is not None:
            self.histogram = self.img.get_histogram()
            self.img_stats = self.histogram.get_statistics()
            adv = 1 if self.settings["slow_profile"] else 2
            latest_stars, code = star_finder.find_stars(self.img, hist = self.histogram, stats = self.img_stats, thresh = self.settings["thresh"], force_solve = True, advanced = adv)
            self.dbg_t1 = pyb.millis()
            if self.simulator is not None:
                latest_stars = self.simulator.get_stars(self, latest_stars)
                self.dbg_t2 = pyb.millis()
            else:
                self.dbg_t2 = self.dbg_t1
            print("%u stars" % len(latest_stars))
            if self.hotpixels is not None and self.settings["use_hotpixels"]:
                before_len = len(latest_stars)
                latest_stars = star_finder.filter_hotpixels(latest_stars, self.hotpixels)
                self.hotpixels_eff = before_len - len(latest_stars)
            latest_stars = blobstar.sort_rating(latest_stars)
            self.expo_code = code
            if code != star_finder.EXPO_JUST_RIGHT or len(latest_stars) <= 0:
                self.expo_err += 1
                if self.debug:
                    print("exposure error %u %u" % (code, len(latest_stars)))
                if self.expo_err > self.settings["panicthresh_expoerr"]:
                    self.panic(msg = "too many exposure errors")
                self.dither_calm = 0
                return decided_pulse
            else:
                # exposure is just right
                self.expo_err = 0
                self.prev_stars = self.stars
                self.stars = latest_stars

                # motion can be detected if previous data is available
                # if previous data is unavailable, then just populate it for no motion
                if self.prev_stars is None:
                    self.prev_stars = latest_stars

                if self.settings["multistar"]:
                    real_star, virtual_star, move_data, score, avg_cnt = star_motion.get_all_star_movement(self.prev_stars, self.stars, selected_star = self.selected_star, cnt_min = self.settings["multistar_cnt_min"], cnt_limit = self.settings["multistar_cnt_max"], rating_thresh = self.settings["multistar_ratings_thresh"], tolerance = self.settings["starmove_tolerance"], fast_mode = self.settings["fast_mode"])
                else:
                    if self.selected_star is None and self.stars is not None:
                        if len(self.stars) > 0:
                            self.selected_star = self.stars[0]
                            self.log_msg("MSG: auto selected star from list, at %0.1f %0.1f" % (self.selected_star.cx, self.selected_star.cy))
                    real_star, score, nearby = star_motion.get_star_movement(self.prev_stars, self.selected_star, self.stars, tolerance = self.settings["starmove_tolerance"], fast_mode = self.settings["fast_mode"])
                    virtual_star = real_star
                    avg_cnt = nearby
                self.dbg_t3 = pyb.millis()
                if self.selected_star is None and real_star is not None:
                    self.log_msg("MSG: auto selected star at %0.1f %0.1f" % (real_star.cx, real_star.cy))
                self.selected_star = real_star
                self.virtual_star  = virtual_star

                if self.debug:
                    print("dbg move score %0.4f cnt %u " % (score, avg_cnt), end="")
                    if real_star is not None:
                        print("rating %0.4f" % real_star.rating)
                    else:
                        print("no star")

                if score > self.settings["panicthresh_movescore"] or score < 0:
                    self.panic(msg = "movement analysis score too low %f" % score)

                if self.guide_state == GUIDESTATE_GUIDING:
                    if self.selected_star is None:
                        self.log_msg("WARN: guidance requested without selected star")
                        self.guide_state = GUIDESTATE_IDLE
                        return
                    if self.calibration[CALIIDX_RA] is None:
                        self.log_msg("WARN: guidance requested without RA calibration")
                        self.guide_state = GUIDESTATE_IDLE
                        return
                    if self.target_coord is None:
                        self.target_coord = [self.selected_star.cx, self.selected_star.cy]
                        if self.debug:
                            print("target coord auto-selected: (%0.1f , %0.2f)" % (self.target_coord[0], self.target_coord[1]))
                    if self.origin_coord is None:
                        self.origin_coord = self.target_coord
                        if self.debug:
                            print("origin coord auto-selected: (%0.1f , %0.2f)" % (self.origin_coord[0], self.origin_coord[1]))
                    if self.settings["use_dithering"] and self.intervalometer_state == INTERVALSTATE_ACTIVE and guidepulser.is_shutter_open() == False:
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
                        guidepulser.shutter(self.settings["intervalometer_bulb_time"])
                        self.intervalometer_timestamp = 0
                        if self.settings["intervalometer_digital"]:
                            print("!SHUTTER!")
                    return decided_pulse
                elif self.guide_state == GUIDESTATE_CALIBRATING_RA or self.guide_state == GUIDESTATE_CALIBRATING_DEC:
                    self.backlash_ra.neutralize()
                    self.backlash_dec.neutralize()
                    if self.selected_star is None:
                        self.log_msg("WARN: calibration requested without selected star")
                        self.guide_state = GUIDESTATE_IDLE
                        return decided_pulse
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
                            guidepulser.move(decided_pulse, 0, self.settings["move_grace"])
                        else:
                            guidepulser.move(0, decided_pulse, self.settings["move_grace"])
                        self.stop_time = guidepulser.get_stop_time()
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
        if ret > 0 and ret <= 1:
            ret = 1
        pulse_ra_fin  = self.backlash_ra.filter(pulse_ra_ori)
        if self.calibration[CALIIDX_DEC] is None:
            pulse_dec_ori = 0
        pulse_dec_fin = self.backlash_dec.filter(pulse_dec_ori)
        if pulse_ra_fin != 0 or pulse_dec_fin != 0:
            guidepulser.move(pulse_ra_fin, pulse_dec_fin, self.settings["move_grace"])
            self.stop_time = guidepulser.get_stop_time()
            return ret
        return 0

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
                guidepulser.task()
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
        guidepulser.task()
        while True:
            if pyb.elapsed_millis(self.snap_millis) <= (self.move - self.settings["net_quiet_time"]) or self.move == 0 or guidepulser.is_moving() == False:
                self.task_network()
            guidepulser.task()
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

        if self.cam is None:
            guidepulser.panic(True)
            guidepulser.task()
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
        if self.img is not None:
            img_ts = self.img.timestamp()
            self.analysis_dur[0] = pyb.elapsed_millis(img_ts)
            self.analysis_dur[1] = self.dbg_t1 - img_ts
            self.analysis_dur[2] = self.dbg_t2 - self.dbg_t1
            self.analysis_dur[3] = self.dbg_t3 - self.dbg_t2
            if self.debug:
                print("analysis time %s" % self.analysis_dur)
        self.send_state()
        if self.snap_wait():
            img = self.cam.snapshot_finish()
            img_time = img.timestamp()
            if img_time > self.stop_time and (img_time - (self.cam.get_timespan() + 100)) > self.stop_time:
                # this image was taken while staying still
                self.img = img
            else:
                # did not stay still, do another one while staying still
                if self.snap_start():
                    if self.snap_wait():
                        self.img = self.cam.snapshot_finish()
                    else:
                        self.log_msg("ERR: guidecam failed to read image during wait")
            if self.imgstream_sock is not None and self.img_is_compressed == False:
                if self.guide_state != GUIDESTATE_IDLE:
                    print("warning: compressing JPG while autoguiding")
                self.compress_img()
                self.img_is_compressed = True
                self.update_imgstream()
        else:
            self.log_msg("ERR: guidecam failed to read image")

    # note: check py_guidepulser.c and qstrdefsomv.h for available function calls
    def task_pulser(self):
        guidepulser.task()
        now_hw_err = guidepulser.get_hw_err()
        if self.hw_err == 0 and now_hw_err > 0:
            self.log_msg("ERR: hardware I2C error detected")
        elif now_hw_err == 0 and self.hw_err > 0:
            self.log_msg("MSG: no hardware I2C errors anymore")
        self.hw_err = now_hw_err
        gap_time = self.settings["intervalometer_gap_time"] * 1000
        if gap_time <= 1000:
            gap_time = 1000
        if guidepulser.is_shutter_open() == False:
            self.pulse_sum = 0
            self.queue_shutter_closed = True
            dither = self.settings["use_dithering"]
            # queue_shutter_closed is used to guarantee at least a small gap in the graph
            if self.intervalometer_timestamp <= 0:
                self.intervalometer_timestamp = pyb.millis()
                if dither:
                    if self.debug:
                        print("shutter closed while in dither mode")
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
            elif self.intervalometer_state == INTERVALSTATE_ACTIVE_ENDING:
                self.intervalometer_state = INTERVALSTATE_IDLE
                self.log_msg("MSG: intervalometer ended")
            elif dither and self.guide_state != GUIDESTATE_GUIDING and self.guide_state != GUIDESTATE_DITHER:
                self.intervalometer_state = INTERVALSTATE_IDLE
                self.log_msg("MSG: intervalometer interrupted")

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
            self.shutter(self.settings["intervalometer_bulb_time"])
            self.intervalometer_timestamp = 0
            self.pulse_sum = 0
            self.log_msg("CMD: intervalometer activated")
        elif cmd == INTERVALSTATE_BULB_TEST:
            guidepulser.shutter(self.settings["intervalometer_bulb_time"])
            self.intervalometer_timestamp = 0
            self.pulse_sum = 0
            self.log_msg("CMD: bulb test")
            self.intervalometer_state = INTERVALSTATE_ACTIVE_ENDING
        elif cmd == INTERVALSTATE_ACTIVE_ENDING:
            self.intervalometer_state = cmd
            self.log_msg("CMD: intervalometer ending on next shutter close")
        elif cmd == INTERVALSTATE_ACTIVE_HALT:
            guidepulser.halt_shutter()
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
            guidepulser.panic(False)
            self.prev_panic = ""
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

    def handle_memory(self, client_stream, req, headers, content):
        if self.debug:
            print("handle_memory")
        micropython.mem_info(True)
        return True

    def save_settings(self, filename = "settings.json"):
        if self.debug:
            print("save_settings")
        with open(filename, mode="wb") as f:
            ujson.dump(self.settings, f)

    def load_settings(self, filename = "settings.json"):
        obj = {}
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
        try:
            with open("hotpixels.txt", mode="w") as f:
                f.write(encoded)
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
        captive_portal.gen_page(client_stream, "polarscope.htm", add_files = ["web/jquery-ui-1.12.1-darkness.css", "web/jquery-3.5.1.min.js", "web/jquery-ui-1.12.1.min.js", "web/websocketutils.js", "web/mathutils.js"], debug = self.debug)
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
        self.websock.settimeout(10)
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
                roi = (int(math.floor(self.selected_star.cx - iwc)), int(math.floor(self.selected_star.cy - ihc)), iw, ih)
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
