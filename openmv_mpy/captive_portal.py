import micropython
micropython.opt_level(2)

import pyb, uos, uio, time, gc
import ubinascii, uhashlib, ujson
import network
import usocket as socket
import exclogger

STS_IDLE     = micropython.const(0)
STS_SERVED   = micropython.const(1)
STS_KICKED   = micropython.const(-1)

class CaptivePortal(object):
    def __init__(self, debug = False, enable_dns = False):
        self.debug = debug
        self.enable_dns = enable_dns

        self.wlan = None
        self.station_retries = 0
        self.hw_retries = 0
        self.allow_hw_kick = True

        self.start_wifi()

        self.udps = None
        self.s = None
        self.handlers = {}
        self.list_files()

        self.last_http_time = -1
        self.full_reboot_timer = -1

    def start_wifi(self, skip_file = False):
        obj = None
        valid = False
        try:
            with open("wifi_settings.json", mode="rb") as f:
                obj = ujson.load(f)
                valid = True
        except KeyboardInterrupt:
            raise
        except OSError as exc:
            valid = False
            exclogger.log_exception(exc)
            exclogger.log_exception("setting file probably not found or unusable")
        except Exception as exc:
            valid = False
            exclogger.log_exception(exc)
        if obj is not None:
            if "ssid" in obj:
                self.ssid = obj["ssid"]
                self.password = ""
                self.winc_security = network.WINC.OPEN
                self.winc_mode = network.WINC.MODE_STA
            else:
                valid = False
            if "password" in obj:
                self.password = obj["password"]
                if len(self.password) > 0:
                    self.winc_security = network.WINC.WPA_PSK
                else:
                    self.winc_security = network.WINC.OPEN
            if "security" in obj:
                secstr = obj["security"].lower()
                if "open" in secstr:
                    self.winc_security = network.WINC.OPEN
                elif "wpa" in secstr:
                    self.winc_security = network.WINC.WPA_PSK
                elif "psk" in secstr:
                    self.winc_security = network.WINC.WPA_PSK
                elif "wep" in secstr:
                    self.winc_security = network.WINC.WEP
            if "mode" in obj:
                modestr = obj["mode"].lower()
                if "soft" in modestr and "ap" in modestr:
                    self.winc_mode = network.WINC.MODE_AP
                elif "remote" in modestr:
                    self.winc_mode = network.WINC.MODE_AP
                elif "access" in modestr and "point" in modestr:
                    self.winc_mode = network.WINC.MODE_AP
        else:
            valid = False
            print("ERROR: could not load WiFi settings file")

        # if failed to connect to an expected router
        # start soft-AP
        if self.station_retries > 8:
            print("ERROR: too many failed connection attempts, starting soft AP")
            valid = False

        if valid == False:
            self.ssid = "OpenMV-?"
            self.password = "1234567890"
            self.winc_security = network.WINC.WEP
            self.winc_mode = network.WINC.MODE_AP

        if "?" in self.ssid: # question mark is replaced with a unique identifier
            uidstr = ubinascii.hexlify(pyb.unique_id()).decode("ascii").upper()
            self.ssid = self.ssid.replace("?", uidstr)
        if self.winc_mode == network.WINC.MODE_AP:
            # limit SSID length
            if len(self.ssid) > 7 + 8:
                self.ssid = self.ssid[0:(7 + 8)]

        if valid == False:
            # write out a template for the JSON file
            obj = {}
            obj.update({"ssid": self.ssid})
            obj.update({"password": self.password})
            obj.update({"security": "wep"})
            obj.update({"mode": "soft ap"})
            try:
                with open("wifi_settings_template.json", mode="wb+") as f:
                    ujson.dump(obj, f)
                    print("wifi settings template file saved")
            except Exception as exc:
                exclogger.log_exception(exc)

        self.start_wifi_hw()

    def start_wifi_hw(self):
        if self.wlan is None:
            try:
                self.wlan = network.WINC(mode = self.winc_mode)
                self.hw_retries = 0
            except OSError as exc:
                excstr = exclogger.log_exception(exc)
                if "irmware version mismatch" in excstr:
                    print("WiFi shield requires a firmware update!")
                    attempt_fw_update()
                else:
                    exclogger.log_exception("most likely hardware fault")
                    self.wlan = None
                    self.hw_retries += 1

        if self.wlan is None:
            self.wifi_timestamp = pyb.millis()
            return

        if self.winc_mode == network.WINC.MODE_AP:
            if self.winc_security == network.WINC.WPA_PSK:
                self.winc_security = network.WINC.WEP
            self.wlan.start_ap(self.ssid, key = self.password, security = self.winc_security)
            self.ip = self.wlan.ifconfig()[0]
            if self.ip == "0.0.0.0":
                self.ip = "192.168.1.1"
        else:
            self.wlan.connect(self.ssid, key = self.password, security = self.winc_security)
            self.ip = "0.0.0.0"
            self.wifi_timestamp = pyb.millis()

    def task_conn(self):
        if self.wlan is None:
            if pyb.elapsed_millis(self.wifi_timestamp) > 2000:
                self.start_wifi()
            return False

        if self.winc_mode == network.WINC.MODE_STA:
            if self.wlan.isconnected():
                ip = self.wlan.ifconfig()[0]
                if self.ip != ip:
                    self.ip = ip
                    print("Connected! IP: " + self.ip)
                self.station_retries = 0
                return True
            else:
                self.ip = "0.0.0.0"
                if pyb.elapsed_millis(self.wifi_timestamp) > 2000:
                    self.start_wifi()
                    self.station_retries += 1
                return False
        else: # AP mode, no need to check connection
            return True
        return False

    def start_dns(self):
        if self.winc_mode != network.WINC.MODE_AP:
            return # no DNS server if we are not a soft-AP
        try:
            self.udps = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP
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
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # TCP
            self.s.bind(('', 80))
            self.s.listen(1)
            self.s.settimeout(0.1)
            self.need_kill = False
        except OSError as e:
            if self.s is not None:
                self.s.close()
            self.s = None

    def install_handler(self, key, func):
        self.handlers.update({key: func})

    def list_files(self):
        # this function is called to cache the file list, preventing too many disk IOs
        self.file_list = uos.listdir()

    def file_try_open(self, fname):
        try:
            # take our first attempt without screwing with the file name
            fstats = uos.stat(fname)
            if fstats[0] & 0x4000 != 0: # is a directory
                return None, None, 0, ""
            fsize = fstats[6]
            f = open(fname, "rb")
            return f, fname, fsize, get_content_type(fname)
        except OSError:
            # welp, didn't work, let's try the rest of the code
            # code below attempts case-insensitive search
            # plus, fixing typos
            pass
        try:
            if fname[0] == "/":
                fname = fname[1:]
            fname = fname.lower()
            fname2 = None
            # typo fixing
            if fname.endswith(".htm"):
                fname2 = fname.replace(".htm", ".html")
            if fname.endswith(".html"):
                fname2 = fname.replace(".html", ".htm")
            if fname.endswith(".jpg"):
                fname2 = fname.replace(".jpg", ".jpeg")
            if fname.endswith(".jpeg"):
                fname2 = fname.replace(".jpeg", ".jpg")
            res = None
            # case-insensitive search
            for i in self.file_list:
                j = i.lower()
                if fname == j or fname2 == j:
                    res = i
                    break
            # found it
            if res is not None:
                fstats = uos.stat(res)
                if fstats[0] & 0x4000 != 0: # is a directory
                    return None, None, 0, ""
                fsize = fstats[6]
                f = open(fname, "rb")
                return f, res, fsize, get_content_type(res)
        except OSError:
            pass
        return None, None, 0, ""

    def handle_default(self, client_stream, req, headers, content):
        if self.debug:
            print("default http handler", end="")

        request_page, request_urlparams = split_get_request(req)
        if request_page == "/":
            request_page = "index.htm"
        f, fname, fsize, content_type = self.file_try_open(request_page)

        if f is not None:
            if self.debug:
                print(", file \"%s\" as \"%s\" size %u ..." % (fname, content_type, fsize), end="")
            try:
                client_stream.write("HTTP/1.0 200 OK\r\ncontent-type: %s\r\ncache-control: no-cache\r\ncontent-length: %u\r\n\r\n" % (content_type, fsize))
                stream_file(client_stream, f)
            except Exception as exc:
                exclogger.log_exception(exc)

            try:
                f.close()
            except Exception as exc:
                exclogger.log_exception(exc, to_print = False, to_file = False)
            if self.debug:
                print(" done")
        else:
            if self.debug:
                print(", error 404 \"%s\"" % request_page)
            client_stream.write("HTTP/1.0 404\r\ncontent-type: text/html\r\ncache-control: no-cache\r\n\r\n<html><h1>Error 404</h1><br /><h3>File Not Found</h3><br />%s</html>" % request_page)

        try:
            client_stream.close()
        except Exception as exc:
            exclogger.log_exception(exc, to_print = False, to_file = False)

    def update_imgstream(self, client, img):
        client.send("\r\n--openmv\r\n" \
             "Content-Type: image/jpeg\r\n"\
             "Content-Length:%u\r\n\r\n" % img.size())
        client.send(img)
        self.tickle()

    def websocket_send(self, sock, data):
        dlen = int(len(data))
        opcode = 0x81 if type(data) == str else 0x80
        self.websocket_send_start(sock, dlen, opcode)
        sock.send(data)
        self.tickle()

    def websocket_send_start(self, sock, dlen, opcode, timeout = 0.5):
        if dlen <= 125:
            header = bytearray(2)
            paylen = dlen
            header[1] = paylen
        elif dlen <= 65535:
            header = bytearray(4)
            paylen = 126
            header[1] = paylen
            header[2] = (dlen & 0xFF00) >> 8
            header[3] = (dlen & 0x00FF) >> 0
        else:
            header = bytearray(10)
            paylen = 127
            header[1] = paylen
            # I'm not going to deal with a 64 bit data length
            # there's just no way a packet is that big
            header[2] = 0
            header[3] = 0
            header[4] = 0
            header[5] = 0
            header[6] = (dlen & 0xFF000000) >> 24
            header[7] = (dlen & 0x00FF0000) >> 16
            header[8] = (dlen & 0x0000FF00) >> 8
            header[9] = (dlen & 0x000000FF) >> 0
        header[0] = opcode
        if timeout is not None:
            if timeout >= 0:
                sock.settimeout(timeout)
        sock.send(header)

    def tickle(self):
        self.last_http_time = pyb.millis()
        self.full_reboot_timer = self.last_http_time

    def task_dns(self):
        if self.winc_mode != network.WINC.MODE_AP:
            return STS_IDLE # no DNS server if we are not a soft-AP
        if self.enable_dns == False:
            return STS_IDLE
        if self.wlan is None:
            return STS_IDLE
        # some code borrowed from https://github.com/amora-labs/micropython-captive-portal/blob/master/captive.py
        if self.udps is None:
            self.start_dns()
        try:
            data, addr = self.udps.recvfrom(1024)
            if len(data) <= 0:
                return STS_IDLE
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
        except KeyboardInterrupt:
            raise
        except OSError as e:
            print("dns OSError " + str(e))
            self.udps.close()
            self.udps = None
        except Exception as e:
            exclogger.log_exception(e)
            pass
        return STS_IDLE

    def task_http(self):
        if self.wlan is None:
            return STS_IDLE
        if self.s is None:
            self.start_http()
        if self.s is None:
            return STS_IDLE # this only happens if the WiFi hardware is missing
        res = None
        try:
            res = self.s.accept()
            self.need_kill = True
            self.s.settimeout(10000)
        except OSError as e:
            #if self.need_kill:
            self.s.close()
            self.s = None
            self.start_http()
            return STS_IDLE
        if res is None:
            return STS_IDLE
        try:
            if self.debug:
                print("http req[%s]: " % str(res[1]), end="")
            self.last_http_time = pyb.millis()
            self.full_reboot_timer = self.last_http_time
            client_sock = res[0]
            client_addr = res[1]
            client_sock.settimeout(10)
            can_drop = True
            client_stream = client_sock
            req = socket_readline(client_stream, blocking = True)
            if req is None:
                if self.debug:
                    print("None")
                raise OSError("socket no data")
            if self.debug:
                print(req)
            req_split = req.split(' ')
            request_page, request_urlparams = split_get_request(req)
            headers = []
            content = ""
            if req_split[0] == "GET":
                if request_page in self.handlers:
                    can_drop = self.handlers[request_page](client_stream, req, headers, content)
                else:
                    self.handle_default(client_stream, req, headers, content)
            elif req_split[0] == "POST":
                # WARNING: POST requests are not used or tested right now
                # note: we have full control as to what the webpages will send, POST requests are not used for our applications
                headers, content = get_all_headers(client_stream)
                client_sock.settimeout(10) # needs to be re-established
                if request_page in self.handlers:
                    can_drop = self.handlers[request_page](client_stream, req, headers, content)
                else:
                    self.handle_default(client_stream, req, headers, content)
            self.last_http_time = pyb.millis()
            self.full_reboot_timer = self.last_http_time
            self.s.settimeout(0.3)
            if can_drop:
                try:
                    client_sock.settimeout(0.3) # might be closed by request
                except Exception as exc:
                    exclogger.log_exception(exc, to_print = False, to_file = False)
            return STS_SERVED
        except KeyboardInterrupt:
            raise
        except OSError as e:
            print("http serve OSError " + str(e) + " " + str(e.args[0]))
            self.s.close()
            self.s = None
        except Exception as e:
            exclogger.log_exception(e)
            pass
        return STS_IDLE

    def task(self, allow_kick = True):
        self.task_conn()
        if allow_kick:
            if self.last_http_time > 0 and pyb.elapsed_millis(self.last_http_time) > 10000:
                self.kick()
                return STS_KICKED
            if self.allow_hw_kick:
                if self.last_http_time < 0 and self.full_reboot_timer > 0 and pyb.elapsed_millis(self.full_reboot_timer) > 12000:
                    self.reboot()
                    return STS_KICKED
        else:
            if self.last_http_time > 0:
                self.last_http_time = pyb.millis()
            if self.full_reboot_timer > 0:
                self.full_reboot_timer = pyb.millis()
        x = self.task_dns()
        y = self.task_http()
        if x == STS_SERVED or y == STS_SERVED:
            return STS_SERVED
        return STS_IDLE

    def kick(self):
        self.last_http_time = -1
        if self.debug:
            print("server being kicked")
        if self.s is not None:
            try:
                self.s.close()
            except Exception as exc:
                exclogger.log_exception(exc, to_print = True, to_file = False)
            finally:
                self.s = None
                self.need_kill = False
        if self.winc_mode != network.WINC.MODE_AP and self.udps is not None:
            try:
                self.udps.close()
            except Exception as exc:
                exclogger.log_exception(exc, to_print = True, to_file = False)
            finally:
                self.udps = None
        gc.collect()
        if self.wlan is not None:
            self.wlan.closeall()
        #try:
        #    self.start_wifi()
        #except Exception as exc:
        #    exclogger.log_exception(exc, fatal = True, reboot = False)
        gc.collect()

    def reboot(self):
        self.kick()
        try:
            del self.wlan
        except:
            pass
        self.wlan = None
        self.start_wifi_hw()
        self.full_reboot_timer = pyb.millis()

