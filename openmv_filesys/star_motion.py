import micropython
micropython.opt_level(2)

import math
import blobstar
import comutils
from comutils import SENSOR_WIDTH, SENSOR_HEIGHT

class PossibleMove(object):
    def __init__(self, dx, dy, star):
        self.dx = dx
        self.dy = dy
        self.star = star
        self.nearby = 0
        self.err_sum = 0
        self.score = 999999

    def calc_score(self):
        if self.nearby <= 0:
            self.score = 999999
            return self.score
        self.score = self.err_sum / (math.pow(self.nearby, 1.1))
        return self.score

class TestStar(object):
    def __init__(self, cx, cy):
        self.cx = cx
        self.cy = cy

def eval_move(move, old_list, new_list, declination, tolerance):
    for j in old_list:
        # if this is the movement, then where should the new star be, referencing the old star
        nx = j.cx + move.dx
        ny = j.cy + move.dy
        min_dist = 9999
        # find the closest match in the new list to the new star
        for k in new_list:
            mag = comutils.vector_between([nx, ny], [k.cx, k.cy], mag_only = True)
            if mag < min_dist:
                min_dist = mag
        if declination is not None:
            tolerance += tolerance * abs(math.tan(math.radians(declination)))
        if min_dist < tolerance:
            move.nearby += 1
            move.err_sum += min_dist
    move.calc_score()
    return move

def get_star_movement(old_list, star, new_list, declination = None, tolerance = 50, fast_mode = False):
    if old_list is None or star is None:
        return None, 999999, 0

# if only one star in new view, then assume it's the one
    if len(new_list) <= 1:
        return new_list[0], 0, 1

    possible_moves = []
    closest_dist = 9999
    closest_star = None
    for i in new_list:
        # each star in the new list is a possible movement vector
        dx = i.cx - star.cx
        dy = i.cy - star.cy
        mag = math.sqrt((dx * dx) + (dy * dy))
        move = PossibleMove(dx, dy, i)
        possible_moves.append(move)
        if mag < closest_dist:
            closest_dist = mag
            closest_star = i
        if fast_mode:
            eval_move(move, old_list, new_list, declination, tolerance)
            if move.score < tolerance and move.nearby > len(new_list) * 0.75:
                return move.star, move.score, move.nearby

    # if only one star in old view, then assume the movement is minimal
    if len(old_list) <= 1:
        return closest_star, 0, 1

    if fast_mode == False:
        for move in possible_moves:
            eval_move(move, old_list, new_list, declination, tolerance)

    # we have examined each possibility, take the top percentile, ignore the bottom
    acceptable_moves = []
    max_nearby = 0
    min_nearby = 0
    min_score  = -1
    best_move = None
    for i in possible_moves:
        nb = i.nearby
        s  = i.score
        if nb > max_nearby:
            max_nearby = nb
        elif nb < min_nearby or min_nearby <= 0:
            min_nearby = nb
        if s < min_score or min_score < 0:
            min_score = s
            best_move = i
    acceptable_nearby = min_nearby + ((max_nearby - min_nearby) * 0.75)
    for i in possible_moves:
        if i.nearby >= acceptable_nearby and i.nearby >= len(new_list) / 2:
            acceptable_moves.append(i)

    if len(acceptable_moves) <= 0:
        return None, 999999, 0
    """
    # at least have one possibility to work with
    if len(acceptable_moves) <= 0 and len(possible_moves) >= 1:
        if best_move is not None:
            acceptable_moves.append(best_move)
        else:
            acceptable_moves.append(possible_moves[0])
    """

    # find the most likely move, the one with most matches and least error
    lowest_score = -1
    best_move = None
    for i in acceptable_moves:
        s = i.score
        if lowest_score < 0 or s < lowest_score:
            lowest_score = s
            best_move = i

    if best_move is None:
        return None, 999999, 0
    return best_move.star, best_move.score, best_move.nearby

