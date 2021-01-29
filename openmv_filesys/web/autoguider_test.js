function rand_int(minv, maxv)
{
    return Math.floor(Math.random() * Math.floor(maxv - minv)) + minv;
}

function test_starprofile()
{
    var len = rand_int(5, 15);
    var arr = [];
    var start = rand_int(200, 255);
    arr.push(start);
    var i, j = start;
    for (i = 0; i < len; i++)
    {
        j -= rand_int(10, 30);
        if (j < 0) {
            j = 0;
        }
        arr.push(j);
    }
    starprofile = arr;
    draw_starprofile();
}

var sim_ts = 0;
var sim_cnt = 0;
function test_errgraph()
{
    sim_cnt = 0;
    errgraph_push(sim_ts, rand_int(-1000, 1000), rand_int(-1000, 1000), rand_int(0, 4000), rand_int(0, 5));
    sim_ts += 1000;
    setTimeout(function()
    {
        if (sim_cnt < 10) {
            test_errgraph();
            sim_cnt += 1;
        }
    }, 1000);
}

function test_guidescope(vis)
{
    var obj = {"pkt_type": "status"};
    obj["img_mean"] = 8 + (Math.random() * 32);
    var num_stars = parseInt(Math.round(20 + (Math.random() * 50)));
    var sel_i = parseInt(Math.round(Math.random() * num_stars))

    selected_star = [0,0];
    tgt_coord = [0,0];
    ori_coord = [0,0];

    star_list = null;
    var stars_str = "";
    var i;
    for (i = 0; i < num_stars; i++)
    {
        var r = parseInt(Math.round(2 + (Math.random() * 10)));
        var b = parseInt(Math.round(127 + (Math.random() * 127)));
        var x = parseInt(Math.round(Math.random() * sensor_width));
        var y = parseInt(Math.round(Math.random() * sensor_height));
        var rating = parseInt(Math.round(Math.random() * 100));
        var s = x.toString() + "," + y.toString() + "," + r.toString() + "," + b.toString() + "," + rating.toString() + ";";
        stars_str += s;
        if (i == sel_i)
        {
            selected_star[0] = x;
            selected_star[1] = y;
            tgt_coord[0] = parseInt(Math.round(x - 3 + (Math.random() * 6)));
            tgt_coord[1] = parseInt(Math.round(y - 3 + (Math.random() * 6)));
            ori_coord[0] = parseInt(Math.round(x - 3 + (Math.random() * 6)));
            ori_coord[1] = parseInt(Math.round(y - 3 + (Math.random() * 6)));
        }
    }

    obj["stars"] = stars_str;

    var angle = Math.random() * 360.0;

    if (vis == 1 || vis == 3)
    {
        obj["calib_ra"] = make_fake_calib(angle);
        handleCalibration(obj, "ra");
        viz_calib = vis;
    }
    if (vis == 2 || vis == 3)
    {
        obj["calib_dec"] = make_fake_calib(angle + 90);
        handleCalibration(obj, "dec");
        viz_calib = vis;
    }

    draw_guidescope(obj);
}

function make_fake_calib(angle)
{
    angle = math_normalizeAngleDegrees(angle);
    var obj = {"success": "done"};
    var num_pts = parseInt(Math.round(7 + (Math.random() * 7)));
    var x = parseInt(Math.round(Math.random() * sensor_width));
    var y = parseInt(Math.round(Math.random() * sensor_height));
    var pulse_width = parseInt(Math.round(500 + (Math.random() * 500)));
    var farthest = parseInt(Math.round(200 + (Math.random() * 200)));
    var pix_per_ms = farthest / pulse_width;
    var ms_per_pix = pulse_width / farthest;
    var prev_pt = [x, y];
    var pts = [];
    var i;
    for (i = 0; i < num_pts; i++)
    {
        var mag = (pix_per_ms * pulse_width) - 1 + (Math.random() * 2);
        var ang = angle - 1 + (Math.random() * 2);
        var new_pt = math_movePointTowards(prev_pt, [mag, ang]);
        pts.push(new_pt);
        prev_pt = new_pt;
    }
    obj["pulse_width"] = pulse_width;
    obj["points"     ] = pts;
    obj["points_cnt" ] = pts.length;
    obj["start_coord"] = [x, y];
    obj["farthest"   ] = farthest;
    obj["pix_per_ms" ] = pix_per_ms;
    obj["ms_per_pix" ] = ms_per_pix;
    obj["time"       ] = time_getNowEpoch();
    obj["angle"      ] = angle;

    return obj;
}