# usocket implementation is missing readline
def socket_readline(sock, blocking = False):
    if blocking == False:
        sock.settimeout(0)
    res = ""
    while True:
        try:
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
        except:
            break
    return res

# usocket implementation is missing readall
def socket_readall(sock, blocking = False):
    if blocking == False:
        sock.settimeout(0)
    chunk = 1024
    res = ""
    while True:
        try:
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
        except:
            return res
    return res

def websocket_readmsg(sock):
    sock.settimeout(0)
    try:
        hd1 = sock.recv(2)
        sock.settimeout(0.1)
        if len(hd1) != 2:
            if len(hd1) != 0:
                print("incomplete websocket reply")
            return None
        sock.settimeout(0.5)
    except:
        return None
    try:
        # assume no fragmentation
        mask = False
        opcode0 = hd1[0]
        opcode1 = hd1[1]
        if (opcode1 & 0x80) != 0:
            mask = True
            opcode1 &= 0x7F
        paylen = opcode1
        datalen = 0
        if paylen <= 125:
            datalen = paylen
        elif paylen == 126:
            hd2 = sock.recv(2)
            datalen = hd2[0] << 8
            datalen += hd2[1]
        elif paylen == 127:
            hd2 = sock.recv(8)
            i = 0
            while i < 8:
                datalen += hd2[i] << (8 * (7 - i))
                i += 1
        if mask:
            mask = sock.recv(4)

        data = sock.recv(datalen)
        data = bytearray(data)
        if mask != False:
            i = 0
            while i < datalen:
                data[i] = data[i] ^ mask[i % 4]
                i += 1
        if (opcode0 & 0x0F) == 0x01:
            return data.decode('utf-8')
        return data
    except Exception as exc:
        print("incomplete websocket reply")
        exclogger.log_exception(exc, to_file=False)
        return None

