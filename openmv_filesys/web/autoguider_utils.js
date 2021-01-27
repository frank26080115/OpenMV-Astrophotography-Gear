var sensor_width  = 2592;
var sensor_height = 1944;
var svgNS = "http://www.w3.org/2000/svg";

const GUIDESTATE_IDLE              = 0;
const GUIDESTATE_GUIDING           = 1;
const GUIDESTATE_DITHER            = 2;
const GUIDESTATE_PANIC             = 3;
const GUIDESTATE_CALIBRATING_RA    = 4;
const GUIDESTATE_CALIBRATING_DEC   = 5;

const INTERVALSTATE_IDLE           = 0;
const INTERVALSTATE_ACTIVE         = 1;
const INTERVALSTATE_ACTIVE_GAP     = 2;
const INTERVALSTATE_BULB_TEST      = 3;
const INTERVALSTATE_HALT           = 4;
const INTERVALSTATE_ENDING         = 5;

function getExposureCode(exposure_code) {
    if (exposure_code == 0) {
        return "correct";
    }
    else if (exposure_code == -1) {
        return "too dark";
    }
    else if (exposure_code == -2) {
        return "no image";
    }
    else if (exposure_code == 1) {
        return "too bright";
    }
    else if (exposure_code == 2) {
        return "too noisy";
    }
    else if (exposure_code == 3) {
        return "movement";
    }
    else if (exposure_code == 4) {
        return "big blob";
    }
    else if (exposure_code == 5) {
        return "too many stars";
    }
    else if (exposure_code == 6) {
        return "INTERNAL MEMORY ERROR";
    }
    else if (exposure_code == 7) {
        return "CAMERA HARDWARE ERROR";
    }
    else if (exposure_code == 8) {
        return "camera still initializing";
    }
    return "unknown";
}

function epochToDate(x)
{
    var epoch2000 = new Date(Date.UTC(2000, 0, 1)).getTime();
    var epoch = epoch2000 + (x * 1000);
    return new Date(epoch);
}

function fmtTime(x)
{
    var hour   = x.getHours();
    var minute = x.getMinutes();
    var second = x.getSeconds();
    var temp = '' + hour.toString();
    temp += ((minute < 10) ? ':0' : ':') + minute;
    temp += ((second < 10) ? ':0' : ':') + second;
    return temp;
}

function fmtDate(x)
{
    const ye = new Intl.DateTimeFormat('en', { year:  'numeric' }).format(x);
    const mo = new Intl.DateTimeFormat('en', { month: 'short'   }).format(x);
    const da = new Intl.DateTimeFormat('en', { day:   '2-digit' }).format(x);
    return da + "-" + mo + "-" + ye;
}

function parseStarsStr(x)
{
    var stars = [];
    var chunks = x.split(";");
    var i;
    for (i = 0; i < chunks.length; i++)
    {
        var chunk = chunks[i];
        if (chunk.includes(","))
        {
            var data = chunk.split(",");
            var star = {};
            star["cx"] = parseFloat(data[0]);
            star["cy"] = parseFloat(data[1]);
            if (data.length > 2)
            {
                star["r"]  = parseInt(data[2]);
                star["max_brite"] = parseInt(data[3]);
                star["rating"]    = parseInt(data[4]);
            }
            stars.push(star);
        }
    }
    return stars;
}

var ui_list = {};
var autopopulate_func_list = {};
var autopopulate_dict_list = {};

function register_ui(uiele, name, func)
{
    ui_list[name] = uiele;
    ui_list[name + "/func"] = func;
}

function makeSlider(id, minval, maxval, defval, stepval, zero_val, unit, slide_func, sync_with)
{
    if (defval < minval) {
        defval = minval;
    }
    if (defval > maxval) {
        defval = maxval;
    }

    var handle = $( "#" + id + "_handle" );
    var handler = function(v) {
        var text = v;
        if (v == 0) { text = zero_val; }
        else { text = v.toString() + unit; }
        handle.text( text );
        console.log("slider \"" + id + "\" evt = " + text);
        if (slide_func)
        {
            if (typeof slide_func === 'string' || slide_func instanceof String) {
                console.log("auto sending \"" + slide_func + "\" = " + v.toString());
                queueSettingsUpdate(slide_func, v);
            }
            else {
                slide_func(v);
            }
        }

        if (sync_with !== undefined && typeof sync_with !== 'undefined') {
            if (typeof sync_with === 'string' || sync_with instanceof String) {
                sliderSync(sync_with, v);
            }
        }
    };
    var slider = $( "#" + id ).slider({
      create: function() {
        var v = $( this ).slider( "value" );
        if (v == 0) { v = zero_val; }
        else { v = v.toString() + unit; }
        handle.text( v );
      },
      min: minval,
      max: maxval,
      step: stepval,
      value: defval,
      slide: function( event, ui ) {
        var v = ui.value;
        handler(v);
      }
    });

    register_ui(slider, id, handler);
    if (typeof slide_func === 'string' || slide_func instanceof String) {
        autopopulate_dict_list[slide_func] = id;
        autopopulate_func_list[slide_func] = function(x) {
            if (x < minval) {
                x = minval;
            }
            if (x > maxval) {
                x = maxval;
            }
            sliderSync(id, x);
        };
    }
}

