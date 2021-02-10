var errgraph_height = 300;
var errgraph_stepwidth = 15;
var errgraph_totallimit = 4096 * 2;
var errgraph_data = [];
var errgraph_lasttime = 0;
var errgraph_timeout = Math.round(1333.0 * 1.5);
var errgraph_timeoutEvent = null;
var errgraph_lasthoricnt = 0;

function errgraph_draw()
{
    var wrap_div = document.getElementById("div_errgraph");
    var cli_wid = wrap_div.clientWidth;

    // here we figure out how many items to draw
    var show_cnt = Math.floor(cli_wid / errgraph_stepwidth);
    var fast_redraw = false;
    if (errgraph_lasthoricnt == 0) {
        errgraph_lasthoricnt = show_cnt;
    }
    else
    {
        // grow or shrink graph one item at a time
        if (show_cnt > errgraph_lasthoricnt) {
            errgraph_lasthoricnt += 1;
            fast_redraw = true;
        }
        else if (show_cnt < errgraph_lasthoricnt) {
            errgraph_lasthoricnt -= 1;
            fast_redraw = true;
        }
        show_cnt = errgraph_lasthoricnt;
    }

    var hori_labels   = [];
    var zero_data     = [];
    var err_ra_data   = [];
    var err_dec_data  = [];
    var pul_sum_data  = [];
    var shutter_data1 = [];
    var shutter_data2 = [];
    var max_err = 0;
    var max_graph_limit = 0;
    var i, j;
    var first_ts;

    var max_possible_time = 2000;
    if (typeof settings !== 'undefined') {
        max_possible_time *= settings["intervalometer_bulb_time"];
    }

    for (i = 0, j = errgraph_data.length - 1; i < show_cnt; i++, j--)
    {
        var pkt = [0, 0, 0, 0, 0, 0]; // if data buffer isn't long enough, fill with blank
        if (j >= 0)
        {
            // data exists (data buffer long enough), use real data
            pkt = errgraph_data[j];
        }
        if (Math.abs(pkt[1]) > max_err) {
            max_err = Math.abs(pkt[1]);
        }
        if (Math.abs(pkt[2]) > max_err) {
            max_err = Math.abs(pkt[2]);
        }
        if (max_err > max_graph_limit) {
            max_graph_limit = max_err;
        }
    }

    for (i = 0, j = errgraph_data.length - 1; i < show_cnt; i++, j--)
    {
        var pkt = [0, 0, 0, 0, 0, 0]; // if data buffer isn't long enough, fill with blank
        if (j >= 0)
        {
            // data exists (data buffer long enough), use real data
            pkt = errgraph_data[j];
        }
        if (i == 0)
        {
            first_ts = pkt[0];
            hori_labels.push("0");
        }
        else if ((i % 5) == 0 && pkt[0] != 0)
        {
            // only put a label on every 5th data point
            hori_labels.push((Math.abs(Math.round((pkt[0] - first_ts) / 100.0)) / 10.0).toString());
        }
        else
        {
            hori_labels.push(" ");
        }

        err_ra_data  .push(pkt[1]);
        err_dec_data .push(pkt[2]);
        pul_sum_data .push((pkt[3] * max_graph_limit) / max_possible_time);
        shutter_data1.push(pkt[4] == 0 ? 0 : max_graph_limit);
        shutter_data2.push(pkt[4] == 0 ? 0 : -max_graph_limit);
        zero_data    .push(0);
    }

    var chart = new Chartist.Line('#errgraph-chart', {
        labels: hori_labels,
        series: [{
                name: 'series-err-ra',
                data: err_ra_data
            }, {
                name: 'series-err-dec',
                data: err_dec_data
            }, {
                name: 'series-pul-sum',
                data: pul_sum_data
            }, {
                name: 'series-shutter1',
                data: shutter_data1
            }, {
                name: 'series-shutter2',
                data: shutter_data2
            }, {
                name: 'series-zero',
                data: zero_data
            }]
        }, {
        fullWidth: true,
        series: {
            'series-err-ra': {
              //lineSmooth: Chartist.Interpolation.simple(),
              lineSmooth: Chartist.Interpolation.none(),
              showPoint: true,
              showArea:  false
            },
            'series-err-dec': {
              //lineSmooth: Chartist.Interpolation.simple(),
              lineSmooth: Chartist.Interpolation.none(),
              showPoint: true,
              showArea:  false
            },
            'series-pul-sum': {
              lineSmooth: Chartist.Interpolation.step(),
              showPoint: false,
              showArea:  true,
              showLine:  false
            },
            'series-shutter1': {
              lineSmooth: Chartist.Interpolation.step(),
              showPoint: false,
              showArea:  true,
              showLine:  true
            },
            'series-shutter2': {
              lineSmooth: Chartist.Interpolation.step(),
              showPoint: false,
              showArea:  true,
              showLine:  true
            },
            'series-zero': {
              lineSmooth: Chartist.Interpolation.none(),
              showPoint: false,
              showArea:  false
            }
        }
    });

    if (fast_redraw) {
        setTimeout(function(){
            errgraph_draw();
        }, 100);
    }
}