def gen_page(conn, main_file, add_files = [], add_dir = None, debug = False):
    total_size = 0
    total_size += uos.stat(main_file)[6]
    flist = []
    # find all files required and add them to the list
    # also estimate the content length
    if add_dir is not None:
        try:
            lst = uos.listdir(add_dir)
            for i in lst:
                pt = add_dir + "/" + i
                if pt not in add_files:
                    add_files.append(pt)
        except OSError as exc:
            exclogger.log_exception(exc)
    for i in add_files:
        try:
            total_size = uos.stat(i)[6] + 200
            flist.append(i)
        except OSError as exc:
            exclogger.log_exception(exc)

    if debug:
        print("gen_page \"%s\" sz %u files %u ..." % (main_file, total_size, len(flist)), end="")

    conn.write(default_reply_header(content_length = total_size))

    sent = 0
    seekpos = 0
    with open(main_file, "rb") as f:
        headstr = ""
        while "</title>" not in headstr:
            headstr += f.read(1).decode("ascii")
            seekpos += 1
            sent += 1
        conn.write(headstr + "\r\n")
        sent += 2
    if debug:
        print("-", end="")

    # trying not to have more than one file open at once
    for fn in flist:
        try:
            with open(fn, "rb") as f:
                if fn.lower().endswith(".js"):
                    s = "\r\n<script type=\"text/javascript\">\r\n"
                    sent += len(s)
                    conn.write(s)
                    sent += stream_file(conn, f)
                    s = "\r\n</script>\r\n"
                    sent += len(s)
                    conn.write(s)
                elif fn.lower().endswith(".css"):
                    s = "\r\n<style type=\"text/css\">\r\n"
                    sent += len(s)
                    conn.write(s)
                    sent += stream_file(conn, f)
                    s = "\r\n</style>\r\n"
                    sent += len(s)
                    conn.write(s)
                else:
                    raise Exception("unsupported file type")
                if debug:
                    print("=", end="")
        except OSError as exc:
            exclogger.log_exception(exc)

    # send the rest of the file
    with open(main_file, "rb") as f:
        f.seek(seekpos)
        sent += stream_html_to_body(conn, f)
        sent += stream_file(conn, f)
        if debug:
            print("+", end="")

    # pad the end
    while sent < total_size - 2:
        conn.write(" ")
        sent += 1

    if debug:
        print(" done!")

    conn.close()