function makeSliderLookup(id, defval, lut, slide_func)
{
    var handle = $( "#" + id + "_handle" );
    var handler = function(v) {
        var text = lut[v].toString();
        handle.text( text );
        console.log("slider \"" + id + "\" evt = " + text);
        if (slide_func)
        {
            if (typeof slide_func === 'string' || slide_func instanceof String) {
                console.log("auto sending \"" + slide_func + "\" = " + lut[v].toString());
                queueSettingsUpdate(slide_func, lut[v]);
            }
            else {
                slide_func(lut[v]);
            }
        }
    };
    var slider = $( "#" + id ).slider({
      create: function() {
        var v = $( this ).slider( "value" );
        v = lut[v].toString();
        handle.text( v );
      },
      min: 0,
      max: lut.length -1,
      step: 1,
      value: defval,
      slide: function( event, ui ) {
        var v = ui.value;
        handler(v);
      }
    });

    register_ui(slider, id, handler);
    ui_list[id + "/lut"] = lut;
    if (typeof slide_func === 'string' || slide_func instanceof String) {
        autopopulate_dict_list[slide_func] = id;
        autopopulate_func_list[slide_func] = function(x) {
            var i, tgt = -1;
            var dist = -1;
            for (i = 0; i < lut.length; i++) {
                var j = lut[i];
                var k = Math.abs(x - j);
                if (dist < 0 || k < dist) {
                    dist = k;
                    tgt = i;
                }
            }
            if (tgt >= 0) {
                slider.slider("value", tgt);
                handler(tgt);
            }
        };
    }
}

function makeButton(id, click_func)
{
    var btn = $("#" + id ).button().click(function() {
        console.log("button \"" + id + "\" click");
        if (click_func) {
            click_func();
        }
    });
    register_ui(btn, id, click_func);
}

function makeCheckbox(id, initstate, click_func)
{
    var chk = $("#" + id ).checkboxradio().prop("checked", initstate).checkboxradio("refresh").on("change", function() {
        var x = $("#" + id ).prop("checked");
        console.log("button \"" + id + "\" on_change: " + x);
        if (click_func) {
            if (typeof click_func === 'string' || click_func instanceof String) {
                console.log("auto sending \"" + click_func + "\" = " + x);
                queueSettingsUpdate(click_func, x);
            }
            else {
                click_func(x);
            }
        }
    });
    register_ui(chk, id, click_func);
    if (typeof click_func === 'string' || click_func instanceof String) {
        autopopulate_dict_list[click_func] = id;
        autopopulate_func_list[click_func] = function(x) {
            chk.checkboxradio().prop("checked", x).checkboxradio("refresh");
        }
    }
}

function sliderSync(id, v)
{
    if (v != $("#" + id).slider( "value" )) {
        $("#" + id).slider( "value", v );
        ui_list[id + "/func"](v);
    }
}

function show_toast_msg(s)
{
    var toast = new iqwerty.toast.Toast();
    toast = toast.setText(s);

    var slower = s.toLowerCase();
    if (slower.startsWith("err:") || slower.startsWith("error:") || slower.startsWith("fail:") || slower.startsWith("failed:")) {
        toast = toast.stylize({background: "red", color: "white",}).setDuration(5000);
    }
    else if (slower.startsWith("warn:") || slower.startsWith("warning:")) {
        toast = toast.stylize({background: "#D07000", color: "white",});
    }
    else if (slower.startsWith("success:") || slower.startsWith("done:")) {
        toast = toast.stylize({background: "green", color: "white",});
    }
    else if (slower.startsWith("info:") || slower.startsWith("msg:") || slower.startsWith("message:")) {
        toast = toast.stylize({background: "blue", color: "white",});
    }

    toast.show();
}

function fetchAndFill(eleId, filename)
{
    var obj = {"pkt_type": "fetch", "shortname": eleId, "filename": filename, "time": time_getNowEpoch()};
    websock_ping_delay();
    websock_send(obj);
}
