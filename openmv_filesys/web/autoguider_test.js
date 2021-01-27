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