def stream_html_to_body(dest, f):
    strbuf = ""
    ignoring = False
    sent = 0
    while True:
        x = f.read(1).decode("ascii")
        if x is None:
            break
        if len(x) <= 0:
            break
        strbuf += x
        if "<body" in strbuf:
            sent += len(strbuf)
            dest.write(strbuf)
            break
        elif "<!-- ignore -->" in strbuf:
            sent += len(strbuf)
            dest.write(strbuf)
            strbuf = ""
            ignoring = True
        elif "<!-- end ignore -->" in strbuf:
            strbuf = ""
            ignoring = False
            break
        elif "\n" in strbuf and ignoring == False:
            sent += len(strbuf)
            dest.write(strbuf)
            strbuf = ""
    return sent

def stream_file(dest, f, bufsz = -1, buflim = 2048):
    gc.collect()
    if bufsz <= 0:
        # handle large files by reading one chunk at a time
        mf = gc.mem_free()
        if mf > 0:
            mf = mf // 4
        if mf < 32:
            mf = 32
        if mf > buflim:
            mf = buflim
        mf = int(round(mf))
    sent = 0
    while True:
        x = f.read(mf)
        if x is None:
            break
        xlen = len(x)
        sent += xlen
        if xlen > 0:
            dest.write(x)
        else:
            break
    return sent

