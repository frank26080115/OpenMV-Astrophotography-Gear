import micropython
micropython.opt_level(2)
import time
import math
import pyb
import blobstar
import ujson

# NOTE: data table and image both respect computer image coordinate system (origin at top left corner)
# positive angle is clockwise

# this table is pre-generated
# vector to a star from Polaris, magnitude in pixels
# sorted by closest first
STARS_NEAR_POLARIS = micropython.const([
    ["HD 5914",         98.867180,  -10.647256 ],
    ["* lam UMi",      479.008301, -118.529852 ],
    ["HD 66368",       524.994808,  164.780381 ],
    ["HD 213126",      534.725064,  -51.636087 ],
    ["HD 6319",        654.323145,   12.759174 ],
    ["HD 221525",      676.906523,  -21.909059 ],
    ["HD 22701",       820.441622,   68.948647 ],
    ["HD 224687",      829.461143,   -9.602170 ],
    ["V* OV Cep",      875.677409,  129.407251 ], # 2.9063 arc degs from Polaris
    ["HD 96870",       876.265358, -178.807660 ],
    ["V* UY UMi",      884.833301, -168.092577 ],
    ["HD 203836",      896.804216,  -59.867339 ],
    ["HD 221488",      897.533794,  -18.299156 ],
    ["HD 114282",      914.532044, -160.757620 ],
    ["* 2 UMi",        924.487512,   12.313035 ],
    ["HD 42855",       927.519046,  115.447469 ],
    ["V* V377 Cep",    942.226371,  -18.793331 ],
    ["V* V378 Cep",   1007.975111,  -16.059071 ],
    ["HD 135294",     1060.463568, -140.366796 ],
    ["HD 212774",     1063.289980,  -37.557174 ],
    ["* 24 UMi",      1082.153394, -105.587018 ],
    ["HD 212710",     1096.976152,  -37.222721 ],
    ["HD 174878",     1146.140083,  -95.341928 ],
    ["* del UMi",     1195.457555, -104.488215 ],
    ["HD 107113",     1264.471354, -170.201903 ]])

PIXELS_PER_DEGREE = micropython.const(875.677409 / 2.9063) # calculated using "OV Cep"
DIST_TOL = micropython.const(0.1)     # percentage
SCORE_REQUIRED = micropython.const(4) # must have this many stars that match their estimated coordinates
ENABLE_PENALTY = micropython.const(True)