function errgraph_onresize()
{
    var ele = document.getElementById("errgraph-chart");
    try
    {
        if (window.innerHeight > window.innerWidth)
        {
            ele.classList.add("ct-square");
            ele.classList.remove(".ct-minor-seventh");
        }
        else
        {
            ele.classList.remove("ct-square");
            ele.classList.add(".ct-minor-seventh");
        }
    }
    catch
    {
        console.log("boo");
    }
}

function errgraph_prune()
{
    if (errgraph_data.length < errgraph_totallimit) {
        return;
    }
    var i = Math.trunc(errgraph_data.length / 2);
    errgraph_data = errgraph_data.slice(i);
}

function errgraph_push(timestamp, err_ra, err_dec, pulse_sum, shutter)
{
    if (timestamp == errgraph_lasttime) {
        return;
    }
    var pkt = [timestamp, err_ra, err_dec, pulse_sum, shutter];
    errgraph_data.push(pkt);
    errgraph_prune();
    errgraph_lasttime = timestamp;
    errgraph_setNextTimeout();
    errgraph_draw();
}

function errgraph_setNextTimeout()
{
    if (errgraph_timeoutEvent != null) {
        clearTimeout(errgraph_timeoutEvent);
    }
    errgraph_timeoutEvent = setTimeout(function(){
        errgraph_push(errgraph_lasttime + errgraph_timeout, 0, 0, 0, 0);
    }, errgraph_timeout);
}

function errgraph_clear()
{
    if (errgraph_timeoutEvent != null) {
        clearTimeout(errgraph_timeoutEvent);
    }
    errgraph_data = [];
    errgraph_lasttime = 0;
}

function errgraph_save()
{
    try
    {
        var filename = "guideerror-" + Date.now().toString() + ".csv";
        var textdata = "timestamp, err_ra, err_dec, pulse_sum, shutter, \r\n";
        errgraph_data.forEach(function(ele, idx) {
            ele.forEach(function(num, col) {
                textdata += num.toString() + ", ";
            });
            textdata += "\r\n";
        });

        var file = new Blob([textdata], {type: 'text/csv;charset=utf-8;'});
        if (window.navigator.msSaveOrOpenBlob) {
            // IE10+
            window.navigator.msSaveOrOpenBlob(file, filename);
        }
        else
        {
            // other browsers
            var a = document.createElement("a"), url = URL.createObjectURL(file);
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            setTimeout(function()
            {
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            }, 200);
        }
    }
    catch (err)
    {
        var errstr = "ERROR while saving graph data: " + err.toString();
        alert(errstr);
        console.log(errstr);
    }
}