def split_get_request(req):
    req_split = req.split(' ')
    if len(req_split) > 1:
        request_url = req_split[1]
    else:
        request_url = ""
    request_page = request_url
    request_urlparams = {}
    if '?' in request_page:
        request_page = request_url[:request_url.index('?')]
        request_urlparams = request_url[request_url.index('?') + 1:]
        d = {}
        try:
            pairs = request_urlparams.split('&')
            for p in pairs:
                if "=" in p:
                    ei = p.index("=")
                    k = p[0:ei].lstrip().rstrip()
                    v = p[ei + 1:]
                    if len(k) > 0:
                        d.update({k: v})
                elif p is not None:
                    p = p.lstrip().rstrip()
                    if len(p) > 0:
                        d.update({p: None})
        except ValueError as exc:
            exclogger.log_exception(exc, to_print = False, to_file = False)
        except Exception as exc:
            exclogger.log_exception(exc)
        request_urlparams = d
    return request_page, request_urlparams

def get_all_headers(client_stream, blocking = False):
    headers = {}
    content = ""
    while True:
        line = socket_readline(client_stream, blocking = blocking)
        if line is None:
            break
        if ':' in line:
            header_key = line[0:line.index(':')].lower()
            header_value = line[line.index(':') + 1:].lstrip()
            headers.update({header_key: header_value})
            if header_key == "content-length":
                socket_readline(client_stream) # extra line
                content = socket_readall(client_stream, blocking = blocking)
                break
    return headers, content

