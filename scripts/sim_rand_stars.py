#!/usr/bin/env python

import sys, random
import numpy as np
from PIL import Image, ImageDraw

SENSOR_WIDTH  = 2592
SENSOR_HEIGHT = 1944

im = Image.new("RGB", (SENSOR_WIDTH, SENSOR_HEIGHT), (0, 0, 0))
draw = ImageDraw.Draw(im)

# generate some random background noise
x = 0
while x < SENSOR_WIDTH:
    y = 0
    while y < SENSOR_HEIGHT:
        b = random.randint(4, 24)
        draw.point((x, y), fill = (b, b, b))
        y += 1
    x += 1

num_stars = random.randint(30, 100)

i = 0
while i < num_stars:
    r = random.randint(5, 30) / 3.0
    x = random.randint(int(round(r * 3)), int(round(SENSOR_WIDTH - (r * 3))))
    y = random.randint(int(round(r * 3)), int(round(SENSOR_HEIGHT - (r * 3))))
    d = 255 // int(round(r * 1.5))
    j = 8
    k = r
    # draw filled circles with increasing brightness but decreasing radius
    # this makes sort-of-realistic stars
    while k >= 0:
        j += random.randint(d, d + 32)
        if j > 255:
            j = 255
        draw.ellipse(((x - k, y - k), (x + k, y + k)), fill = (j, j, j))
        k -= 1
    i += 1

im.show()
im.save("rand_stars.bmp")
