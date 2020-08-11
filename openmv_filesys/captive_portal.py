import pyb, uos, time
import network
import usocket as socket

class CaptivePortal(object):
    def __init__(self, ssid = None, password = "1234567890"):
        self.wlan = network.WINC(mode = network.WINC.MODE_AP)

        # generate a SSID if none is provided
        if ssid is None:
            uid = pyb.unique_id()
            uidstr = ""
            for h in uid:
                uidstr += "%02X" % h
            self.ssid = "OpenMV-" + uidstr
            if len(self.ssid) > 7 + 8:
                self.ssid = self.ssid[0:(7 + 8)]

        self.wlan.start_ap(self.ssid, key = password, security = network.WINC.WEP)
        self.ip = self.wlan.ifconfig()[0]

        # provide hardcoded IP address if the one obtained is invalid
        if self.ip == "0.0.0.0":
            self.ip = "192.168.1.1"

        self.debug = False

        self.udps = None
        self.s = None
        self.handlers = {}

    def start_dns(self):
        try:
            self.udps = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udps.bind(('', 53))
            self.udps.settimeout(0)
            if self.debug:
                print("start_dns")
        except OSError as e:
            print("dns error " + str(e))
            if self.udps is not None:
                self.udps.close()
            self.udps = None

    def start_http(self):
        try:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.bind(('', 80))
            self.s.listen(5)
            self.s.settimeout(0.1)
            self.need_kill = False
            if self.debug:
                print("start_http")
        except OSError as e:
            if self.s is not None:
                self.s.close()
            self.s = None

    def install_handler(self, key, func):
        self.handlers.update({key: func})

    def handle_default(self, client_stream, req, headers, content):
        if self.debug:
            print("default handler")
        client_stream.write("HTTP/1.0 200 OK\r\ncontent-type: text/html\r\ncache-control: no-cache\r\n\r\n" + "<html>hello<br />" + req + "</html>\r\n")
        client_stream.close()

    def task_dns(self):
        # some code borrowed from https://github.com/amora-labs/micropython-captive-portal/blob/master/captive.py
        if self.udps is None:
            self.start_dns()
        try:
            data, addr = self.udps.recvfrom(1024)
            if len(data) <= 0:
                return False
            if self.debug:
                print("dns rx[%s] %u" % (str(addr), len(data)))
            dominio = ''
            m = data[2]             # ord(data[2])
            tipo = (m >> 3) & 15    # Opcode bits
            if tipo == 0:           # Standard query
                ini = 12
                lon = data[ini]     # ord(data[ini])
                while lon != 0:
                    dominio += data[ini + 1 : ini + lon + 1].decode("utf-8") + '.'
                    ini += lon + 1
                    lon = data[ini] # ord(data[ini])
            packet = b''
            if dominio:
                packet += data[:2] + b"\x81\x80"
                packet += data[4:6] + data[4:6] + b'\x00\x00\x00\x00'       # Questions and Answers Counts
                packet += data[12:]                                         # Original Domain Name Question
                packet += b'\xc0\x0c'                                       # Pointer to domain name
                packet += b'\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04'       # Response type, ttl and resource data length -> 4 bytes
                packet += bytes(map(int, self.ip.split('.'))) # 4 bytes of IP
            self.udps.sendto(packet, addr)
            if self.debug:
                print("dns resoved %u bytes %s" % (len(packet), dominio))
            return True
        except OSError as e:
            print("dns OSError " + str(e))
            self.udps.close()
            self.udps = None
        except Exception as e:
            print("dns Exception " + str(e))
            pass
        return False

    def task_http(self):
        if self.s is None:
            self.start_http()
        res = None
        try:
            res = self.s.accept()
            self.need_kill = True
            self.s.settimeout(0.3) # trigger release when done
        except OSError as e:
            #if self.need_kill:
            self.s.close()
            self.s = None
            self.start_http()
            return False
        if res is None:
            return False
        try:
            if self.debug:
                print("http req[%s]: " % str(res[1]), end="")
            client_sock = res[0]
            client_addr = res[1]
            client_sock.settimeout(10)
            client_stream = client_sock
            req = socket_readline(client_stream)
            if self.debug:
                print(req)
            req_split = req.split(' ')
            if req_split[0] == "GET":
                request_page, request_urlparams = split_get_request(req)
                if request_page in self.handlers:
                    self.handlers[request_page](client_stream, req, {}, "")
                else:
                    self.handle_default(client_stream, req, {}, "")
            elif req_split[0] == "POST":
                # WARNING: POST requests are not used or tested right now
                request_page = req_split[1]
                headers = {}
                content = ""
                while True:
                    line = socket_readline(client_stream)
                    if line is None:
                        break
                    if ':' in line:
                        header_key = line[0:line.index(':')].lower()
                        header_value = line[line.index(':'):].lstrip()
                        headers.update({header_key: header_value})
                        if header_key == "content-length":
                            socket_readline(client_stream) # extra line
                            content = socket_readall(client_stream)
                            break
                if request_page in self.handlers:
                    self.handlers[request_page](client_stream, req, headers, content)
                else:
                    self.handle_default(client_stream, req, headers, content)
            return True
        except OSError as e:
            print("http serve OSError " + str(e) + " " + str(e.args[0]))
            self.s.close()
            self.s = None
        except Exception as e:
            print("http Exception " + str(e))
            pass
        return False

    def task(self):
        x = self.task_dns()
        y = self.task_http()
        if x or y:
            return True
        return False