def get_all_star_movement(old_list, new_list, selected_star = None, cnt_min = 1, cnt_limit = 10, rating_thresh = 0, declination = None, tolerance = 50, fast_mode = False):
    if len(old_list) <= 0:
        return None, None, None, -1, 0
    # the most reliable stars should be processed first,
    # and the very first one used as the target star for initial analysis
    old_list = blobstar.sort_rating(old_list)
    if selected_star is None:
        selected_star = old_list[0]
    star, score, nearby = get_star_movement(old_list, selected_star, new_list, declination = declination, tolerance = tolerance, fast_mode = fast_mode)
    if star is None:
        return None, None, None, -1, 0
    dx = star.cx - selected_star.cx
    dy = star.cy - selected_star.cy
    dx_sum = 0
    dy_sum = 0
    avg_cnt = 0
    avg_weight = 0
    for i in old_list:
        # for every star in the old list, find the predicted new coordinate using the info about the best possible move
        nx = i.cx + dx
        ny = i.cy + dy
        # find the star in the new list that is closest to the new predicted coordinate
        nearest = None
        nearest_mag = 9999
        best_dx = 0
        best_dy = 0
        for j in new_list:
            ndx = j.cx - i.cx
            ndy = j.cy - i.cy
            mag = math.sqrt((ndx * ndx) + (ndy * ndy))
            if mag < nearest_mag:
                # if we find the one closest to the new predicted coordinate, remember the actual movement between the old and new coordinate
                nearest_mag = mag
                nearest = j
                best_dx = ndx
                best_dy = ndy
        if nearest is not None and nearest_mag < tolerance:
            # if confidently found one closest to the new predicted coordinate
            # use it in the average movement if it meets the criteria
            if avg_cnt < cnt_min or (i.rating >= rating_thresh and nearest.rating >= rating_thresh):
                # the average movement is computed with a weight
                # the closer it is to selected_star, the more weight it has
                dist_ori = comutils.vector_between([selected_star.cx, selected_star.cy], [i.cx, i.cy], mag_only=True)
                dist_weight = comutils.SENSOR_DIAG - dist_ori
                dx_sum  += best_dx * dist_weight
                dy_sum  += best_dy * dist_weight
                avg_cnt += 1
                avg_weight += dist_weight
            if avg_cnt >= cnt_limit:
                break # limit reached, end the analysis
    if avg_cnt <= 0:
        # hmm... all stars have bad rating?
        # fall back on using the original calculated move
        dx_avg = dx
        dx_avg = dy
    else:
        # average all of the movements
        dx_avg = dx_sum / avg_weight
        dy_avg = dy_sum / avg_weight
    mag, ang = comutils.vector_between([0, 0], [dx_avg, dy_avg])
    return star, [selected_star.cx + dx_avg, selected_star.cy + dy_avg], [dx_avg, dy_avg, mag, ang], score, avg_cnt

def move_multistar(dx, dy, new_list, old_selected):
    new_list = []
    for i in old_selected:
        nx = i.cx + dx
        ny = i.cy + dy
        nearest = None
        nearest_mag = 9999
        for j in new_list:
            mag = comutils.vector_between([nx, ny], [j.cx, j.cy], mag_only = True)
            if mag < nearest_mag:
                nearest_mag = mag
                nearest = j
        if nearest is not None:
            new_list.append(nearest)
    return new_list

def test(fname = None):
    from PIL import Image, ImageDraw, ImageFont
    import random

    SENSOR_WIDTH  = 2592
    SENSOR_HEIGHT = 1944

    start_x = random.randint(int(round(SENSOR_WIDTH / 3)), int(round(SENSOR_WIDTH * 2 / 3)))
    start_y = random.randint(int(round(SENSOR_HEIGHT / 3)), int(round(SENSOR_HEIGHT * 2 / 3)))

    star_cnt = random.randint(200, 400)
    print("star cnt %u" % star_cnt)
    star_list = []
    star_list.append(TestStar(start_x, start_y))
    while len(star_list) < star_cnt:
        x = random.randint(int(round(SENSOR_WIDTH / 8)), int(round(SENSOR_WIDTH * 7 / 8)))
        y = random.randint(int(round(SENSOR_HEIGHT / 8)), int(round(SENSOR_HEIGHT * 7 / 8)))
        star_list.append(TestStar(x, y))

    shift_x = random.randint(-int(round(SENSOR_HEIGHT / 8)), int(round(SENSOR_HEIGHT / 8)))
    shift_y = random.randint(-int(round(SENSOR_HEIGHT / 8)), int(round(SENSOR_HEIGHT / 8)))
    print("shift (%d , %d)" % (shift_x, shift_y))

    new_list = []
    for i in star_list:
        x = i.cx + shift_x + random.randint(-10, 10)
        y = i.cy + shift_y + random.randint(-10, 10)
        new_list.append(TestStar(x, y))

    best_star, best_score, nearby, move = get_star_movement(star_list, star_list[0], new_list, fast_mode = True)
    print("result %.1f %u/%u" % (best_score, nearby, len(star_list)))

    im = Image.new("RGB", (SENSOR_WIDTH, SENSOR_HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(im)
    radius = 6
    for i in star_list:
        draw.ellipse([(i.cx - radius, i.cy - radius), (i.cx + radius, i.cy + radius)], fill=(64, 64 * 3, 64))
    for i in new_list:
        draw.ellipse([(i.cx - radius, i.cy - radius), (i.cx + radius, i.cy + radius)], fill=(255, 255, 255))
    draw.line([(start_x, start_y), (best_star.cx, best_star.cy)], fill=(255, 0, 0), width = radius)
    for i in star_list:
        draw.line([(i.cx, i.cy), (i.cx + (best_star.cx - start_x), i.cy + (best_star.cy - start_y))], fill=(0, 0, 128), width = int(round(radius / 2)))
    if fname is None:
        im.save("test_movement_result.png")
    else:
        if len(fname) == 0:
            im.save("test_movement_result.png")
        else:
            im.save(fname)
    im.show()

if __name__ == "__main__":
    test()
