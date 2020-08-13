import micropython, sys, uos, uio, pyb

def log_exception(exc, time_str = "", to_print = True, to_file = True, fatal = False):

    # use built-in exception formatter
    f = uio.StringIO(2048)
    sys.print_exception(exc,f)
    f.seek(0)
    s = f.read()
    f.close()

    # use sys time if real time is not provided
    if time_str is None:
        time_str = ""
    if len(time_str) <= 0:
        time_str = "%u" % pyb.millis()

    headstr = "ERROR[%s]: %s" % (time_str, str(type(exc)))

    # traceback made single line
    s = s.replace("\n  ", " >> ")

    if to_print:
        print(headstr)
        print(s)
    if to_file:
        # append to this file
        fname = "exc_log.txt"
        fsize = 0
        retries = 0
        while retries < 2:
            retries += 1
            try:
                try:
                    fsize = uos.stat(fname)[6]
                except OSError:
                    # no such file, file size is 0 (unchanged)
                    pass
                with open(fname, "wba+") as f:
                    f.seek(fsize) # the append flag does not work in micropython
                    f.write("\r\n")
                    f.write(headstr + "\r\n")
                    f.write(s + "\r\n")
                    f.write("\r\n")
                break # done, no need to loop
            except:
                # something wrong happened
                # backup the old file, start a new one
                try:
                    nfn = "exc_log_old.txt"
                    try:
                        uos.remove(nfn)
                    except OSError:
                        pass
                    uos.rename(fname, nfn)
                except OSError:
                    pass
                continue
    if fatal:
        raise exc
    return headstr + "\r\n" + s

"""
def testnest():
    f = open("2")

def test():
    try:
        testnest()
    except Exception as exc:
        log_exception(exc, fatal = True)
        print("done\n\n")

if __name__ == "__main__":
    test()
"""