# usocket implementation is missing readline
def socket_readline(sock):
    res = ""
    while True:
        x = sock.recv(1)
        if x is None:
            if len(res) > 0:
                return res
            else:
                return None
        if len(x) <= 0:
            if len(res) > 0:
                return res
            else:
                return None
        y = x.decode('utf-8')
        if y == "\n":
            if len(res) > 0:
                if res[-1] == "\r":
                    res = res[:-1]
            return res
        res += y
    return res

# usocket implementation is missing readall
def socket_readall(sock):
    chunk = 1024
    res = ""
    while True:
        x = sock.recv(chunk)
        if x is None:
            if len(res) > 0:
                return res
            else:
                return None
        if len(x) <= 0:
            if len(res) > 0:
                return res
            else:
                return None
        res += x.decode('utf-8')
        if len(x) < chunk:
            return res
    return res

def split_get_request(req):
    req_split = req.split(' ')
    request_url = req_split[1]
    request_page = request_url
    request_urlparams = {}
    if '?' in request_page:
        request_page = request_url[:request_url.index('?')]
        request_urlparams = request_url[request_url.index('?') + 1:]
        try:
            d = {key: value for (key, value) in [x.split(b'=') for x in request_urlparams.split(b'&')]}
        except:
            d = {}
        request_urlparams = d
    return request_page, request_urlparams

def split_post_form(headers, content):
    d = {}
    if "content-type" in headers:
        if headers["content-type"] == "application/x-www-form-urlencoded":
            try:
                d = {key: value for (key, value) in [x.split(b'=') for x in content.split(b'&')]}
            except:
                pass
    return d

def default_reply_header(content_type = "text/html"):
    return "HTTP/1.0 200 OK\r\ncontent-type: %s\r\ncache-control: no-cache\r\n\r\n" % content_type

def stream_img_start(conn):
    conn.send("HTTP/1.1 200 OK\r\n" \
              #"connection: Keep-Alive" \
              "content-type: multipart/x-mixed-replace;boundary=stream\r\n" \
              "x-frame-options: deny\r\n" \
              "x-xss-protection: 1; mode=block\r\n" \
              "x-content-type-options: nosniff\r\n" \
              "vary: Accept-Encoding\r\n" \
              #"keep-alive: timeout=10, max=1000" \
              "cache-control: no-cache\r\n\r\n")

def stream_img_continue(img, conn):
    cframe = img.compressed(quality=50)
    conn.send("\r\n--stream\r\n" \
               "content-type: image/jpeg\r\n" \
               "content-length:%u\r\n\r\n" % cframe.size())
    conn.send(cframe)

def handle_test(client_stream, req, headers, content):
    print("test handler")
    client_stream.write(default_reply_header() + "<html>test<br />" + req + "</html>\r\n")
    client_stream.close()

if __name__ == "__main__":
    print("Starting CaptivePortal")
    portal = CaptivePortal()
    portal.debug = True
    portal.install_handler("/test", handle_test)
    dbg_cnt = 0
    clock = time.clock()
    while True:
        dbg_cnt += 1
        clock.tick()
        portal.task()
        fps = clock.fps()
        if portal.debug:
            print("%u - %0.2f" % (dbg_cnt, fps))
