var errgraph_height = 300;
var errgraph_stepwidth = 5;
var errgraph_totallimit = 4096 * 2;
var errgraph_data = [];
var errgraph_lasttime = 0;
var errgraph_timeout = Math.round(1333.0 * 1.5);
var errgraph_timeoutEvent = null;
var errgraph_lasthoricnt = 0;

function errgraph_draw()
{
    var wrap_div = document.getElementById("div_errgraph");
    var cli_wid = wrapdiv.clientWidth;

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

    var hori_labels  = [];
    var zero_data    = []
    var err_ra_data  = [];
    var err_dec_data = [];
    var pul_ra_data  = [];
    var pul_dec_data = [];
    var shutter_data = [];
    var i, j;
    var first_ts;

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
            hori_labels.push((Math.round((pkt[0] - first_ts) / 100.0) / 10.0).toString());
        }
        else
        {
            hori_labels.push(" ");
        }

        err_ra_data .push(pkt[1]);
        err_dec_data.push(pkt[2]);
        pul_ra_data .push(pkt[3]);
        pul_dec_data.push(pkt[4]);
        shutter_data.push(pkt[5] == 0 ? 0 : 750);
        zero_data   .push(0);
    }

    var chart = new Chartist.Line('#errgraph-chart', {
        labels: hori_labels,
        series: [{
                name: 'series-1',
                data: err_ra_data
            }, {
                name: 'series-2',
                data: err_dec_data
            }, {
                name: 'series-3',
                data: pul_ra_data
            }, {
                name: 'series-4',
                data: pul_dec_data
            }, {
                name: 'series-5',
                data: shutter_data
            }, {
                name: 'series-6',
                data: zero_data
            }]
        }, {
        fullWidth: true,
        series: {
            'series-1': {
              //lineSmooth: Chartist.Interpolation.simple(),
              lineSmooth: Chartist.Interpolation.none(),
              showPoint: true,
              showArea:  false
            },
            'series-2': {
              //lineSmooth: Chartist.Interpolation.simple(),
              lineSmooth: Chartist.Interpolation.none(),
              showPoint: true,
              showArea:  false
            },
            'series-3': {
              lineSmooth: Chartist.Interpolation.step(),
              showPoint: false,
              showArea:  true
            },
            'series-4': {
              lineSmooth: Chartist.Interpolation.step(),
              showPoint: false,
              showArea:  true
            },
            'series-5': {
              lineSmooth: Chartist.Interpolation.step(),
              showPoint: false,
              showArea:  true
            },
            'series-6': {
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

function errgraph_prune()
{
    if (errgraph_data.length < errgraph_totallimit) {
        return;
    }
    var i = Math.trunc(errgraph_data.length / 2);
    errgraph_data = errgraph_data.slice(i);
}

function errgraph_push(timestamp, err_ra, err_dec, pulse_ra, pulse_dec, shutter)
{
    if (timestamp == errgraph_lasttime) {
        return;
    }
    var pkt = [timestamp, err_ra, err_dec, pulse_ra, pulse_dec, shutter];
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
        var textdata = "timestamp, err_ra, err_dec, pulse_ra, pulse_dec, shutter, \r\n";
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
