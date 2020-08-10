import blobstar
try:
    import numpy as np
    pass
except:
    import math
try:
    import gc
    pass
except:
    pass

# NOTE: data table and image both respect computer image coordinate system (origin at top left corner)
# positive angle is clockwise

# this table is pre-generated
# vector to a star from Polaris, magnitude in pixels
# sorted by closest first
STARS_NEAR_POLARIS = [
    ["HD 5914",         98.867180,  -10.647256],
    ["* lam UMi",      479.008301, -118.529852],
    ["HD 66368",       524.994808,  164.780381],
    ["HD 213126",      534.725064,  -51.636087],
    ["HD 6319",        654.323145,   12.759174],
    ["HD 22701",       820.441622,   68.948647],
    ["V* OV Cep",      875.677409,  129.407251], # 2.9063 arc degs from Polaris
    ["V* UY UMi",      884.833301, -168.092577],
    ["HD 203836",      896.804216,  -59.867339],
    ["HD 114282",      914.532044, -160.757620],
    ["HD 42855",       927.519046,  115.447469],
    ["HD 135294",     1060.463568, -140.366796],
    ["* 24 UMi",      1082.153394, -105.587018],
    ["* del UMi",     1195.457555, -104.488215],
    ["HD 107113",     1264.471354, -170.201903]]

PIXELS_PER_DEGREE = 875.677409 / 2.9063 # calculated using "OV Cep"
DIST_TOL = 0.03 # percentage
ANG_TOL  = 1.0  # degrees
SCORE_REQUIRED = 4 # must have this many stars that match their estimated coordinates

class PoleSolution(object):
    def __init__(self, star_list):
        self.solved = False
        self.star_list = star_list

    def solve(self):
        try:
            gc.collect()
        except:
            pass

        if len(self.star_list) < SCORE_REQUIRED:
            return False # impossible to have a solution if not enough stars

        # Polaris is the brightest object in the potential field of view, so it's faster to start with it
        brite_sorted = blobstar.sort_brightness(self.star_list)
        for i in brite_sorted:
            # we are guessing "i" is Polaris for this iteration
            i.score = []
            i.rotation = 0
            i.rot_ang_sum = 0
            i.rot_dist_sum = 0
            i.pix_calibration = []

            for j in brite_sorted:
                j.set_ref_star(i) # this is required for all entries in the list, so that sort_dist can work
                # set_ref_star also computes the vector to the ref star and caches the result
            dist_sorted = blobstar.sort_dist(self.star_list) # sorted closest-to-Polaris first

            rot_ang = None # without a known reference angle, use the first angle we encounter to establish a reference angle
            # rot_ang is set after the match is made

            idx_tbl = 0
            idx_blobs_start = 1 # start at [1] because [0] is supposed to be Polaris
            len_tbl = len(STARS_NEAR_POLARIS)
            len_blobs = len(dist_sorted)
            while idx_tbl < len_tbl:
                idx_blobs = idx_blobs_start # previous blobs (closer-to-Polaris) will be ignored
                while idx_blobs < len_blobs:
                    k = dist_sorted[idx_blobs]
                    match = False
                    if dist_match(k.ref_star_dist, STARS_NEAR_POLARIS[idx_tbl][1]):
                        if rot_ang is None:
                            # without a known reference angle, use the first angle we encounter to establish a reference angle
                            # rot_ang is set after the match is made
                            match = True
                        else:
                            adj_ang = ang_normalize(STARS_NEAR_POLARIS[idx_tbl][2] - rot_ang)
                            if angle_match(k.ref_star_angle, adj_ang):
                                match = True
                    if match:
                        # each match is a further star, which means more precise angle
                        # compute (and update) the weighted average of the angle offset
                        rot_ang = angle_diff(k.ref_star_angle, STARS_NEAR_POLARIS[idx_tbl][2])
                        i.rot_ang_sum += rot_ang * k.ref_star_dist
                        i.rot_dist_sum += k.ref_star_dist
                        rot_ang = i.rot_ang_sum / i.rot_dist_sum
                        i.rotation = rot_ang

                        # measured vs supposed distances may be different, track the differences
                        # this will account for distortion and focus-breathing
                        i.pix_calibration.append(k.ref_star_dist / STARS_NEAR_POLARIS[idx_tbl][1])

                        # all previous (closer-to-Polaris) entries to be ignored on the next loop
                        idx_blobs_start = idx_blobs # doing this will prevent potential out-of-order matches

                        i.score.append(STARS_NEAR_POLARIS[idx_tbl][0]) # save the name to the list of matches (score)
                    idx_blobs += 1
                idx_tbl += 1
        # end of the for loop that goes from brightest to dimmest
        # each entry of that list will now have a "score" (number of matches)
        # find the one that has the most matches
        score_sorted = sorted(brite_sorted, key = sort_score_func, reverse = True)
        if len(score_sorted[0].score) < SCORE_REQUIRED:
            return False # not enough matches, no solution

        self.solved = True
        # store the solution states
        self.Polaris = score_sorted[0]
        self.rotation = score_sorted[0].rotation
        self.stars_matched = score_sorted[0].score # for debug purposes
        dist_calibration = 0
        for i in score_sorted[0].pix_calibration:
            dist_calibration += i
        dist_calibration /= len(score_sorted[0].pix_calibration)
        self.pix_per_deg = PIXELS_PER_DEGREE * dist_calibration
        return True

    def get_pole_coords(self, polaris_ra_dec = (2.960856, 89.349278)):
        if self.solved == False:
            raise Exception("no solution")
        # polaris_ra_dec default to values at Jan 1 2020
        # supply new values according to current date
        rahr  = polaris_ra_dec[0]
        dec   = polaris_ra_dec[1]
        radeg = (rahr * 360.0) / 24.0
        ra_adj = radeg - self.rotation
        rho = (90.0 - dec) * self.pix_per_deg
        try:
            phi = np.radians(360.0 * ra_adj / 24.0)
            dx = rho * np.cos(phi)
            dy = rho * np.sin(phi)
        except:
            phi = math.radians(360.0 * ra_adj / 24.0)
            dx = rho * math.cos(phi)
            dy = rho * math.sin(phi)
        self.x = self.Polaris.cx + dx
        self.y = self.Polaris.cy - dy # y is flipped!
        return self.x, self.y

