function circle_fit_coords(data, coords)
{
    var results = [];
    coords.forEach(function(ele1, idx1) {
        var dists = [];
        data.forEach(function(ele2, idx2) {
            var dx = ele2[0] - ele1[0];
            var dy = ele2[1] - ele1[1];
            var dist = Math.sqrt((dx ** 2) + (dy ** 2));
            dists.push(dist);
        });
        var avg = 0;
        dists.forEach(function(ele2, idx2) {
            avg += ele2;
        });
        avg /= dists.length;
        var stdev = 0;
        dists.forEach(function(ele2, idx2) {
            stdev += Math.pow(ele2 - avg, 2);
        });
        stdev = Math.sqrt(stdev / dists.length);
        results.push({coord: ele1, avg: avg, stdev: stdev});
    });
    results.sort(function(a, b) {
        return a.stdev - b.stdev;
    });
    return results[0];
}

function circle_fit_roi(data, center, radius, depth)
{
    var cx = center[0];
    var cy = center[1];
    var coords = [];
    var step = radius / 10;
    var dx, dy;
    for (dx = 0; dx < radius; dx += step) {
        for (dy = 0; dy < radius; dy += step) {
            coords.push([cx + dx, cy + dy]);
            coords.push([cx + dx, cy - dy]);
            coords.push([cx - dx, cy + dy]);
            coords.push([cx - dx, cy - dy]);
        }
    }
    var result = circle_fit_coords(data, coords);
    if (step < 1.0 || depth > 6) {
        return result;
    }
    return circle_fit_roi(data, result.coord, step * 0.75, depth + 1);
}

function circle_fit(data, frame_sz)
{
    return circle_fit_roi(data, [frame_sz[0] / 2, frame_sz[1] / 2], frame_sz[0] / 2, 0);
}