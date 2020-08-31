import astro_sensor
import star_finder
import pole_finder

def test():
    print("hello")
    cam = astro_sensor.AstroCam(simulate = "simulate.bmp")
    print("loaded image")

    img = cam.snapshot()

    stars, code = star_finder.find_stars(img, thresh = 0, force_solve = True)

    print("found %u stars" % len(stars))

    i = 0
    while i < len(stars):
        s = stars[i]
        print("[%u]: [%.1f, %.1f, %.1f, %.1f]" %(i, s.cx, s.cx, s.r, s.brightness))
        i += 1

    solution = pole_finder.PoleSolution(stars, search_limit = 1, debug = True)

    if solution.solve():
        print("solved, %u matches" % len(solution.stars_matched))
    else:
        print("failed")

    print("bye")

if __name__ == "__main__":
    test()
