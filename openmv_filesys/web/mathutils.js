function math_radians2degrees(x)
{
    return x * 180.0 / Math.PI;
}

function math_degrees2radians(x)
{
    return x * Math.PI / 180.0;
}

function math_normalizeAngleDegrees(x)
{
    while (x > 180.0) {
        x -= 360.0;
    }
    while (x < -180.0) {
        x += 360.0;
    }
    return x;
}

function math_getVector(p1, p2)
{
    var dx = p2[0] - p1[0];
    var dy = p2[1] - p1[1];
    var angle = math_radians2degrees(Math.atan2(dy, dx));
    var mag = Math.sqrt((dx * dx) + (dy * dy));
    return [mag, angle];
}

function math_getMidpointFromTwoPoints(p1, p2)
{
    var xsum = p1[0] + p2[0];
    var ysum = p1[1] + p2[1];
    return [xsum / 2.0, ysum / 2.0];
}

function math_getSlopeAngleFromTwoPoints(p1, p2)
{
    var v = math_getVector(p1, p2);
    return v[1];
}

function math_getAngleDiff(a1, a2)
{
    return 180.0 - Math.abs(Math.abs(math_normalizeAngleDegrees(a1) - math_normalizeAngleDegrees(a2)) - 180.0)
}

function math_isNear90Apart(x, tol)
{
    if (x == null) {
        return false;
    }

    var d = Math.abs(math_getAngleDiff(x, 90));
    if (d <= tol) {
        return true;
    }
    d = Math.abs(math_getAngleDiff(x, 270));
    if (d <= tol) {
        return true;
    }
    d = Math.abs(math_getAngleDiff(x, -90));
    if (d <= tol) {
        return true;
    }
    d = Math.abs(math_getAngleDiff(x, -270));
    if (d <= tol) {
        return true;
    }
    return false;
}

function math_getPerpendicularBisectLineForTwoPoints(p1, p2)
{
    var midpoint = math_getMidpointFromTwoPoints(p1, p2);
    var angle = math_getSlopeAngleFromTwoPoints(p1, p2);
    angle += 90.0;
    var angr = math_degrees2radians(angle);
    var rho = 100.0;
    var dx = rho * Math.cos(angr);
    var dy = rho * Math.sin(angr);
    var x = midpoint[0] + dx;
    var y = midpoint[1] + dy;
    return [midpoint, [x, y], angle];
}

// https://stackoverflow.com/questions/13937782/calculating-the-point-of-intersection-of-two-lines
// http://jsfiddle.net/justin_c_rounds/Gd2S2/
function checkLineIntersection(line1StartX, line1StartY, line1EndX, line1EndY, line2StartX, line2StartY, line2EndX, line2EndY) {
    // if the lines intersect, the result contains the x and y of the intersection (treating the lines as infinite) and booleans for whether line segment 1 or line segment 2 contain the point
    var denominator, a, b, numerator1, numerator2, result = {
        x: null,
        y: null
    };
    denominator = ((line2EndY - line2StartY) * (line1EndX - line1StartX)) - ((line2EndX - line2StartX) * (line1EndY - line1StartY));
    if (denominator == 0) {
        return result;
    }
    a = line1StartY - line2StartY;
    b = line1StartX - line2StartX;
    numerator1 = ((line2EndX - line2StartX) * a) - ((line2EndY - line2StartY) * b);
    numerator2 = ((line1EndX - line1StartX) * a) - ((line1EndY - line1StartY) * b);
    a = numerator1 / denominator;
    b = numerator2 / denominator;

    // if we cast these lines infinitely in both directions, they intersect here:
    result.x = line1StartX + (a * (line1EndX - line1StartX));
    result.y = line1StartY + (a * (line1EndY - line1StartY));
    return result;
}

function math_calcRotationCenterFromTwoPointPairs(pp1, pp2)
{
    var midpoint1 = math_getMidpointFromTwoPoints(pp1[0], pp2[0]);
    var midpoint2 = math_getMidpointFromTwoPoints(pp1[1], pp2[1]);
    var bisect1 = math_getPerpendicularBisectLineForTwoPoints(pp1[0], pp2[0]);
    var bisect2 = math_getPerpendicularBisectLineForTwoPoints(pp1[1], pp2[1]);
    var anglediff = math_getAngleDiff(math_getSlopeAngleFromTwoPoints(bisect1[0], bisect1[1]), math_getSlopeAngleFromTwoPoints(bisect2[0], bisect2[1]));
    var result = checkLineIntersection(bisect1[0][0], bisect1[0][1], bisect1[1][0], bisect1[1][1], bisect2[0][0], bisect2[0][1], bisect2[1][0], bisect2[1][1]);

    if (result.x != null && result.x != 0 && result.y != null && result.y != 0)
    {
        // validate angles
        var vect1 = math_getVector(pp1[0], midpoint1);
        var vect2 = math_getVector(pp2[1], midpoint2);
        var vect3 = math_getVector([result.x, result.y], midpoint1);
        var vect4 = math_getVector([result.x, result.y], midpoint2);
        // this validation only works if the lines are long enough
        var maglim = 10.0;
        if (vect1[0] >= maglim && vect2[0] >= maglim && vect3[0] >= maglim && vect4[0] >= maglim)
        {
            if (math_isNear90Apart(math_getAngleDiff(vect1[1], vect3[1]), 1) == false || math_isNear90Apart(math_getAngleDiff(vect2[1], vect4[1]), 1) == false) {
                anglediff = null;
            }
        }
    }

    return [[result.x, result.y], midpoint1, midpoint2, bisect1[2], bisect2[2], anglediff];
}