def split_post_form(headers, content):
    d = {}
    if "content-type" in headers:
        if headers["content-type"] == "application/x-www-form-urlencoded":
            try:
                pairs = content.split('&')
                for p in pairs:
                    if "=" in p:
                        ei = p.index("=")
                        k = p[0:ei].lstrip().rstrip()
                        v = p[ei + 1:]
                        if len(k) > 0:
                            d.update({k: v})
                    elif p is not None:
                        p = p.lstrip().rstrip()
                        if len(p) > 0:
                            d.update({p: None})
            except ValueError as exc:
                exclogger.log_exception(exc, to_print = False, to_file = False)
            except Exception as exc:
                exclogger.log_exception(exc)
    return d

def default_reply_header(content_type = "text/html", content_length = -1):
    s = "HTTP/1.0 200 OK\r\ncontent-type: %s\r\n" % content_type
    if "x-icon" not in content_type:
        s += "cache-control: no-cache\r\n"
    if content_length >= 0:
        s += "content_length: %u\r\n" % content_length
    return s + "\r\n"

def handle_websocket(client_stream, req, headers):
    # hints taken from https://github.com/micropython/webrepl/blob/master/websocket_helper.py
    webkey = None
    header_keys = headers.keys()
    for i in header_keys:
        if i.lower() == "sec-websocket-key":
            webkey = headers[i]
            break
    if webkey is None:
        return False
    respkey = calc_websocket_resp(webkey)
    resp = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n" % str(respkey)
    client_stream.settimeout(10)
    client_stream.send(resp)
    return True

def calc_websocket_resp(key):
    concatkey = key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    binarr = uhashlib.sha1(concatkey).digest()
    #hexstr = ubinascii.hexlify(binarr)
    #print(hexstr)
    respkey = ubinascii.b2a_base64(binarr).decode('utf-8').rstrip()
    #respkey = respkey[:-1] # strips the \n
    return respkey

def debug_headers(headers):
    header_keys = headers.keys()
    for i in header_keys:
        print("%s: %s" % (i, headers[i]))

