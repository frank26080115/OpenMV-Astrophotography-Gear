var socket = null;

function websocket_init(page)
{
    var cur_url = window.location.href;
    var r = new RegExp("([a-z]+):\/\/([^\/]+)(.*)", 'i');
    var res = r.exec(cur_url);
    var domain = res[2];
    var sock_url = "ws://" + domain + "/" + page;
    console.log("websocket init to " + sock_url);
    socket = new WebSocket(sock_url);

    socket.onopen = function (evt) {
        console.log("websocket open");
        if (typeof websock_onopen === "function") { 
            websock_onopen(evt);
        }
    };

    socket.onmessage = function (evt) {
        if (typeof websock_onmessage === "function") { 
            websock_onmessage(evt);
        }
        else {
            console.log("websocket message " + evt.data);
        }
    };

    socket.onerror = function (evt) {
        console.log("websocket error " + evt.message);
        if (typeof websock_onerror === "function") { 
            websock_onerror(evt);
        }
    };
}