function math_getGhostResults(obj, ghost)
{
    if (ghost === null || ghost === false) {
        return null;
    }
    var v1 = math_getVector([obj["star_x"], obj["star_y"]], [ghost["star_x"], ghost["star_y"]]);
    var v2 = math_getVector([obj["pole_x"], obj["pole_y"]], [ghost["pole_x"], ghost["pole_y"]]);
    if (v1[0] < 8 && v2[0] < 8) {
        return null;
    }
    var res = { star_x: obj["star_x"], star_y: obj["star_y"],
                pole_x: obj["pole_x"], pole_y: obj["pole_y"],
                ghost_sx: ghost["star_x"], ghost_sy: ghost["star_y"],
                ghost_px: ghost["pole_x"], ghost_py: ghost["pole_y"],
                mp1_x: 0, mp1_y: 0, mp2_x: 0, mp2_y: 0, cent_x: 0, cent_y: 0, angle: 0};

    var calc = math_calcRotationCenterFromTwoPointPairs([[res.star_x, res.star_y],[res.pole_x, res.pole_y]], [[res.ghost_sx, res.ghost_sy],[res.ghost_px, res.ghost_py]]);
    res.cent_x = calc[0][0];
    res.cent_y = calc[0][1];
    res.mp1_x = calc[1][0];
    res.mp1_y = calc[1][1];
    res.mp2_x = calc[2][0];
    res.mp2_y = calc[2][1];
    res.angle = calc[5];
    return res;
}

function math_movePoint(p, dx, dy)
{
    return [p[0] + dx, p[1] + dy];
}

function math_movePointTowards(p, v)
{
    var phi = math_degrees2radians(v[1]);
    var dx = v[0] * Math.cos(phi);
    var dy = v[0] * Math.sin(phi);
    return math_movePoint(p, dx, dy);
}

function math_mapStarRadius(r, minr, maxr, imgh)
{
    var imgr = imgh * 0.01;
    if (imgr < 4) {
        imgr = 4;
    }
    var d1 = maxr - minr;
    var d2 = imgr - 2;
    r -= minr;
    r *= d2;
    r /= d1;
    r += 2;
    if (r > imgr) {
        return imgr;
    }
    else if (r < 2) {
        return 2;
    }
    return r;
}

function math_getRefraction(lat, pressure, temperature)
{
    var x = math_degrees2radians(lat + (10.3 / (lat + 5.11)));
    x = 1.02 / Math.tan(x);
    var tempcomp = (pressure / 101) * (283 / (273 + temperature));
    var arcmin = x * tempcomp;
    if (arcmin < 0) {
        arcmin = 0;
    }
    return [arcmin / 60.0, arcmin];
}

function math_roundPlaces(x, places)
{
    var f = 1.0;
    var i;
    for (i = 0; i < places && places >= 0; i++)
    {
        f *= 10.0;
    }
    for (i = 0; i < (-places) && places < 0; i++)
    {
        f /= 10.0;
    }
    return Math.round(x * f) / f;
}

function time_getNowEpoch()
{
    var date = new Date();
    var epoch2000 = new Date(Date.UTC(2000, 0, 1));
    var nowEpoch = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), date.getUTCHours(), date.getUTCMinutes(), date.getUTCSeconds()));
    var nowEpoch2000 = nowEpoch - epoch2000;
    nowEpoch2000 = Math.round(nowEpoch2000 / 1000.0);
    return nowEpoch2000;
}

function hsv_2_rgb(h, s, v)
{
    var r, g, b, i, f, p, q, t;
    if (arguments.length === 1) {
        s = h.s, v = h.v, h = h.h;
    }
    i = Math.floor(h * 6);
    f = h * 6 - i;
    p = v * (1 - s);
    q = v * (1 - f * s);
    t = v * (1 - (1 - f) * s);
    switch (i % 6) {
        case 0: r = v, g = t, b = p; break;
        case 1: r = q, g = v, b = p; break;
        case 2: r = p, g = v, b = t; break;
        case 3: r = p, g = q, b = v; break;
        case 4: r = t, g = p, b = v; break;
        case 5: r = v, g = p, b = q; break;
    }
    return {
        r: Math.round(r * 255),
        g: Math.round(g * 255),
        b: Math.round(b * 255)
    };
}