MIME_TABLE = [ # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
#["aac",    "audio/aac"],
#["abw",    "application/x-abiword"],
#["arc",    "application/x-freearc"],
#["avi",    "video/x-msvideo"],
#["azw",    "application/vnd.amazon.ebook"],
["bin",    "application/octet-stream"],
["bmp",    "image/bmp"],
#["bz",     "application/x-bzip"],
#["bz2",    "application/x-bzip2"],
#["csh",    "application/x-csh"],
["css",    "text/css"],
["csv",    "text/csv"],
#["doc",    "application/msword"],
#["docx",   "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
#["eot",    "application/vnd.ms-fontobject"],
#["epub",   "application/epub+zip"],
#["gz",     "application/gzip"],
["gif",    "image/gif"],
["htm",    "text/html"],
["html",   "text/html"],
["ico",    "image/x-icon"],
["ics",    "text/calendar"],
#["jar",    "application/java-archive"],
["jpeg",   "image/jpeg"],
["jpg",    "image/jpeg"],
["js",     "text/javascript"],
["json",   "application/json"],
["jsonld", "application/ld+json"],
["mid",    "audio/midi"],
["midi",   "audio/midi"],
["mjs",    "text/javascript"],
#["mp3",    "audio/mpeg"],
#["mpeg",   "video/mpeg"],
#["mpkg",   "application/vnd.apple.installer+xml"],
#["odp",    "application/vnd.oasis.opendocument.presentation"],
#["ods",    "application/vnd.oasis.opendocument.spreadsheet"],
#["odt",    "application/vnd.oasis.opendocument.text"],
#["oga",    "audio/ogg"],
#["ogv",    "video/ogg"],
#["ogx",    "application/ogg"],
#["opus",   "audio/opus"],
["otf",    "font/otf"],
["png",    "image/png"],
["pdf",    "application/pdf"],
#["php",    "application/x-httpd-php"],
#["ppt",    "application/vnd.ms-powerpoint"],
#["pptx",   "application/vnd.openxmlformats-officedocument.presentationml.presentation"],
#["rar",    "application/vnd.rar"],
#["rtf",    "application/rtf"],
["sh",     "application/x-sh"],
["svg",    "image/svg+xml"],
#["swf",    "application/x-shockwave-flash"],
#["tar",    "application/x-tar"],
["tif",    "image/tiff"],
["tiff",   "image/tiff"],
#["ts",     "video/mp2t"],
["ttf",    "font/ttf"],
["txt",    "text/plain"],
#["vsd",    "application/vnd.visio"],
#["wav",    "audio/wav"],
#["weba",   "audio/webm"],
#["webm",   "video/webm"],
["webp",   "image/webp"],
["woff",   "font/woff"],
["woff2",  "font/woff2"],
["xhtml",  "application/xhtml+xml"],
#["xls",    "application/vnd.ms-excel"],
#["xlsx",   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
["xml",    "text/xml"],
#["xul",    "application/vnd.mozilla.xul+xml"],
["zip",    "application/zip"],
#["3gp",    "video/3gpp"],
#["3g2",    "video/3gpp2"],
#["7z",     "application/x-7z-compressed"]
]

def get_content_type(fname):
    fname = fname.lower()
    for i in MIME_TABLE:
        if fname.endswith("." + i[0]):
            return i[1]
    return 'application/octet-stream' # forces binary download

"""
def stream_img_start(conn):
    conn.send("HTTP/1.1 200 OK\r\n" \
              "content-type: multipart/x-mixed-replace;boundary=stream\r\n" \
              "x-frame-options: deny\r\n" \
              "x-xss-protection: 1; mode=block\r\n" \
              "x-content-type-options: nosniff\r\n" \
              "vary: Accept-Encoding\r\n" \
              "cache-control: no-cache\r\n\r\n")

def stream_img_continue(img, conn):
    cframe = img.compressed(quality=50)
    conn.send("\r\n--stream\r\n" \
               "content-type: image/jpeg\r\n" \
               "content-length:%u\r\n\r\n" % cframe.size())
    conn.send(cframe)

"""

def handle_test(client_stream, req, headers, content):
    print("test handler")
    client_stream.write(default_reply_header() + "<html>test<br />" + req + "</html>\r\n")
    client_stream.close()

def attempt_fw_update(fpath = "/winc_19_6_1.bin"):
    try:
        st = uos.stat(fpath)
        wlan = network.WINC(mode=network.WINC.MODE_FIRMWARE)
        wlan.fw_update(fpath)
    except OSError as exc2:
        if exc2.args[0] == 2:
            while True:
                print("WiFi shield firmware update file is missing at \"" + fpath + "\"")
                pyb.delay(500)
                pass
        else:
            exclogger.log_exception(exc2)
            while True:
                print("WiFi shield firmware update failed")
                pyb.delay(500)
                pass
    except Exception as exc2:
        exclogger.log_exception(exc2)
        while True:
            print("WiFi shield firmware update failed")
            pyb.delay(500)
            pass

if __name__ == "__main__":
    print("Starting CaptivePortal")
    portal = CaptivePortal("moomoomilk", "1234567890", winc_mode = network.WINC.MODE_STA, winc_security = network.WINC.WPA_PSK, debug = True)
    portal.install_handler("/test", handle_test)
    dbg_cnt = 0
    clock = time.clock()
    while True:
        dbg_cnt += 1
        clock.tick()
        portal.task()
        fps = clock.fps()
        if portal.debug or (dbg_cnt % 100) == 0:
            print("%u - %0.2f" % (dbg_cnt, fps))
            pass
