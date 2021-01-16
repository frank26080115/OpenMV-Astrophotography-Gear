SHUTTER_DURATION_SHORT   = micropython.const(1000)
SHUTTER_DURATION_LONG    = micropython.const(1400)

PANICTHRESH_EXPOERR      = micropython.const(10)
PANICTHRESH_MOVESCORE    = micropython.const(100)

    def decide(self):
        if self.stream_sock is not None or self.img_is_compressed:
            self.guide_state    = GUIDESTATE_IDLE
            self.guide_substate = 0
            return 0
        if self.img is not None:
            panic = False
            self.histogram = self.img.get_histogram()
            self.img_stats = self.histogram.get_statistics()
            stars, code = star_finder.find_stars(self.img, hist = self.histogram, stats = self.img_stats, thresh = self.settings["thresh"], force_solve = self.settings["force_solve"], advanced = True)
            stars = blobstar.sort_rating(stars)
            if code != star_finder.EXPO_JUST_RIGHT or len(stars) <= 0:
                self.expo_err += 1
                if self.expo_err > self.settings["panicthresh_expoerr"]:
                    self.panic()
                self.update_web_img()
            else:
                # exposure is just right
                self.expo_err = 0
                self.prev_stars = self.stars
                self.stars = stars

                # motion can be detected if previous data is available
                # if previous data is unavailable, then just populate it for no motion
                if self.prev_stars is None:
                    self.prev_stars = stars

                move_coord, move_vect, score, avg_cnt = star_motion.get_all_star_movement(self.prev_stars, self.stars)
                if score > self.settings["panicthresh_movescore"]:
                    self.panic()

                self.update_web_img()
        else:
            # self.img is None
            pass

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