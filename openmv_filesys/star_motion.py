import math

class PossibleMove(object):
    def __init__(self, dx, dy, dist, ang, star):
        self.dx = dx
        self.dy = dy
        self.dist = dist
        self.ang = ang
        self.star = star
        self.nearby = 0
        self.err_sum = 0
        self.score = 0

    def calc_score(self):
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
            dx = k.cx - nx
            dy = k.cy - ny
            mag = math.sqrt((dx * dx) + (dy * dy))
            if mag < min_dist:
                min_dist = mag
        if min_dist < tolerance + (tolerance * abs(math.tan(math.radians(declination)))):
            move.nearby += 1
            move.err_sum += min_dist
    return move

def get_star_movement(old_list, star, new_list, declination = 0, tolerance = 100, fast_mode = False):
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
        ang = math.degrees(math.atan2(dy, dx))
        move = PossibleMove(dx, dy, mag, ang, i)
        possible_moves.append(move)
        if mag < closest_dist:
            closest_dist = mag
            closest_star = i
        if fast_mode:
            eval_move(move, old_list, new_list, declination, tolerance)
            if move.calc_score() < tolerance and move.nearby > len(new_list) * 0.75:
                return move.star, move.score, move.nearby

    # if only one star in old view, then assume the movement is minimal
    if len(old_list) <= 1:
        return closest_star, 0, 1

    if fast_mode == False:
        for move in possible_moves:
            eval_move(move, old_list, new_list, declination, tolerance)

    # we have examined each possibility, take the top percentile, ignore the bottom
    acceptable_moves = []
    avg_nearby = 0
    for i in possible_moves:
        avg_nearby += i.nearby
    avg_nearby /= len(possible_moves)
    acceptable_nearby = avg_nearby * 1.5
    for i in possible_moves:
        if i.nearby >= acceptable_nearby and i.nearby >= len(new_list) / 2:
            acceptable_moves.append(i)

    # at least have one possibility to work with
    if len(acceptable_moves) <= 0 and len(possible_moves) >= 1:
        acceptable_moves.append(possible_moves[0])

    # find the most likely move, the one with most matches and least error
    lowest_score = -1
    best_move = None
    for i in acceptable_moves:
        score = i.calc_score()
        if lowest_score < 0 or score < lowest_score:
            lowest_score = score
            best_move = i

    if best_move is None:
        return None, 0, 0
    return best_move.star, best_move.score, best_move.nearby

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

    best_star, best_score, nearby = get_star_movement(star_list, star_list[0], new_list, fast_mode = True)
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
