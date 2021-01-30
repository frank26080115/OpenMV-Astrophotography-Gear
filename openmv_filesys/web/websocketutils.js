var socket = null;
var socket_err_cnt = 0;
var socket_state = 0;

function websocket_init(page)
{
    var cur_url = window.location.href;
    var r = new RegExp("([a-z]+):\/\/([^\/]+)(.*)", 'i');
    var res = r.exec(cur_url);
    if (res == null) {
        console.log("cannot init websocket, URL does not have a domain: " + cur_url);
        return;
    }
    var domain = res[2];
    var sock_url = "ws://" + domain + "/" + page;
    console.log("websocket init to " + sock_url);
    socket = new WebSocket(sock_url);
    socket_state = 1;

    socket.onopen = function (evt) {
        socket_state = 2;
        socket_err_cnt = 0;
        console.log("websocket open");
        if (typeof websock_onopen === "function") { 
            websock_onopen(evt);
        }
    };

    socket.onmessage = function (evt) {
        websocket_last_transmission = null;
        socket_err_cnt = 0;
        var d = evt.data;
        if (typeof websock_onmessage === "function") {
            websock_onmessage(evt);
        }
        else if (typeof d === 'string' || d instanceof String)
        {
            d = d.trim();
            if (d.startsWith("{") && d.endsWith("}"))
            {
                try
                {
                    var jsonobj = JSON.parse(d);
                    websock_onmessage_jsonobj(jsonobj);
                    return;
                }
                catch (e) {
                    // meh
                }

                if (typeof websock_onmessage_str === "function") {
                    websock_onmessage_str(d);
                }
                else if (typeof websock_onmessage_data === "function") {
                    websock_onmessage_data(evt.data);
                }
                else {
                    console.log("websocket message JSON obj: " + d);
                }
            }
            else
            {
                if (typeof websock_onmessage_str === "function") {
                    websock_onmessage_str(d);
                }
                else if (typeof websock_onmessage_data === "function") {
                    websock_onmessage_data(evt.data);
                }
                else {
                    console.log("websocket message string: " + d);
                }
            }
        }
        else
        {
            if (typeof websock_onmessage_data === "function") {
                websock_onmessage_data(evt.data);
            }
            else {
                console.log("websocket message data: " + evt.data);
            }
        }
    };

    socket.onerror = function (evt) {
        socket_err_cnt += 1;
        socket_state = -1;
        console.log("websocket error " + evt.message);
        if (typeof websock_onerror === "function") { 
            websock_onerror(evt);
        }
    };

    window.onbeforeunload = function() {
        if (socket != null) {
            socket.onclose = function () {}; // disable onclose handler first
            socket.close();
        }
    };
}

var websocket_last_transmission = null;

function websock_send(x) {
    if ((typeof x === 'string' || x instanceof String) == false) {
        x = JSON.stringify(x);
    }
    websocket_last_transmission = x;
    if (socket != null) {
        socket.send(x);
    }
}

function websock_retransmit()
{
    if (websocket_last_transmission == null) {
        return false;
    }
    websock_send(websocket_last_transmission);
    websocket_last_transmission = null; // only 1 retry
    return true;
}

var websock_ping_timer = null;
function websock_ping_send() {
    websock_ping_delay();
    websock_send("ping");
}

function websock_ping_delay() {
    if (websock_ping_timer != null) {
        clearTimeout(websock_ping_timer);
    }
    websock_ping_timer = setTimeout(websock_ping_send, 5000);
}