class PoleSolution(object):
    def __init__(self, star_list, hot_pixels = [], search_limit = 3, debug = False):
        self.solved = False
        self.star_list = star_list
        self.search_limit = search_limit
        self.hot_pixels = hot_pixels
        self.accel_sec = 0
        self.debug = debug

    def solve(self, polaris_ra_dec = (2.960856, 89.349278)):

        # polaris_ra_dec default to values at Jan 1 2020
        # supply new values according to current date
        self.polaris_ra_dec = polaris_ra_dec
        self.x = None
        self.y = None
        self.solu_time = 0
        self.solu_time = int(round(pyb.millis() // 1000))

        if len(self.star_list) < SCORE_REQUIRED:
            return False # impossible to have a solution if not enough stars

        # Polaris is the brightest object in the potential field of view, so it's faster to start with it
        brite_sorted = blobstar.sort_brightness(self.star_list)
        # limit the search for the first few possibilities
        if len(brite_sorted) > self.search_limit:
            brite_sorted = brite_sorted[0:self.search_limit]

        # iterate through all posibilities, brightest first
        for i in brite_sorted:
            # we are guessing "i" is Polaris for this iteration
            i.score_list = []
            i.score = 0
            i.penalty = 0
            i.rotation = 0
            i.rot_angi_sum = 0
            i.rot_angj_sum = 0
            i.rot_dist_sum = 0
            i.pix_calibration = []
            ang_tol = 4

            for j in self.star_list:
                j.set_ref_star(i) # this is required for all entries in the list, so that sort_dist can work
                # set_ref_star also computes the vector to the ref star and caches the result
            dist_sorted = blobstar.sort_dist(self.star_list) # sorted closest-to-Polaris first

            if self.debug:
                print("center star (%.1f , %.1f)" % (i.cx, i.cy))
                dbgi = 0
                for dbg in dist_sorted:
                    print("[%u]: (%.1f , %.1f) -> (%.1f , %.1f)" % (dbgi, dbg.cx, dbg.cy, dbg.ref_star_dist, dbg.ref_star_angle))
                    dbgi += 1

            rot_ang = None # without a known reference angle, use the first angle we encounter to establish a reference angle
            # rot_ang is set after the match is made

            # these are used for the penalizing later
            max_dist = 0
            min_brite = -1

            idx_tbl = 0
            idx_blobs_start = 1 # start at [1] because [0] is supposed to be Polaris
            len_tbl = len(STARS_NEAR_POLARIS)
            len_blobs = len(dist_sorted)
            while idx_tbl < len_tbl:

                # skip stars that might have too similar of a vector distance if the reference angle is not established yet
                # it is unlikely that this logic is actually useful in real life
                if rot_ang is None and idx_tbl >= 1:
                    if abs(STARS_NEAR_POLARIS[idx_tbl][1] - STARS_NEAR_POLARIS[idx_tbl - 1][1]) <= 2:
                        idx_tbl += 1
                        continue

                idx_blobs = idx_blobs_start # previous blobs (closer-to-Polaris) will be ignored
                while idx_blobs < len_blobs:
                    k = dist_sorted[idx_blobs]
                    match = False
                    if dist_match(k.ref_star_dist, STARS_NEAR_POLARIS[idx_tbl][1]):

                        if self.debug:
                            print("dist matched [%s , %u] %.1f %.1f %.1f" % (STARS_NEAR_POLARIS[idx_tbl][0], idx_blobs, STARS_NEAR_POLARIS[idx_tbl][1], k.ref_star_dist, abs(k.ref_star_dist - STARS_NEAR_POLARIS[idx_tbl][1])))

                        if rot_ang is None:
                            # without a known reference angle, use the first angle we encounter to establish a reference angle
                            # rot_ang is set after the match is made
                            match = True
                            if self.debug:
                                print("first angle match [%s , %u] %.1f %.1f %.1f" % (STARS_NEAR_POLARIS[idx_tbl][0], idx_blobs, STARS_NEAR_POLARIS[idx_tbl][2], k.ref_star_angle, angle_diff(k.ref_star_angle, STARS_NEAR_POLARIS[idx_tbl][2])))
                        else:
                            adj_ang = ang_normalize(STARS_NEAR_POLARIS[idx_tbl][2] + rot_ang)
                            if angle_match(k.ref_star_angle, adj_ang, tol = ang_tol):
                                match = True
                                if ang_tol > 1:
                                    ang_tol -= 1
                                if self.debug:
                                    print("angle matched ", end="")
                            else:
                                if self.debug:
                                    print("angle match failed ", end="")
                            if self.debug:
                                print("[%s , %u] %.1f %.1f %.1f %.1f %.1f" % (STARS_NEAR_POLARIS[idx_tbl][0], idx_blobs, STARS_NEAR_POLARIS[idx_tbl][2], k.ref_star_angle, angle_diff(k.ref_star_angle, adj_ang), rot_ang, adj_ang))
                    if match:
                        # each match is a further star, which means more precise angle
                        # compute (and update) the weighted average of the angle offset
                        rot_ang = angle_diff(k.ref_star_angle, STARS_NEAR_POLARIS[idx_tbl][2])
                        unitvector = [math.cos(math.radians(rot_ang)), math.sin(math.radians(rot_ang))]
                        i.rot_angi_sum += unitvector[0] * k.ref_star_dist
                        i.rot_angj_sum += unitvector[1] * k.ref_star_dist
                        i.rot_dist_sum += k.ref_star_dist
                        rot_ang = math.degrees(math.atan2(i.rot_angj_sum / i.rot_dist_sum, i.rot_angi_sum / i.rot_dist_sum))
                        i.rotation = rot_ang

                        if k.ref_star_dist > max_dist:
                            max_dist = k.ref_star_dist # establishes maximum matching area
                        if k.brightness < min_brite or min_brite < 0:
                            min_brite = k.brightness # establishes minimum matching brightness

                        # measured vs supposed distances may be different, track the differences
                        # this will account for distortion and focus-breathing
                        i.pix_calibration.append(k.ref_star_dist / STARS_NEAR_POLARIS[idx_tbl][1])

                        # all previous (closer-to-Polaris) entries to be ignored on the next loop
                        idx_blobs_start = idx_blobs # doing this will prevent potential out-of-order matches

                        #i.score_list.append(STARS_NEAR_POLARIS[idx_tbl][0]) # save the name to the list of matches (score)
                        i.score_list.append(k)

                        if self.debug:
                            print("score %u , new rotation %.1f" % (len(i.score_list), rot_ang))

                    idx_blobs += 1
                idx_tbl += 1

            # penalty function is optional
            if ENABLE_PENALTY:
                # go through all blobs again to see if we should penalize for mystery stars
                # if a star is brighter than some of the stars we've been able to match against
                # then it's a mystery star, and makes the solution less confident
                idx_blobs = 1
                while idx_blobs < len_blobs:
                    k = dist_sorted[idx_blobs]
                    if k.ref_star_dist < max_dist and k.brightness > min_brite:
                        # within the area and also brighter than expected
                        # does it match an entry in the table? (some of the table entries were ignored previously, so we have to do the whole check again)
                        in_database = False
                        idx_tbl = 0
                        len_tbl = len(STARS_NEAR_POLARIS)
                        while idx_tbl < len_tbl:
                            if dist_match(k.ref_star_dist, STARS_NEAR_POLARIS[idx_tbl][1]) and angle_match(k.ref_star_angle, ang_normalize(STARS_NEAR_POLARIS[idx_tbl][2] + rot_ang)):
                                in_database = True
                                break
                            idx_tbl += 1

                        if in_database == False:
                            is_hot = False
                            # check if it's a hot pixel
                            for hp in self.hot_pixels:
                                d = math.sqrt(((k.cx - hp[0]) ** 2) + ((k.cy - hp[1]) ** 2))
                                if d < 2.0:
                                    is_hot = True
                                    break
                            if is_hot == False:
                                i.penalty += 1
                                if self.debug:
                                    print("penalty (%.1f , %.1f)" % (k.cx, k.cy))
                    idx_blobs += 1
                # calculate score accounting for penalty
                i.score = len(i.score_list) - i.penalty

        # end of the for loop that goes from brightest to dimmest
        # each entry of that list will now have a "score" (number of matches)
        # find the one that has the most matches
        score_sorted = sorted(brite_sorted, key = sort_score_func, reverse = True)
        self.star_list = None # garbage collect
        if score_sorted[0].score < SCORE_REQUIRED:
            return False # not enough matches, no solution

        self.solved = True
        # store the solution states
        self.Polaris = score_sorted[0]
        self.rotation = score_sorted[0].rotation
        self.rotation = ang_normalize(self.rotation + 180.0) # everything needs to be flipped
        self.stars_matched = score_sorted[0].score_list # for debug purposes
        self.penalty = score_sorted[0].penalty
        dist_calibration = 0
        for i in score_sorted[0].pix_calibration:
            dist_calibration += i
        dist_calibration /= len(score_sorted[0].pix_calibration)
        self.pix_per_deg = PIXELS_PER_DEGREE * dist_calibration
        return True

    def get_rotation(self, compensate = True):
        if self.solu_time == 0 or compensate == False:
            return self.rotation
        # compensate for the rotation that occured between solution and now
        t = int(round(pyb.millis() // 1000))
        dt = t - self.solu_time
        dt += self.accel_sec # for simulation only
        rot = float(dt) * 360.0
        rot /= 86164.09054 # sidereal day length
        return self.rotation - rot

    def get_pole_coords(self):
        if self.solved == False:
            raise Exception("no solution")
        if self.x is not None:
            return self.x, self.y, self.get_rotation()
        x, y, r = self.get_pole_coords_for(self.Polaris)
        self.x = x
        self.y = y
        return self.x, self.y, self.get_rotation()

    def get_pole_coords_for(self, star):
        if self.solved == False:
            raise Exception("no solution")
        rahr  = self.polaris_ra_dec[0]
        dec   = self.polaris_ra_dec[1]
        radeg = (rahr * 360.0) / 24.0
        ra_adj = radeg + self.get_rotation()
        rho = (90.0 - dec) * self.pix_per_deg
        phi = math.radians(ra_adj + 180.0)
        dx = rho * math.cos(phi)
        dy = rho * math.sin(phi)
        x = star.cx + dx
        y = star.cy + dy # y is flipped!
        return x, y, self.get_rotation()

    def compare(self, tgt):
        if tgt.solved == False:
            return False
        x, y, r = self.get_pole_coords()
        if abs(tgt.x - x) < 1.0 and abs(tgt.y - y) < 1.0 and abs(angle_diff(tgt.rotation, r)) < 1.0:
            return True
        return False

    def to_jsonobj(self):
        x, y, r = self.get_pole_coords()
        obj = {}
        obj.update({"cx": x})
        obj.update({"cy": y})
        obj.update({"r": r})
        obj.update({"cnt": len(self.stars_matched)})
        obj.update({"pix_per_deg": self.pix_per_deg})
        obj.update({"px": self.Polaris.cx})
        obj.update({"py": self.Polaris.cy})
        obj.update({"matches": blobstar.to_jsonobj(self.stars_matched)})
        return obj

def dist_match(x, y):
    err_tol = x * DIST_TOL
    abs_err = abs(x - y)
    return abs_err <= err_tol

def angle_diff(x, y):
    x = ang_normalize(x)
    y = ang_normalize(y)
    return ang_normalize(x - y)

def angle_match(x, y, tol = 1.0):
    d = abs(angle_diff(x, y))
    return d <= tol

def ang_normalize(x):
    while x > 180.0:
        x -= 360.0
    while x < -180.0:
        x += 360.0
    return x

def sort_score_func(x):
    return x.score

if __name__ == "__main__":
    import test_bench
    test_bench.test()
