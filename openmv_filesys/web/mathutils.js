function math_radians2degrees(x)
{
    return x * 180.0 / Math.PI;
}

function math_degrees2radians(x)
{
    return x * (Math.PI / 180.0);
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
        y: null,
        onLine1: false,
        onLine2: false
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
/*
        // it is worth noting that this should be the same as:
        x = line2StartX + (b * (line2EndX - line2StartX));
        y = line2StartX + (b * (line2EndY - line2StartY));
        */
    // if line1 is a segment and line2 is infinite, they intersect if:
    if (a > 0 && a < 1) {
        result.onLine1 = true;
    }
    // if line2 is a segment and line1 is infinite, they intersect if:
    if (b > 0 && b < 1) {
        result.onLine2 = true;
    }
    // if line1 and line2 are segments, they intersect if both of the above are true
    return result;
}

function math_calcRotationCenterFromTwoPointPairs(pp1, pp2)
{
    var midpoint1 = math_getMidpointFromTwoPoints(pp1[0], pp2[0]);
    var midpoint2 = math_getMidpointFromTwoPoints(pp1[1], pp2[1]);
    var bisect1 = math_getPerpendicularBisectLineForTwoPoints(pp1[0], pp2[0]);
    var bisect2 = math_getPerpendicularBisectLineForTwoPoints(pp1[1], pp2[1]);
    var anglediff = math_getAngleDiff(math_getSlopeAngleFromTwoPoints(bisect1[0], bisect1[1]), math_getSlopeAngleFromTwoPoints(bisect2[0], bisect2[1]));
    var result = checkLineIntersection(bisect1[0][0], bisect1[0][1], bisect1[1][0], bisect1[1][1], bisect2[0][0], bisect2[0][1], bisect2[1][0], bisect2[1][1])
    return [[result.x, result.y], midpoint1, midpoint2, bisect1[2], bisect2[2], anglediff];
}

function math_getGhostResults(obj, ghost)
{
    if (ghost === null || ghost === false) {
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