def dist_match(x, y):
    err_tol = x * DIST_TOL
    abs_err = abs(x - y)
    return abs_err <= err_tol

def angle_diff(x, y):
    return 180.0 - abs(abs(ang_normalize(x) - ang_normalize(y)) - 180)

def angle_match(x, y):
    d = angle_diff(x, y)
    return d <= ANG_TOL

def ang_normalize(x):
    while x > 180.0:
        x -= 360.0
    while x < -180.0:
        x += 360.0
    return x

def sort_score_func(x):
    return len(x.score)

def test():
    test_input = [
    [397.18523026, 352.17618942, 3.00000000, 663.99998665 ],
    [2083.69231224, 353.98778915, 5.33333349, 2782.00006485 ],
    [2054.12411690, 369.41549778, 2.66666675, 709.99999046 ],
    [2463.42802048, 439.18943405, 5.00000000, 2702.99983025 ],
    [2368.38316917, 465.73734283, 4.66666651, 2588.99998665 ],
    [986.39898300, 603.85775566, 5.33333349, 2826.99985504 ],
    [1842.11635590, 765.32363892, 3.66666675, 1822.99995422 ],
    [350.78625679, 845.62540054, 3.00000000, 944.99998093 ],
    [1314.42451477, 1002.91526318, 2.33333325, 708.99996758 ],
    [1215.90340137, 1021.48807049, 13.33333373, 31816.99991226 ],
    [1855.34992218, 1161.86487675, 3.33333325, 1517.00010300 ],
    [2118.60203743, 1212.23235130, 8.00000000, 9802.00004578 ],
    [666.57261848, 1701.49030685, 8.00000000, 8348.99997711 ],
    [1517.31705666, 1784.47270393, 3.00000000, 1722.00002670 ],
    [825.48303604, 1862.05902100, 2.33333325, 558.99996758 ]]
    uidmgr = blobstar.BlobStarUidManager()
    stars = []
    for i in test_input:
        stars.append(blobstar.BlobStar(uidmgr.generate(), i[0], i[1], i[2], i[3]))
    sol = PoleSolution(stars)
    if sol.solve():
        print("solution found!")
        print(sol.stars_matched)
        x, y = sol.get_pole_coords()
        print("%f, %f, %f" % (x, y, sol.rotation))
    else:
        print("no solution")

if __name__ == "__main__":
    test()
